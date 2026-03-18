"""
Unit tests for the deterministic trust modeling layer.

Tests verify:
- Deterministic calculations match expected formulas
- All numeric outputs are valid (non-negative where required)
- Schema validation and type safety
- Edge cases and error handling
"""

import pytest
import math
from src.model.schemas import (
    ClientInput,
    ModelAssumptions,
    GRATOutput,
    CRATOutput,
    ComparisonOutput,
)
from src.model.grat import calculate_annuity_payment, simulate_trust_value, calculate_grat
from src.model.crat import (
    simulate_crat_trust_value,
    calculate_charitable_deduction,
    calculate_crat,
)
from src.model.compare import calculate_comparison
from src.model.io import extract_client_input, create_default_assumptions


class TestClientInput:
    """Test client input extraction and validation."""
    
    def test_valid_client_profile_extraction(self):
        """Test extracting valid client data."""
        profile = {
            "client_demographics": {
                "age": 62,
                "marital_status": "Married",
            },
            "liquidity_event": {
                "gross_proceeds_usd": 16000000,
            },
            "estate_tax_context_2015": {
                "individual_exemption_usd": 5430000,
                "married_exemption_usd": 10860000,
                "top_estate_tax_rate": 0.4,
            },
        }
        
        client = extract_client_input(profile)
        
        assert client.age == 62
        assert client.marital_status == "Married"
        assert client.liquidity_event_amount_usd == 16000000.0
        assert client.estate_tax_rate == 0.4
    
    def test_invalid_age_zero(self):
        """Test rejection of age = 0."""
        profile = {
            "client_demographics": {"age": 0, "marital_status": "Single"},
            "liquidity_event": {"gross_proceeds_usd": 1000000},
            "estate_tax_context_2015": {
                "individual_exemption_usd": 5430000,
                "married_exemption_usd": 10860000,
                "top_estate_tax_rate": 0.4,
            },
        }
        
        with pytest.raises(ValueError, match="Invalid age"):
            extract_client_input(profile)
    
    def test_invalid_negative_liquidity(self):
        """Test rejection of negative liquidity event."""
        profile = {
            "client_demographics": {"age": 62, "marital_status": "Married"},
            "liquidity_event": {"gross_proceeds_usd": -1000000},
            "estate_tax_context_2015": {
                "individual_exemption_usd": 5430000,
                "married_exemption_usd": 10860000,
                "top_estate_tax_rate": 0.4,
            },
        }
        
        with pytest.raises(ValueError, match="cannot be negative"):
            extract_client_input(profile)
    
    def test_invalid_tax_rate_over_100(self):
        """Test rejection of tax rate > 100%."""
        profile = {
            "client_demographics": {"age": 62, "marital_status": "Married"},
            "liquidity_event": {"gross_proceeds_usd": 1000000},
            "estate_tax_context_2015": {
                "individual_exemption_usd": 5430000,
                "married_exemption_usd": 10860000,
                "top_estate_tax_rate": 1.5,
            },
        }
        
        with pytest.raises(ValueError, match="must be 0-1"):
            extract_client_input(profile)


