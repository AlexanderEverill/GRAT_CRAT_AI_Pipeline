"""
Deterministic Trust Modeling Layer

This module contains the financial models for GRAT and CRAT scenarios.
All numeric outputs are deterministic and traceable to client inputs or formulas.
"""

from src.model.engine import run_deterministic_model

__all__ = ["run_deterministic_model"]
