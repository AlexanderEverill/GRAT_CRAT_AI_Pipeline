"""Numeric placeholder substitution for drafted markdown sections."""

from __future__ import annotations

import re
from typing import Mapping


PLACEHOLDER_PATTERN = re.compile(r"\{\{[a-zA-Z0-9_]+\}\}")


class MissingPlaceholderError(ValueError):
    """Raised when one or more placeholders have no bound numeric value."""


def _normalize_placeholder_map(
    numeric_substitution_map: Mapping[str, str],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in numeric_substitution_map.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("numeric_substitution_map keys must be non-empty strings")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "numeric_substitution_map values must be non-empty strings"
            )

        cleaned_key = key.strip()
        if cleaned_key.startswith("{{") and cleaned_key.endswith("}}"):
            token = cleaned_key
        else:
            token = f"{{{{{cleaned_key}}}}}"
        normalized[token] = value.strip()
    return normalized


def substitute_numerics(
    annotated_markdown: str,
    numeric_substitution_map: Mapping[str, str],
) -> str:
    """Replace {{placeholder}} tokens with bound numeric values."""
    if not isinstance(annotated_markdown, str):
        raise ValueError("annotated_markdown must be a string")

    normalized_map = _normalize_placeholder_map(numeric_substitution_map)

    found_tokens = PLACEHOLDER_PATTERN.findall(annotated_markdown)
    seen_missing: list[str] = []
    for token in found_tokens:
        if token not in normalized_map and token not in seen_missing:
            seen_missing.append(token)

    if seen_missing:
        raise MissingPlaceholderError(
            "Unresolved placeholders: " + ", ".join(seen_missing)
        )

    def replacer(match: re.Match[str]) -> str:
        return normalized_map[match.group(0)]

    return PLACEHOLDER_PATTERN.sub(replacer, annotated_markdown)