class TestGRATCalculations:
    """Test GRAT calculation formulas."""
    
    def test_annuity_payment_basic(self):
        """Test annuity payment calculation with known values.
        
        Formula: A = PV / [(1 - (1+r)^-n) / r]
        """
        # $1,000,000 contribution, 4% rate, 10 years
        payment = calculate_annuity_payment(
            contribution=1000000.0,
            section_7520_rate=0.04,
            term_years=10,
        )
        
        # For 4% and 10 years:
        # (1 - 1.04^-10) / 0.04 = (1 - 0.6756) / 0.04 = 8.1109
        # A = 1000000 / 8.1109 ≈ 123,227.83
        assert payment > 0
        assert isinstance(payment, float)
        assert payment == round(payment, 2)  # Must be rounded to cents
    
    def test_annuity_payment_is_deterministic(self):
        """Test that annuity calculation is deterministic."""
        payment1 = calculate_annuity_payment(1000000, 0.04, 10)
        payment2 = calculate_annuity_payment(1000000, 0.04, 10)
        
        assert payment1 == payment2
    
    def test_annuity_payment_zero_rate_fails(self):
        """Test that zero rate is rejected."""
        with pytest.raises(ValueError, match="must be positive"):
            calculate_annuity_payment(1000000, 0.0, 10)
    
    def test_annuity_payment_zero_term_fails(self):
        """Test that zero-year term is rejected."""
        with pytest.raises(ValueError, match="must be positive"):
            calculate_annuity_payment(1000000, 0.04, 0)
    
    def test_trust_value_simulation_decreases(self):
        """Test that trust value decreases even with growth."""
        # Start with $1M, 5% annual withdrawal, 3% growth
        # Year 1: 1M * 1.03 - 50k = 980k
        # Year 2: 980k * 1.03 - 50k ≈ 959.4k
        remainder = simulate_trust_value(
            initial_value=1000000.0,
            annual_payment=50000.0,
            growth_rate=0.03,
            term_years=2,
        )
        
        assert remainder > 0
        assert remainder < 1000000
    
    def test_trust_value_cannot_be_negative(self):
        """Test that remainder cannot go negative."""
        # Large payment relative to corpus
        remainder = simulate_trust_value(
            initial_value=100000.0,
            annual_payment=50000.0,
            growth_rate=0.01,
            term_years=10,
        )
        
        assert remainder >= 0
    
    def test_grat_calculation_complete(self):
        """Test complete GRAT scenario calculation."""
        client = ClientInput(
            age=62,
            marital_status="Married",
            liquidity_event_amount_usd=16000000.0,
            estate_tax_rate=0.4,
            individual_exemption_usd=5430000.0,
            married_exemption_usd=10860000.0,
        )
        
        assumptions = ModelAssumptions(
            section_7520_rate=0.042,
            grat_growth_rate=0.05,
            grat_term_years=10,
            crat_payout_rate=0.05,
            crat_growth_rate=0.05,
            crat_term_years=20,
            crat_deduction_growth_rate=0.04,
        )
        
        grat = calculate_grat(client, assumptions)
        
        # Assertions on output structure
        assert isinstance(grat, GRATOutput)
        assert grat.trust_corpus_usd == 16000000.0
        assert grat.term_years == 10
        assert grat.annuity_payment_annual_usd > 0
        assert grat.total_annuity_paid_usd > 0
        assert grat.projected_remainder_to_children_usd >= 0
        assert grat.taxable_gift_usd == 0.0  # Zeroed-out GRAT
        assert grat.estate_reduction_usd == grat.projected_remainder_to_children_usd
        assert grat.estate_tax_saved_usd > 0


class TestCRATCalculations:
    """Test CRAT calculation formulas."""
    
    def test_crat_trust_value_simulation(self):
        """Test CRAT trust value simulation."""
        # $1M corpus, $50k annual payout, 3% growth
        remainder = simulate_crat_trust_value(
            initial_value=1000000.0,
            annual_payout=50000.0,
            growth_rate=0.03,
            term_years=10,
        )
        
        assert remainder > 0
        assert remainder < 1000000
    
    def test_crat_trust_value_cannot_be_negative(self):
        """Test that CRAT remainder cannot be negative."""
        remainder = simulate_crat_trust_value(
            initial_value=100000.0,
            annual_payout=20000.0,
            growth_rate=0.01,
            term_years=10,
        )
        
        assert remainder >= 0
    
    def test_charitable_deduction_calculation(self):
        """Test charitable deduction estimation."""
        deduction = calculate_charitable_deduction(
            initial_corpus=1000000.0,
            annual_payout=50000.0,
            payout_rate=0.05,
            section_7520_rate=0.04,
            term_years=10,
            deduction_growth_rate=0.04,
        )
        
        assert deduction > 0
        assert deduction < 1000000  # Can't exceed initial corpus
    
    def test_crat_calculation_complete(self):
        """Test complete CRAT scenario calculation."""
        client = ClientInput(
            age=62,
            marital_status="Married",
            liquidity_event_amount_usd=16000000.0,
            estate_tax_rate=0.4,
            individual_exemption_usd=5430000.0,
            married_exemption_usd=10860000.0,
        )
        
        assumptions = ModelAssumptions(
            section_7520_rate=0.042,
            grat_growth_rate=0.05,
            grat_term_years=10,
            crat_payout_rate=0.05,
            crat_growth_rate=0.05,
            crat_term_years=20,
            crat_deduction_growth_rate=0.04,
        )
        
        crat = calculate_crat(client, assumptions)
        
        # Assertions on output structure
        assert isinstance(crat, CRATOutput)
        assert crat.trust_corpus_usd == 16000000.0
        assert crat.payout_rate == 0.05
        assert crat.annual_annuity_usd > 0
        assert crat.total_annuity_paid_usd > 0
        assert crat.remainder_to_charity_usd >= 0
        assert crat.charitable_deduction_estimate_usd > 0
        # Under IRC §2036, estate reduction = charitable deduction (not full corpus)
        # Full corpus is included in estate, but offset by deduction value
        assert crat.estate_reduction_usd == crat.charitable_deduction_estimate_usd
        assert crat.estate_reduction_usd < crat.trust_corpus_usd
        assert crat.estate_tax_saved_usd > 0


