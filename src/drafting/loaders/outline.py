"""Loader for drafting Outline input."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.io import load_json


ALLOWED_CONTENT_TYPES = {"narrative", "table", "chart_prose"}


@dataclass(frozen=True)
class OutlineSection:
    """Single ordered section directive for the drafting stage."""

    section_id: str
    title: str
    content_type: str
    order: int
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Outline:
    """Typed outline contract consumed by the drafting stage."""

    sections: list[OutlineSection]
    extra: dict[str, Any] = field(default_factory=dict)


def _normalize_content_type(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def load_outline(path: str | Path) -> Outline:
    """Load, validate, and parse Outline JSON into a typed dataclass."""
    payload = load_json(path)
    sections_payload = payload.get("sections")
    if not isinstance(sections_payload, list) or not sections_payload:
        raise ValueError("Outline field 'sections' must be a non-empty list")

    sections: list[OutlineSection] = []
    seen_ids: set[str] = set()
    required = ("id", "title", "content_type")
    for idx, section in enumerate(sections_payload):
        if not isinstance(section, dict):
            raise ValueError(f"Outline section at index {idx} must be an object")

        missing = [key for key in required if key not in section]
        if missing:
            raise ValueError(
                f"Outline section at index {idx} missing required fields: {', '.join(missing)}"
            )

        section_id = section["id"]
        title = section["title"]
        content_type = section["content_type"]
        if not isinstance(section_id, str) or not section_id.strip():
            raise ValueError(
                f"Outline section at index {idx} field 'id' must be a non-empty string"
            )
        if section_id in seen_ids:
            raise ValueError(f"Outline contains duplicate section id: {section_id}")
        seen_ids.add(section_id)

        if not isinstance(title, str) or not title.strip():
            raise ValueError(
                f"Outline section at index {idx} field 'title' must be a non-empty string"
            )
        if not isinstance(content_type, str) or not content_type.strip():
            raise ValueError(
                f"Outline section at index {idx} field 'content_type' must be a non-empty string"
            )

        normalized_content_type = _normalize_content_type(content_type)
        if normalized_content_type not in ALLOWED_CONTENT_TYPES:
            allowed = ", ".join(sorted(ALLOWED_CONTENT_TYPES))
            raise ValueError(
                (
                    f"Outline section '{section_id}' has unsupported content_type "
                    f"'{content_type}'. Allowed values: {allowed}"
                )
            )

        extra = {
            key: value for key, value in section.items() if key not in required
        }
        sections.append(
            OutlineSection(
                section_id=section_id,
                title=title,
                content_type=normalized_content_type,
                order=idx,
                extra=extra,
            )
        )

    extra_outline = {key: value for key, value in payload.items() if key != "sections"}
    return Outline(sections=sections, extra=extra_outline)
