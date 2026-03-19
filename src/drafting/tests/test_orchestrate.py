from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm.client import DraftingError
from pipeline.orchestrate import (
    DraftingInputPaths,
    DraftingPipelineConfig,
    drafting_pipeline,
)


def test_drafting_pipeline_writes_draft_md_with_override_client(tmp_path: Path) -> None:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    output_path = tmp_path / "Draft.md"

    input_paths = DraftingInputPaths(
        client_profile_path=data_dir / "ClientProfile.json",
        retrieval_bundle_path=data_dir / "RetrievalBundle.json",
        model_outputs_path=data_dir / "ModelOutputs.json",
        outline_path=data_dir / "Outline.json",
    )

    def fake_llm_client(_: str) -> str:
        return "Generated section text with source support [S002]."

    config = DraftingPipelineConfig(
        output_path=output_path,
        llm_client_override=fake_llm_client,
        parallel_sections=False,
        fail_on_validation_error=False,
    )

    written_path = drafting_pipeline(input_paths, config)

    assert written_path == output_path
    assert output_path.exists()
    manifest_path = tmp_path / "DraftManifest.json"
    assert manifest_path.exists()

    content = output_path.read_text(encoding="utf-8")
    assert "## Table of Contents" in content
    assert "## Global References" in content
    assert "## Generation Metadata" in content
    assert "26 CFR" in content or "law.cornell.edu" in content

    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["manifest_version"] == "v1"
    assert manifest_payload["summary"]["sections_written"] == len(
        manifest_payload["sections"]
    )
    assert "token_usage_totals" in manifest_payload["summary"]


def test_drafting_pipeline_requires_model_config_without_override() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    input_paths = DraftingInputPaths(
        client_profile_path=data_dir / "ClientProfile.json",
        retrieval_bundle_path=data_dir / "RetrievalBundle.json",
        model_outputs_path=data_dir / "ModelOutputs.json",
        outline_path=data_dir / "Outline.json",
    )

    with pytest.raises(ValueError, match="model_config is required"):
        drafting_pipeline(input_paths, DraftingPipelineConfig())


def test_drafting_pipeline_wraps_postprocessing_failures(tmp_path: Path) -> None:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    input_paths = DraftingInputPaths(
        client_profile_path=data_dir / "ClientProfile.json",
        retrieval_bundle_path=data_dir / "RetrievalBundle.json",
        model_outputs_path=data_dir / "ModelOutputs.json",
        outline_path=data_dir / "Outline.json",
    )

    def fake_llm_client(_: str) -> str:
        return "Invalid citation that cannot be resolved [S999]."

    config = DraftingPipelineConfig(
        output_path=tmp_path / "Draft.md",
        llm_client_override=fake_llm_client,
    )

    with pytest.raises(DraftingError, match="Postprocessing failed"):
        drafting_pipeline(input_paths, config)
