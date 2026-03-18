from __future__ import annotations

import json
from pathlib import Path

import pytest

from loaders.retrieval_bundle import RetrievalBundle, load_retrieval_bundle


def test_seed_retrieval_bundle_matches_loader_contract() -> None:
    seed_path = Path(__file__).resolve().parents[1] / "data" / "RetrievalBundle.json"

    bundle = load_retrieval_bundle(seed_path)

    assert isinstance(bundle, RetrievalBundle)
    assert bundle.chunks
    assert bundle.chunks[0].source_id
    assert bundle.chunks[0].text
    assert bundle.chunks[0].citation_key in bundle.citation_keys


def test_retrieval_bundle_rejects_unknown_citation_key(tmp_path: Path) -> None:
    payload = {
        "citation_manifest": {
            "citations": [
                {"cite_key": "[S1]"},
            ]
        },
        "chunks": [
            {
                "source_id": "S002",
                "score": 0.8,
                "text": "chunk text",
                "citation_key": "[S2]",
            }
        ],
    }
    bundle_path = tmp_path / "RetrievalBundle.json"
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="not present in citation manifest"):
        load_retrieval_bundle(bundle_path)
