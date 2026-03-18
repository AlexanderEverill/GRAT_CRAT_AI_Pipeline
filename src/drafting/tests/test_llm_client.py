from __future__ import annotations

import logging

import pytest

from llm.client import DraftingError, ModelConfig, raw_completion


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int, total_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = total_tokens


class _FakeOpenAIResponse:
    def __init__(self, text: str) -> None:
        self.output_text = text
        self.usage = _FakeUsage(100, 50, 150)


class _FakeOpenAIResponses:
    def __init__(self, outputs: list[object]) -> None:
        self._outputs = outputs
        self.calls = 0
        self.last_create_kwargs: dict[str, object] | None = None

    def create(self, **_: object) -> object:
        self.last_create_kwargs = _
        result = self._outputs[self.calls]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return result


class _FakeOpenAIClient:
    def __init__(self, outputs: list[object]) -> None:
        self.responses = _FakeOpenAIResponses(outputs)


class _FakeRateLimitError(Exception):
    pass


class _FakeAnthropicUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeAnthropicBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeAnthropicResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeAnthropicBlock(text)]
        self.usage = _FakeAnthropicUsage(80, 30)


class _FakeAnthropicMessages:
    def __init__(self, response: _FakeAnthropicResponse) -> None:
        self._response = response

    def create(self, **_: object) -> _FakeAnthropicResponse:
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response: _FakeAnthropicResponse) -> None:
        self.messages = _FakeAnthropicMessages(response)


def test_raw_completion_openai_success_logs_usage(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    config = ModelConfig(provider="openai", model="gpt-test")
    fake_client = _FakeOpenAIClient([_FakeOpenAIResponse("Hello world")])

    result = raw_completion(
        prompt="draft section",
        model_config=config,
        system_prompt="system prompt",
        client=fake_client,
    )

    assert result == "Hello world"
    assert "token usage" in caplog.text


def test_raw_completion_retries_on_rate_limit_then_succeeds() -> None:
    config = ModelConfig(
        provider="openai",
        model="gpt-test",
        max_retries=3,
        retry_backoff_seconds=0.5,
    )
    fake_client = _FakeOpenAIClient(
        [_FakeRateLimitError("rate limited"), _FakeOpenAIResponse("Recovered")]
    )
    sleep_calls: list[float] = []

    result = raw_completion(
        prompt="retry prompt",
        model_config=config,
        client=fake_client,
        sleep_fn=sleep_calls.append,
    )

    assert result == "Recovered"
    assert fake_client.responses.calls == 2
    assert sleep_calls == [0.5]


def test_raw_completion_raises_typed_error_on_failure() -> None:
    config = ModelConfig(provider="openai", model="gpt-test", max_retries=1)
    fake_client = _FakeOpenAIClient([RuntimeError("boom")])

    with pytest.raises(DraftingError, match="Draft completion failed"):
        raw_completion(prompt="failing prompt", model_config=config, client=fake_client)


def test_raw_completion_supports_anthropic_client() -> None:
    config = ModelConfig(provider="anthropic", model="claude-test")
    fake_client = _FakeAnthropicClient(_FakeAnthropicResponse("Anthropic output"))

    result = raw_completion(
        prompt="anthropic prompt",
        model_config=config,
        client=fake_client,
    )

    assert result == "Anthropic output"


def test_raw_completion_applies_token_budget_guard_before_api_call() -> None:
    config = ModelConfig(
        provider="openai",
        model="gpt-test",
        max_prompt_tokens=80,
        reserved_output_tokens=20,
    )
    fake_client = _FakeOpenAIClient([_FakeOpenAIResponse("Trimmed ok")])
    prompt = (
        "Header\n\n"
        "Relevant Retrieved Chunks:\n"
        "1. source_id=S001; citation_key=[S1]; score=0.900\n"
        "   text: High relevance chunk.\n"
        "2. source_id=S002; citation_key=[S2]; score=0.100\n"
        "   text: Low relevance chunk that should be removed first.\n\n"
        "Citation Instructions:\n"
        "- Use [SRC-N].\n"
    )

    result = raw_completion(prompt=prompt, model_config=config, client=fake_client)

    assert result == "Trimmed ok"
    assert fake_client.responses.last_create_kwargs is not None
    input_payload = fake_client.responses.last_create_kwargs["input"]
    assert isinstance(input_payload, list)
    user_content = input_payload[-1]["content"][0]["text"]
    assert "source_id=S002" not in user_content
