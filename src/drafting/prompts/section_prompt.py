"""Per-section prompt assembly for drafting requests."""

from __future__ import annotations

from loaders.outline import OutlineSection
from loaders.retrieval_bundle import RetrievalChunk


DEFAULT_TOKEN_BUDGET = 1400


def _estimate_tokens(text: str) -> int:
    # Lightweight approximation: average of ~4 chars per token in English prose.
    return max(1, (len(text) + 3) // 4)


def _trim_to_budget(text: str, token_budget: int) -> str:
    if _estimate_tokens(text) <= token_budget:
        return text

    max_chars = max(1, token_budget * 4)
    marker = "\n\n[TRUNCATED_FOR_TOKEN_BUDGET]"
    if max_chars <= len(marker):
        return marker[:max_chars]
    return text[: max_chars - len(marker)].rstrip() + marker


def _section_purpose(section: OutlineSection) -> str:
    purpose = section.extra.get("purpose")
    if isinstance(purpose, str) and purpose.strip():
        return purpose.strip()
    return "Deliver a concise, evidence-backed section aligned with client goals."


def _render_numeric_map(numeric_substitution_map: dict[str, str]) -> str:
    if not numeric_substitution_map:
        return "None provided."

    lines = [f"- {placeholder}: {value}" for placeholder, value in sorted(numeric_substitution_map.items())]
    return "\n".join(lines)


def _render_chunk(chunk: RetrievalChunk, index: int) -> str:
    return (
        f"{index}. source_id={chunk.source_id}; citation_key={chunk.citation_key}; "
        f"score={chunk.score:.3f}\n"
        f"   text: {chunk.text}"
    )


def section_draft_prompt_builder(
    section: OutlineSection,
    client_context_block: str,
    chunks: list[RetrievalChunk],
    numeric_substitution_map: dict[str, str],
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> str:
    """Build a per-section user prompt with context, evidence, and numeric bindings."""
    if token_budget <= 0:
        raise ValueError("token_budget must be a positive integer")

    header = (
        "Draft the requested section using only supplied context and evidence.\n\n"
        f"Section ID: {section.section_id}\n"
        f"Section Title: {section.title}\n"
        f"Section Content Type: {section.content_type}\n"
        f"Section Purpose: {_section_purpose(section)}\n"
    )
    client_block = f"\nClient Context:\n{client_context_block}\n"
    numeric_block = (
        "\nResolved Numeric Values (placeholder -> formatted value):\n"
        f"{_render_numeric_map(numeric_substitution_map)}\n"
    )
    evidence_intro = "\nRelevant Retrieved Chunks:\n"

    base_prompt = header + client_block + numeric_block + evidence_intro
    remaining_budget = token_budget - _estimate_tokens(base_prompt)

    rendered_chunks: list[str] = []
    omitted_count = 0
    if chunks and remaining_budget > 0:
        for index, chunk in enumerate(chunks, start=1):
            candidate = _render_chunk(chunk, index)
            candidate_tokens = _estimate_tokens(candidate + "\n")
            if candidate_tokens <= remaining_budget:
                rendered_chunks.append(candidate)
                remaining_budget -= candidate_tokens
            else:
                omitted_count += 1
    else:
        omitted_count = len(chunks)

    if rendered_chunks:
        evidence_block = "\n".join(rendered_chunks)
    else:
        evidence_block = "No section-specific chunks provided."

    if omitted_count > 0:
        evidence_block += f"\n\nOmitted {omitted_count} additional chunks due to token budget."

    prompt = base_prompt + evidence_block
    return _trim_to_budget(prompt, token_budget)