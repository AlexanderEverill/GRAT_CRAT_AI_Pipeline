from __future__ import annotations

import json
from pathlib import Path

import pytest

from context.numeric_binder import bind_numeric_values
from loaders.model_outputs import load_model_outputs
from loaders.outline import load_outline


def test_bind_numeric_values_from_seed_contract() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    model_outputs = load_model_outputs(base_dir / "data" / "ModelOutputs.json")
    outline = load_outline(base_dir / "data" / "Outline.json")

    substitution_map = bind_numeric_values(model_outputs, outline)

    assert substitution_map["{{estate_tax_rate}}"] == "40.00%"
    assert substitution_map["{{section_7520_rate_bps}}"] == "196 bps"
    assert substitution_map["{{taxable_estate_after_grat_usd}}"] == "$12,294,873.22"
    assert substitution_map["{{taxable_estate_after_crat_usd}}"] == "$8,379,277.36"
    assert substitution_map["{{grat_allocation_weight}}"] == "60.00%"
    assert substitution_map["{{crat_allocation_weight}}"] == "40.00%"


def test_bind_numeric_values_rejects_unknown_model_key(tmp_path: Path) -> None:
    model_payload = {
        "forecasts": {"projected_return_5yr": 0.12},
        "risk_metrics": {"volatility": 0.22},
        "allocation_weights": {"equity": 0.6, "fixed_income": 0.4},
    }
    outline_payload = {
        "sections": [
            {
                "id": "summary",
                "title": "Summary",
                "content_type": "narrative",
                "expected_placeholders": [
                    {
                        "placeholder": "{{missing_key}}",
                        "model_key": "missing_key",
                        "source": "forecasts",
                        "format": "percent",
                    }
                ],
            }
        ]
    }

    model_path = tmp_path / "ModelOutputs.json"
    outline_path = tmp_path / "Outline.json"
    model_path.write_text(json.dumps(model_payload), encoding="utf-8")
    outline_path.write_text(json.dumps(outline_payload), encoding="utf-8")

    model_outputs = load_model_outputs(model_path)
    outline = load_outline(outline_path)

    with pytest.raises(ValueError, match="missing key"):
        bind_numeric_values(model_outputs, outline)
