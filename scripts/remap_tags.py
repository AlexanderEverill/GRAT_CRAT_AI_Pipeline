"""Remap RetrievalBundle section_tags to match the new 10-section outline."""
import json
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent / "src" / "drafting" / "data" / "RetrievalBundle.json"

TAG_REMAP = {
    "executive_summary": ["executive_summary", "client_overview"],
    "grat_analysis":     ["grat_analysis", "scenario_illustration"],
    "crat_analysis":     ["crat_analysis", "scenario_illustration"],
    "comparison_recommendation": ["comparative_analysis", "recommendation"],
    "citations_disclosures": ["risks_considerations", "next_steps"],
}

TOPIC_EXTRA = {
    "gift_estate_tax_treatment": ["planning_objectives"],
    "section_7520_rate": ["planning_objectives"],
    "risks_limitations": ["risks_considerations"],
    "GRAT_core_mechanics": ["scenario_illustration"],
    "CRAT_core_mechanics": ["scenario_illustration"],
}

with open(BUNDLE) as f:
    data = json.load(f)

for chunk in data["chunks"]:
    old_tags = chunk.get("section_tags", [])
    new_tags = set()
    for t in old_tags:
        new_tags.update(TAG_REMAP.get(t, [t]))
    topic = chunk.get("topic", "")
    if topic in TOPIC_EXTRA:
        new_tags.update(TOPIC_EXTRA[topic])
    chunk["section_tags"] = sorted(new_tags)

tags = set()
for c in data["chunks"]:
    tags.update(c["section_tags"])
print("New tags:", sorted(tags))

with open(BUNDLE, "w") as f:
    json.dump(data, f, indent=2, sort_keys=False)
print("Done. Updated", len(data["chunks"]), "chunks.")
