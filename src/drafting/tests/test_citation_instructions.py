import pytest

from prompts.citation_instructions import citation_instruction_block


def test_citation_instruction_block_with_sources() -> None:
    block = citation_instruction_block(["S002", "S004", "S002"])

    assert "[SXXX]" in block
    assert "Never invent statistics or quotes" in block
    assert "[S002] = " in block
    assert "[S004] = " in block


def test_citation_instruction_block_with_empty_sources() -> None:
    block = citation_instruction_block([])

    assert "No sources were provided" in block
    assert "Do not fabricate citations" in block


def test_citation_instruction_block_rejects_invalid_source_ids() -> None:
    with pytest.raises(ValueError, match="non-empty strings"):
        citation_instruction_block(["S001", ""])  # type: ignore[list-item]
