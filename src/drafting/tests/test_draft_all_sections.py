from __future__ import annotations

import logging
from pathlib import Path
import threading
import time

import pytest

from drafting.pipeline import draft_all_sections
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
