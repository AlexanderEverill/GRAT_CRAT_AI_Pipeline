"""Append a deduplicated global bibliography to assembled draft markdown."""

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
        short_id = (
            citation.get("short_id")
            or citation.get("src_tag")
            or citation.get("src_id")
            or citation.get("cite_key")
        )
        if isinstance(short_id, str) and short_id.strip() == tag:
            return citation

    if 1 <= citation_num <= len(citations):
        entry = citations[citation_num - 1]
        if isinstance(entry, dict):
            return entry
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
    for match in SRC_TAG_PATTERN.finditer(assembled_markdown):
        tag = match.group(0)
        if tag not in seen:
            seen.add(tag)
            ordered_unique_tags.append(tag)

    bibliography_lines = ["## Global References"]
    if not ordered_unique_tags:
        bibliography_lines.append("- No citations detected in assembled draft.")
    else:
        for tag in ordered_unique_tags:
            citation_num = int(tag.removeprefix("[SRC-").removesuffix("]"))
            citation_entry = _find_citation_entry(citation_num, citations)
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