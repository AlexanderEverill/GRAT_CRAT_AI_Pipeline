"""
GRAT (Grantor Retained Annuity Trust) deterministic financial model.

Implements IRC §2702 qualified annuity interest valuation.
Uses present value of annuity formula with Section 7520 rate.
"""

import math
from src.model.schemas import ClientInput, ModelAssumptions, GRATOutput


def calculate_annuity_payment(
    contribution: float,
    section_7520_rate: float,
    term_years: int,
) -> float:
    """Calculate fixed annual annuity payment using PV of annuity formula.
    
    Formula: A = PV / [(1 - (1+r)^-n) / r]
    
    Where:
        A = annuity payment (solve for this)
        PV = contribution (present value)
        r = section_7520_rate (discount rate)
        n = term_years
    
    Args:
        contribution: Trust corpus in USD
        section_7520_rate: IRS Section 7520 rate (e.g., 0.042 for 4.2%)
        term_years: Duration of annuity term
        
    Returns:
        float: Annual fixed annuity payment, rounded to 2 decimals
        
    Raises:
        ValueError: If rate is invalid or term is <= 0
    """
    if section_7520_rate <= 0:
        raise ValueError(f"Section 7520 rate must be positive: {section_7520_rate}")
    if term_years <= 0:
        raise ValueError(f"Term years must be positive: {term_years}")
    
    r = section_7520_rate
    n = term_years
    
    # Calculate annuity factor: (1 - (1+r)^-n) / r
    annuity_factor = (1 - (1 + r) ** (-n)) / r
    
    # Annuity payment = PV / annuity_factor
    annuity_payment = contribution / annuity_factor
    
    return round(annuity_payment, 2)


def simulate_trust_value(
    initial_value: float,
    annual_payment: float,
    growth_rate: float,
    term_years: int,
) -> float:
    """Simulate GRAT trust value at end of term after annual distributions.
    
    Algorithm:
        For each year:
            value = value * (1 + growth_rate)
            value = value - annual_payment
    
    Args:
        initial_value: Initial trust corpus
        annual_payment: Fixed annual distribution to grantor
        growth_rate: Annual trust asset growth rate
        term_years: Number of years to simulate
        
    Returns:
        float: Projected remainder value, minimum 0, rounded to 2 decimals
    """
    if growth_rate > 0.2:
        raise ValueError(f"Growth rate unreasonably high (>20%): {growth_rate}")
    
    value = initial_value
    
    for year in range(term_years):
        value = value * (1 + growth_rate)
        value = value - annual_payment
    
    # Remainder cannot be negative
    remainder = max(value, 0)
    return round(remainder, 2)


def calculate_grat(
    client: ClientInput,
    assumptions: ModelAssumptions,
) -> GRATOutput:
    """Calculate complete GRAT scenario with zeroed-out gift tax treatment.
    
    Implements a zeroed-out GRAT model where:
    - Annuity is calculated so PV of annuity ≈ PV of remainder
    - Taxable gift is minimized (≈ 0) due to GRAT mechanics
    - Remainder passes to children at end of term
    - Estate reduction = remainder value at term
    - Estate tax saved = remainder * estate_tax_rate
    
    Args:
        client: Client input data
        assumptions: Modeling assumptions
        
    Returns:
        GRATOutput: Complete GRAT scenario results
    """
    # Use liquidity event amount as GRAT corpus
    corpus = client.liquidity_event_amount_usd
    
    # Calculate fixed annuity payment
    annuity_payment = calculate_annuity_payment(
        contribution=corpus,
        section_7520_rate=assumptions.section_7520_rate,
        term_years=assumptions.grat_term_years,
    )
    
    # Total annuities paid over term
    total_annuities_paid = round(annuity_payment * assumptions.grat_term_years, 2)
    
    # Project remainder at end of term
    remainder = simulate_trust_value(
        initial_value=corpus,
        annual_payment=annuity_payment,
        growth_rate=assumptions.grat_growth_rate,
        term_years=assumptions.grat_term_years,
    )
    
    # Estate reduction = remainder transferred to children
    estate_reduction = remainder
    
    # Estate tax saved at 40% rate
    estate_tax_saved = round(remainder * client.estate_tax_rate, 2)
    
    # Zeroed-out GRAT: taxable gift is minimal (all value to annuity)
    taxable_gift = 0.0
    
    return GRATOutput(
        trust_corpus_usd=corpus,
        term_years=assumptions.grat_term_years,
        section_7520_rate=assumptions.section_7520_rate,
        growth_rate=assumptions.grat_growth_rate,
        annuity_payment_annual_usd=annuity_payment,
        total_annuity_paid_usd=total_annuities_paid,
        projected_remainder_to_children_usd=remainder,
        taxable_gift_usd=taxable_gift,
        estate_reduction_usd=estate_reduction,
        estate_tax_saved_usd=estate_tax_saved,
    )
