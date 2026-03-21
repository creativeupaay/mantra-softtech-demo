"""RAG tool handler for the voice agent.

Uses Qdrant (local Docker) + fastembed (local ONNX embeddings) to search
a knowledge base and return relevant context to the LLM.

Supports optional page-level filtering: the LLM can pass a list of `pages`
to restrict the search to specific pages of the knowledge base.
"""

import json
import os

from loguru import logger
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny
from pipecat.services.llm_service import FunctionCallParams

# ─── Configuration ────────────────────────────────────────────────

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "mantra_knowledge")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
TOP_K = int(os.getenv("RAG_TOP_K", "5"))
SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.3"))

# ─── Initialize clients (module-level singletons) ─────────────────

logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

logger.info(f"Loading embedding model: {EMBEDDING_MODEL} (local ONNX)")
embedding_model = TextEmbedding(model_name=EMBEDDING_MODEL)
logger.info("Embedding model loaded successfully")


def _embed_query(text: str) -> list[float]:
    """Embed a single query string using fastembed (local, no API call)."""
    embeddings = list(embedding_model.embed([text]))
    return embeddings[0].tolist()


# ─── Tool Handler ─────────────────────────────────────────────────


async def search_knowledge(params: FunctionCallParams):
    """Search the knowledge base for information relevant to the user's question.

    Embeds the query locally, searches Qdrant for top-k similar chunks,
    and returns the matching text passages to the LLM for answering.

    Optional `pages` parameter restricts the search to specific page(s).
    """
    query = params.arguments.get("query", "").strip()
    pages = params.arguments.get("pages", [])  # list of page slugs, e.g. ["about-us", "clientele"]

    if not query:
        result = {
            "found": False,
            "context": "",
            "message": "No query provided.",
        }
        await params.result_callback(json.dumps(result))
        return

    if pages:
        logger.info(f"RAG search: query='{query}' | pages={pages}")
    else:
        logger.info(f"RAG search: query='{query}' | pages=ALL")

    try:
        # Embed the query locally (fast, no network call)
        query_vector = _embed_query(query)

        # Build optional page filter
        query_filter = None
        if pages:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="page",
                        match=MatchAny(any=pages),
                    )
                ]
            )

        # Search Qdrant
        hits = qdrant.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector,
            limit=TOP_K,
            score_threshold=SCORE_THRESHOLD,
            query_filter=query_filter,
        )

        if hits.points:
            # Build context from top results
            chunks = []
            for i, hit in enumerate(hits.points):
                text = hit.payload.get("text", "")
                source_page = hit.payload.get("page", hit.payload.get("source", "unknown"))
                score = round(hit.score, 3)
                chunks.append(f"[Page: {source_page} | Relevance: {score}]\n{text}")
                logger.debug(
                    f"  Hit {i+1}: score={score}, page={source_page}, text={text[:100]}..."
                )

            context = "\n\n---\n\n".join(chunks)

            result = {
                "found": True,
                "context": context,
                "num_results": len(hits.points),
                "message": f"Found {len(hits.points)} relevant knowledge chunk(s).",
            }
            logger.info(f"RAG search returned {len(hits.points)} results")
        else:
            result = {
                "found": False,
                "context": "",
                "num_results": 0,
                "message": "No relevant information found in the knowledge base.",
            }
            logger.info("RAG search returned 0 results")

    except Exception as e:
        logger.error(f"RAG search error: {e}")
        result = {
            "found": False,
            "context": "",
            "message": f"Knowledge search encountered an error: {str(e)}",
        }

    await params.result_callback(json.dumps(result))
