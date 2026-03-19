"""Append a deduplicated global bibliography to assembled draft markdown."""

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


def _extract_reference_fields(citation: dict[str, Any]) -> tuple[str, str, str, str | None]:
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

    url = citation.get("url")
    url_text = url.strip() if isinstance(url, str) and url.strip() else None
    return author_text, title_text, year_text, url_text


def append_global_references(
    assembled_markdown: str,
    citation_manifest: dict[str, Any],
) -> str:
    """Append a deduplicated global references section to assembled markdown."""
    if not isinstance(assembled_markdown, str) or not assembled_markdown.strip():
        raise ValueError("assembled_markdown must be a non-empty string")

    citations = _normalize_manifest(citation_manifest)

    ordered_unique_tags: list[str] = []
    seen: set[str] = set()
    for match in CITE_KEY_PATTERN.finditer(assembled_markdown):
        tag = match.group(0)
        if tag not in seen:
            seen.add(tag)
            ordered_unique_tags.append(tag)

    bibliography_lines = ["## Global References"]
    if not ordered_unique_tags:
        bibliography_lines.append("- No citations detected in assembled draft.")
    else:
        for tag in ordered_unique_tags:
            citation_entry = _find_citation_by_key(tag, citations)
            if citation_entry is None:
                raise ValueError(f"No citation manifest entry found for {tag}")

            author, title, year, url = _extract_reference_fields(citation_entry)
            if url:
                bibliography_lines.append(
                    f"- {tag} {author}. {title}. ({year}). {url}"
                )
            else:
                bibliography_lines.append(f"- {tag} {author}. {title}. ({year}).")

    bibliography = "\n".join(bibliography_lines)
    return f"{assembled_markdown.rstrip()}\n\n{bibliography}\n"