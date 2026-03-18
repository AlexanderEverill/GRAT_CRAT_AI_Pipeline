from pathlib import Path

from loaders.client_profile import ClientProfile, load_client_profile


def test_seed_client_profile_matches_loader_contract() -> None:
    seed_path = Path(__file__).resolve().parents[1] / "data" / "ClientProfile.json"

    profile = load_client_profile(seed_path)

    assert isinstance(profile, ClientProfile)
    assert profile.client_id
    assert profile.risk_tolerance
    assert profile.horizon > 0
    assert profile.goals
    assert "client_demographics" in profile.extra
