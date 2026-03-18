from __future__ import annotations

import logging

from utils.token_budget import TokenBudgetConfig, estimate_tokens, token_budget_guard


def test_token_budget_guard_removes_lowest_score_chunks_first(
    caplog,
) -> None:
    caplog.set_level(logging.WARNING)
    prompt = (
        "Header\n\n"
        "Relevant Retrieved Chunks:\n"
        "1. source_id=S001; citation_key=[S1]; score=0.900\n"
        "   text: High relevance chunk.\n"
        "2. source_id=S002; citation_key=[S2]; score=0.100\n"
        "   text: Low relevance chunk that should be removed first.\n"
        "3. source_id=S003; citation_key=[S3]; score=0.500\n"
        "   text: Medium relevance chunk.\n\n"
        "Citation Instructions:\n"
        "- Use [SRC-N].\n"
    )

    trimmed = token_budget_guard(
        prompt,
        TokenBudgetConfig(model_max_tokens=80, reserved_output_tokens=20),
    )

    assert "source_id=S002" not in trimmed
    assert "source_id=S001" in trimmed
    assert estimate_tokens(trimmed) <= 60
    assert "removed chunk source_id=S002" in caplog.text


def test_token_budget_guard_hard_trims_when_no_chunks_present(caplog) -> None:
    caplog.set_level(logging.WARNING)
    prompt = "A" * 2000

    trimmed = token_budget_guard(prompt, TokenBudgetConfig(model_max_tokens=100))

    assert estimate_tokens(trimmed) <= 100
    assert "TRUNCATED_FOR_TOKEN_BUDGET" in trimmed
    assert "hard trim" in caplog.text
