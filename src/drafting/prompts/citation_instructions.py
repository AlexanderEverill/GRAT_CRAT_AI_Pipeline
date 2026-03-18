"""Reusable citation-instruction fragment for section prompts."""

from __future__ import annotations


def _normalize_source_ids(source_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    for source_id in source_ids:
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_ids must contain only non-empty strings")
        source_id = source_id.strip()
        if source_id not in normalized:
            normalized.append(source_id)
    return normalized


def citation_instruction_block(source_ids: list[str]) -> str:
    """Build a prompt fragment enforcing source-bounded [SRC-N] citations."""
    ordered_source_ids = _normalize_source_ids(source_ids)

    if not ordered_source_ids:
        return (
            "Citation Instructions:\n"
            "- No sources were provided for this section.\n"
            "- Do not fabricate citations, statistics, quotes, or factual claims.\n"
            "- If support is missing, state that evidence is unavailable."
        )

    source_lines = [
        f"- [SRC-{idx}] -> {source_id}"
        for idx, source_id in enumerate(ordered_source_ids, start=1)
    ]
    return (
        "Citation Instructions:\n"
        "- Cite only from the source IDs listed below.\n"
        "- Use inline citations exactly in [SRC-N] notation.\n"
        "- Never invent statistics or quotes.\n"
        "- Do not cite any source that is not listed below.\n"
        "Allowed Sources:\n"
        + "\n".join(source_lines)
    )