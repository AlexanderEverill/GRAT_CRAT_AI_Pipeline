"""
Data schemas for deterministic trust modeling.

Uses dataclasses for type safety and immutability.
All monetary values are in USD and rounded to 2 decimal places.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ClientInput:
    """Client financial and demographic data from intake."""
    age: int
    marital_status: str
    liquidity_event_amount_usd: float
    estate_tax_rate: float
    individual_exemption_usd: float
    married_exemption_usd: float


@dataclass(frozen=True)
class ModelAssumptions:
    """Modeling assumptions used in calculations. All values are loaded
    from pipeline_artifacts/config/model_assumptions.json — never hardcoded."""
    section_7520_rate: float
    grat_growth_rate: float
    grat_term_years: int
    crat_payout_rate: float
    crat_growth_rate: float
    crat_term_years: int
    crat_deduction_growth_rate: float


@dataclass(frozen=True)
class GRATOutput:
    """GRAT scenario outputs."""
    trust_corpus_usd: float
    term_years: int
    section_7520_rate: float
    growth_rate: float
    annuity_payment_annual_usd: float
    total_annuity_paid_usd: float
    projected_remainder_to_children_usd: float
    taxable_gift_usd: float
    estate_reduction_usd: float
    estate_tax_saved_usd: float


@dataclass(frozen=True)
class CRATOutput:
    """CRAT scenario outputs."""
    trust_corpus_usd: float
    payout_rate: float
    growth_rate: float
    annual_annuity_usd: float
    total_annuity_paid_usd: float
    remainder_to_charity_usd: float
    charitable_deduction_estimate_usd: float
    estate_reduction_usd: float
    estate_tax_saved_usd: float


@dataclass(frozen=True)
class ComparisonOutput:
    """Comparison between GRAT and CRAT scenarios."""
    taxable_estate_before_usd: float
    taxable_estate_after_grat_usd: float
    taxable_estate_after_crat_usd: float
    estate_tax_saved_by_grat_usd: float
    estate_tax_saved_by_crat_usd: float
    estate_tax_saving_difference_usd: float
    wealth_to_children_grat_usd: float
    wealth_to_children_crat_usd: float
    wealth_to_children_difference_usd: float
    charitable_component_grat_usd: float
    charitable_component_crat_usd: float
    charitable_component_difference_usd: float


@dataclass(frozen=True)
class TrustComparisonModel:
    """Complete deterministic model output."""
    model_version: str
    client_age: int
    marital_status: str
    inputs: ClientInput
    assumptions: ModelAssumptions
    grat: GRATOutput
    crat: CRATOutput
    comparison: ComparisonOutput
