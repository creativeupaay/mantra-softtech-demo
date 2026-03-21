import os
import re
from pathlib import Path

# Configuration
KNOWLEDGE_DIR = Path("/Users/manishbulchandani/D/Creative Upaay/Work/mantra-tec-voice-agent/server/knowledge")
CLEANED_DIR = KNOWLEDGE_DIR / "cleaned"
CLEANED_DIR.mkdir(exist_ok=True)

def cleanup_file(file_path):
    print(f"🧹 Cleaning: {file_path.name}")
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 1. Extract frontmatter (metadata)
    frontmatter = []
    content_start_idx = 0
    if lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                frontmatter = lines[0:i+1]
                content_start_idx = i + 1
                break
    
    # 2. Skip the massive boilerplate navigation block (approx lines 1 to 697)
    # Most informative content starts after the "Download Technical Resources" link
    # which is around line 695.
    real_content_idx = content_start_idx
    for i in range(content_start_idx, len(lines)):
        if "Download\\n\\ Technical Resources" in lines[i] or "Download\\n\\nTechnical Resources" in lines[i]:
            real_content_idx = i + 1
            break
        # Fallback: if we see the main heading of the page after some lines
        if i > 600 and lines[i].startswith("# "):
            real_content_idx = i
            break
    
    # If we couldn't find a clear break, start from line 697 as a heuristic
    if real_content_idx == content_start_idx and len(lines) > 700:
        real_content_idx = 697

    # 3. Process the content
    raw_content = lines[real_content_idx:]
    cleaned_lines = []
    
    # Pattern to match those ugly multi-line link buttons: [Text\\ \n \\ \n Sub](link)
    # And other navigational artifacts
    skip_patterns = [
        re.compile(r"\[.*\\$"), # Lines ending in backslash (part of buttons)
        re.compile(r"^\\$"),    # Lines with just backslash
        re.compile(r"^##### "), # Side-bar headers used in boilerplate
        re.compile(r"\[Explore more\]"),
        re.compile(r"Read More\]"), # Matches both [Read More] and remnants like Read More]
        re.compile(r"\[Get In Touch\]"),
        re.compile(r"\[Book Discovery Call\]"),
        re.compile(r"\[Schedule Appointment\]"),
        re.compile(r"Enquire now"),
        re.compile(r"^!\["),    # Image tags
        re.compile(r"\[Home\]\(https://www\.mantratec\.com/\)"), # Breadcrumb Home
        re.compile(r"^- /\s*$"), # Breadcrumb separator
        re.compile(r"^\*\*.*\*\*\s*$"), # Page title repeats in bold (breadcrumb)
        re.compile(r"\[!\[Mantratec\]"), # Logo
    ]

    footer_started = False
    
    for line in raw_content:
        stripped = line.strip()
        
        # Skip empty lines early
        if not stripped:
            if cleaned_lines and cleaned_lines[-1].strip():
                cleaned_lines.append("\n")
            continue

        # Detect footer start
        if "#### Address :" in line or "#### Sales :" in line or "#### Support :" in line or "Questions?" in line:
            footer_started = True
            
        if footer_started:
            if any(x in line for x in ["2026 All rights reserved", "Cookies", "Privacy Statement", "DMCA.com", "Copyscape", "CMMI"]):
                continue
            if "Accept Cookies" in line:
                break

        # Skip known boilerplate patterns
        if any(p.search(line) for p in skip_patterns):
            # Special case: if it was a descriptive block followed by Read More], 
            # we already kept the description in previous iterations usually.
            continue
            
        # Clean up line: remove trailing \\ and normalize
        line = line.replace("\\\\", "").replace("\\", "").strip()
        if not line: continue
        
        cleaned_lines.append(line + "\n")

    # 4. Final Polish: remove trailing emptiness and repeated headers
    final_output = "".join(frontmatter) + "\n" + "".join(cleaned_lines)
    
    # Derive name: www.mantratec.com_About-Us.md -> about-us.md
    name = file_path.name.replace("www.mantratec.com_", "").replace("_", "-").lower() or "home.md"
    if name == ".md": name = "home.md"
    
    output_path = CLEANED_DIR / name
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_output.strip() + "\n")
    print(f"✅ Saved to: {output_path}")

if __name__ == "__main__":
    files = [f for f in KNOWLEDGE_DIR.glob("*.md") if f.is_file() and f.name != "knowledge.md"]
    for f in files:
        cleanup_file(f)
    print("\n🎉 Basic cleanup complete!")
