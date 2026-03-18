from __future__ import annotations

import json
from pathlib import Path

import pytest

from loaders.model_outputs import ModelOutputs, load_model_outputs


def test_seed_model_outputs_matches_loader_contract() -> None:
    seed_path = Path(__file__).resolve().parents[1] / "data" / "ModelOutputs.json"

    outputs = load_model_outputs(seed_path)

    assert isinstance(outputs, ModelOutputs)
    assert outputs.forecasts
    assert outputs.risk_metrics
    assert outputs.allocation_weights
    assert abs(sum(outputs.allocation_weights.values()) - 1.0) < 1e-9
    assert "comparison" in outputs.extra


def test_model_outputs_rejects_non_numeric_value(tmp_path: Path) -> None:
    payload = {
        "forecasts": {"net_wealth": 1000000.0},
        "risk_metrics": {"drawdown": "high"},
        "allocation_weights": {"grat": 0.5, "crat": 0.5},
    }
    model_outputs_path = tmp_path / "ModelOutputs.json"
    model_outputs_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="must be numeric"):
        load_model_outputs(model_outputs_path)


def test_model_outputs_rejects_weights_not_summing_to_one(tmp_path: Path) -> None:
    payload = {
        "forecasts": {"net_wealth": 1000000.0},
        "risk_metrics": {"volatility": 0.2},
        "allocation_weights": {"grat": 0.7, "crat": 0.4},
    }
    model_outputs_path = tmp_path / "ModelOutputs.json"
    model_outputs_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="must sum to 1.0"):
        load_model_outputs(model_outputs_path)
