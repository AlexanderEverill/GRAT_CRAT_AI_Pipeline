"""Loader for drafting ModelOutputs input."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.io import load_json


@dataclass(frozen=True)
class ModelOutputs:
    """Typed quantitative outputs produced by the deterministic model stage."""

    forecasts: dict[str, float]
    risk_metrics: dict[str, float]
    allocation_weights: dict[str, float]
    extra: dict[str, Any] = field(default_factory=dict)


def _require_fields(payload: dict[str, Any], required: tuple[str, ...]) -> None:
    missing = [name for name in required if name not in payload]
    if missing:
        raise ValueError(
            "ModelOutputs missing required fields: " + ", ".join(missing)
        )


def _parse_numeric_map(payload: dict[str, Any], field_name: str) -> dict[str, float]:
    raw = payload.get(field_name)
    if not isinstance(raw, dict) or not raw:
        raise ValueError(
            f"ModelOutputs field '{field_name}' must be a non-empty object"
        )

    parsed: dict[str, float] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(
                f"ModelOutputs field '{field_name}' contains an invalid key"
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                (
                    f"ModelOutputs field '{field_name}.{key}' must be numeric, "
                    f"got {type(value).__name__}"
                )
            )
        parsed[key] = float(value)

    return parsed


def _validate_allocation_weights(weights: dict[str, float]) -> None:
    if any(value < 0.0 or value > 1.0 for value in weights.values()):
        raise ValueError(
            "ModelOutputs field 'allocation_weights' values must be within [0.0, 1.0]"
        )

    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            (
                "ModelOutputs field 'allocation_weights' values must sum to 1.0 "
                f"(found {total:.6f})"
            )
        )


def load_model_outputs(path: str | Path) -> ModelOutputs:
    """Load, validate, and parse quantitative model outputs into a dataclass."""
    payload = load_json(path)
    required_fields = ("forecasts", "risk_metrics", "allocation_weights")
    _require_fields(payload, required_fields)

    forecasts = _parse_numeric_map(payload, "forecasts")
    risk_metrics = _parse_numeric_map(payload, "risk_metrics")
    allocation_weights = _parse_numeric_map(payload, "allocation_weights")
    _validate_allocation_weights(allocation_weights)

    extra = {key: value for key, value in payload.items() if key not in required_fields}
    return ModelOutputs(
        forecasts=forecasts,
        risk_metrics=risk_metrics,
        allocation_weights=allocation_weights,
        extra=extra,
    )
