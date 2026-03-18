from __future__ import annotations

import json
from pathlib import Path

import pytest

from loaders.outline import Outline, load_outline


def test_seed_outline_matches_loader_contract() -> None:
    seed_path = Path(__file__).resolve().parents[1] / "data" / "Outline.json"

    outline = load_outline(seed_path)

    assert isinstance(outline, Outline)
    assert len(outline.sections) >= 1
    assert outline.sections[0].order == 0
    assert outline.sections[0].section_id
    assert outline.sections[0].title
    assert outline.sections[0].content_type in {"narrative", "table", "chart_prose"}


def test_outline_rejects_duplicate_section_ids(tmp_path: Path) -> None:
    payload = {
        "sections": [
            {
                "id": "summary",
                "title": "Executive Summary",
                "content_type": "narrative",
            },
            {
                "id": "summary",
                "title": "Duplicate Summary",
                "content_type": "table",
            },
        ]
    }
    outline_path = tmp_path / "Outline.json"
    outline_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate section id"):
        load_outline(outline_path)
