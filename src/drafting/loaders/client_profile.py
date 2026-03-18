"""Loader for drafting ClientProfile input."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.io import load_json


@dataclass(frozen=True)
class ClientProfile:
    """Typed client profile payload consumed by the drafting stage."""

    client_id: str
    risk_tolerance: str
    goals: list[str]
    horizon: int
    extra: dict[str, Any] = field(default_factory=dict)


def _require_fields(payload: dict[str, Any], required: tuple[str, ...]) -> None:
    missing = [name for name in required if name not in payload]
    if missing:
        raise ValueError(
            "ClientProfile missing required fields: " + ", ".join(missing)
        )


def load_client_profile(path: str | Path) -> ClientProfile:
    """Load, validate, and parse ClientProfile JSON into a typed dataclass."""
    payload = load_json(path)
    required_fields = ("client_id", "risk_tolerance", "goals", "horizon")
    _require_fields(payload, required_fields)

    client_id = payload["client_id"]
    risk_tolerance = payload["risk_tolerance"]
    goals = payload["goals"]
    horizon = payload["horizon"]

    if not isinstance(client_id, str) or not client_id.strip():
        raise ValueError("ClientProfile field 'client_id' must be a non-empty string")
    if not isinstance(risk_tolerance, str) or not risk_tolerance.strip():
        raise ValueError(
            "ClientProfile field 'risk_tolerance' must be a non-empty string"
        )
    if not isinstance(goals, list) or not goals or not all(
        isinstance(goal, str) and goal.strip() for goal in goals
    ):
        raise ValueError(
            "ClientProfile field 'goals' must be a non-empty list of strings"
        )
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("ClientProfile field 'horizon' must be a positive integer")

    extra = {
        key: value for key, value in payload.items() if key not in required_fields
    }
    return ClientProfile(
        client_id=client_id,
        risk_tolerance=risk_tolerance,
        goals=goals,
        horizon=horizon,
        extra=extra,
    )
