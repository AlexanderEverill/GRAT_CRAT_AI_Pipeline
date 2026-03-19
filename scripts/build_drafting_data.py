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

# ── Build source_id → cite_key mapping (1:1 from new manifest) ────────
source_to_cite: dict[str, str] = {}
for c in citations_manifest["citations"]:
    source_to_cite[c["source_id"]] = c["cite_key"]

# ── Convert topic key_points → drafting chunks ────────────────────────
# The new bundle embeds cite_key and source_id on every key_point,
# so we use them directly instead of guessing from a topic map.
# Selection strategy: ensure at least one key_point per unique source,
# then fill remaining slots with the longest quotes for richness.
MAX_PER_TOPIC = 10
chunks: list[dict] = []

for item in real_bundle["items"]:
    topic = item["source_id"]  # topic name
    section_tags = TOPIC_SECTION_MAP.get(topic, [])

    key_points = item.get("key_points", [])

    # First pass: pick the best key_point per unique source_id
    by_source: dict[str, list[dict]] = {}
    for kp in key_points:
        sid = kp.get("source_id", "")
        by_source.setdefault(sid, []).append(kp)

    selected: list[dict] = []
    selected_keys: set[tuple] = set()
    for sid, kps in sorted(by_source.items()):
        best = max(kps, key=lambda kp: len(kp.get("quote", "")))
        key = (best.get("source_id"), best.get("quote"))
        selected.append(best)
        selected_keys.add(key)

    # Second pass: fill remaining slots with longest quotes (any source)
    remaining = sorted(key_points, key=lambda kp: len(kp.get("quote", "")), reverse=True)
    for kp in remaining:
        if len(selected) >= MAX_PER_TOPIC:
            break
        key = (kp.get("source_id"), kp.get("quote"))
        if key not in selected_keys:
            selected.append(kp)
            selected_keys.add(key)

    for i, kp in enumerate(selected):
        src_id = kp.get("source_id", "")
        cite_key = kp.get("cite_key") or source_to_cite.get(src_id, f"[{src_id}]")

        chunks.append({
            "source_id": src_id,
            "score": round(0.95 - (i * 0.02), 3),
            "text": kp.get("quote", "").strip(),
            "citation_key": cite_key,
            "section_tags": section_tags,
            "topic": topic,
        })

