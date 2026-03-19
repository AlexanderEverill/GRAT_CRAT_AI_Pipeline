"""Pipeline helpers for drafting all outline sections."""

from __future__ import annotations

import re
from concurrent.futures import Future, ThreadPoolExecutor
import logging
from typing import Callable, Mapping

from llm.client import DraftingError
from loaders.outline import Outline, OutlineSection

from .section_drafter import draft_section


logger = logging.getLogger(__name__)

# Section IDs that must share a consistent recommendation.
_EXEC_SUMMARY_ID = "executive_summary"
_COMPARISON_REC_ID = "comparison_recommendation"


def _extract_recommendation_block(executive_summary_md: str) -> str | None:
    """Return the recommendation paragraph(s) from the executive summary.

    Looks for a ### Recommendation heading or the last paragraph that contains
    the word "recommended" / "primary" / "complementary".  Returns *None* if
    no recommendation text can be identified.
    """
    # Try heading-delimited block first.
    match = re.search(
        r"(?:^|\n)###?\s*Recommendation\s*\n(.*?)(?=\n###?\s|\Z)",
        executive_summary_md,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        block = match.group(1).strip()
        if block:
            return block

    # Fallback: find paragraphs containing recommendation keywords.
    paragraphs = executive_summary_md.split("\n\n")
    for para in reversed(paragraphs):
        if re.search(r"\b(recommended|primary|complementary)\b", para, re.IGNORECASE):
            return para.strip()

    return None


def _inject_recommendation_anchor(
    prompt: str, recommendation_block: str
) -> str:
    """Prepend a consistency anchor to a section prompt."""
    anchor = (
        "IMPORTANT — Recommendation consistency requirement:\n"
        "The executive summary has already been drafted and contains the "
        "following recommendation. Your recommendation MUST use the same "
        "primary/complementary ordering and consistent language. Do NOT "
        "reverse which strategy is primary and which is complementary.\n\n"
        "--- Executive Summary Recommendation ---\n"
        f"{recommendation_block}\n"
        "--- End Executive Summary Recommendation ---\n\n"
    )
    return anchor + prompt


def _draft_one_section(
    section: OutlineSection,
    section_prompt: str,
    llm_client: Callable[[str], str],
    enable_self_critique: bool,
    ordinal: int,
    total: int,
) -> str:
    logger.info(
        "drafting section %d/%d section_id=%s", ordinal, total, section.section_id
    )
    markdown = draft_section(
        section_prompt=section_prompt,
        llm_client=llm_client,
        enable_self_critique=enable_self_critique,
    )
    logger.info(
        "completed section %d/%d section_id=%s chars=%d",
        ordinal,
        total,
        section.section_id,
        len(markdown),
    )
    return markdown


def draft_all_sections(
    outline: Outline,
    section_prompts: Mapping[str, str],
    llm_client: Callable[[str], str],
    enable_self_critique: bool = False,
    parallel: bool = False,
    max_concurrency: int = 4,
) -> dict[str, str]:
    """Draft every section in outline order and return section_id->markdown."""
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be >= 1")

    missing_prompts = [
        section.section_id
        for section in outline.sections
        if section.section_id not in section_prompts
    ]
    if missing_prompts:
        raise ValueError(
            "Missing section prompts for section IDs: " + ", ".join(missing_prompts)
        )

    total = len(outline.sections)
    if not parallel:
        result: dict[str, str] = {}
        recommendation_anchor: str | None = None
        for ordinal, section in enumerate(outline.sections, start=1):
            effective_prompt = section_prompts[section.section_id]

            # Inject the executive-summary recommendation into the
            # comparison/recommendation prompt so the LLM aligns its
            # primary/complementary framing with the earlier section.
            if (
                section.section_id == _COMPARISON_REC_ID
                and recommendation_anchor is not None
            ):
                effective_prompt = _inject_recommendation_anchor(
                    effective_prompt, recommendation_anchor
                )
                logger.info(
                    "injected recommendation anchor into '%s' prompt",
                    _COMPARISON_REC_ID,
                )

            try:
                drafted = _draft_one_section(
                    section=section,
                    section_prompt=effective_prompt,
                    llm_client=llm_client,
                    enable_self_critique=enable_self_critique,
                    ordinal=ordinal,
                    total=total,
                )
            except Exception as exc:
                raise DraftingError(
                    f"Failed drafting section '{section.section_id}'"
                ) from exc

            result[section.section_id] = drafted

            # After drafting the executive summary, extract its
            # recommendation so later sections can be anchored to it.
            if section.section_id == _EXEC_SUMMARY_ID:
                recommendation_anchor = _extract_recommendation_block(drafted)
                if recommendation_anchor:
                    logger.info(
                        "extracted recommendation anchor from '%s' (%d chars)",
                        _EXEC_SUMMARY_ID,
                        len(recommendation_anchor),
                    )
                else:
                    logger.warning(
                        "could not extract recommendation from '%s'; "
                        "consistency anchor will not be injected",
                        _EXEC_SUMMARY_ID,
                    )
        return result

    futures_by_section_id: dict[str, Future[str]] = {}
    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        for ordinal, section in enumerate(outline.sections, start=1):
            future = executor.submit(
                _draft_one_section,
                section,
                section_prompts[section.section_id],
                llm_client,
                enable_self_critique,
                ordinal,
                total,
            )
            futures_by_section_id[section.section_id] = future

        ordered_result: dict[str, str] = {}
        for section in outline.sections:
            try:
                ordered_result[section.section_id] = futures_by_section_id[
                    section.section_id
                ].result()
            except Exception as exc:
                raise DraftingError(
                    f"Failed drafting section '{section.section_id}'"
                ) from exc
        return ordered_result