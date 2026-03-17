"""
CRAT (Charitable Remainder Annuity Trust) deterministic financial model.

Implements IRC §664 charitable remainder annuity trust valuation.
Uses present value formulas with Section 7520 rate.
"""

from src.model.schemas import ClientInput, ModelAssumptions, CRATOutput


def simulate_crat_trust_value(
    initial_value: float,
    annual_payout: float,
    growth_rate: float,
    term_years: int,
) -> float:
    """Simulate CRAT trust value at end of term after annual distributions.
    
    Algorithm:
        For each year:
            value = value * (1 + growth_rate)
            value = value - annual_payout
    
    Args:
        initial_value: Initial trust corpus
        annual_payout: Fixed annual distribution to income beneficiary
        growth_rate: Annual trust asset growth rate
        term_years: Number of years to simulate
        
    Returns:
        float: Projected remainder for charity, minimum 0, rounded to 2 decimals
    """
    if growth_rate > 0.2:
        raise ValueError(f"Growth rate unreasonably high (>20%): {growth_rate}")
    
    value = initial_value
    
    for year in range(term_years):
        value = value * (1 + growth_rate)
        value = value - annual_payout
    
    # Remainder cannot be negative
    remainder = max(value, 0)
    return round(remainder, 2)


def calculate_charitable_deduction(
    initial_corpus: float,
    annual_payout: float,
    payout_rate: float,
    section_7520_rate: float,
    term_years: int,
    deduction_growth_rate: float,
) -> float:
    """Calculate present value of charitable remainder interest.

    The charitable deduction is the present value of the remainder
    interest that passes to the charitable beneficiary at the end of
    the trust term.

    Simplified calculation:
        PV_remainder ≈ final_value / (1 + 7520_rate)^term_years

    Args:
        initial_corpus: Initial trust value
        annual_payout: Annual annuity payment
        payout_rate: Payout rate as decimal (e.g., 0.05 for 5%)
        section_7520_rate: IRS Section 7520 rate used as discount rate
        term_years: Trust term in years
        deduction_growth_rate: Growth rate used for the remainder simulation
                               (sourced from model_assumptions.json;
                               typically conservative relative to crat_growth_rate)

    Returns:
        float: Estimated charitable deduction, rounded to 2 decimals
    """
    if section_7520_rate <= 0:
        raise ValueError(f"Section 7520 rate must be positive: {section_7520_rate}")
    if term_years <= 0:
        raise ValueError(f"Term years must be positive: {term_years}")
    if deduction_growth_rate < 0:
        raise ValueError(f"Deduction growth rate cannot be negative: {deduction_growth_rate}")

    # Simulate remainder using the explicitly-supplied deduction growth rate
    # (no hardcoded fallback — caller must pass a value from config)
    projected_remainder = simulate_crat_trust_value(
        initial_value=initial_corpus,
        annual_payout=annual_payout,
        growth_rate=deduction_growth_rate,
        term_years=term_years,
    )

    # Present value of remainder
    discount_factor = (1 + section_7520_rate) ** term_years
    deduction = projected_remainder / discount_factor

    return round(deduction, 2)


def calculate_crat(
    client: ClientInput,
    assumptions: ModelAssumptions,
) -> CRATOutput:
    """Calculate complete CRAT scenario with charitable remainder interest.
    
    Implements an IRC §664 charitable remainder annuity trust where:
    - Annual annuity is fixed percentage of initial corpus
    - Donor receives income stream during term (taxable to donor)
    - Under IRC §2036, grantor retains income interest → assets included in estate
    - Estate reduction = only the charitable remainder interest (deduction value)
    - Remainder at end of term passes to designated charity
    - Provides income stream to donor for term
    
    NOTE: IRC §2036 inclusion means the full corpus enters the estate at grantor's
    death, but the charitable deduction (PV of remainder) offsets the estate tax.
    Net estate reduction = charitable deduction amount only.
    
    Args:
        client: Client input data
        assumptions: Modeling assumptions
        
    Returns:
        CRATOutput: Complete CRAT scenario results
    """
    # Use liquidity event amount as CRAT corpus
    corpus = client.liquidity_event_amount_usd
    
    # Calculate fixed annual distribution
    annual_annuity = round(corpus * assumptions.crat_payout_rate, 2)
    
    # Total annuities received over term
    total_annuities = round(annual_annuity * assumptions.crat_term_years, 2)
    
    # Project remainder to charity at end of term
    remainder_to_charity = simulate_crat_trust_value(
        initial_value=corpus,
        annual_payout=annual_annuity,
        growth_rate=assumptions.crat_growth_rate,
        term_years=assumptions.crat_term_years,
    )
    
    # Calculate charitable deduction
    charitable_deduction = calculate_charitable_deduction(
        initial_corpus=corpus,
        annual_payout=annual_annuity,
        payout_rate=assumptions.crat_payout_rate,
        section_7520_rate=assumptions.section_7520_rate,
        term_years=assumptions.crat_term_years,
        deduction_growth_rate=assumptions.crat_deduction_growth_rate,
    )
    
    # Estate reduction: Under IRC §2036, only the charitable remainder (deduction)
    # escapes estate tax. The income interest is included at grantor's death.
    # Net estate reduction = present value of charitable remainder only.
    estate_reduction = charitable_deduction
    
    # Estate tax saved on the charitable remainder amount only
    # (This is the amount that actually escapes the taxable estate)
    estate_tax_saved = round(charitable_deduction * client.estate_tax_rate, 2)
    
    return CRATOutput(
        trust_corpus_usd=corpus,
        payout_rate=assumptions.crat_payout_rate,
        growth_rate=assumptions.crat_growth_rate,
        annual_annuity_usd=annual_annuity,
        total_annuity_paid_usd=total_annuities,
        remainder_to_charity_usd=remainder_to_charity,
        charitable_deduction_estimate_usd=charitable_deduction,
        estate_reduction_usd=estate_reduction,
        estate_tax_saved_usd=estate_tax_saved,
    )
