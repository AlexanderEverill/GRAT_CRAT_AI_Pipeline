"""Token budget guardrails for drafting prompts."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re


logger = logging.getLogger(__name__)


_CHUNK_BLOCK_PATTERN = re.compile(
    r"(?ms)^\d+\.\s+source_id=(?P<source>[^;]+);\s+"
    r"citation_key=(?P<citation>[^;]+);\s+score=(?P<score>-?\d+(?:\.\d+)?)\n"
    r"\s+text:\s.*?"
    r"(?=^\d+\.\s+source_id=|\n\nOmitted\s+\d+\s+additional\s+chunks|\n\nCitation Instructions:|\Z)",
)


@dataclass(frozen=True)
class TokenBudgetConfig:
    """Configuration for pre-request prompt budget enforcement."""

    model_max_tokens: int
    reserved_output_tokens: int = 0


def estimate_tokens(text: str) -> int:
    """Estimate token count using a lightweight character-based heuristic."""
    return max(1, (len(text) + 3) // 4)


def _effective_prompt_budget(config: TokenBudgetConfig) -> int:
    if config.model_max_tokens <= 0:
        raise ValueError("model_max_tokens must be > 0")
    if config.reserved_output_tokens < 0:
        raise ValueError("reserved_output_tokens must be >= 0")

    budget = config.model_max_tokens - config.reserved_output_tokens
    if budget <= 0:
        raise ValueError("effective prompt token budget must be > 0")
    return budget


def _trim_hard(prompt: str, token_budget: int) -> str:
    marker = "\n\n[TRUNCATED_FOR_TOKEN_BUDGET]"
    max_chars = max(1, token_budget * 4)
    if max_chars <= len(marker):
        return marker[:max_chars]
    return prompt[: max_chars - len(marker)].rstrip() + marker


def token_budget_guard(prompt: str, config: TokenBudgetConfig) -> str:
    """Ensure prompt fits budget, trimming least-relevant chunks first."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    budget = _effective_prompt_budget(config)
    current = prompt

    if estimate_tokens(current) <= budget:
        return current

    removed = 0
    while estimate_tokens(current) > budget:
        matches = list(_CHUNK_BLOCK_PATTERN.finditer(current))
        if not matches:
            break

        lowest = min(matches, key=lambda match: float(match.group("score")))
        source = lowest.group("source").strip()
        citation = lowest.group("citation").strip()
        score = float(lowest.group("score"))
        removed += 1

        current = current[: lowest.start()] + current[lowest.end() :]
        logger.warning(
            "token budget guard removed chunk source_id=%s citation_key=%s score=%.3f",
            source,
            citation,
            score,
        )

    if estimate_tokens(current) > budget:
        logger.warning(
            "token budget guard applied hard trim after removing %d chunk(s)", removed
        )
        current = _trim_hard(current, budget)
    elif removed > 0:
        logger.warning(
            "token budget guard prompt now within budget after removing %d chunk(s)",
            removed,
        )

    return current