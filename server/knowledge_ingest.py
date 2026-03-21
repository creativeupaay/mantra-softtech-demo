"""Knowledge Ingestion Utility — Feed markdown files into Qdrant.

Reads .md file(s), splits them into logical chunks (by headings with overlap),
embeds each chunk using fastembed (local ONNX), and upserts into Qdrant.

Each chunk is tagged with a `page` field derived from the filename, enabling
page-aware retrieval at query time.

Usage:
    # Single file:
    python knowledge_ingest.py --file knowledge/cleaned/about-us.md

    # Entire folder (recommended — ingests all .md files, page-separated):
    python knowledge_ingest.py --folder knowledge/cleaned/ --clear

    # With options:
    python knowledge_ingest.py --folder knowledge/cleaned/ --chunk-size 600 --overlap 80
"""

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

load_dotenv(override=True)

# ─── Configuration ────────────────────────────────────────────────

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "mantra_knowledge")
DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
VECTOR_DIM = 384  # all-MiniLM-L6-v2 output dimension


# ─── Page Slug Derivation ─────────────────────────────────────────

def derive_page_slug(file_path: str) -> str:
    """Derive a clean page slug from a filename.

    Examples:
        about-us.md          → about-us
        company-profile.md   → company-profile
        home.md              → home
        research-and-development-innovation-and-knowledge.md
                             → research-and-development-innovation-and-knowledge
    """
    name = Path(file_path).stem  # filename without extension
    return name.lower()


# ─── Markdown Chunking ────────────────────────────────────────────


def chunk_markdown(text: str, chunk_size: int = 600, overlap: int = 80) -> list[dict]:
    """Split markdown into logical chunks by headings, with size limits and overlap.

    Strategy:
    1. Split by markdown headings (# / ## / ### etc.)
    2. Each section becomes a chunk with its heading as metadata
    3. If a section exceeds chunk_size, split it further by paragraphs
    4. Apply overlap between consecutive chunks (repeats tail of previous chunk)

    Returns list of {"text": str, "heading": str, "chunk_index": int}
    """
    # Split by headings — keep the heading with its content
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    sections = []
    last_end = 0
    current_heading = "Introduction"

    for match in heading_pattern.finditer(text):
        # Capture content before this heading
        content_before = text[last_end : match.start()].strip()
        if content_before:
            sections.append({"heading": current_heading, "content": content_before})

        current_heading = match.group(2).strip()
        last_end = match.end()

    # Capture remaining content after last heading
    remaining = text[last_end:].strip()
    if remaining:
        sections.append({"heading": current_heading, "content": remaining})

    # Now split large sections into smaller chunks
    raw_chunks = []
    for section in sections:
        heading = section["heading"]
        content = section["content"]

        if len(content) <= chunk_size:
            raw_chunks.append({"heading": heading, "text": content})
        else:
            # Split by paragraphs (double newline)
            paragraphs = re.split(r"\n\s*\n", content)
            current_chunk = ""

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                if len(current_chunk) + len(para) + 2 <= chunk_size:
                    current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
                else:
                    if current_chunk:
                        raw_chunks.append({"heading": heading, "text": current_chunk})
                    # If single paragraph exceeds chunk_size, split by sentences
                    if len(para) > chunk_size:
                        sentences = re.split(r"(?<=[.!?])\s+", para)
                        current_chunk = ""
                        for sentence in sentences:
                            if len(current_chunk) + len(sentence) + 1 <= chunk_size:
                                current_chunk = (
                                    f"{current_chunk} {sentence}" if current_chunk else sentence
                                )
                            else:
                                if current_chunk:
                                    raw_chunks.append({"heading": heading, "text": current_chunk})
                                current_chunk = sentence
                    else:
                        current_chunk = para

            if current_chunk:
                raw_chunks.append({"heading": heading, "text": current_chunk})

    # Apply overlap — prepend tail of previous chunk to current chunk
    final_chunks = []
    for i, chunk in enumerate(raw_chunks):
        text_with_context = chunk["text"]

        if i > 0 and overlap > 0:
            prev_text = raw_chunks[i - 1]["text"]
            # Take last `overlap` characters from previous chunk
            overlap_text = prev_text[-overlap:].strip()
            if overlap_text:
                text_with_context = f"...{overlap_text}\n\n{text_with_context}"

        # Prepend heading for context
        chunk_text = f"[{chunk['heading']}]\n{text_with_context}"

        final_chunks.append(
            {
                "text": chunk_text,
                "heading": chunk["heading"],
                "chunk_index": i,
            }
        )

    return final_chunks


def generate_point_id(source: str, chunk_index: int) -> str:
    """Generate a deterministic UUID-like ID for a chunk (idempotent re-ingestion)."""
    raw = f"{source}::chunk::{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()


# ─── Main Ingestion ───────────────────────────────────────────────


