"""Loader for drafting RetrievalBundle input."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.io import load_json


@dataclass(frozen=True)
class RetrievalChunk:
    """Single retrieved chunk used by drafting prompts."""

    source_id: str
    score: float
    text: str
    citation_key: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalBundle:
    """Typed retrieval payload consumed by the drafting stage."""

    chunks: list[RetrievalChunk]
    citation_keys: set[str]
    extra: dict[str, Any] = field(default_factory=dict)


def _parse_manifest_keys(manifest_payload: dict[str, Any]) -> set[str]:
    if "citation_keys" in manifest_payload:
        raw_keys = manifest_payload["citation_keys"]
        if not isinstance(raw_keys, list) or not all(
            isinstance(key, str) and key.strip() for key in raw_keys
        ):
            raise ValueError(
                "RetrievalBundle citation manifest field 'citation_keys' must be a list of strings"
            )
        return set(raw_keys)

    citations = manifest_payload.get("citations")
    if not isinstance(citations, list):
        raise ValueError(
            "RetrievalBundle citation manifest must include 'citations' or 'citation_keys'"
        )

    keys: set[str] = set()
    for idx, citation in enumerate(citations):
        if not isinstance(citation, dict):
            raise ValueError(
                f"RetrievalBundle citation manifest entry at index {idx} must be an object"
            )
        cite_key = citation.get("cite_key")
        if not isinstance(cite_key, str) or not cite_key.strip():
            raise ValueError(
                f"RetrievalBundle citation manifest entry at index {idx} missing valid 'cite_key'"
            )
        keys.add(cite_key)

    return keys


def _resolve_manifest_keys(
    bundle_payload: dict[str, Any],
    manifest_path: str | Path | None,
) -> set[str]:
    if manifest_path is not None:
        manifest_payload = load_json(manifest_path)
        return _parse_manifest_keys(manifest_payload)

    embedded_manifest = bundle_payload.get("citation_manifest")
    if not isinstance(embedded_manifest, dict):
        raise ValueError(
            "RetrievalBundle missing 'citation_manifest'; provide embedded manifest or manifest_path"
        )
    return _parse_manifest_keys(embedded_manifest)


def load_retrieval_bundle(
    path: str | Path,
    manifest_path: str | Path | None = None,
) -> RetrievalBundle:
    """Load RetrievalBundle JSON, validate chunks, and return typed payload."""
    payload = load_json(path)
    citation_keys = _resolve_manifest_keys(payload, manifest_path)

    chunks_payload = payload.get("chunks")
    if not isinstance(chunks_payload, list):
        raise ValueError("RetrievalBundle field 'chunks' must be a list")

    chunks: list[RetrievalChunk] = []
    required = ("source_id", "score", "text", "citation_key")
    for idx, chunk in enumerate(chunks_payload):
        if not isinstance(chunk, dict):
            raise ValueError(f"RetrievalBundle chunk at index {idx} must be an object")

        missing = [key for key in required if key not in chunk]
        if missing:
            raise ValueError(
                f"RetrievalBundle chunk at index {idx} missing required fields: {', '.join(missing)}"
            )

        source_id = chunk["source_id"]
        score = chunk["score"]
        text = chunk["text"]
        citation_key = chunk["citation_key"]

        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError(
                f"RetrievalBundle chunk at index {idx} field 'source_id' must be a non-empty string"
            )
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError(
                f"RetrievalBundle chunk at index {idx} field 'score' must be numeric"
            )
        if not isinstance(text, str) or not text.strip():
            raise ValueError(
                f"RetrievalBundle chunk at index {idx} field 'text' must be a non-empty string"
            )
        if not isinstance(citation_key, str) or not citation_key.strip():
            raise ValueError(
                f"RetrievalBundle chunk at index {idx} field 'citation_key' must be a non-empty string"
            )
        if citation_key not in citation_keys:
            raise ValueError(
                f"RetrievalBundle chunk at index {idx} citation_key '{citation_key}' not present in citation manifest"
            )

        extra = {key: value for key, value in chunk.items() if key not in required}
        chunks.append(
            RetrievalChunk(
                source_id=source_id,
                score=float(score),
                text=text,
                citation_key=citation_key,
                extra=extra,
            )
        )

    extra_bundle = {
        key: value
        for key, value in payload.items()
        if key not in {"chunks", "citation_manifest"}
    }
    return RetrievalBundle(chunks=chunks, citation_keys=citation_keys, extra=extra_bundle)
