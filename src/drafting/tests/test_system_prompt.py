from prompts.system_prompt import system_prompt_template


def test_system_prompt_template_contains_required_contract() -> None:
    prompt = system_prompt_template()

    assert isinstance(prompt, str)
    assert "senior financial advisor" in prompt.lower()
    assert "factual" in prompt.lower()
    assert "citation" in prompt.lower()
    assert "do not hallucinate" in prompt.lower()
    assert "markdown section headings" in prompt.lower()
    assert "[SXXX]" in prompt or "[S001]" in prompt
