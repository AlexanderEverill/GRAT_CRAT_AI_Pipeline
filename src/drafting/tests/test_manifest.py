from __future__ import annotations

import json
from pathlib import Path

from loaders.client_profile import ClientProfile
from loaders.model_outputs import ModelOutputs
from loaders.outline import Outline, OutlineSection
from loaders.retrieval_bundle import RetrievalBundle, RetrievalChunk
from output.manifest import build_draft_manifest, write_draft_manifest
from postprocessing.validator import ValidationResult


def test_build_draft_manifest_includes_sections_citations_numerics_and_tokens() -> None:
    client_profile = ClientProfile(
        client_id="client-1",
        risk_tolerance="moderate",
        goals=["preserve wealth", "support charity"],
        horizon=15,
    )
    retrieval_bundle = RetrievalBundle(
        chunks=[
            RetrievalChunk(
                source_id="S001",
                score=0.91,
                text="Relevant support.",
                citation_key="[S1]",
                extra={"section_tags": ["executive_summary"]},
            )
        ],
        citation_keys={"[S1]"},
    )
    model_outputs = ModelOutputs(
        forecasts={"taxable_estate_after_grat_usd": 12000000.0},
        risk_metrics={"estate_tax_rate": 0.4},
        allocation_weights={"grat": 0.6, "crat": 0.4},
    )
    outline = Outline(
        sections=[
            OutlineSection(
                section_id="executive_summary",
                title="Executive Summary",
                content_type="narrative",
                order=0,
                extra={
                    "expected_placeholders": [
                        {"placeholder": "{{estate_tax_rate}}"},
                        {"placeholder": "{{taxable_estate_after_grat_usd}}"},
                    ]
                },
            )
        ]
    )
    validations = {
        "executive_summary": ValidationResult(
            is_valid=False,
            errors=["Section length below minimum bound: 12 words < 100"],
            measured_length=12,
            min_length=100,
            max_length=None,
            length_unit="words",
        )
    }
    section_markdown_map = {
        "executive_summary": (
            "Summary text with support [S001].\n\n"
            "### References\n"
            "- [S001] Source Author. Source Title. (2026).\n"
        )
    }
    section_prompts = {"executive_summary": "Prompt with context and instructions."}

    manifest = build_draft_manifest(
        client_profile=client_profile,
        retrieval_bundle=retrieval_bundle,
        model_outputs=model_outputs,
        outline=outline,
        validation_results_by_section=validations,
        section_markdown_map=section_markdown_map,
        section_prompts=section_prompts,
    )

    assert manifest["client"]["client_id"] == "client-1"
    assert manifest["summary"]["sections_written"] == 1
    assert manifest["summary"]["validation_warnings"] == 1
    assert "[S001]" in manifest["summary"]["src_tags_used"]
    assert "[S1]" in manifest["summary"]["citation_keys_used"]

    section_payload = manifest["sections"][0]
    assert section_payload["written"] is True
    assert section_payload["citations_used"]["src_tags"] == ["[S001]"]
    assert section_payload["citations_used"]["citation_keys"] == ["[S1]"]
    assert section_payload["validation"]["warnings"]
    assert section_payload["token_usage"]["source"] == "estimated"
    assert section_payload["token_usage"]["total_tokens"] is not None
    assert section_payload["numerics_bound"][0]["is_bound"] is True


def test_write_draft_manifest_writes_json_payload(tmp_path: Path) -> None:
    payload = {
        "manifest_version": "v1",
        "sections": [],
        "summary": {"sections_written": 0},
    }
    output_path = tmp_path / "DraftManifest.json"

    written_path = write_draft_manifest(payload, output_path)

    assert written_path == output_path
    assert output_path.exists()
    on_disk = json.loads(output_path.read_text(encoding="utf-8"))
    assert on_disk == payload
