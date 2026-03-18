"""Validation helpers for finalized drafted section markdown."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from loaders.outline import OutlineSection


PLACEHOLDER_PATTERN = re.compile(r"\{\{[a-zA-Z0-9_]+\}\}")
SRC_TAG_PATTERN = re.compile(r"\[SRC-[^\]]+\]")
REFERENCE_LINE_PATTERN = re.compile(r"^\s*-\s*(\[SRC-[^\]]+\])", re.MULTILINE)
WORD_PATTERN = re.compile(r"\b\w+\b")


@dataclass(frozen=True)
class ValidationResult:
    """Validation report for a single section's finalized markdown."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    unresolved_placeholders: list[str] = field(default_factory=list)
    dangling_citations: list[str] = field(default_factory=list)
    measured_length: int | None = None
    min_length: int | None = None
    max_length: int | None = None
    length_unit: str = "words"


def _coerce_bound(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Section metadata field '{field_name}' must be an integer")
    if value < 0:
        raise ValueError(f"Section metadata field '{field_name}' must be >= 0")
    return value


def _extract_length_config(section: OutlineSection) -> tuple[int | None, int | None, str]:
    extra = section.extra

    has_word_bounds = "min_words" in extra or "max_words" in extra
    has_char_bounds = "min_chars" in extra or "max_chars" in extra
    if has_word_bounds and has_char_bounds:
        raise ValueError(
            "Section metadata must not mix word and char length bounds"
        )

    if has_char_bounds:
        min_len = _coerce_bound(extra.get("min_chars"), "min_chars")
        max_len = _coerce_bound(extra.get("max_chars"), "max_chars")
        unit = "chars"
    elif has_word_bounds:
        min_len = _coerce_bound(extra.get("min_words"), "min_words")
        max_len = _coerce_bound(extra.get("max_words"), "max_words")
        unit = "words"
    else:
        # Backward-compatible generic keys default to word-based bounds.
        min_len = _coerce_bound(extra.get("min_length"), "min_length")
        max_len = _coerce_bound(extra.get("max_length"), "max_length")
        unit = "words"

    if min_len is not None and max_len is not None and min_len > max_len:
        raise ValueError("Section metadata min length must be <= max length")

    return min_len, max_len, unit


def _measure_length(markdown: str, unit: str) -> int:
    if unit == "chars":
        return len(markdown)
    return len(WORD_PATTERN.findall(markdown))


def validate_section_output(
    final_section_markdown: str,
    section_metadata: OutlineSection,
) -> ValidationResult:
    """Validate finalized section markdown against placeholder/citation/length rules."""
    if not isinstance(final_section_markdown, str) or not final_section_markdown.strip():
        raise ValueError("final_section_markdown must be a non-empty string")

    min_length, max_length, length_unit = _extract_length_config(section_metadata)

    unresolved_placeholders = sorted(set(PLACEHOLDER_PATTERN.findall(final_section_markdown)))
    citation_tags = sorted(set(SRC_TAG_PATTERN.findall(final_section_markdown)))
    reference_tags = sorted(set(REFERENCE_LINE_PATTERN.findall(final_section_markdown)))
    dangling_citations = [tag for tag in citation_tags if tag not in reference_tags]

    measured_length = _measure_length(final_section_markdown, length_unit)

    errors: list[str] = []
    if unresolved_placeholders:
        errors.append(
            "Unresolved placeholders found: " + ", ".join(unresolved_placeholders)
        )
    if dangling_citations:
        errors.append("Dangling citation tags found: " + ", ".join(dangling_citations))
    if min_length is not None and measured_length < min_length:
        errors.append(
            (
                f"Section length below minimum bound: {measured_length} {length_unit} "
                f"< {min_length}"
            )
        )
    if max_length is not None and measured_length > max_length:
        errors.append(
            (
                f"Section length above maximum bound: {measured_length} {length_unit} "
                f"> {max_length}"
            )
        )

    return ValidationResult(
        is_valid=not errors,
        errors=errors,
        unresolved_placeholders=unresolved_placeholders,
        dangling_citations=dangling_citations,
        measured_length=measured_length,
        min_length=min_length,
        max_length=max_length,
        length_unit=length_unit,
    )