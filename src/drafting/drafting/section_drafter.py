"""Section drafting orchestration over an injected LLM client."""

from __future__ import annotations

from typing import Callable

from llm.client import DraftingError


SELF_CRITIQUE_QUESTION = (
    "Does this section contain any figures not from the provided context?"
)


def _build_self_critique_prompt(section_prompt: str, raw_section_markdown: str) -> str:
    return (
        "You are reviewing a drafted section for unsupported numeric claims.\n"
        f"Self-critique question: {SELF_CRITIQUE_QUESTION}\n\n"
        "Original section prompt:\n"
        f"{section_prompt}\n\n"
        "Drafted section markdown:\n"
        f"{raw_section_markdown}\n\n"
        "If any figure is not grounded in provided context, revise the section to remove "
        "or qualify it. Return only the final markdown section."
    )


def draft_section(
    section_prompt: str,
    llm_client: Callable[[str], str],
    enable_self_critique: bool = False,
) -> str:
    """Generate section markdown using an injected llm_client callable."""
    if not isinstance(section_prompt, str) or not section_prompt.strip():
        raise ValueError("section_prompt must be a non-empty string")

    try:
        raw_section_markdown = llm_client(section_prompt).strip()
    except Exception as exc:
        raise DraftingError("Section drafting failed") from exc

    if not raw_section_markdown:
        raise DraftingError("Section drafting produced empty output")

    if not enable_self_critique:
        return raw_section_markdown

    critique_prompt = _build_self_critique_prompt(section_prompt, raw_section_markdown)
    try:
        critiqued_markdown = llm_client(critique_prompt).strip()
    except Exception as exc:
        raise DraftingError("Section self-critique pass failed") from exc

    if critiqued_markdown:
        return critiqued_markdown
    return raw_section_markdown