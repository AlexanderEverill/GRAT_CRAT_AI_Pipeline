"""Thin LLM client wrapper for drafting-stage completions."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any, Callable, Literal

from utils.token_budget import TokenBudgetConfig, token_budget_guard


logger = logging.getLogger(__name__)


class DraftingError(RuntimeError):
    """Raised when drafting completion generation fails."""


@dataclass(frozen=True)
class ModelConfig:
    """Runtime model settings for drafting completion generation."""

    provider: Literal["openai", "anthropic"]
    model: str
    temperature: float = 0.2
    max_tokens: int = 1200
    max_prompt_tokens: int | None = None
    reserved_output_tokens: int = 0
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0


def _extract_openai_text(response: Any) -> str:
    direct_text = getattr(response, "output_text", None)
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        raise DraftingError("OpenAI response did not contain completion text")

    parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            continue
        for block in content:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())

    combined = "\n".join(parts).strip()
    if not combined:
        raise DraftingError("OpenAI response did not contain completion text")
    return combined


def _extract_openai_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}

    extracted: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if isinstance(value, int):
            extracted[key] = value
    return extracted


def _extract_anthropic_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if not isinstance(content, list):
        raise DraftingError("Anthropic response did not contain completion text")

    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())

    combined = "\n".join(parts).strip()
    if not combined:
        raise DraftingError("Anthropic response did not contain completion text")
    return combined


def _extract_anthropic_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}

    extracted: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens"):
        value = getattr(usage, key, None)
        if isinstance(value, int):
            extracted[key] = value

    if "input_tokens" in extracted and "output_tokens" in extracted:
        extracted["total_tokens"] = (
            extracted["input_tokens"] + extracted["output_tokens"]
        )
    return extracted


def _is_rate_limit_error(exc: Exception, provider: str) -> bool:
    if getattr(exc, "status_code", None) == 429:
        return True

    class_name = exc.__class__.__name__.lower()
    if "ratelimit" in class_name or "rate_limit" in class_name:
        return True

    if provider == "openai":
        try:
            from openai import RateLimitError as OpenAIRateLimitError

            return isinstance(exc, OpenAIRateLimitError)
        except Exception:
            return False

    if provider == "anthropic":
        try:
            from anthropic import RateLimitError as AnthropicRateLimitError

            return isinstance(exc, AnthropicRateLimitError)
        except Exception:
            return False

    return False


def _openai_completion(
    prompt: str,
    config: ModelConfig,
    system_prompt: str | None,
    client: Any | None,
) -> tuple[str, dict[str, int]]:
    if client is None:
        try:
            from openai import OpenAI
        except Exception as exc:
            raise DraftingError(
                "OpenAI client is not available; install and configure openai package"
            ) from exc
        client = OpenAI()

    input_payload: list[dict[str, Any]] = []
    if system_prompt:
        input_payload.append(
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            }
        )
    input_payload.append(
        {
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        }
    )

    response = client.responses.create(
        model=config.model,
        input=input_payload,
        temperature=config.temperature,
        max_output_tokens=config.max_tokens,
    )
    return _extract_openai_text(response), _extract_openai_usage(response)


def _anthropic_completion(
    prompt: str,
    config: ModelConfig,
    system_prompt: str | None,
    client: Any | None,
) -> tuple[str, dict[str, int]]:
    if client is None:
        try:
            from anthropic import Anthropic
        except Exception as exc:
            raise DraftingError(
                "Anthropic client is not available; install and configure anthropic package"
            ) from exc
        client = Anthropic()

    response = client.messages.create(
        model=config.model,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        system=system_prompt or "",
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_anthropic_text(response), _extract_anthropic_usage(response)


def raw_completion(
    prompt: str,
    model_config: ModelConfig,
    system_prompt: str | None = None,
    client: Any | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> str:
    """Request a raw model completion with retries and typed failure handling."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if model_config.max_retries < 1:
        raise ValueError("max_retries must be >= 1")

    guarded_prompt = prompt
    if model_config.max_prompt_tokens is not None:
        guarded_prompt = token_budget_guard(
            prompt,
            TokenBudgetConfig(
                model_max_tokens=model_config.max_prompt_tokens,
                reserved_output_tokens=model_config.reserved_output_tokens,
            ),
        )

    for attempt in range(1, model_config.max_retries + 1):
        try:
            if model_config.provider == "openai":
                completion, usage = _openai_completion(
                    prompt=guarded_prompt,
                    config=model_config,
                    system_prompt=system_prompt,
                    client=client,
                )
            elif model_config.provider == "anthropic":
                completion, usage = _anthropic_completion(
                    prompt=guarded_prompt,
                    config=model_config,
                    system_prompt=system_prompt,
                    client=client,
                )
            else:
                raise DraftingError(
                    f"Unsupported LLM provider '{model_config.provider}'"
                )

            if usage:
                logger.info(
                    "llm token usage provider=%s model=%s usage=%s",
                    model_config.provider,
                    model_config.model,
                    usage,
                )
            return completion
        except Exception as exc:
            if _is_rate_limit_error(exc, model_config.provider) and (
                attempt < model_config.max_retries
            ):
                backoff = model_config.retry_backoff_seconds * attempt
                logger.warning(
                    (
                        "rate limit from %s model=%s attempt=%d/%d; "
                        "retrying in %.2fs"
                    ),
                    model_config.provider,
                    model_config.model,
                    attempt,
                    model_config.max_retries,
                    backoff,
                )
                sleep_fn(backoff)
                continue

            raise DraftingError(
                (
                    f"Draft completion failed for provider={model_config.provider} "
                    f"model={model_config.model}"
                )
            ) from exc

    raise DraftingError(
        f"Draft completion failed for provider={model_config.provider} model={model_config.model}"
    )