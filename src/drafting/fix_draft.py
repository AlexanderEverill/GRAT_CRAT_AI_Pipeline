"""One-time cleanup of Draft.md before PDF rendering.

Problem: The assembler uses ## for top-level sections, but the LLM also used ##
for sub-headings inside sections. The PDF parser splits on ## so every sub-heading
becomes its own page. Fix: demote inner ## to ### so only the 5 main sections
trigger page breaks.
"""
from pathlib import Path
import re

draft_path = Path(__file__).parent / "output" / "Draft.md"
md = draft_path.read_text("utf-8")

# Known top-level section titles (from the assembler's TOC)
TOP_SECTIONS = {
    "Table of Contents",
    "Executive Summary",
    "GRAT Analysis",
    "CRAT Analysis",
    "Comparison and Recommendation",
    "Citations and Disclosures",
    "Global References",
    "Generation Metadata",
}

lines = md.split("\n")
cleaned = []
for line in lines:
    stripped = line.strip()

    # Handle ## headings: keep top-level ones, demote the rest to ###
    if stripped.startswith("## ") and not stripped.startswith("### "):
        title = stripped[3:].strip()
        if title in TOP_SECTIONS:
            cleaned.append(line)
        else:
            cleaned.append("### " + title)
        continue

    # Remove duplicate # headings that match a preceding ## section
    if stripped.startswith("# ") and not stripped.startswith("## "):
        h1_title = stripped.lstrip("# ").strip()
        if h1_title in TOP_SECTIONS:
            continue  # duplicate of the assembler heading
        # Demote to ### as well
        cleaned.append("### " + h1_title)
        continue

    cleaned.append(line)

md = "\n".join(cleaned)

# Unwrap comparison section from code block (```markdown ... ```)
md = md.replace("```markdown\n## Comparison and Recommendation", "## Comparison and Recommendation")
md = re.sub(r"\n```\s*\n(\n### References)", r"\1", md)
md = re.sub(r"\n```\s*$", "", md)

draft_path.write_text(md, "utf-8")
print(f"Cleaned draft written. Lines: {md.count(chr(10))}")
