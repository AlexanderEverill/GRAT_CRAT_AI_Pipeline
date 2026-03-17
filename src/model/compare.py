"""
Scenario comparison logic.

Compares GRAT and CRAT outcomes and computes differential impacts.
"""

from src.model.schemas import GRATOutput, CRATOutput, ComparisonOutput, ClientInput


def calculate_comparison(
    client: ClientInput,
    grat: GRATOutput,
    crat: CRATOutput,
) -> ComparisonOutput:
    """Compare GRAT and CRAT scenarios.
    
    Calculates:
    - Estate tax savings difference (GRAT vs CRAT)
    - Wealth to children difference
    - Charitable component difference
    
    Args:
        client: Client input data
        grat: GRAT scenario results
        crat: CRAT scenario results
        
    Returns:
        ComparisonOutput: Comparison metrics
    """
    # Calculate baseline taxable estate
    taxable_estate_before = client.liquidity_event_amount_usd
    
    # Estate after GRAT: original corpus less remainder that goes to children
    # (The remainder is now held in trust, removing it from grantor's estate)
    taxable_estate_after_grat = round(
        taxable_estate_before - grat.estate_reduction_usd, 2
    )
    
    # Estate after CRAT: Only charitable remainder (deduction) removes value from estate
    # (Under IRC §2036, income interest is included in grantor's estate at death)
    taxable_estate_after_crat = round(
        taxable_estate_before - crat.estate_reduction_usd, 2
    )
    
    # Estate tax differences
    estate_tax_saving_difference = round(
        grat.estate_tax_saved_usd - crat.estate_tax_saved_usd, 2
    )
    
    # Wealth to children: what they receive at end of term
    # GRAT: remainder distributed to children
    # CRAT: charitable remainder, so children get nothing from CRAT itself
    wealth_to_children_grat = grat.projected_remainder_to_children_usd
    wealth_to_children_crat = 0.0  # Passes to charity, not to children
    wealth_to_children_difference = round(
        wealth_to_children_grat - wealth_to_children_crat, 2
    )
    
    # Charitable component
    # GRAT: no direct charitable benefit
    # CRAT: remainder to charity
    charitable_component_grat = 0.0
    charitable_component_crat = crat.remainder_to_charity_usd
    charitable_component_difference = round(
        charitable_component_crat - charitable_component_grat, 2
    )
    
    return ComparisonOutput(
        taxable_estate_before_usd=taxable_estate_before,
        taxable_estate_after_grat_usd=taxable_estate_after_grat,
        taxable_estate_after_crat_usd=taxable_estate_after_crat,
        estate_tax_saved_by_grat_usd=grat.estate_tax_saved_usd,
        estate_tax_saved_by_crat_usd=crat.estate_tax_saved_usd,
        estate_tax_saving_difference_usd=estate_tax_saving_difference,
        wealth_to_children_grat_usd=wealth_to_children_grat,
        wealth_to_children_crat_usd=wealth_to_children_crat,
        wealth_to_children_difference_usd=wealth_to_children_difference,
        charitable_component_grat_usd=charitable_component_grat,
        charitable_component_crat_usd=charitable_component_crat,
        charitable_component_difference_usd=charitable_component_difference,
    )
