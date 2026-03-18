"""Build proper drafting data files from real pipeline artifacts.

Converts the topic-based RetrievalBundle_v1.json into the chunk-based format
expected by the drafting loaders, and expands the Outline with all relevant
model output placeholders.
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ARTIFACTS = BASE / "pipeline_artifacts"
DATA_DIR = BASE / "src" / "drafting" / "data"

# ── Load real retrieval artifacts ──────────────────────────────────────
real_bundle = json.loads(
    (ARTIFACTS / "retrieval/bundle/RetrievalBundle_v1.json").read_text("utf-8")
)
citations_manifest = json.loads(
    (ARTIFACTS / "retrieval/bundle/CitationsManifest_v1.json").read_text("utf-8")
)

# ── Topic → outline section mapping ───────────────────────────────────
TOPIC_SECTION_MAP: dict[str, list[str]] = {
    "GRAT_core_mechanics":      ["grat_analysis", "executive_summary"],
    "CRAT_core_mechanics":      ["crat_analysis", "executive_summary"],
    "gift_estate_tax_treatment": ["grat_analysis", "crat_analysis", "comparison_recommendation"],
    "section_7520_rate":         ["grat_analysis", "executive_summary"],
    "CRT_taxation_basics":      ["crat_analysis"],
    "risks_limitations":         ["comparison_recommendation", "grat_analysis", "crat_analysis"],
    "required_disclosures_limitations_language": ["citations_disclosures"],
}

# Topic → primary IRC source documents
TOPIC_PRIMARY_SOURCES: dict[str, list[str]] = {
    "GRAT_core_mechanics":      ["S001", "S002"],
    "CRAT_core_mechanics":      ["S003", "S004"],
    "gift_estate_tax_treatment": ["S005", "S006", "S010"],
    "section_7520_rate":         ["S007"],
    "CRT_taxation_basics":      ["S003", "S009"],
    "risks_limitations":         ["S001", "S002", "S003", "S004"],
    "required_disclosures_limitations_language": ["S011"],
}

# ── Build source_id → first cite_key mapping ──────────────────────────
source_to_cite: dict[str, str] = {}
for c in citations_manifest["citations"]:
    sid = c["source_id"]
    if sid not in source_to_cite:
        source_to_cite[sid] = c["cite_key"]

# ── Convert topic key_points → drafting chunks ────────────────────────
chunks: list[dict] = []

for item in real_bundle["items"]:
    topic = item["source_id"]  # topic name
    section_tags = TOPIC_SECTION_MAP.get(topic, [])
    primary_sources = TOPIC_PRIMARY_SOURCES.get(topic, ["S002"])

    # Select top key_points by quote length (longer = more informative)
    key_points = item["key_points"]
    sorted_kps = sorted(key_points, key=lambda kp: len(kp["quote"]), reverse=True)
    selected = sorted_kps[:5]

    for i, kp in enumerate(selected):
        src_id = primary_sources[i % len(primary_sources)]
        cite_key = source_to_cite.get(src_id, "[S1]")

        chunks.append({
            "source_id": src_id,
            "score": round(0.95 - (i * 0.02), 3),
            "text": kp["quote"].strip(),
            "citation_key": cite_key,
            "section_tags": section_tags,
            "topic": topic,
        })

# ── Build citation manifest for the drafting bundle ───────────────────
used_cite_keys = set(c["citation_key"] for c in chunks)
drafting_citations = [
    c for c in citations_manifest["citations"]
    if c["cite_key"] in used_cite_keys
]

drafting_bundle = {
    "metadata": {
        "created_timestamp": "2026-03-17T00:00:00+00:00",
        "pipeline_stage": "RAG Retrieval (converted from RetrievalBundle_v1)",
        "inputs": {
            "source_bundle": "pipeline_artifacts/retrieval/bundle/RetrievalBundle_v1.json",
            "source_manifest": "pipeline_artifacts/retrieval/bundle/CitationsManifest_v1.json",
        },
    },
    "citation_manifest": {
        "citation_style": "inline-short-id",
        "citations": drafting_citations,
    },
    "chunks": chunks,
    "items": [],
}

out_path = DATA_DIR / "RetrievalBundle.json"
out_path.write_text(
    json.dumps(drafting_bundle, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(f"Wrote {len(chunks)} chunks -> {out_path}")
print(f"  Used {len(used_cite_keys)} unique citation keys")
print(f"  Topics covered: {[item['source_id'] for item in real_bundle['items']]}")

# ── Expanded Outline ──────────────────────────────────────────────────
outline = {
    "version": "v1",
    "sections": [
        {
            "id": "executive_summary",
            "title": "Executive Summary",
            "content_type": "narrative",
            "purpose": (
                "Summarize client objectives, key findings from the GRAT and CRAT "
                "analysis, and provide a decision framework. Include the client's "
                "estate size, applicable tax rates, and top-level comparison of both "
                "strategies."
            ),
            "expected_placeholders": [
                {"placeholder": "{{estate_tax_rate}}", "model_key": "estate_tax_rate", "source": "risk_metrics", "format": "percent"},
                {"placeholder": "{{section_7520_rate_bps}}", "model_key": "section_7520_rate", "source": "risk_metrics", "format": "bps"},
                {"placeholder": "{{taxable_estate_before_usd}}", "model_key": "taxable_estate_before_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{estate_tax_saved_by_grat_usd}}", "model_key": "estate_tax_saved_by_grat_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{estate_tax_saved_by_crat_usd}}", "model_key": "estate_tax_saved_by_crat_usd", "source": "forecasts", "format": "currency"},
            ],
            "required_inputs": ["ClientProfile", "ModelOutputs"],
        },
        {
            "id": "grat_analysis",
            "title": "GRAT Analysis",
            "content_type": "narrative",
            "purpose": (
                "Explain GRAT mechanics under IRC §2702, projected outcomes for this "
                "client, annuity payment structure, remainder to beneficiaries, gift "
                "tax implications, and planning considerations. Reference the §7520 "
                "hurdle rate used."
            ),
            "expected_placeholders": [
                {"placeholder": "{{grat_trust_corpus_usd}}", "model_key": "grat_trust_corpus_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{grat_term_years}}", "model_key": "grat_term_years", "source": "forecasts", "format": "number"},
                {"placeholder": "{{grat_annuity_payment_annual_usd}}", "model_key": "grat_annuity_payment_annual_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{grat_total_annuity_paid_usd}}", "model_key": "grat_total_annuity_paid_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{grat_projected_remainder_usd}}", "model_key": "grat_projected_remainder_to_children_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{grat_taxable_gift_usd}}", "model_key": "grat_taxable_gift_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{grat_estate_tax_saved_usd}}", "model_key": "grat_estate_tax_saved_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{grat_growth_rate}}", "model_key": "grat_growth_rate", "source": "risk_metrics", "format": "percent"},
                {"placeholder": "{{section_7520_rate_bps}}", "model_key": "section_7520_rate", "source": "risk_metrics", "format": "bps"},
                {"placeholder": "{{taxable_estate_after_grat_usd}}", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{wealth_to_children_grat_usd}}", "source": "forecasts", "format": "currency"},
            ],
            "required_inputs": ["ClientProfile", "RetrievalBundle", "ModelOutputs"],
        },
        {
            "id": "crat_analysis",
            "title": "CRAT Analysis",
            "content_type": "narrative",
            "purpose": (
                "Explain CRAT mechanics under IRC §664, the charitable remainder "
                "structure, annual annuity payments to the donor, charitable "
                "deduction, estate removal, and trade-offs vs GRAT for this client."
            ),
            "expected_placeholders": [
                {"placeholder": "{{crat_trust_corpus_usd}}", "model_key": "crat_trust_corpus_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{crat_annual_annuity_usd}}", "model_key": "crat_annual_annuity_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{crat_total_annuity_paid_usd}}", "model_key": "crat_total_annuity_paid_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{crat_charitable_deduction_usd}}", "model_key": "crat_charitable_deduction_estimate_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{crat_remainder_to_charity_usd}}", "model_key": "crat_remainder_to_charity_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{crat_estate_tax_saved_usd}}", "model_key": "crat_estate_tax_saved_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{crat_payout_rate}}", "model_key": "crat_growth_rate", "source": "risk_metrics", "format": "percent"},
                {"placeholder": "{{taxable_estate_after_crat_usd}}", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{wealth_to_children_crat_usd}}", "source": "forecasts", "format": "currency"},
            ],
            "required_inputs": ["ClientProfile", "RetrievalBundle", "ModelOutputs"],
        },
        {
            "id": "comparison_recommendation",
            "title": "Comparison and Recommendation",
            "content_type": "table",
            "purpose": (
                "Compare GRAT and CRAT strategies side-by-side on key metrics: "
                "estate tax savings, wealth transfer to children, charitable "
                "component, net estate after each strategy. Provide a recommendation "
                "tied to client goals and priorities."
            ),
            "expected_placeholders": [
                {"placeholder": "{{taxable_estate_before_usd}}", "model_key": "taxable_estate_before_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{taxable_estate_after_grat_usd}}", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{taxable_estate_after_crat_usd}}", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{estate_tax_saved_by_grat_usd}}", "model_key": "estate_tax_saved_by_grat_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{estate_tax_saved_by_crat_usd}}", "model_key": "estate_tax_saved_by_crat_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{wealth_to_children_grat_usd}}", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{wealth_to_children_crat_usd}}", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{grat_allocation_weight}}", "model_key": "grat", "source": "allocation_weights", "format": "percent"},
                {"placeholder": "{{crat_allocation_weight}}", "model_key": "crat", "source": "allocation_weights", "format": "percent"},
            ],
            "required_inputs": ["ClientProfile", "RetrievalBundle", "ModelOutputs"],
        },
        {
            "id": "citations_disclosures",
            "title": "Citations and Disclosures",
            "content_type": "chart prose",
            "purpose": (
                "List all supporting citations from allowlisted sources. State "
                "assumptions, limitations, and uncertainties. Include Circular 230 "
                "disclosure language as required."
            ),
            "required_inputs": ["RetrievalBundle"],
        },
    ],
}

outline_path = DATA_DIR / "Outline.json"
outline_path.write_text(
    json.dumps(outline, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(f"Wrote expanded Outline -> {outline_path}")

# Count total placeholders
total_ph = sum(
    len(s.get("expected_placeholders", []))
    for s in outline["sections"]
)
print(f"  Total placeholders: {total_ph}")
