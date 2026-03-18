from pathlib import Path
from src.retrieval.plan import load_plan


def test_load_valid_plan():
    path = Path("pipeline_artifacts/retrieval/plan/RetrievalPlan_v1.json")
    plan = load_plan(path)
    assert plan["retrieval_plan_version"] == "1.0"
    assert len(plan["topics"]) > 0

