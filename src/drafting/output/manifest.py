"""Build and write machine-readable draft manifest artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping

from context import bind_numeric_values
from loaders.client_profile import ClientProfile
from loaders.model_outputs import ModelOutputs
from loaders.outline import Outline, OutlineSection
from loaders.retrieval_bundle import RetrievalBundle
from postprocessing.validator import ValidationResult
from utils.token_budget import estimate_tokens


SRC_TAG_PATTERN = re.compile(r"\[SRC-\d+\]")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _normalize_placeholder_token(value: str) -> str:
    token = value.strip()
    if token.startswith("{{") and token.endswith("}}"):
        return token
    return f"{{{{{token}}}}}"


def _extract_expected_placeholders(section: OutlineSection) -> list[str]:
    payload = section.extra.get("expected_placeholders")
    if not isinstance(payload, list):
        return []

    tokens: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        placeholder = item.get("placeholder")
        if isinstance(placeholder, str) and placeholder.strip():
            token = _normalize_placeholder_token(placeholder)
            if token not in tokens:
                tokens.append(token)
    return tokens


def _extract_citation_keys_by_section(
    retrieval_bundle: RetrievalBundle,
    section_ids: set[str],
) -> dict[str, list[str]]:
    keys_by_section: dict[str, set[str]] = {section_id: set() for section_id in section_ids}
    for chunk in retrieval_bundle.chunks:
        section_tags = chunk.extra.get("section_tags")
        if not isinstance(section_tags, list):
            continue
        for tag in section_tags:
            if isinstance(tag, str) and tag in section_ids:
                keys_by_section[tag].add(chunk.citation_key)

    return {
        section_id: sorted(keys)
        for section_id, keys in keys_by_section.items()
        if keys
    }


def _extract_src_tags(markdown: str | None) -> list[str]:
    if not isinstance(markdown, str):
        return []
    tags = sorted(set(SRC_TAG_PATTERN.findall(markdown)))
    return tags


def _coerce_token_map(payload: Mapping[str, Any] | None) -> dict[str, int]:
    if payload is None:
        return {}

    normalized: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            continue
        normalized[key] = value

    if "total_tokens" not in normalized and {
        "input_tokens",
        "output_tokens",
    }.issubset(normalized):
        normalized["total_tokens"] = (
            normalized["input_tokens"] + normalized["output_tokens"]
        )
    return normalized


def _estimate_section_tokens(
    section_prompt: str | None,
    section_markdown: str | None,
) -> dict[str, int]:
    estimated: dict[str, int] = {}
    if isinstance(section_prompt, str) and section_prompt.strip():
        estimated["input_tokens"] = estimate_tokens(section_prompt)
    if isinstance(section_markdown, str) and section_markdown.strip():
        estimated["output_tokens"] = estimate_tokens(section_markdown)

    if "input_tokens" in estimated and "output_tokens" in estimated:
        estimated["total_tokens"] = (
            estimated["input_tokens"] + estimated["output_tokens"]
        )
    return estimated


def _token_usage_payload(
    section_id: str,
    section_prompts: Mapping[str, str] | None,
    section_markdown_map: Mapping[str, str] | None,
    token_usage_by_section: Mapping[str, Mapping[str, int]] | None,
) -> dict[str, Any]:
    provided = _coerce_token_map(
        token_usage_by_section.get(section_id) if token_usage_by_section else None
    )
    if provided:
        return {
            "source": "provided",
            "input_tokens": provided.get("input_tokens"),
            "output_tokens": provided.get("output_tokens"),
            "total_tokens": provided.get("total_tokens"),
        }

    estimated = _estimate_section_tokens(
        section_prompts.get(section_id) if section_prompts else None,
        section_markdown_map.get(section_id) if section_markdown_map else None,
    )
    if estimated:
        return {
            "source": "estimated",
            "input_tokens": estimated.get("input_tokens"),
            "output_tokens": estimated.get("output_tokens"),
            "total_tokens": estimated.get("total_tokens"),
        }

    return {
        "source": "unknown",
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
    }


def build_draft_manifest(
    client_profile: ClientProfile,
    retrieval_bundle: RetrievalBundle,
    model_outputs: ModelOutputs,
    outline: Outline,
    validation_results_by_section: Mapping[str, ValidationResult],
    section_markdown_map: Mapping[str, str] | None = None,
    numeric_substitution_map: Mapping[str, str] | None = None,
    section_prompts: Mapping[str, str] | None = None,
    token_usage_by_section: Mapping[str, Mapping[str, int]] | None = None,
) -> dict[str, Any]:
    """Build a machine-readable manifest summarizing completed draft outputs."""
    section_ids = {section.section_id for section in outline.sections}
    citation_keys_by_section = _extract_citation_keys_by_section(retrieval_bundle, section_ids)
    numeric_map = (
        dict(numeric_substitution_map)
        if numeric_substitution_map is not None
        else bind_numeric_values(model_outputs, outline)
    )

    sections_payload: list[dict[str, Any]] = []
    all_src_tags: set[str] = set()
    all_citation_keys: set[str] = set()
    total_validation_warnings = 0
    token_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    for section in outline.sections:
        section_id = section.section_id
        validation = validation_results_by_section.get(section_id)
        section_markdown = (
            section_markdown_map.get(section_id) if section_markdown_map else None
        )
        src_tags = _extract_src_tags(section_markdown)
        citation_keys = citation_keys_by_section.get(section_id, [])
        expected_placeholders = _extract_expected_placeholders(section)

        numerics_bound = [
            {
                "placeholder": placeholder,
                "bound_value": numeric_map.get(placeholder),
                "is_bound": placeholder in numeric_map,
            }
            for placeholder in expected_placeholders
        ]

        token_usage = _token_usage_payload(
            section_id=section_id,
            section_prompts=section_prompts,
            section_markdown_map=section_markdown_map,
            token_usage_by_section=token_usage_by_section,
        )
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = token_usage.get(key)
            if isinstance(value, int):
                token_totals[key] += value

        warnings: list[str]
        if validation is None:
            warnings = ["No validation result recorded for section"]
        else:
            warnings = list(validation.errors)
        total_validation_warnings += len(warnings)

        written = validation is not None
        if section_markdown_map is not None:
            written = written and isinstance(section_markdown, str) and bool(
                section_markdown.strip()
            )

        validation_payload = (
            {
                "is_valid": validation.is_valid,
                "warnings": warnings,
                "unresolved_placeholders": validation.unresolved_placeholders,
                "dangling_citations": validation.dangling_citations,
                "measured_length": validation.measured_length,
                "min_length": validation.min_length,
                "max_length": validation.max_length,
                "length_unit": validation.length_unit,
            }
            if validation is not None
            else {
                "is_valid": False,
                "warnings": warnings,
                "unresolved_placeholders": [],
                "dangling_citations": [],
                "measured_length": None,
                "min_length": None,
                "max_length": None,
                "length_unit": "words",
            }
        )

        sections_payload.append(
            {
                "section_id": section_id,
                "title": section.title,
                "content_type": section.content_type,
                "written": written,
                "citations_used": {
                    "src_tags": src_tags,
                    "citation_keys": citation_keys,
                },
                "numerics_bound": numerics_bound,
                "validation": validation_payload,
                "token_usage": token_usage,
            }
        )

        all_src_tags.update(src_tags)
        all_citation_keys.update(citation_keys)

    sections_written = sum(1 for section in sections_payload if section["written"])
    placeholder_total = sum(len(section["numerics_bound"]) for section in sections_payload)
    placeholders_bound = sum(
        1
        for section in sections_payload
        for binding in section["numerics_bound"]
        if binding["is_bound"]
    )

    return {
        "manifest_version": "v1",
        "generated_at_utc": _utc_timestamp(),
        "client": {
            "client_id": client_profile.client_id,
            "risk_tolerance": client_profile.risk_tolerance,
            "horizon": client_profile.horizon,
            "goals": client_profile.goals,
        },
        "inputs": {
            "section_count": len(outline.sections),
            "retrieval_chunk_count": len(retrieval_bundle.chunks),
            "retrieval_citation_key_count": len(retrieval_bundle.citation_keys),
            "forecast_metric_count": len(model_outputs.forecasts),
            "risk_metric_count": len(model_outputs.risk_metrics),
            "allocation_weight_count": len(model_outputs.allocation_weights),
        },
        "sections": sections_payload,
        "summary": {
            "sections_written": sections_written,
            "src_tags_used": sorted(all_src_tags),
            "citation_keys_used": sorted(all_citation_keys),
            "numeric_placeholders": {
                "total": placeholder_total,
                "bound": placeholders_bound,
            },
            "validation_warnings": total_validation_warnings,
            "token_usage_totals": token_totals,
        },
    }


def write_draft_manifest(draft_manifest: Mapping[str, Any], output_path: str | Path) -> Path:
    """Write DraftManifest.json payload to disk."""
    if not isinstance(draft_manifest, Mapping):
        raise ValueError("draft_manifest must be a mapping")

    path = Path(output_path)
    if path.suffix.lower() != ".json":
        raise ValueError("output_path must point to a .json file")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(draft_manifest), indent=2) + "\n", encoding="utf-8")
    return path
