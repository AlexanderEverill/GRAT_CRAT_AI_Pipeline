"""Pipeline helpers for drafting all outline sections."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import logging
from typing import Callable, Mapping

from llm.client import DraftingError
from loaders.outline import Outline, OutlineSection

from .section_drafter import draft_section


logger = logging.getLogger(__name__)


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
        for ordinal, section in enumerate(outline.sections, start=1):
            try:
                result[section.section_id] = _draft_one_section(
                    section=section,
                    section_prompt=section_prompts[section.section_id],
                    llm_client=llm_client,
                    enable_self_critique=enable_self_critique,
                    ordinal=ordinal,
                    total=total,
                )
            except Exception as exc:
                raise DraftingError(
                    f"Failed drafting section '{section.section_id}'"
                ) from exc
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