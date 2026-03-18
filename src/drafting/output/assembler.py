"""Assemble finalized section markdown into a single draft document."""

from __future__ import annotations

import re
from typing import Mapping

from loaders.outline import Outline


SECTION_SEPARATOR = "\n\n---\n\n"


def _slugify_heading(title: str) -> str:
    slug = title.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _build_toc(outline: Outline) -> str:
    lines = ["## Table of Contents"]
    for section in outline.sections:
        anchor = _slugify_heading(section.title)
        lines.append(f"- [{section.title}](#{anchor})")
    return "\n".join(lines)


def assemble_draft(
    section_markdown_map: Mapping[str, str],
    outline: Outline,
) -> str:
    """Concatenate section markdown in outline order with TOC and separators."""
    missing = [
        section.section_id
        for section in outline.sections
        if section.section_id not in section_markdown_map
    ]
    if missing:
        raise ValueError(
            "Missing finalized markdown for section IDs: " + ", ".join(missing)
        )

    parts: list[str] = [_build_toc(outline)]
    for section in outline.sections:
        raw_markdown = section_markdown_map[section.section_id]
        if not isinstance(raw_markdown, str) or not raw_markdown.strip():
            raise ValueError(
                f"Section '{section.section_id}' markdown must be a non-empty string"
            )

        body = raw_markdown.strip()
        heading_line = f"## {section.title}"
        if body.startswith("## "):
            block = body
        else:
            block = f"{heading_line}\n\n{body}"
        parts.append(block)

    return SECTION_SEPARATOR.join(parts).rstrip() + "\n"