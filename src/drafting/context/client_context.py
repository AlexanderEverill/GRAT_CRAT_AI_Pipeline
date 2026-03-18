"""Client context block formatter for drafting prompts."""

from __future__ import annotations

from loaders.client_profile import ClientProfile


def _join_natural(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _extract_constraints(profile: ClientProfile) -> list[str]:
    raw_constraints = profile.extra.get("constraints")
    if isinstance(raw_constraints, list):
        normalized = [
            item.strip()
            for item in raw_constraints
            if isinstance(item, str) and item.strip()
        ]
        if normalized:
            return normalized

    engagement_context = profile.extra.get("engagement_context")
    if isinstance(engagement_context, dict):
        deliverable_format = engagement_context.get("deliverable_format")
        if isinstance(deliverable_format, str) and deliverable_format.strip():
            return [f"Deliverable preference: {deliverable_format.strip()}"]

    return []


def format_client_context_block(profile: ClientProfile) -> str:
    """Render a compact natural-language client context paragraph."""
    goals_text = _join_natural(profile.goals)
    constraints = _extract_constraints(profile)

    if constraints:
        constraints_text = _join_natural(constraints)
        constraints_sentence = f"Key constraints: {constraints_text}."
    else:
        constraints_sentence = "No explicit constraints were provided."

    return (
        f"Client {profile.client_id} has a {profile.risk_tolerance} risk tolerance, "
        f"stated goals of {goals_text}, and a {profile.horizon}-year investment horizon. "
        f"{constraints_sentence}"
    )