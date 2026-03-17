"""
Integration and end-to-end tests for deterministic trust modeling layer.

These tests follow the format of existing retrieval tests, focusing on:
- File I/O and artifact generation
- End-to-end pipeline execution
- Output validation and schema compliance
- Integration with client intake data
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.model.engine import run_deterministic_model
from src.model.io import (
    load_client_profile,
    extract_client_input,
    create_default_assumptions,
    write_model_output,
)
from src.model.grat import calculate_grat
from src.model.crat import calculate_crat
from src.model.compare import calculate_comparison


class TestClientProfileLoading:
    """Test loading and validating client profile."""

    def test_load_valid_client_profile(self):
        """Test loading the actual client profile from artifacts."""
        profile = load_client_profile()
        
        assert profile is not None
        assert "client_demographics" in profile
        assert "liquidity_event" in profile
        assert "estate_tax_context_2015" in profile
        assert profile["client_demographics"]["age"] == 62
        assert profile["client_demographics"]["marital_status"] == "Married"

    def test_client_profile_has_required_fields(self):
        """Test that client profile contains all required fields."""
        profile = load_client_profile()
        
        # Demographics
        assert profile["client_demographics"]["age"] is not None
        assert profile["client_demographics"]["marital_status"] is not None
        
        # Liquidity event
        assert profile["liquidity_event"]["gross_proceeds_usd"] == 16000000
        
        # Estate tax context
        estate_context = profile["estate_tax_context_2015"]
        assert estate_context["individual_exemption_usd"] == 5430000
        assert estate_context["married_exemption_usd"] == 10860000
        assert estate_context["top_estate_tax_rate"] == 0.4


class TestInputExtraction:
    """Test extracting and validating client input."""

    def test_extract_client_input_from_profile(self):
        """Test extracting ClientInput from loaded profile."""
        profile = load_client_profile()
        client = extract_client_input(profile)
        
        assert client.age == 62
        assert client.marital_status == "Married"
        assert client.liquidity_event_amount_usd == 16000000.0
        assert client.estate_tax_rate == 0.4

    def test_client_input_is_immutable(self):
        """Test that ClientInput is frozen and cannot be modified."""
        profile = load_client_profile()
        client = extract_client_input(profile)
        
        # Attempting to modify should raise an error
        with pytest.raises(Exception):  # FrozenInstanceError
            client.age = 65


class TestModelAssumptions:
    """Test creating and validating model assumptions."""

    def test_default_assumptions_created(self):
        """Test creating default assumptions."""
        assumptions = create_default_assumptions(section_7520_rate=0.042)
        
        assert assumptions.section_7520_rate == 0.042
        assert assumptions.grat_growth_rate == 0.05
        assert assumptions.grat_term_years == 10
        assert assumptions.crat_payout_rate == 0.05
        assert assumptions.crat_growth_rate == 0.05
        assert assumptions.crat_term_years == 20

    def test_assumptions_with_custom_rate(self):
        """Test creating assumptions with custom Section 7520 rate."""
        rate = 0.035
        assumptions = create_default_assumptions(section_7520_rate=rate)
        
        assert assumptions.section_7520_rate == rate
        assert assumptions.grat_growth_rate == 0.05  # Still default


class TestModelOutputFile:
    """Test writing and reading model output files."""

    def test_write_model_output(self):
        """Test writing model output to JSON file."""
        output_data = {
            "model_version": "1.0",
            "grat": {"estate_tax_saved_usd": 401128.31},
            "crat": {"estate_tax_saved_usd": 6400000.0},
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Monkey-patch the output directory
            from src.model import io as io_module
            original_base = io_module.BASE_DIR
            
            try:
                # Create temp structure
                temp_path = Path(tmpdir)
                model_out_dir = temp_path / "pipeline_artifacts" / "model_outputs"
                model_out_dir.mkdir(parents=True, exist_ok=True)
                
                io_module.BASE_DIR = temp_path
                output_path = io_module.write_model_output(output_data)
                
                # Verify file exists and is valid JSON
                assert output_path.exists()
                
                with open(output_path) as f:
                    written_data = json.load(f)
                
                assert written_data["model_version"] == "1.0"
                assert written_data["grat"]["estate_tax_saved_usd"] == 401128.31
            
            finally:
                io_module.BASE_DIR = original_base

    def test_model_output_json_format(self):
        """Test that model output JSON is properly formatted."""
        # Load actual model output
        output_path = Path(
            "pipeline_artifacts/model_outputs/TrustComparison_v1.json"
        )
        
        if output_path.exists():
            with open(output_path) as f:
                data = json.load(f)
            
            # Verify structure
            assert "model_version" in data
            assert "inputs" in data
            assert "assumptions" in data
            assert "grat" in data
            assert "crat" in data
            assert "comparison" in data
            
            # Verify GRAT fields
            assert "annuity_payment_annual_usd" in data["grat"]
            assert "projected_remainder_to_children_usd" in data["grat"]
            assert "estate_tax_saved_usd" in data["grat"]
            
            # Verify CRAT fields
            assert "annual_annuity_usd" in data["crat"]
            assert "remainder_to_charity_usd" in data["crat"]
            assert "estate_tax_saved_usd" in data["crat"]
            
            # Verify comparison fields
            assert "estate_tax_saving_difference_usd" in data["comparison"]
            assert "wealth_to_children_difference_usd" in data["comparison"]


class TestEndToEndModelRun:
    """Test complete deterministic model execution."""

    def test_run_deterministic_model_succeeds(self):
        """Test running the complete deterministic model."""
        output_path = run_deterministic_model()
        
        assert output_path is not None
        assert output_path.exists()
        assert output_path.name == "TrustComparison_v1.json"

    def test_model_output_contains_all_scenarios(self):
        """Test that model output contains both GRAT and CRAT scenarios."""
        output_path = run_deterministic_model()
        
        with open(output_path) as f:
            data = json.load(f)
        
        # GRAT scenario
        assert data["grat"]["trust_corpus_usd"] == 16000000.0
        assert data["grat"]["annuity_payment_annual_usd"] > 0
        assert data["grat"]["projected_remainder_to_children_usd"] > 0
        
        # CRAT scenario
        assert data["crat"]["trust_corpus_usd"] == 16000000.0
        assert data["crat"]["annual_annuity_usd"] > 0
        assert data["crat"]["remainder_to_charity_usd"] > 0

    def test_model_output_numerical_relationships(self):
        """Test logical relationships between numeric values."""
        output_path = run_deterministic_model()
        
        with open(output_path) as f:
            data = json.load(f)
        
        # GRAT: annuities paid should equal individual × years
        grat_annuities_computed = (
            data["grat"]["annuity_payment_annual_usd"] 
            * data["grat"]["term_years"]
        )
        assert abs(
            grat_annuities_computed - data["grat"]["total_annuity_paid_usd"]
        ) < 1  # Within 1 cent due to rounding
        
        # CRAT: annuities paid should equal individual × years
        crat_annuities_computed = (
            data["crat"]["annual_annuity_usd"] 
            * data["crat"]["payout_rate"] == 0  # Wait, this formula is wrong
        )
        # Actually check: annual_annuity should be corpus × payout_rate
        expected_annual = data["crat"]["trust_corpus_usd"] * data["crat"]["payout_rate"]
        assert abs(data["crat"]["annual_annuity_usd"] - expected_annual) < 1
        
        # Tax saved should be positive
        assert data["grat"]["estate_tax_saved_usd"] > 0
        assert data["crat"]["estate_tax_saved_usd"] > 0


class TestScenarioComparison:
    """Test comparison between GRAT and CRAT."""

    def test_comparison_shows_tax_difference(self):
        """Test that comparison captures tax saving differential."""
        output_path = run_deterministic_model()
        
        with open(output_path) as f:
            data = json.load(f)
        
        grat_tax = data["grat"]["estate_tax_saved_usd"]
        crat_tax = data["crat"]["estate_tax_saved_usd"]
        difference = data["comparison"]["estate_tax_saving_difference_usd"]
        
        assert abs(difference - (grat_tax - crat_tax)) < 1

    def test_comparison_shows_wealth_transfer_difference(self):
        """Test that comparison shows wealth transfer to children."""
        output_path = run_deterministic_model()
        
        with open(output_path) as f:
            data = json.load(f)
        
        grat_wealth = data["comparison"]["wealth_to_children_grat_usd"]
        crat_wealth = data["comparison"]["wealth_to_children_crat_usd"]
        difference = data["comparison"]["wealth_to_children_difference_usd"]
        
        # GRAT should have wealth to children, CRAT should not
        assert grat_wealth > 0
        assert crat_wealth == 0
        assert difference == grat_wealth

    def test_comparison_shows_charitable_difference(self):
        """Test that comparison shows charitable component."""
        output_path = run_deterministic_model()
        
        with open(output_path) as f:
            data = json.load(f)
        
        grat_charity = data["comparison"]["charitable_component_grat_usd"]
        crat_charity = data["comparison"]["charitable_component_crat_usd"]
        difference = data["comparison"]["charitable_component_difference_usd"]
        
        # GRAT should have no charitable component, CRAT should
        assert grat_charity == 0
        assert crat_charity > 0
        assert difference == crat_charity


class TestDeterminism:
    """Test that model is deterministic (same input = same output)."""

    def test_multiple_runs_produce_identical_results(self):
        """Test that running model twice produces identical results."""
        output_path_1 = run_deterministic_model(section_7520_rate=0.042)
        output_path_2 = run_deterministic_model(section_7520_rate=0.042)
        
        with open(output_path_1) as f:
            data_1 = json.load(f)
        
        with open(output_path_2) as f:
            data_2 = json.load(f)
        
        # Compare key numeric values (excluding timestamp which changes)
        assert data_1["grat"]["annuity_payment_annual_usd"] == \
               data_2["grat"]["annuity_payment_annual_usd"]
        assert data_1["crat"]["annual_annuity_usd"] == \
               data_2["crat"]["annual_annuity_usd"]
        assert data_1["comparison"]["estate_tax_saving_difference_usd"] == \
               data_2["comparison"]["estate_tax_saving_difference_usd"]

    def test_different_rates_produce_different_results(self):
        """Test that different Section 7520 rates produce different results."""
        # Run with low rate and capture data
        output_path_low = run_deterministic_model(section_7520_rate=0.035)
        with open(output_path_low) as f:
            data_low = json.load(f)
        
        # Run with high rate and capture data
        output_path_high = run_deterministic_model(section_7520_rate=0.050)
        with open(output_path_high) as f:
            data_high = json.load(f)
        
        # Annuity payment should be different (higher rate = higher annuity payment)
        assert data_low["grat"]["annuity_payment_annual_usd"] < \
               data_high["grat"]["annuity_payment_annual_usd"]
        
        # Verify the rates are indeed different
        assert data_low["assumptions"]["section_7520_rate"] == 0.035
        assert data_high["assumptions"]["section_7520_rate"] == 0.050


class TestDataRounding:
    """Test that all monetary values are properly rounded."""

    def test_all_monetary_values_rounded_to_cents(self):
        """Test that all USD values have exactly 2 decimal places."""
        output_path = run_deterministic_model()
        
        with open(output_path) as f:
            data = json.load(f)
        
        def check_rounding(obj, path=""):
            """Recursively check all numeric values for proper rounding."""
            if isinstance(obj, dict):
                for key, value in obj.items():
                    check_rounding(value, f"{path}.{key}" if path else key)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_rounding(item, f"{path}[{i}]")
            elif isinstance(obj, float) and "_usd" in path:
                # Should not have more than 2 decimal places
                rounded = round(obj, 2)
                assert obj == rounded, \
                    f"{path} = {obj} is not rounded to 2 decimals"
        
        check_rounding(data)


class TestCustomRates:
    """Test model with various Section 7520 rates."""

    @pytest.mark.parametrize("rate", [0.02, 0.035, 0.042, 0.05, 0.10])
    def test_model_succeeds_with_valid_rates(self, rate):
        """Test model with various valid Section 7520 rates."""
        output_path = run_deterministic_model(section_7520_rate=rate)
        
        assert output_path.exists()
        
        with open(output_path) as f:
            data = json.load(f)
        
        assert data["assumptions"]["section_7520_rate"] == rate
        assert data["grat"]["annuity_payment_annual_usd"] > 0
        assert data["crat"]["annual_annuity_usd"] > 0

    def test_invalid_rate_raises_error(self):
        """Test that invalid Section 7520 rate raises ValueError."""
        with pytest.raises(ValueError):
            run_deterministic_model(section_7520_rate=0.0)
        
        with pytest.raises(ValueError):
            run_deterministic_model(section_7520_rate=0.25)


class TestOutputMetadata:
    """Test metadata in model output."""

    def test_output_contains_metadata(self):
        """Test that output includes metadata."""
        output_path = run_deterministic_model()
        
        with open(output_path) as f:
            data = json.load(f)
        
        assert "metadata" in data
        assert data["metadata"]["model_version"] == "1.0"
        assert data["metadata"]["pipeline_stage"] == "Stage 3 — Deterministic Trust Modeler"
        assert "generated_timestamp" in data["metadata"]

    def test_output_includes_inputs_and_assumptions(self):
        """Test that output documents inputs and assumptions."""
        output_path = run_deterministic_model()
        
        with open(output_path) as f:
            data = json.load(f)
        
        # Inputs should match client profile
        assert data["inputs"]["age"] == 62
        assert data["inputs"]["liquidity_event_amount_usd"] == 16000000.0
        assert data["inputs"]["estate_tax_rate"] == 0.4
        
        # Assumptions should be documented
        assert data["assumptions"]["grat_term_years"] == 10
        assert data["assumptions"]["crat_term_years"] == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
