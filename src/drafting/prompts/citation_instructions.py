"""Reusable citation-instruction fragment for section prompts."""

from __future__ import annotations


# Human-readable labels for source IDs used in prompts
SOURCE_LABELS: dict[str, str] = {
    "S001": "IRC §2702 — GRAT core statute",
    "S002": "26 CFR §25.2702-3 — GRAT qualified interest regulations",
    "S003": "IRC §664 — CRAT core statute",
    "S004": "26 CFR §1.664-2 — CRAT annuity trust regulations",
    "S005": "IRC §2501 — Gift tax imposition",
    "S006": "IRC §2033 — Estate inclusion",
    "S007": "IRC §7520 — Hurdle rate / valuation tables",
    "S008": "IRC §671 — Grantor trust income tax rules",
    "S009": "IRC §170 — Charitable income tax deduction",
    "S010": "IRS estate tax — exemptions and rates",
    "S011": "31 CFR Part 10 — Circular 230 disclosure standards",
}


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
    """Build a prompt fragment enforcing source-bounded [SXXX] citations."""
    ordered_source_ids = _normalize_source_ids(source_ids)

    if not ordered_source_ids:
        return (
            "Citation Instructions:\n"
            "- No sources were provided for this section.\n"
            "- Do not fabricate citations, statistics, quotes, or factual claims.\n"
            "- If support is missing, state that evidence is unavailable."
        )

    source_lines = [
        f"- [{sid}] = {SOURCE_LABELS.get(sid, sid)}"
        for sid in ordered_source_ids
    ]
    return (
        "Citation Instructions:\n"
        "- Cite only from the source IDs listed below.\n"
        "- Use inline citations exactly in [SXXX] notation (e.g. [S001], [S007]).\n"
        "- Match each citation to the specific authority that supports the claim.\n"
        "- Never invent statistics or quotes.\n"
        "- Do not cite any source that is not listed below.\n"
        "Allowed Sources:\n"
        + "\n".join(source_lines)
    )