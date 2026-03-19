from __future__ import annotations

import logging
from pathlib import Path
import threading
import time

import pytest

from drafting.pipeline import (
    _extract_recommendation_block,
    _inject_recommendation_anchor,
    draft_all_sections,
)
from loaders.outline import Outline, OutlineSection, load_outline
from llm.client import DraftingError


def test_draft_all_sections_sequential_order_and_progress_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    outline = load_outline(Path(__file__).resolve().parents[1] / "data" / "Outline.json")

    prompts = {
        section.section_id: f"Prompt for {section.section_id}"
        for section in outline.sections
    }

    call_order: list[str] = []

    def fake_llm_client(prompt: str) -> str:
        call_order.append(prompt)
        return f"markdown::{prompt}"

    result = draft_all_sections(
        outline=outline,
        section_prompts=prompts,
        llm_client=fake_llm_client,
        parallel=False,
    )

    expected_ids = [section.section_id for section in outline.sections]
    assert list(result.keys()) == expected_ids
    assert call_order == [prompts[section_id] for section_id in expected_ids]
    assert "drafting section" in caplog.text
    assert "completed section" in caplog.text


def test_draft_all_sections_parallel_respects_concurrency_cap() -> None:
    outline = Outline(
        sections=[
            OutlineSection("s1", "S1", "narrative", 0),
            OutlineSection("s2", "S2", "narrative", 1),
            OutlineSection("s3", "S3", "narrative", 2),
            OutlineSection("s4", "S4", "narrative", 3),
        ]
    )
    prompts = {section.section_id: section.section_id for section in outline.sections}

    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_llm_client(prompt: str) -> str:
        nonlocal active, max_active
        with lock:
            active += 1
            if active > max_active:
                max_active = active
        time.sleep(0.02)
        with lock:
            active -= 1
        return f"md::{prompt}"

    result = draft_all_sections(
        outline=outline,
        section_prompts=prompts,
        llm_client=fake_llm_client,
        parallel=True,
        max_concurrency=2,
    )

    assert len(result) == 4
    assert max_active <= 2


def test_draft_all_sections_raises_on_missing_prompt() -> None:
    outline = Outline(sections=[OutlineSection("s1", "S1", "narrative", 0)])

    with pytest.raises(ValueError, match="Missing section prompts"):
        draft_all_sections(
            outline=outline,
            section_prompts={},
            llm_client=lambda _: "ok",
        )


def test_draft_all_sections_wraps_section_failure() -> None:
    outline = Outline(sections=[OutlineSection("s1", "S1", "narrative", 0)])

    with pytest.raises(DraftingError, match="Failed drafting section 's1'"):
        draft_all_sections(
            outline=outline,
            section_prompts={"s1": "prompt"},
            llm_client=lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
        )


# --- Recommendation consistency tests ---


class TestExtractRecommendationBlock:
    def test_extracts_from_heading(self) -> None:
        md = (
            "## Executive Summary\n\nSome intro.\n\n"
            "### Recommendation\n\n"
            "The GRAT is recommended as the **primary** vehicle.\n"
        )
        result = _extract_recommendation_block(md)
        assert result is not None
        assert "primary" in result
        assert "GRAT" in result

    def test_extracts_from_h2_heading(self) -> None:
        md = "## Recommendation\n\nThe CRAT is complementary.\n"
        result = _extract_recommendation_block(md)
        assert result is not None
        assert "complementary" in result

    def test_falls_back_to_keyword_paragraph(self) -> None:
        md = (
            "Some intro text.\n\n"
            "The GRAT is recommended as the primary strategy.\n\n"
            "Some unrelated closing text.\n"
        )
        result = _extract_recommendation_block(md)
        assert result is not None
        assert "primary" in result

    def test_returns_none_for_no_recommendation(self) -> None:
        md = "Some factual text without any recommendation keywords.\n"
        assert _extract_recommendation_block(md) is None


class TestInjectRecommendationAnchor:
    def test_prepends_anchor_to_prompt(self) -> None:
        prompt = "Draft the requested section."
        anchor_text = "GRAT is primary, CRAT is complementary."
        result = _inject_recommendation_anchor(prompt, anchor_text)
        assert result.startswith("IMPORTANT")
        assert "GRAT is primary" in result
        assert result.endswith(prompt)

    def test_anchor_includes_consistency_instructions(self) -> None:
        result = _inject_recommendation_anchor("prompt", "rec block")
        assert "MUST use the same" in result
        assert "Do NOT reverse" in result


class TestRecommendationConsistencyInSequentialDrafting:
    """Verify that the comparison_recommendation prompt receives the
    executive summary's recommendation when drafting sequentially."""

    def test_comparison_prompt_receives_exec_summary_recommendation(self) -> None:
        outline = Outline(
            sections=[
                OutlineSection("executive_summary", "Exec", "narrative", 0),
                OutlineSection("comparison_recommendation", "Compare", "table", 1),
            ]
        )

        exec_output = (
            "Summary text.\n\n"
            "### Recommendation\n\n"
            "The GRAT is recommended as the **primary** vehicle."
        )
        prompts = {
            "executive_summary": "Draft exec summary",
            "comparison_recommendation": "Draft comparison",
        }

        received_prompts: dict[str, str] = {}

        def fake_llm(prompt: str) -> str:
            # Return exec_output for the first call, record all prompts.
            if "Draft exec summary" in prompt:
                received_prompts["executive_summary"] = prompt
                return exec_output
            received_prompts["comparison_recommendation"] = prompt
            return "Comparison text."

        draft_all_sections(
            outline=outline,
            section_prompts=prompts,
            llm_client=fake_llm,
            parallel=False,
        )

        comp_prompt = received_prompts["comparison_recommendation"]
        assert "Recommendation consistency requirement" in comp_prompt
        assert "primary" in comp_prompt
        assert "GRAT" in comp_prompt

    def test_no_anchor_when_exec_summary_lacks_recommendation(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.WARNING)
        outline = Outline(
            sections=[
                OutlineSection("executive_summary", "Exec", "narrative", 0),
                OutlineSection("comparison_recommendation", "Compare", "table", 1),
            ]
        )
        prompts = {
            "executive_summary": "Draft exec summary",
            "comparison_recommendation": "Draft comparison",
        }

        received_prompts: dict[str, str] = {}

        def fake_llm(prompt: str) -> str:
            if "Draft exec summary" in prompt:
                return "Plain factual text with no keywords."
            received_prompts["comparison_recommendation"] = prompt
            return "Comparison text."

        draft_all_sections(
            outline=outline,
            section_prompts=prompts,
            llm_client=fake_llm,
            parallel=False,
        )

        comp_prompt = received_prompts["comparison_recommendation"]
        assert "Recommendation consistency" not in comp_prompt
        assert "could not extract recommendation" in caplog.text