# ── Build citation manifest for the drafting bundle ───────────────────
# Include ALL manifest citations so every source is available for citing,
# even if no chunks were retrieved for that source (e.g. sparse HTML).
drafting_citations = list(citations_manifest["citations"])

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
used_cite_keys = set(c["citation_key"] for c in chunks)
print(f"Wrote {len(chunks)} chunks -> {out_path}")
print(f"  {len(used_cite_keys)} cite keys with chunks; {len(drafting_citations)} total in manifest")
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
                "strategies. REQUIRED: (1) Explain the \u00a77520 hurdle rate and its role in both trusts. "
                "(2) State the GRAT mortality risk explicitly \u2014 a 62-year-old must survive a 10-year term "
                "to age 72, with approximately 15-20% actuarial mortality probability during the term based "
                "on IRS Table 90CM. (3) Note the CRAT carries no equivalent mortality risk. (4) State a clear "
                "recommendation: GRAT as PRIMARY for wealth transfer to children, CRAT as COMPLEMENTARY for "
                "philanthropy. (5) Cite specific dollar figures for estate tax savings and wealth transfer for "
                "both strategies. The recommendation wording here must be identical to the recommendation "
                "in the Comparison and Recommendation section."
            ),
            "expected_placeholders": [
                {"placeholder": "{{estate_tax_rate}}", "model_key": "estate_tax_rate", "source": "risk_metrics", "format": "percent"},
                {"placeholder": "{{section_7520_rate_bps}}", "model_key": "section_7520_rate", "source": "risk_metrics", "format": "bps"},
                {"placeholder": "{{taxable_estate_before_usd}}", "model_key": "taxable_estate_before_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{estate_tax_saved_by_grat_usd}}", "model_key": "estate_tax_saved_by_grat_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{estate_tax_saved_by_crat_usd}}", "model_key": "estate_tax_saved_by_crat_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{client_age}}", "model_key": "client_age", "source": "forecasts", "format": "number"},
                {"placeholder": "{{grat_term_years}}", "model_key": "grat_term_years", "source": "forecasts", "format": "number"},
                {"placeholder": "{{crat_term_years}}", "model_key": "crat_term_years", "source": "forecasts", "format": "number"},
                {"placeholder": "{{wealth_to_children_grat_usd}}", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{crat_charitable_deduction_usd}}", "model_key": "crat_charitable_deduction_estimate_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{crat_remainder_to_charity_usd}}", "model_key": "crat_remainder_to_charity_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{grat_growth_rate}}", "model_key": "grat_growth_rate", "source": "risk_metrics", "format": "percent"},
                {"placeholder": "{{crat_payout_rate}}", "model_key": "crat_payout_rate", "source": "risk_metrics", "format": "percent"},
                {"placeholder": "{{wealth_to_children_crat_usd}}", "source": "forecasts", "format": "currency"},
            ],
            "required_inputs": ["ClientProfile", "ModelOutputs"],
        },
        {
            "id": "grat_analysis",
            "title": "GRAT Analysis",
            "content_type": "narrative",
            "purpose": (
                "Explain GRAT mechanics under IRC \u00a72702, projected outcomes for this "
                "client, annuity payment structure, remainder to beneficiaries, gift "
                "tax implications, and planning considerations. REQUIRED: (1) Define the \u00a77520 rate "
                "as the IRS-prescribed hurdle rate; state its numeric value and compute the explicit spread "
                "between the assumed growth rate and the \u00a77520 rate. (2) Explain grantor-trust treatment "
                "under IRC \u00a7671. (3) Provide an explicit mortality-risk analysis: state that a 62-year-old "
                "must survive to age 72, cite approximate 15-20% mortality probability from IRS actuarial "
                "tables, and explain the binary consequence under IRC \u00a72033. (4) Justify the 10-year term "
                "selection vs shorter rolling GRATs and longer terms. (5) State the zeroed-out structure "
                "and resulting $0 taxable gift."
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
                {"placeholder": "{{client_age}}", "model_key": "client_age", "source": "forecasts", "format": "number"},
                {"placeholder": "{{estate_tax_rate}}", "model_key": "estate_tax_rate", "source": "risk_metrics", "format": "percent"},
                {"placeholder": "{{crat_payout_rate}}", "model_key": "crat_payout_rate", "source": "risk_metrics", "format": "percent"},
            ],
            "required_inputs": ["ClientProfile", "RetrievalBundle", "ModelOutputs"],
        },
        {
            "id": "crat_analysis",
            "title": "CRAT Analysis",
            "content_type": "narrative",
            "purpose": (
                "Explain CRAT mechanics under IRC \u00a7664, the charitable remainder "
                "structure, annual annuity payments to the donor, charitable "
                "deduction, estate removal, and trade-offs vs GRAT for this client. "
                "REQUIRED: (1) Explain both lifetime and term-of-years CRAT structures; state the "
                "20-year maximum for a term-of-years CRAT under 26 CFR \u00a71.664-2. (2) Explain the "
                "10% charitable remainder minimum and state whether this CRAT clears the threshold. "
                "(3) Explain the four-tier taxation of CRAT distributions under IRC \u00a7664. "
                "(4) Explain estate tax treatment under IRC \u00a72036. (5) Compare CRAT performance "
                "dependence (payout rate) vs GRAT performance dependence (\u00a77520 rate). "
                "(6) Note the CRAT carries NO mortality risk equivalent to the GRAT."
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
                {"placeholder": "{{crat_term_years}}", "model_key": "crat_term_years", "source": "forecasts", "format": "number"},
                {"placeholder": "{{client_age}}", "model_key": "client_age", "source": "forecasts", "format": "number"},
                {"placeholder": "{{section_7520_rate_bps}}", "model_key": "section_7520_rate", "source": "risk_metrics", "format": "bps"},
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
                "tied to client goals and priorities. REQUIRED: (1) Include a comprehensive comparison "
                "table. (2) Provide a Performance Dependence Comparison subsection with explicit spread "
                "calculations. (3) Provide a Mortality-Risk Analysis subsection quantifying the risk for "
                "a 62-year-old. (4) State the IDENTICAL recommendation as the Executive Summary: GRAT as "
                "PRIMARY for wealth transfer, CRAT as COMPLEMENTARY for philanthropy."
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
                {"placeholder": "{{client_age}}", "model_key": "client_age", "source": "forecasts", "format": "number"},
                {"placeholder": "{{crat_term_years}}", "model_key": "crat_term_years", "source": "forecasts", "format": "number"},
                {"placeholder": "{{grat_term_years}}", "model_key": "grat_term_years", "source": "forecasts", "format": "number"},
                {"placeholder": "{{crat_charitable_deduction_usd}}", "model_key": "crat_charitable_deduction_estimate_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{crat_remainder_to_charity_usd}}", "model_key": "crat_remainder_to_charity_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{grat_projected_remainder_usd}}", "model_key": "grat_projected_remainder_to_children_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{section_7520_rate_bps}}", "model_key": "section_7520_rate", "source": "risk_metrics", "format": "bps"},
                {"placeholder": "{{grat_trust_corpus_usd}}", "model_key": "grat_trust_corpus_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{crat_trust_corpus_usd}}", "model_key": "crat_trust_corpus_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{grat_annuity_payment_annual_usd}}", "model_key": "grat_annuity_payment_annual_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{crat_annual_annuity_usd}}", "model_key": "crat_annual_annuity_usd", "source": "forecasts", "format": "currency"},
                {"placeholder": "{{grat_growth_rate}}", "model_key": "grat_growth_rate", "source": "risk_metrics", "format": "percent"},
                {"placeholder": "{{crat_payout_rate}}", "model_key": "crat_payout_rate", "source": "risk_metrics", "format": "percent"},
                {"placeholder": "{{estate_tax_rate}}", "model_key": "estate_tax_rate", "source": "risk_metrics", "format": "percent"},
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
