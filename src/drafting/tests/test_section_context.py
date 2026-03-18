from __future__ import annotations

import json
from pathlib import Path

import pytest

from context.section_context import GENERAL_BUCKET_ID, build_section_context
from loaders.outline import load_outline
from loaders.retrieval_bundle import load_retrieval_bundle


def test_build_section_context_maps_chunks_to_section_ids() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    outline = load_outline(base_dir / "data" / "Outline.json")
    retrieval_bundle = load_retrieval_bundle(base_dir / "data" / "RetrievalBundle.json")

    section_context = build_section_context(outline, retrieval_bundle)

    assert "grat_analysis" in section_context
    assert "comparative_analysis" in section_context
    assert GENERAL_BUCKET_ID in section_context
    assert len(section_context["grat_analysis"]) >= 1
    assert len(section_context["comparative_analysis"]) >= 1


def test_build_section_context_routes_unknown_tags_to_general(tmp_path: Path) -> None:
    outline_payload = {
        "sections": [
            {
                "id": "executive_summary",
                "title": "Executive Summary",
                "content_type": "narrative",
            }
        ]
    }
    retrieval_payload = {
        "citation_manifest": {"citations": [{"cite_key": "[S1]"}]},
        "chunks": [
            {
                "source_id": "S001",
                "score": 0.75,
                "text": "Unmapped chunk",
                "citation_key": "[S1]",
                "section_tags": ["nonexistent_section"],
            }
        ],
    }

    outline_path = tmp_path / "Outline.json"
    bundle_path = tmp_path / "RetrievalBundle.json"
    outline_path.write_text(json.dumps(outline_payload), encoding="utf-8")
    bundle_path.write_text(json.dumps(retrieval_payload), encoding="utf-8")

    outline = load_outline(outline_path)
    retrieval_bundle = load_retrieval_bundle(bundle_path)

    section_context = build_section_context(outline, retrieval_bundle)

    assert len(section_context["executive_summary"]) == 0
    assert len(section_context[GENERAL_BUCKET_ID]) == 1


def test_build_section_context_rejects_invalid_section_tags_type(tmp_path: Path) -> None:
    outline_payload = {
        "sections": [
            {
                "id": "executive_summary",
                "title": "Executive Summary",
                "content_type": "narrative",
            }
        ]
    }
    retrieval_payload = {
        "citation_manifest": {"citations": [{"cite_key": "[S1]"}]},
        "chunks": [
            {
                "source_id": "S001",
                "score": 0.75,
                "text": "Invalid tags chunk",
                "citation_key": "[S1]",
                "section_tags": "executive_summary",
            }
        ],
    }

    outline_path = tmp_path / "Outline.json"
    bundle_path = tmp_path / "RetrievalBundle.json"
    outline_path.write_text(json.dumps(outline_payload), encoding="utf-8")
    bundle_path.write_text(json.dumps(retrieval_payload), encoding="utf-8")

    outline = load_outline(outline_path)
    retrieval_bundle = load_retrieval_bundle(bundle_path)

    with pytest.raises(ValueError, match="section_tags"):
        build_section_context(outline, retrieval_bundle)
