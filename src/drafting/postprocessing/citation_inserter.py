"""Citation postprocessing for drafted section markdown."""

from __future__ import annotations

import re
from typing import Any


# Matches direct source cite keys like [S001], [S002], ..., [S999]
CITE_KEY_PATTERN = re.compile(r"\[S(\d{3})\]")


def _normalize_manifest(citation_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    citations = citation_manifest.get("citations")
    if not isinstance(citations, list):
        raise ValueError("citation_manifest must include a 'citations' list")
    return citations


def _find_citation_by_key(
    cite_key: str,
    citations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Look up a citation entry by its cite_key field (e.g. '[S001]')."""
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        entry_key = (
            citation.get("cite_key")
            or citation.get("short_id")
            or citation.get("src_tag")
            or citation.get("src_id")
        )
        if isinstance(entry_key, str) and entry_key.strip() == cite_key:
            return citation
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
    """Resolve [SXXX] tags and append a per-section references list."""
    if not isinstance(raw_section_markdown, str) or not raw_section_markdown.strip():
        raise ValueError("raw_section_markdown must be a non-empty string")

    citations = _normalize_manifest(citation_manifest)
    matches = list(CITE_KEY_PATTERN.finditer(raw_section_markdown))
    if not matches:
        return raw_section_markdown

    used_tags: list[str] = []
    for match in matches:
        tag = match.group(0)  # e.g. "[S001]"
        if tag in used_tags:
            continue

        citation_entry = _find_citation_by_key(tag, citations)
        if citation_entry is None:
            raise ValueError(f"No citation manifest entry found for {tag}")

        used_tags.append(tag)

    # Keep [SXXX] tags inline — the PDF renderer converts them to footnotes.
    annotated_markdown = raw_section_markdown

    references_lines = ["### References"]
    for tag in used_tags:
        citation_entry = _find_citation_by_key(tag, citations)
        if citation_entry is None:
            continue
        author, title, year = _extract_reference_fields(citation_entry)
        references_lines.append(f"- {tag} {author}. {title}. ({year}).")

    references_block = "\n".join(references_lines)
    return f"{annotated_markdown.rstrip()}\n\n{references_block}\n"