def ingest(
    file_path: str,
    collection: str = DEFAULT_COLLECTION,
    model_name: str = DEFAULT_MODEL,
    chunk_size: int = 600,
    overlap: int = 80,
    clear: bool = False,
    client: QdrantClient | None = None,
    model: TextEmbedding | None = None,
    page: str | None = None,
):
    """Ingest a single markdown file into Qdrant.

    Args:
        file_path: Path to the .md file.
        collection: Qdrant collection name.
        model_name: fastembed model name.
        chunk_size: Max characters per chunk.
        overlap: Character overlap between chunks.
        clear: Clear the collection before ingesting.
        client: Optional pre-created QdrantClient (for batch ingestion).
        model: Optional pre-loaded TextEmbedding model (for batch ingestion).
        page: Page slug (e.g. "about-us"). Derived from filename if not provided.
    """

    # Validate file
    if not os.path.isfile(file_path):
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    source_name = os.path.basename(file_path)
    page_slug = page or derive_page_slug(file_path)
    print(f"\n📄 Ingesting: {file_path}  (page='{page_slug}')")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        print("❌ File is empty — skipping")
        return

    # Chunk the markdown
    chunks = chunk_markdown(content, chunk_size=chunk_size, overlap=overlap)
    print(f"   ✂️  Split into {len(chunks)} chunks (size={chunk_size}, overlap={overlap})")

    # Connect to Qdrant (reuse or create)
    if client is None:
        print(f"\n🔌 Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Create or clear collection
    collections = [c.name for c in client.get_collections().collections]

    if clear and collection in collections:
        print(f"🗑️  Clearing existing collection: {collection}")
        client.delete_collection(collection)
        collections.remove(collection)

    if collection not in collections:
        print(f"📦 Creating collection: {collection} (dim={VECTOR_DIM}, cosine)")
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
    else:
        if clear:
            pass  # already cleared/re-created above
        else:
            print(f"📦 Using existing collection: {collection}")

    # Load embedding model (reuse or create)
    if model is None:
        print(f"🧠 Loading embedding model: {model_name} (local ONNX)")
        model = TextEmbedding(model_name=model_name)
        print("   Model loaded ✓")

    # Embed all chunks
    texts = [chunk["text"] for chunk in chunks]
    embeddings = list(model.embed(texts))

    # Build points for Qdrant
    points = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        point_id = generate_point_id(source_name, chunk["chunk_index"])
        # Convert hex MD5 to integer for Qdrant (needs int or UUID)
        int_id = int(point_id, 16) % (2**63)

        points.append(
            PointStruct(
                id=int_id,
                vector=embedding.tolist(),
                payload={
                    "text": chunk["text"],
                    "heading": chunk["heading"],
                    "source": source_name,
                    "chunk_index": chunk["chunk_index"],
                    "page": page_slug,          # ← NEW: page metadata for filtering
                },
            )
        )

    # Upsert into Qdrant (in batches of 100)
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=collection, points=batch)

    info = client.get_collection(collection)
    print(f"   ✅ {len(chunks)} chunks ingested — collection now has {info.points_count} points total")
    return client, model


def ingest_folder(
    folder_path: str,
    collection: str = DEFAULT_COLLECTION,
    model_name: str = DEFAULT_MODEL,
    chunk_size: int = 600,
    overlap: int = 80,
    clear: bool = False,
):
    """Ingest all .md files in a folder into Qdrant, page-separated."""
    folder = Path(folder_path)
    if not folder.is_dir():
        print(f"❌ Folder not found: {folder_path}")
        sys.exit(1)

    md_files = sorted(folder.glob("*.md"))
    if not md_files:
        print(f"❌ No .md files found in: {folder_path}")
        sys.exit(1)

    print(f"📂 Found {len(md_files)} files in: {folder_path}")

    # Connect to Qdrant and load model once for all files
    print(f"\n🔌 Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Clear collection if requested (only once before first file)
    if clear:
        collections = [c.name for c in client.get_collections().collections]
        if collection in collections:
            print(f"🗑️  Clearing collection: {collection}")
            client.delete_collection(collection)

    print(f"🧠 Loading embedding model: {model_name} (local ONNX)")
    model = TextEmbedding(model_name=model_name)
    print("   Model loaded ✓")

    # Ingest each file
    for md_file in md_files:
        result = ingest(
            file_path=str(md_file),
            collection=collection,
            model_name=model_name,
            chunk_size=chunk_size,
            overlap=overlap,
            clear=False,  # collection already cleared above
            client=client,
            model=model,
        )
        if result:
            client, model = result

    # Final summary
    info = client.get_collection(collection)
    print(f"\n🎉 All done! Collection '{collection}' contains {info.points_count} total points across {len(md_files)} pages.")

    # Print page breakdown
    print("\n📊 Page breakdown:")
    for md_file in md_files:
        page_slug = derive_page_slug(str(md_file))
        # Quick count via scroll (approximate)
        count_result, _ = client.scroll(
            collection_name=collection,
            scroll_filter={"must": [{"key": "page", "match": {"value": page_slug}}]},
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        # Use count_points for accuracy
        try:
            count = client.count(
                collection_name=collection,
                count_filter={"must": [{"key": "page", "match": {"value": page_slug}}]},
            ).count
            print(f"   {page_slug:<55} {count} chunks")
        except Exception:
            print(f"   {page_slug}")


# ─── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest markdown file(s) into Qdrant vector database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file:
  python knowledge_ingest.py --file knowledge/cleaned/about-us.md

  # Full folder (page-separated):
  python knowledge_ingest.py --folder knowledge/cleaned/ --clear

  # Custom settings:
  python knowledge_ingest.py --folder knowledge/cleaned/ --chunk-size 800 --overlap 100
        """,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", "-f", help="Path to a single markdown (.md) file")
    group.add_argument("--folder", help="Path to a folder of markdown (.md) files")

    parser.add_argument(
        "--collection",
        "-c",
        default=DEFAULT_COLLECTION,
        help=f"Qdrant collection name (default: {DEFAULT_COLLECTION})",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=600,
        help="Max characters per chunk (default: 600)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=80,
        help="Character overlap between chunks (default: 80)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the collection before ingesting (removes all existing data)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Embedding model name (default: {DEFAULT_MODEL})",
    )

    args = parser.parse_args()

    if args.folder:
        ingest_folder(
            folder_path=args.folder,
            collection=args.collection,
            model_name=args.model,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            clear=args.clear,
        )
    else:
        ingest(
            file_path=args.file,
            collection=args.collection,
            model_name=args.model,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            clear=args.clear,
        )
