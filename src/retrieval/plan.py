# src/retrieval/plan.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Set

from .allowlist import normalize_host


class RetrievalPlanError(ValueError):
    pass


def load_plan(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RetrievalPlanError(f"RetrievalPlan not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        plan = json.load(f)

    validate_plan(plan)
    normalize_plan(plan)

    return plan


def validate_plan(plan: Dict[str, Any]) -> None:
    if plan.get("retrieval_plan_version") != "1.0":
        raise RetrievalPlanError("Invalid or missing retrieval_plan_version.")

    allowlist = plan.get("allowlist", {})
    domains = allowlist.get("domains", [])

    if not domains:
        raise RetrievalPlanError("Allowlist domains must not be empty.")

    # Ensure topic_ids unique
    topic_ids = [t["topic_id"] for t in plan.get("topics", [])]
    if len(topic_ids) != len(set(topic_ids)):
        raise RetrievalPlanError("Duplicate topic_id detected.")

    # Validate open question IDs
    open_questions = plan.get("open_questions", [])
    oq_ids = [oq["id"] for oq in open_questions]
    if len(oq_ids) != len(set(oq_ids)):
        raise RetrievalPlanError("Duplicate open_question id detected.")

    oq_set = set(oq_ids)

    # Validate topics
    for topic in plan.get("topics", []):
        if not topic.get("queries"):
            raise RetrievalPlanError(f"Topic {topic['topic_id']} has no queries.")

        for query in topic["queries"]:
            if "q" not in query:
                raise RetrievalPlanError(
                    f"Query missing 'q' in topic {topic['topic_id']}"
                )

            # Validate must_domains inside allowlist
            for d in query.get("must_domains", []):
                if normalize_host(d) not in map(normalize_host, domains):
                    raise RetrievalPlanError(
                        f"Query in topic {topic['topic_id']} references domain "
                        f"{d} not in allowlist."
                    )

            # Validate open question reference
            oq_ref = query.get("resolves_open_question")
            if oq_ref and oq_ref not in oq_set:
                raise RetrievalPlanError(
                    f"Query references unknown open question: {oq_ref}"
                )


def normalize_plan(plan: Dict[str, Any]) -> None:
    # Normalize allowlist domains
    plan["allowlist"]["domains"] = [
        normalize_host(d) for d in plan["allowlist"]["domains"]
    ]

    # Normalize must_domains in queries
    for topic in plan.get("topics", []):
        for query in topic.get("queries", []):
            if "must_domains" in query:
                query["must_domains"] = [
                    normalize_host(d) for d in query["must_domains"]
                ]
