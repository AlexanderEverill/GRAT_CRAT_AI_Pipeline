from __future__ import annotations

from loaders.client_profile import ClientProfile, load_client_profile
from context.client_context import format_client_context_block


def test_format_client_context_block_from_seed_profile() -> None:
    from pathlib import Path

    seed_path = Path(__file__).resolve().parents[1] / "data" / "ClientProfile.json"
    profile = load_client_profile(seed_path)

    context_block = format_client_context_block(profile)

    assert "risk tolerance" in context_block
    assert "investment horizon" in context_block
    assert "Minimize estate tax exposure" in context_block
    assert "Maintain sufficient annual liquidity" in context_block


def test_format_client_context_block_without_constraints() -> None:
    profile = ClientProfile(
        client_id="CLIENT-TEST-001",
        risk_tolerance="conservative",
        goals=["Capital preservation", "Income stability"],
        horizon=5,
        extra={},
    )

    context_block = format_client_context_block(profile)

    assert "No explicit constraints were provided." in context_block
    assert "CLIENT-TEST-001" in context_block
    assert "5-year investment horizon" in context_block
