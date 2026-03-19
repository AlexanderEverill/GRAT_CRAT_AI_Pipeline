from __future__ import annotations

from pathlib import Path

import pytest

from loaders.outline import load_outline
from output.assembler import assemble_draft


def test_assemble_draft_in_outline_order_with_toc_and_separators() -> None:
    outline = load_outline(Path(__file__).resolve().parents[1] / "data" / "Outline.json")

    section_map = {
        section.section_id: f"Content for {section.section_id}."
        for section in outline.sections
    }

    assembled = assemble_draft(section_map, outline)

    assert assembled.startswith("## Table of Contents")
    assert "- [Executive Summary](#executive-summary)" in assembled
    assert "\n\n---\n\n## Executive Summary\n\nContent for executive_summary." in assembled
    assert "\n\n---\n\n## GRAT Analysis\n\nContent for grat_analysis." in assembled
    assert assembled.endswith("\n")


def test_assemble_draft_preserves_existing_section_heading() -> None:
    outline = load_outline(Path(__file__).resolve().parents[1] / "data" / "Outline.json")
    first_section = outline.sections[0]

    section_map = {
        section.section_id: "## Existing Heading\n\nExisting content."
        if section.section_id == first_section.section_id
        else "Plain body."
        for section in outline.sections
    }

    assembled = assemble_draft(section_map, outline)

    assert "## Existing Heading\n\nExisting content." in assembled


def test_assemble_draft_raises_for_missing_section_markdown() -> None:
    outline = load_outline(Path(__file__).resolve().parents[1] / "data" / "Outline.json")

    section_map = {
        outline.sections[0].section_id: "Only one section present."
    }

    with pytest.raises(ValueError, match="Missing finalized markdown"):
        assemble_draft(section_map, outline)
