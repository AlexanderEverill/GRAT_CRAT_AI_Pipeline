"""Validation helpers for finalized drafted section markdown."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from loaders.outline import OutlineSection


PLACEHOLDER_PATTERN = re.compile(r"\{\{[a-zA-Z0-9_]+\}\}")
CITE_KEY_PATTERN = re.compile(r"\[S\d{3}\]")
REFERENCE_LINE_PATTERN = re.compile(r"^\s*-\s*(\[S\d{3}\])", re.MULTILINE)
WORD_PATTERN = re.compile(r"\b\w+\b")

# Semantic relevance map: claim keywords → acceptable source IDs.
# If a sentence contains one of these keyword patterns and cites a source,
# the cited source must be in the acceptable set (or we flag a warning).
_CLAIM_SOURCE_MAP: dict[str, set[str]] = {
    r"(?:IRC|Section)\s*(?:§\s*)?2702|GRAT\b.*(?:statute|code|qualified annuity)":
        {"S001", "S002"},
    r"(?:25\.2702-3|GRAT\b.*regulation|valuation\s+table)":
        {"S002", "S001"},
    r"(?:IRC|Section)\s*(?:§\s*)?664|CRAT\b.*(?:statute|code|charitable\s+remainder)":
        {"S003", "S004"},
    r"(?:1\.664-2|CRAT\b.*regulation|annuity\s+trust\s+regulation)":
        {"S004", "S003"},
    r"(?:IRC|Section)\s*(?:§\s*)?2501|gift\s+tax\b":
        {"S005", "S001"},
    r"(?:IRC|Section)\s*(?:§\s*)?2033|estate\s+inclusion|(?:grantor\s+dies|mortality).*(?:gross\s+estate|included)":
        {"S006"},
    r"(?:IRC|Section)\s*(?:§\s*)?7520|hurdle\s+rate|present.value.*(?:table|rate)":
        {"S007", "S002"},
    r"(?:IRC|Section)\s*(?:§\s*)?671|grantor\s+trust.*(?:income\s+tax|taxation)":
        {"S008", "S001"},
    r"(?:IRC|Section)\s*(?:§\s*)?170|charitable.*(?:deduction|income\s+tax\s+deduction)":
        {"S009", "S003"},
    r"(?:estate\s+tax\s+rate|exemption.*\$5\.43|exemption.*\$10\.86|40\s*%)":
        {"S010"},
    r"(?:Circular\s+230|31\s+CFR|Treasury\s+Department\s+Circular)":
        {"S011"},
}
_COMPILED_CLAIM_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), sources)
    for pattern, sources in _CLAIM_SOURCE_MAP.items()
]

# Pattern to split markdown into rough sentence segments
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?\n])\s+")


@dataclass(frozen=True)
class ValidationResult:
    """Validation report for a single section's finalized markdown."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unresolved_placeholders: list[str] = field(default_factory=list)
    dangling_citations: list[str] = field(default_factory=list)
    mismatched_citations: list[str] = field(default_factory=list)
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


def check_citation_relevance(markdown: str) -> list[str]:
    """Check whether cited sources are semantically relevant to the claims they support.

    Runs on raw markdown (before citation insertion) so that [SXXX] tags are still present.
    Returns a list of human-readable mismatch descriptions.
    """
    return _check_citation_relevance(markdown)


def _check_citation_relevance(markdown: str) -> list[str]:
    """Check whether cited sources are semantically relevant to the claims they support.

    For each cite tag in a segment, we collect ALL claim-patterns that fire.
    The tag is acceptable if it appears in the acceptable-sources set of at
    least ONE of those patterns.  This avoids false positives in sentences
    that contain multiple distinct claims with separate citations.
    """
    mismatches: list[str] = []
    segments = _SENTENCE_SPLIT.split(markdown)

    for segment in segments:
        cite_keys_in_segment = CITE_KEY_PATTERN.findall(segment)
        if not cite_keys_in_segment:
            continue

        # Collect all claim-patterns that fire in this segment.
        triggered: list[tuple[re.Pattern[str], set[str]]] = [
            (pattern, acceptable)
            for pattern, acceptable in _COMPILED_CLAIM_PATTERNS
            if pattern.search(segment)
        ]
        if not triggered:
            continue

        # For each cited source, check if ANY triggered pattern accepts it.
        for cite_key in cite_keys_in_segment:
            source_id = cite_key.strip("[]")
            accepted_by_any = any(
                source_id in acceptable for _, acceptable in triggered
            )
            if not accepted_by_any:
                short_segment = segment.strip()[:120]
                all_acceptable = sorted(
                    sid for _, acceptable in triggered for sid in acceptable
                )
                mismatches.append(
                    f"Claim '{short_segment}...' cites {cite_key} but expected "
                    f"one of {all_acceptable}"
                )
    return mismatches


def validate_section_output(
    final_section_markdown: str,
    section_metadata: OutlineSection,
) -> ValidationResult:
    """Validate finalized section markdown against placeholder/citation/length rules."""
    if not isinstance(final_section_markdown, str) or not final_section_markdown.strip():
        raise ValueError("final_section_markdown must be a non-empty string")

    min_length, max_length, length_unit = _extract_length_config(section_metadata)

    unresolved_placeholders = sorted(set(PLACEHOLDER_PATTERN.findall(final_section_markdown)))
    citation_tags = sorted(set(CITE_KEY_PATTERN.findall(final_section_markdown)))
    reference_tags = sorted(set(REFERENCE_LINE_PATTERN.findall(final_section_markdown)))
    dangling_citations = [tag for tag in citation_tags if tag not in reference_tags]

    # Semantic relevance check
    mismatched_citations = _check_citation_relevance(final_section_markdown)

    measured_length = _measure_length(final_section_markdown, length_unit)

    errors: list[str] = []
    warnings: list[str] = []
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
    if mismatched_citations:
        for mismatch in mismatched_citations:
            warnings.append(f"Citation relevance: {mismatch}")

    return ValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
        unresolved_placeholders=unresolved_placeholders,
        dangling_citations=dangling_citations,
        mismatched_citations=mismatched_citations,
        measured_length=measured_length,
        min_length=min_length,
        max_length=max_length,
        length_unit=length_unit,
    )