from pathlib import Path
from src.retrieval.plan import load_plan
from src.retrieval.fetch import seed_urls_from_plan


def test_seed_urls_from_plan():
    plan = load_plan(Path("pipeline_artifacts/retrieval/plan/RetrievalPlan_v1.json"))
    urls = seed_urls_from_plan(plan)
    assert isinstance(urls, list)
    assert len(urls) > 0
    assert urls[0].startswith("https://")
