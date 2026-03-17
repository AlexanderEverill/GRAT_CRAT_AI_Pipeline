"""
Deterministic trust modeling orchestrator.

Coordinates the complete financial model run:
1. Load client inputs
2. Set modeling assumptions
3. Run GRAT and CRAT models
4. Compare scenarios
5. Write outputs
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from src.run_pipeline import append_notes_log
from src.model.schemas import TrustComparisonModel
from src.model.io import (
    load_client_profile,
    extract_client_input,
    create_default_assumptions,
    write_model_output,
    load_section_7520_rate,
)
from src.model.grat import calculate_grat
from src.model.crat import calculate_crat
from src.model.compare import calculate_comparison


BASE_DIR = Path(__file__).resolve().parent.parent.parent
CLIENT_PROFILE_PATH = BASE_DIR / "pipeline_artifacts" / "intake" / "ClientProfile_v1.json"
MODEL_RUN_REPORT_PATH = BASE_DIR / "pipeline_artifacts" / "model_outputs" / "ModelRunReport.json"


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file.
    
    Args:
        path: Path to file
        
    Returns:
        str: Hexadecimal SHA-256 hash
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_model_run_report(
    client_profile_hash: str,
    section_7520_rate: float,
    model_version: str = "1.0",
) -> Path:
    """Write ModelRunReport.json audit record.
    
    Records:
    - SHA-256 hash of ClientProfile_v1.json used as input
    - Section 7520 rate and its source
    - Model version
    - Timestamp of run
    
    Args:
        client_profile_hash: SHA-256 of ClientProfile_v1.json
        section_7520_rate: The §7520 rate used in calculations
        model_version: Model version string
        
    Returns:
        Path: Location where report was written
    """
    report_dir = BASE_DIR / "pipeline_artifacts" / "model_outputs"
    report_dir.mkdir(parents=True, exist_ok=True)
    
    report = {
        "model_version": model_version,
        "generated_timestamp": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "client_profile_sha256": client_profile_hash,
            "client_profile_path": str(CLIENT_PROFILE_PATH),
        },
        "section_7520_rate": section_7520_rate,
        "section_7520_rate_source": {
            "description": "Historical IRS Section 7520 rate lookup based on valuation year",
            "source_reference": "S007 — IRC §7520 (retrieved via RAG retrieval bundle)",
            "lookup_method": "client profile valuation_date or liquidity_event year",
        },
        "audit_trail": {
            "stage": "3_deterministic_trust_modeler",
            "pipeline_version": "1.0",
        },
    }
    
    report_text = json.dumps(report, indent=2, sort_keys=True)
    MODEL_RUN_REPORT_PATH.write_text(report_text, encoding="utf-8")
    
    return MODEL_RUN_REPORT_PATH


def run_deterministic_model(
    section_7520_rate: Optional[float] = None,
) -> Path:
    """Run the complete deterministic trust modeling pipeline.
    
    This is the main orchestrator function. It:
    1. Loads client profile from intake
    2. Extracts Section 7520 rate from profile (or uses provided override)
    3. Creates modeling assumptions
    4. Calculates GRAT scenario
    5. Calculates CRAT scenario
    6. Compares scenarios
    7. Writes comprehensive JSON output
    
    Args:
        section_7520_rate: Optional override for IRS Section 7520 interest rate.
                          If None, will be extracted from client profile based on
                          valuation date (liquidity event year).
                          Must be between 0 and 0.20 (0-20%) if provided.
    
    Returns:
        Path: Location of written TrustComparison_v1.json file
        
    Raises:
        FileNotFoundError: If client profile missing
        ValueError: If inputs invalid, inconsistent, or Section 7520 rate unknown
    """
    # ----- AUDIT LOG: Before model run -----
    try:
        append_notes_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": "3_deterministic_trust_modeler_start",
            "event": "Model run initiated",
            "inputs": {
                "client_profile_path": str(CLIENT_PROFILE_PATH),
                "section_7520_rate_override": section_7520_rate,
            },
        })
    except Exception as audit_error:
        # Log but continue; audit logging failure shouldn't stop model
        print(f"⚠️  Warning: Could not write pre-run audit log: {audit_error}")
    
    try:
        # Load client profile
        client_profile = load_client_profile()
        client_profile_hash = _sha256_file(CLIENT_PROFILE_PATH)
        
        # Determine Section 7520 rate
        if section_7520_rate is None:
            # Extract from profile based on valuation date (connected to RAG §7520 retrieval)
            section_7520_rate = load_section_7520_rate(client_profile)
        
        # Validate rate parameter
        if not (0 < section_7520_rate <= 0.2):
            raise ValueError(
                f"section_7520_rate must be between 0 and 0.2, got {section_7520_rate}"
            )
        
        client_input = extract_client_input(client_profile)
        
        # Create modeling assumptions
        assumptions = create_default_assumptions(section_7520_rate)
        
        # Calculate GRAT scenario
        grat_output = calculate_grat(client_input, assumptions)
        
        # Calculate CRAT scenario
        crat_output = calculate_crat(client_input, assumptions)
        
        # Compare scenarios
        comparison = calculate_comparison(client_input, grat_output, crat_output)
        
        # Build comprehensive output model
        model = TrustComparisonModel(
            model_version="1.0",
            client_age=client_input.age,
            marital_status=client_input.marital_status,
            inputs=client_input,
            assumptions=assumptions,
            grat=grat_output,
            crat=crat_output,
            comparison=comparison,
        )
        
        # Convert dataclasses to dict for JSON serialization
        model_dict = _dataclass_to_dict(model)
        
        # Add metadata
        model_dict["metadata"] = {
            "generated_timestamp": datetime.now(timezone.utc).isoformat(),
            "model_version": "1.0",
            "pipeline_stage": "Stage 3 — Deterministic Trust Modeler",
        }
        
        # Write to file
        output_path = write_model_output(model_dict)
        trust_comparison_hash = _sha256_file(output_path)
        
        # Write ModelRunReport.json (audit record)
        model_run_report_path = _write_model_run_report(
            client_profile_hash=client_profile_hash,
            section_7520_rate=section_7520_rate,
            model_version="1.0",
        )
        model_run_report_hash = _sha256_file(model_run_report_path)
        
        # ----- AUDIT LOG: After model run -----
        try:
            append_notes_log({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": "3_deterministic_trust_modeler_complete",
                "event": "Model run completed successfully",
                "outputs": {
                    "trust_comparison_path": str(output_path),
                    "trust_comparison_sha256": trust_comparison_hash,
                    "model_run_report_path": str(model_run_report_path),
                    "model_run_report_sha256": model_run_report_hash,
                },
                "section_7520_rate_used": section_7520_rate,
                "client_profile_sha256": client_profile_hash,
            })
        except Exception as audit_error:
            print(f"⚠️  Warning: Could not write post-run audit log: {audit_error}")
        
        return output_path
        
    except Exception as e:
        # ----- AUDIT LOG: On error -----
        try:
            append_notes_log({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": "3_deterministic_trust_modeler_error",
                "event": "Model run failed",
                "error_type": type(e).__name__,
                "error_message": str(e),
            })
        except Exception as audit_error:
            print(f"⚠️  Warning: Could not write error audit log: {audit_error}")
        raise


def _dataclass_to_dict(obj) -> dict:
    """Recursively convert dataclass instances to dicts.
    
    Args:
        obj: Dataclass instance or other object
        
    Returns:
        dict: Dictionary representation with all values rounded appropriately
    """
    if hasattr(obj, "__dataclass_fields__"):
        # It's a dataclass
        result = {}
        for field_name in obj.__dataclass_fields__:
            value = getattr(obj, field_name)
            result[field_name] = _dataclass_to_dict(value)
        return result
    elif isinstance(obj, (list, tuple)):
        return [_dataclass_to_dict(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    else:
        # Primitive type or other object
        return obj


if __name__ == "__main__":
    try:
        output_path = run_deterministic_model()
        print(f"✅ Model run complete. Output: {output_path}")
    except Exception as e:
        print(f"❌ Model run failed: {e}")
        raise
