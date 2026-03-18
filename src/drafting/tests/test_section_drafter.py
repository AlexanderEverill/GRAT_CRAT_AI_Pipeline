from __future__ import annotations

import pytest

from drafting.section_drafter import SELF_CRITIQUE_QUESTION, draft_section
from llm.client import DraftingError


class _FakeLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            raise RuntimeError("no response configured")
        return self.responses.pop(0)


def test_draft_section_calls_llm_once_without_critique() -> None:
    llm_client = _FakeLLMClient(["## GRAT Analysis\nBody text"])

    result = draft_section(
        section_prompt="Write GRAT section",
        llm_client=llm_client,
        enable_self_critique=False,
    )

    assert result.startswith("## GRAT Analysis")
    assert len(llm_client.prompts) == 1


def test_draft_section_runs_optional_self_critique_pass() -> None:
    llm_client = _FakeLLMClient([
        "## GRAT Analysis\nUnsupported number 999.",
        "## GRAT Analysis\nRevised supported text.",
    ])

    result = draft_section(
        section_prompt="Write GRAT section with provided evidence",
        llm_client=llm_client,
        enable_self_critique=True,
    )

    assert result == "## GRAT Analysis\nRevised supported text."
    assert len(llm_client.prompts) == 2
    assert SELF_CRITIQUE_QUESTION in llm_client.prompts[1]


def test_draft_section_wraps_failures_as_drafting_error() -> None:
    def failing_client(_: str) -> str:
        raise RuntimeError("provider unavailable")

    with pytest.raises(DraftingError, match="Section drafting failed"):
        draft_section(section_prompt="Write section", llm_client=failing_client)
