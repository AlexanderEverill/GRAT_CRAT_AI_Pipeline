"""
Input/Output handling for the deterministic model.

Loads client profile and retrieval data, writes model outputs.
All data reads are from allowlisted artifact directories.

No financial constants are defined in this module. All rates and
assumptions are loaded from the following configuration files:
  pipeline_artifacts/config/section_7520_rates.json
  pipeline_artifacts/config/model_assumptions.json
"""

import json
from pathlib import Path
from typing import Tuple, Optional

from src.model.schemas import ClientInput, ModelAssumptions


BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECTION_7520_RATES_PATH = BASE_DIR / "pipeline_artifacts" / "config" / "section_7520_rates.json"
MODEL_ASSUMPTIONS_PATH = BASE_DIR / "pipeline_artifacts" / "config" / "model_assumptions.json"


def load_client_profile() -> dict:
    """Load client intake profile from JSON.
    
    Returns:
        dict: Parsed ClientProfile_v1.json
        
    Raises:
        FileNotFoundError: If profile does not exist
        ValueError: If profile is empty or invalid JSON
    """
    profile_path = BASE_DIR / "pipeline_artifacts" / "intake" / "ClientProfile_v1.json"
    
    if not profile_path.exists():
        raise FileNotFoundError(
            f"Client profile not found at: {profile_path}"
        )
    
    raw = profile_path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Client profile file is empty: {profile_path}")
    
    try:
        profile = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Client profile JSON invalid: {profile_path}") from e
    
    return profile


def _get_section_7520_historical_rate(year: int, month: int = 6) -> Optional[float]:
    """
    Get historical Section 7520 rate for a given month/year.

    Rates are loaded from pipeline_artifacts/config/section_7520_rates.json.
    Source: IRC §7520, IRS Rev. Rul. series, retrieved via RAG source S007.

    Args:
        year: Calendar year (e.g., 2015, 2026)
        month: Calendar month (1-12), defaults to June

    Returns:
        Optional[float]: The 7520 rate for that period, or None if unknown

    Raises:
        FileNotFoundError: If section_7520_rates.json config is missing
        ValueError: If config file JSON is malformed
    """
    if not SECTION_7520_RATES_PATH.exists():
        raise FileNotFoundError(
            f"Section 7520 rates config not found: {SECTION_7520_RATES_PATH}. "
            f"This file must be present and sourced from IRS published tables."
        )

    raw = SECTION_7520_RATES_PATH.read_text(encoding="utf-8")
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"section_7520_rates.json is malformed: {SECTION_7520_RATES_PATH}") from e

    year_key = str(year)
    month_key = f"{month:02d}"

    year_rates = config.get("rates", {}).get(year_key)
    if year_rates is None:
        return None

    rate = year_rates.get(month_key)
    if rate is None:
        return None

    return float(rate)


def load_section_7520_rate(profile: dict) -> float:
    """
    Determine Section 7520 rate from client profile and RAG retrieval.
    
    Process:
    1. Extract valuation date from profile (liquidity event or explicit date)
    2. Look up historical Section 7520 rate from IRS tables (§7520)
    3. Raise error if period not found in rate table
    
    Args:
        profile: Parsed ClientProfile_v1.json
        
    Returns:
        float: Section 7520 rate to use (0.0196 to 0.0500)
        
    Raises:
        ValueError: If profile missing required date info or rate unknown for period
    """
    # Extract valuation date from profile
    # Preference: explicit valuation_date > liquidity_event.year > error
    
    valuation_year = None
    valuation_month = 6  # Default to June if not specified
    
    # Try explicit valuation_date first
    if "valuation_date" in profile:
        try:
            val_date = profile["valuation_date"]
            # Expected format: "2015-06-01" or "2015-06"
            date_parts = val_date.split("-")
            valuation_year = int(date_parts[0])
            valuation_month = int(date_parts[1]) if len(date_parts) > 1 else 6
        except (ValueError, IndexError):
            pass
    
    # Fall back to liquidity event year
    if valuation_year is None:
        try:
            valuation_year = profile["liquidity_event"]["year"]
            # Assume end of year for liquidity event
            valuation_month = 12
        except KeyError:
            raise ValueError(
                "Profile missing both 'valuation_date' and 'liquidity_event.year' "
                "needed to determine Section 7520 rate"
            )
    
    # Look up the rate
    rate = _get_section_7520_historical_rate(valuation_year, valuation_month)
    
    if rate is None:
        raise ValueError(
            f"Section 7520 rate unknown for {valuation_year}-{valuation_month:02d}. "
            f"Please add to historical rates table or provide explicit rate parameter."
        )
    
    return rate


