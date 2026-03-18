"""Numeric placeholder binding for drafting section contexts."""

from __future__ import annotations

import re

from loaders.model_outputs import ModelOutputs
from loaders.outline import Outline


PLACEHOLDER_PATTERN = re.compile(r"^\{\{[a-zA-Z0-9_]+\}\}$")
FORMAT_CURRENCY = "currency"
FORMAT_PERCENT = "percent"
FORMAT_BPS = "bps"
FORMAT_NUMBER = "number"

_FORMAT_ALIASES = {
    "currency": FORMAT_CURRENCY,
    "currency_usd": FORMAT_CURRENCY,
    "usd": FORMAT_CURRENCY,
    "percent": FORMAT_PERCENT,
    "percentage": FORMAT_PERCENT,
    "pct": FORMAT_PERCENT,
    "bps": FORMAT_BPS,
    "bp": FORMAT_BPS,
    "basis_points": FORMAT_BPS,
    "number": FORMAT_NUMBER,
    "raw": FORMAT_NUMBER,
}


def _normalize_format(format_name: str, placeholder: str) -> str:
    normalized = _FORMAT_ALIASES.get(format_name.strip().lower())
    if normalized is None:
        supported = ", ".join(sorted(_FORMAT_ALIASES.keys()))
        raise ValueError(
            f"Unsupported format '{format_name}' for placeholder {placeholder}. Supported: {supported}"
        )
    return normalized


def _format_number(value: float, format_name: str) -> str:
    if format_name == FORMAT_CURRENCY:
        sign = "-" if value < 0 else ""
        return f"{sign}${abs(value):,.2f}"
    if format_name == FORMAT_PERCENT:
        return f"{value * 100:.2f}%"
    if format_name == FORMAT_BPS:
        return f"{value * 10000:.0f} bps"

    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return f"{int(rounded):,}"
    return f"{value:,.2f}"


def _infer_format(model_key: str) -> str:
    if model_key.endswith("_usd"):
        return FORMAT_CURRENCY
    if model_key.endswith("_rate") or model_key.endswith("_weight"):
        return FORMAT_PERCENT
    if model_key.endswith("_bps"):
        return FORMAT_BPS
    return FORMAT_NUMBER


def _extract_model_key(placeholder: str) -> str:
    if not PLACEHOLDER_PATTERN.match(placeholder):
        raise ValueError(
            "Placeholder must match '{{placeholder_name}}' pattern: "
            f"{placeholder}"
        )
    return placeholder[2:-2]


def _lookup_source_map(model_outputs: ModelOutputs) -> dict[str, dict[str, float]]:
    return {
        "forecasts": model_outputs.forecasts,
        "risk_metrics": model_outputs.risk_metrics,
        "allocation_weights": model_outputs.allocation_weights,
    }


def _resolve_value(
    model_key: str,
    source: str | None,
    source_map: dict[str, dict[str, float]],
    placeholder: str,
) -> float:
    if source is not None:
        if source not in source_map:
            available = ", ".join(sorted(source_map.keys()))
            raise ValueError(
                f"Placeholder {placeholder} has unknown source '{source}'. Available: {available}"
            )
        if model_key not in source_map[source]:
            raise ValueError(
                f"Placeholder {placeholder} references missing key '{model_key}' in source '{source}'"
            )
        return source_map[source][model_key]

    matching_sources = [
        source_name
        for source_name, values in source_map.items()
        if model_key in values
    ]
    if not matching_sources:
        raise ValueError(
            f"Placeholder {placeholder} references unknown key '{model_key}' in ModelOutputs"
        )
    if len(matching_sources) > 1:
        raise ValueError(
            (
                f"Placeholder {placeholder} key '{model_key}' is ambiguous across sources "
                f"{matching_sources}; specify 'source' explicitly"
            )
        )
    return source_map[matching_sources[0]][model_key]


def bind_numeric_values(model_outputs: ModelOutputs, outline: Outline) -> dict[str, str]:
    """Resolve outline numeric placeholders into a flat substitution map."""
    source_map = _lookup_source_map(model_outputs)
    substitutions: dict[str, str] = {}

    for section in outline.sections:
        specs = section.extra.get("expected_placeholders", [])
        if specs is None:
            continue
        if not isinstance(specs, list):
            raise ValueError(
                f"Outline section '{section.section_id}' field 'expected_placeholders' must be a list"
            )

        for spec in specs:
            if isinstance(spec, str):
                placeholder = spec
                model_key = _extract_model_key(placeholder)
                source = None
                format_name = _infer_format(model_key)
            elif isinstance(spec, dict):
                placeholder_raw = spec.get("placeholder")
                if not isinstance(placeholder_raw, str) or not placeholder_raw.strip():
                    raise ValueError(
                        f"Outline section '{section.section_id}' has placeholder spec missing 'placeholder'"
                    )
                placeholder = placeholder_raw.strip()
                default_model_key = _extract_model_key(placeholder)

                model_key_raw = spec.get("model_key", default_model_key)
                if not isinstance(model_key_raw, str) or not model_key_raw.strip():
                    raise ValueError(
                        f"Outline section '{section.section_id}' placeholder {placeholder} has invalid 'model_key'"
                    )
                model_key = model_key_raw.strip()

                source_raw = spec.get("source")
                if source_raw is not None and (
                    not isinstance(source_raw, str) or not source_raw.strip()
                ):
                    raise ValueError(
                        f"Outline section '{section.section_id}' placeholder {placeholder} has invalid 'source'"
                    )
                source = source_raw.strip() if isinstance(source_raw, str) else None

                format_raw = spec.get("format", _infer_format(model_key))
                if not isinstance(format_raw, str) or not format_raw.strip():
                    raise ValueError(
                        f"Outline section '{section.section_id}' placeholder {placeholder} has invalid 'format'"
                    )
                format_name = _normalize_format(format_raw, placeholder)
            else:
                raise ValueError(
                    f"Outline section '{section.section_id}' has invalid placeholder spec type"
                )

            value = _resolve_value(model_key, source, source_map, placeholder)
            formatted = _format_number(value, format_name)

            existing = substitutions.get(placeholder)
            if existing is not None and existing != formatted:
                raise ValueError(
                    (
                        f"Placeholder {placeholder} resolved to conflicting values "
                        f"'{existing}' and '{formatted}'"
                    )
                )
            substitutions[placeholder] = formatted

    return substitutions