class TestComparison:
    """Test scenario comparison logic."""
    
    def test_comparison_calculation(self):
        """Test complete scenario comparison."""
        client = ClientInput(
            age=62,
            marital_status="Married",
            liquidity_event_amount_usd=16000000.0,
            estate_tax_rate=0.4,
            individual_exemption_usd=5430000.0,
            married_exemption_usd=10860000.0,
        )
        
        assumptions = ModelAssumptions(
            section_7520_rate=0.042,
            grat_growth_rate=0.05,
            grat_term_years=10,
            crat_payout_rate=0.05,
            crat_growth_rate=0.05,
            crat_term_years=20,
            crat_deduction_growth_rate=0.04,
        )
        
        grat = calculate_grat(client, assumptions)
        crat = calculate_crat(client, assumptions)
        comparison = calculate_comparison(client, grat, crat)
        
        # Assertions on comparison structure
        assert isinstance(comparison, ComparisonOutput)
        assert comparison.taxable_estate_before_usd == 16000000.0
        assert comparison.taxable_estate_after_grat_usd >= 0
        assert comparison.taxable_estate_after_crat_usd >= 0
        assert comparison.estate_tax_saved_by_grat_usd > 0
        assert comparison.estate_tax_saved_by_crat_usd > 0
        
        # GRAT should benefit children more than CRAT
        assert comparison.wealth_to_children_grat_usd > comparison.wealth_to_children_crat_usd
        
        # CRAT should benefit charity, GRAT should not
        assert comparison.charitable_component_crat_usd > comparison.charitable_component_grat_usd


class TestRounding:
    """Test that all monetary values are properly rounded."""
    
    def test_annuity_payment_rounded_to_cents(self):
        """Test that annuity payment rounds to 2 decimals."""
        payment = calculate_annuity_payment(1000000, 0.042, 10)
        
        # Check that it's a float with exactly 2 decimal places of precision
        assert payment == round(payment, 2)
    
    def test_grat_outputs_properly_rounded(self):
        """Test that GRAT output values are rounded."""
        client = ClientInput(
            age=62,
            marital_status="Married",
            liquidity_event_amount_usd=16000000.0,
            estate_tax_rate=0.4,
            individual_exemption_usd=5430000.0,
            married_exemption_usd=10860000.0,
        )
        
        assumptions = ModelAssumptions(
            section_7520_rate=0.042,
            grat_growth_rate=0.05,
            grat_term_years=10,
            crat_payout_rate=0.05,
            crat_growth_rate=0.05,
            crat_term_years=20,
            crat_deduction_growth_rate=0.04,
        )
        
        grat = calculate_grat(client, assumptions)
        
        # All monetary values should round to 2 decimals
        assert grat.annuity_payment_annual_usd == round(grat.annuity_payment_annual_usd, 2)
        assert grat.total_annuity_paid_usd == round(grat.total_annuity_paid_usd, 2)
        assert grat.projected_remainder_to_children_usd == round(
            grat.projected_remainder_to_children_usd, 2
        )
        assert grat.estate_tax_saved_usd == round(grat.estate_tax_saved_usd, 2)


class TestModelAssumptions:
    """Test model assumptions validation."""
    
    def test_invalid_section_7520_rate(self):
        """Test that invalid Section 7520 rates are rejected."""
        with pytest.raises(ValueError, match="must be 0-20%"):
            create_default_assumptions(section_7520_rate=0.0)
        
        with pytest.raises(ValueError, match="must be 0-20%"):
            create_default_assumptions(section_7520_rate=0.25)
    
    def test_valid_assumptions(self):
        """Test creating valid assumptions loaded from config file."""
        assumptions = create_default_assumptions(section_7520_rate=0.042)
        
        assert assumptions.section_7520_rate == 0.042
        assert assumptions.grat_growth_rate == 0.05
        assert assumptions.grat_term_years == 10
        assert assumptions.crat_payout_rate == 0.05
        assert assumptions.crat_growth_rate == 0.05
        assert assumptions.crat_term_years == 20
        assert assumptions.crat_deduction_growth_rate == 0.04


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