def extract_client_input(profile: dict) -> ClientInput:
    """Extract and validate client input from profile.
    
    Args:
        profile: ClientProfile_v1.json content
        
    Returns:
        ClientInput: Validated client data
        
    Raises:
        ValueError: If required fields are missing or invalid
    """
    try:
        age = profile["client_demographics"]["age"]
        marital_status = profile["client_demographics"]["marital_status"]
        liquidity_amount = profile["liquidity_event"]["gross_proceeds_usd"]
        estate_context = profile["estate_tax_context_2015"]
        
        individual_exemption = estate_context["individual_exemption_usd"]
        married_exemption = estate_context["married_exemption_usd"]
        estate_tax_rate = estate_context["top_estate_tax_rate"]
        
    except KeyError as e:
        raise ValueError(f"Required field missing in client profile: {e}") from e
    
    # Validate ranges
    if age <= 0 or age > 150:
        raise ValueError(f"Invalid age: {age}")
    if liquidity_amount < 0:
        raise ValueError(f"Liquidity amount cannot be negative: {liquidity_amount}")
    if not (0 < estate_tax_rate <= 1.0):
        raise ValueError(f"Estate tax rate must be 0-1, got: {estate_tax_rate}")
    if individual_exemption < 0 or married_exemption < 0:
        raise ValueError("Exemptions cannot be negative")
    
    return ClientInput(
        age=age,
        marital_status=marital_status,
        liquidity_event_amount_usd=float(liquidity_amount),
        estate_tax_rate=float(estate_tax_rate),
        individual_exemption_usd=float(individual_exemption),
        married_exemption_usd=float(married_exemption),
    )


def create_default_assumptions(section_7520_rate: float) -> ModelAssumptions:
    """Create modeling assumptions loaded from pipeline_artifacts/config/model_assumptions.json.

    No financial constants are embedded in this function. All growth rates,
    term lengths, and payout rates are read from the external config file so
    they are versioned, auditable, and changeable without touching source code.

    Args:
        section_7520_rate: Required Section 7520 hurdle rate (validated by caller)

    Returns:
        ModelAssumptions: Assumptions sourced entirely from config file

    Raises:
        ValueError: If rate is invalid or config file is missing/malformed
        FileNotFoundError: If model_assumptions.json config is missing
    """
    if not (0 < section_7520_rate <= 0.2):
        raise ValueError(f"Section 7520 rate must be 0-20%, got: {section_7520_rate}")

    if not MODEL_ASSUMPTIONS_PATH.exists():
        raise FileNotFoundError(
            f"Model assumptions config not found: {MODEL_ASSUMPTIONS_PATH}. "
            f"This file must declare all growth rates and term lengths explicitly."
        )

    raw = MODEL_ASSUMPTIONS_PATH.read_text(encoding="utf-8")
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"model_assumptions.json is malformed: {MODEL_ASSUMPTIONS_PATH}") from e

    try:
        grat_cfg = config["grat"]
        crat_cfg = config["crat"]

        return ModelAssumptions(
            section_7520_rate=section_7520_rate,
            grat_growth_rate=float(grat_cfg["growth_rate"]),
            grat_term_years=int(grat_cfg["term_years"]),
            crat_payout_rate=float(crat_cfg["payout_rate"]),
            crat_growth_rate=float(crat_cfg["growth_rate"]),
            crat_term_years=int(crat_cfg["term_years"]),
            crat_deduction_growth_rate=float(crat_cfg["deduction_growth_rate"]),
        )
    except KeyError as e:
        raise ValueError(
            f"model_assumptions.json is missing required key: {e}. "
            f"File: {MODEL_ASSUMPTIONS_PATH}"
        ) from e


def write_model_output(model_output: dict, version: str = "1.0") -> Path:
    """Write deterministic model output to JSON.
    
    Args:
        model_output: Complete model output as dict
        version: Output schema version
        
    Returns:
        Path: Path where output was written
    """
    output_dir = BASE_DIR / "pipeline_artifacts" / "model_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / "TrustComparison_v1.json"
    
    # Ensure all numeric values are properly typed
    output_text = json.dumps(model_output, indent=2, sort_keys=True)
    output_path.write_text(output_text, encoding="utf-8")
    
    return output_path
