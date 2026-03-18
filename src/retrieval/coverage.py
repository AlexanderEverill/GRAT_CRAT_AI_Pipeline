# src/retrieval/coverage.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_coverage_report(
    plan_path: Path,
    bundle_path: Path,
    out_path: Path,
    default_min_key_points: int = 3,
) -> Path:
    plan = load_json(plan_path)
    bundle = load_json(bundle_path)

    # Build lookup: topic_id -> count(key_points)
    bundle_items = bundle.get("items", [])
    kp_count_by_topic: Dict[str, int] = {}
    for item in bundle_items:
        # In your current bundle.py, item["source_id"] is topic_id
        topic_id = item.get("source_id")
        kp_count_by_topic[topic_id] = len(item.get("key_points", []) or [])

    topics = plan.get("topics", [])
    rows: List[Dict[str, Any]] = []

    total = 0
    green = yellow = red = 0

    for t in topics:
        topic_id = t["topic_id"]
        why_needed = t.get("why_needed", "")
        expected = t.get("expected_citable_outputs", []) or []

        kp_count = kp_count_by_topic.get(topic_id, 0)
        total += 1

        # If you later add per-topic minimums, use them here.
        min_kp = default_min_key_points

        if kp_count >= min_kp:
            status = "GREEN"
            green += 1
        elif kp_count > 0:
            status = "YELLOW"
            yellow += 1
        else:
            status = "RED"
            red += 1

        rows.append(
            {
                "topic_id": topic_id,
                "status": status,
                "key_points_found": kp_count,
                "min_key_points_required": min_kp,
                "expected_citable_outputs": expected,
                "why_needed": why_needed,
            }
        )

    report = {
        "report_version": "1.0",
        "plan_version": plan.get("retrieval_plan_version"),
        "bundle_version": bundle.get("bundle_version"),
        "summary": {
            "topics_total": total,
            "green": green,
            "yellow": yellow,
            "red": red,
        },
        "topics": rows,
        "fail_closed_recommendation": (
            "FAIL" if red > 0 else "PASS_WITH_CAUTION" if yellow > 0 else "PASS"
        ),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return out_path
