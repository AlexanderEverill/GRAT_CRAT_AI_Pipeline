from __future__ import annotations

from loaders.outline import OutlineSection
from postprocessing.validator import ValidationResult, validate_section_output


def test_validate_section_output_passes_for_valid_markdown() -> None:
    section = OutlineSection(
        section_id="grat_analysis",
        title="GRAT Analysis",
        content_type="narrative",
        order=0,
        extra={"min_words": 5, "max_words": 120},
    )
    markdown = (
        "GRAT analysis indicates improved transfer efficiency (IRS, Notice 2024-01, 2024). "
        "\n\n### References\n- [S001] IRS. Notice 2024-01. (2024).\n"
    )

    result = validate_section_output(markdown, section)

    assert isinstance(result, ValidationResult)
    assert result.is_valid is True
    assert result.errors == []
    assert result.unresolved_placeholders == []
    assert result.dangling_citations == []


def test_validate_section_output_detects_unresolved_placeholders() -> None:
    section = OutlineSection(
        section_id="summary",
        title="Summary",
        content_type="narrative",
        order=0,
    )
    markdown = "Projected value is {{projected_value_usd}}."

    result = validate_section_output(markdown, section)

    assert result.is_valid is False
    assert "{{projected_value_usd}}" in result.unresolved_placeholders
    assert any("Unresolved placeholders" in err for err in result.errors)


def test_validate_section_output_detects_dangling_citations() -> None:
    section = OutlineSection(
        section_id="summary",
        title="Summary",
        content_type="narrative",
        order=0,
    )
    markdown = (
        "Supported statement [S002].\n\n"
        "### References\n"
        "- [S001] IRS. Source One. (2024).\n"
    )

    result = validate_section_output(markdown, section)

    assert result.is_valid is False
    assert "[S002]" in result.dangling_citations
    assert any("Dangling citation" in err for err in result.errors)


def test_validate_section_output_enforces_length_bounds() -> None:
    section = OutlineSection(
        section_id="summary",
        title="Summary",
        content_type="narrative",
        order=0,
        extra={"min_words": 10, "max_words": 12},
    )
    markdown = "Too short section."

    result = validate_section_output(markdown, section)

    assert result.is_valid is False
    assert result.measured_length is not None
    assert any("below minimum bound" in err for err in result.errors)


def test_validate_section_output_detects_mismatched_citations() -> None:
    section = OutlineSection(
        section_id="summary",
        title="Summary",
        content_type="narrative",
        order=0,
    )
    # Claims about Circular 230 should cite S011, not S001
    markdown = (
        "Under Circular 230 tax advice standards [S001] apply.\n\n"
        "### References\n"
        "- [S001] IRS. Source One. (2024).\n"
    )

    result = validate_section_output(markdown, section)

    assert result.is_valid is True  # mismatches are warnings, not errors
    assert len(result.mismatched_citations) > 0
    assert len(result.warnings) > 0
