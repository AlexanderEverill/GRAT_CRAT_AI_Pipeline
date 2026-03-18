"""Citation postprocessing for drafted section markdown."""

from __future__ import annotations

import re
from typing import Any


SRC_TAG_PATTERN = re.compile(r"\[SRC-(\d+)\]")


def _normalize_manifest(citation_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    citations = citation_manifest.get("citations")
    if not isinstance(citations, list):
        raise ValueError("citation_manifest must include a 'citations' list")
    return citations


def _find_citation_entry(
    citation_num: int,
    citations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    tag = f"[SRC-{citation_num}]"

    for citation in citations:
        if not isinstance(citation, dict):
            continue
        short_id = citation.get("short_id") or citation.get("src_tag") or citation.get("src_id")
        if isinstance(short_id, str) and short_id.strip() == tag:
            return citation

    if 1 <= citation_num <= len(citations):
        entry = citations[citation_num - 1]
        if isinstance(entry, dict):
            return entry
    return None


def _extract_reference_fields(citation: dict[str, Any]) -> tuple[str, str, str]:
    author = citation.get("author") or citation.get("publisher") or citation.get("source_id")
    title = citation.get("title") or citation.get("document_title") or citation.get("url")
    year_value = citation.get("year") or citation.get("publication_year")

    if not year_value:
        date_accessed = citation.get("date_accessed") or citation.get("created_timestamp")
        if isinstance(date_accessed, str) and len(date_accessed) >= 4:
            year_value = date_accessed[:4]

    author_text = author.strip() if isinstance(author, str) and author.strip() else "Unknown Author"
    title_text = title.strip() if isinstance(title, str) and title.strip() else "Untitled Source"
    year_text = str(year_value).strip() if year_value is not None else "n.d."
    if not year_text:
        year_text = "n.d."

    return author_text, title_text, year_text


def insert_citations(raw_section_markdown: str, citation_manifest: dict[str, Any]) -> str:
    """Resolve [SRC-N] tags and append a per-section references list."""
    if not isinstance(raw_section_markdown, str) or not raw_section_markdown.strip():
        raise ValueError("raw_section_markdown must be a non-empty string")

    citations = _normalize_manifest(citation_manifest)
    matches = list(SRC_TAG_PATTERN.finditer(raw_section_markdown))
    if not matches:
        return raw_section_markdown

    inline_by_tag: dict[str, str] = {}
    used_tags: list[str] = []
    for match in matches:
        tag = match.group(0)
        if tag in inline_by_tag:
            continue

        citation_num = int(match.group(1))
        citation_entry = _find_citation_entry(citation_num, citations)
        if citation_entry is None:
            raise ValueError(f"No citation manifest entry found for {tag}")

        author, title, year = _extract_reference_fields(citation_entry)
        inline_by_tag[tag] = f"({author}, {title}, {year})"
        used_tags.append(tag)

    annotated_markdown = raw_section_markdown
    for tag, inline_ref in inline_by_tag.items():
        annotated_markdown = annotated_markdown.replace(tag, inline_ref)

    references_lines = ["### References"]
    for tag in used_tags:
        citation_num = int(tag.removeprefix("[SRC-").removesuffix("]"))
        citation_entry = _find_citation_entry(citation_num, citations)
        if citation_entry is None:
            continue
        author, title, year = _extract_reference_fields(citation_entry)
        references_lines.append(f"- {tag} {author}. {title}. ({year}).")

    references_block = "\n".join(references_lines)
    return f"{annotated_markdown.rstrip()}\n\n{references_block}\n"