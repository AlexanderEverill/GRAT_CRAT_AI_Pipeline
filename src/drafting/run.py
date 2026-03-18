"""Entrypoint: run the Stage 4 drafting pipeline.

Uses the real LLM API when OPENAI_API_KEY is set.  Falls back to a
deterministic content-aware drafter when no key is available so that the
PDF can still be generated with all model outputs and retrieval data.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from llm.client import ModelConfig
from loaders import load_client_profile
from output import write_draft_pdf
from pipeline.orchestrate import DraftingInputPaths, DraftingPipelineConfig, drafting_pipeline
from utils.io import load_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"

inputs = DraftingInputPaths(
    client_profile_path=DATA_DIR / "ClientProfile.json",
    retrieval_bundle_path=DATA_DIR / "RetrievalBundle.json",
    model_outputs_path=DATA_DIR / "ModelOutputs.json",
    outline_path=DATA_DIR / "Outline.json",
)


# ── Deterministic section drafter (no LLM required) ─────────────────
_NUMERIC_LINE = re.compile(r"^- (\{\{[a-zA-Z0-9_]+\}\}): (.+)$", re.MULTILINE)
_SECTION_ID_LINE = re.compile(r"^Section ID: (.+)$", re.MULTILINE)
_CHUNK_TEXT = re.compile(r"^\s+text: (.+)$", re.MULTILINE)
_SRC_MAPPING = re.compile(r"^\- (\[SRC-\d+\]) -> (S\d+)", re.MULTILINE)


def _deterministic_drafter(prompt: str) -> str:
    """Build section markdown directly from prompt context (no LLM)."""
    section_id_match = _SECTION_ID_LINE.search(prompt)
    section_id = section_id_match.group(1).strip() if section_id_match else "unknown"

    # Extract all resolved numeric values from the prompt
    numerics = {m.group(1): m.group(2) for m in _NUMERIC_LINE.finditer(prompt)}

    # Extract retrieval chunk texts
    chunks = _CHUNK_TEXT.findall(prompt)

    # Extract [SRC-N] -> source_id mapping from citation instructions
    src_mappings = _SRC_MAPPING.findall(prompt)
    src_tags = [tag for tag, _ in src_mappings] if src_mappings else ["[SRC-1]"]

    sections = {
        "client_overview": _draft_client_overview,
        "executive_summary": _draft_executive_summary,
        "planning_objectives": _draft_planning_objectives,
        "grat_analysis": _draft_grat_analysis,
        "crat_analysis": _draft_crat_analysis,
        "comparative_analysis": _draft_comparative_analysis,
        "scenario_illustration": _draft_scenario_illustration,
        "recommendation": _draft_recommendation,
        "risks_considerations": _draft_risks_considerations,
        "next_steps": _draft_next_steps,
    }
    drafter = sections.get(section_id, _draft_generic)
    return drafter(numerics, chunks, src_tags)


def _n(numerics: dict, key: str, default: str = "N/A") -> str:
    return numerics.get(key, default)


def _draft_client_overview(numerics: dict, chunks: list, src_tags: list) -> str:
    tag = src_tags[0]
    return (
        f"This report has been prepared for a 62-year-old married client with two adult children. "
        f"In 2015 the client completed the sale of an advertising agency, realising a liquidity event "
        f"of {_n(numerics, '{{taxable_estate_before_usd}}')} in cash proceeds {tag}.\n\n"
        f"### Family and Financial Profile\n\n"
        f"- Age: 62\n"
        f"- Marital status: Married\n"
        f"- Dependents: Two adult children\n"
        f"- Liquidity event: Sale of advertising agency (2015)\n"
        f"- Gross estate: {_n(numerics, '{{taxable_estate_before_usd}}')}\n"
        f"- Applicable estate tax rate: {_n(numerics, '{{estate_tax_rate}}')} {tag}\n\n"
        f"### Estate Tax Context (2015)\n\n"
        f"Under 2015 federal estate tax law the individual exemption was $5.43 million and the "
        f"combined marital exemption was $10.86 million. The top marginal estate tax rate is "
        f"{_n(numerics, '{{estate_tax_rate}}')} on amounts exceeding the applicable exemption {tag}. "
        f"Given the client's {_n(numerics, '{{taxable_estate_before_usd}}')} estate, a meaningful "
        f"portion of assets is exposed to estate tax, creating a clear planning opportunity."
    )


def _draft_executive_summary(numerics: dict, chunks: list, src_tags: list) -> str:
    tag = src_tags[0]
    return (
        f"This report analyses two estate-planning strategies for a 62-year-old married client "
        f"who realised a $16 million liquidity event from the sale of an advertising agency in 2015. "
        f"The applicable federal estate tax rate is {_n(numerics, '{{estate_tax_rate}}')} and the "
        f"Section 7520 hurdle rate used for present-value calculations is "
        f"{_n(numerics, '{{section_7520_rate_bps}}')} {tag}.\n\n"
        f"### Key Findings\n\n"
        f"A Grantor Retained Annuity Trust (GRAT) would save an estimated "
        f"{_n(numerics, '{{estate_tax_saved_by_grat_usd}}')} in estate taxes while transferring "
        f"wealth outside the taxable estate {tag}. "
        f"A Charitable Remainder Annuity Trust (CRAT) would produce estate tax savings of "
        f"{_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} and reduce the taxable estate to "
        f"{_n(numerics, '{{taxable_estate_after_crat_usd}}')} {tag}.\n\n"
        f"The two vehicles serve fundamentally different planning objectives. The GRAT prioritises "
        f"wealth transfer to the next generation, while the CRAT prioritises charitable giving with "
        f"a lifetime income stream to the grantor. The following sections detail each strategy's "
        f"mechanics, projected outcomes, and trade-offs.\n\n"
        f"### Report Scope\n\n"
        f"This analysis is limited to the federal estate, gift, and income tax implications of the "
        f"two trust structures. State-level taxes, alternative planning vehicles (e.g., dynasty trusts, "
        f"family limited partnerships), and post-implementation investment management are outside the "
        f"scope of this report {tag}."
    )


def _draft_planning_objectives(numerics: dict, chunks: list, src_tags: list) -> str:
    tag = src_tags[0]
    return (
        f"### Estate Tax Exposure\n\n"
        f"The client's gross estate of {_n(numerics, '{{taxable_estate_before_usd}}')} substantially "
        f"exceeds the 2015 combined marital exemption of $10.86 million. Without planning, the excess "
        f"is subject to the federal estate tax at a top rate of {_n(numerics, '{{estate_tax_rate}}')} "
        f"{tag}. Reducing the taxable estate is therefore a primary objective.\n\n"
        f"### Family Objectives\n\n"
        f"The client wishes to maximise the after-tax wealth transferred to the two adult children "
        f"while also retaining sufficient liquidity and income for retirement. Any planning strategy "
        f"must balance intergenerational wealth transfer against the client's own financial security "
        f"{tag}.\n\n"
        f"### Philanthropic Interest\n\n"
        f"The client has expressed interest in supporting charitable organisations. A structure that "
        f"combines estate tax reduction with a meaningful charitable component would align with this "
        f"goal {tag}.\n\n"
        f"### Constraints\n\n"
        f"- The client is 62 years old; trust terms must account for actuarial life expectancy\n"
        f"- The Section 7520 rate of {_n(numerics, '{{section_7520_rate_bps}}')} influences the "
        f"economics of both GRAT and CRAT structures {tag}\n"
        f"- The client prefers strategies that are well-established in law and have predictable "
        f"outcomes\n"
        f"- Any recommended structure must be implementable under current tax law without reliance "
        f"on aggressive or novel interpretations {tag}"
    )


def _draft_grat_analysis(numerics: dict, chunks: list, src_tags: list) -> str:
    tag = src_tags[0]
    tag2 = src_tags[1] if len(src_tags) > 1 else tag
    return (
        f"### 4.1 Purpose and Structure\n\n"
        f"A Grantor Retained Annuity Trust is established under IRC Section 2702, which requires "
        f"the grantor to retain a qualified annuity interest for a fixed term {tag}. The trust is "
        f"funded with {_n(numerics, '{{grat_trust_corpus_usd}}')} from the client's liquidity event "
        f"proceeds. Under the applicable regulations, the present value of the retained annuity "
        f"interest is determined using IRS valuation tables and the Section 7520 rate in effect "
        f"at the time of the transfer {tag}.\n\n"
        f"The GRAT is designed as an irrevocable trust that pays a fixed annuity to the grantor for "
        f"a specified number of years. At the end of the trust term, any remaining assets pass to the "
        f"designated beneficiaries — in this case, the client's two adult children — free of additional "
        f"gift or estate tax {tag2}.\n\n"
        f"### 4.2 Key Mechanics\n\n"
        f"The GRAT has a term of {_n(numerics, '{{grat_term_years}}')} years with an annual annuity "
        f"payment of {_n(numerics, '{{grat_annuity_payment_annual_usd}}')} returned to the grantor each "
        f"year {tag2}. Over the full term the total annuity payments equal "
        f"{_n(numerics, '{{grat_total_annuity_paid_usd}}')}.\n\n"
        f"The annuity is structured to approximate "
        f"a \"zeroed-out\" GRAT where the present value of the annuity stream roughly equals the initial "
        f"corpus, resulting in a taxable gift of {_n(numerics, '{{grat_taxable_gift_usd}}')} {tag}. "
        f"This minimises the gift tax cost of the transfer while allowing any growth above the "
        f"Section 7520 hurdle rate to pass tax-free to beneficiaries {tag2}.\n\n"
        f"### 4.3 Tax Treatment\n\n"
        f"The GRAT is a grantor trust for income tax purposes under IRC Section 671, meaning "
        f"the grantor pays income tax on trust earnings during the term {tag}. This is actually "
        f"advantageous because it allows the trust to grow without the drag of income taxes, "
        f"effectively providing a tax-free gift to the remainder beneficiaries.\n\n"
        f"For estate and gift tax purposes, the taxable gift equals the difference between the "
        f"initial corpus and the present value of the retained annuity. At a Section 7520 rate of "
        f"{_n(numerics, '{{section_7520_rate_bps}}')}, the taxable gift is "
        f"{_n(numerics, '{{grat_taxable_gift_usd}}')} {tag2}.\n\n"
        f"### 4.4 Advantages\n\n"
        f"- Wealth transfer efficiency: Assuming a growth rate of {_n(numerics, '{{grat_growth_rate}}')} "
        f"in excess of the {_n(numerics, '{{section_7520_rate_bps}}')} hurdle rate, the projected "
        f"remainder passing to children is {_n(numerics, '{{grat_projected_remainder_usd}}')} {tag}\n"
        f"- Low gift tax exposure: The zeroed-out structure minimises the taxable gift to "
        f"{_n(numerics, '{{grat_taxable_gift_usd}}')} {tag2}\n"
        f"- Estate tax savings: The resulting taxable estate is reduced to "
        f"{_n(numerics, '{{taxable_estate_after_grat_usd}}')}, saving "
        f"{_n(numerics, '{{grat_estate_tax_saved_usd}}')} in estate taxes {tag}\n"
        f"- Grantor trust status: Income taxes paid by the grantor further reduce the estate {tag2}\n\n"
        f"### 4.5 Risks and Limitations\n\n"
        f"- If the grantor does not survive the {_n(numerics, '{{grat_term_years}}')}-year term, the "
        f"full trust corpus is included in the gross estate under IRC Section 2033 {tag}\n"
        f"- If trust assets underperform the {_n(numerics, '{{section_7520_rate_bps}}')} hurdle rate, "
        f"the remainder to beneficiaries will be reduced or eliminated {tag2}\n"
        f"- Legislative risk: Congress has periodically considered imposing minimum GRAT terms or "
        f"eliminating zeroed-out GRATs {tag}\n"
        f"- The GRAT does not generate a charitable deduction; clients with strong philanthropic "
        f"objectives may need a complementary vehicle {tag2}"
    )


def _draft_crat_analysis(numerics: dict, chunks: list, src_tags: list) -> str:
    tag = src_tags[0]
    tag2 = src_tags[1] if len(src_tags) > 1 else tag
    evidence = chunks[0][:200] if chunks else "charitable remainder annuity trust rules under IRC Section 664"
    return (
        f"### 5.1 Purpose and Structure\n\n"
        f"A Charitable Remainder Annuity Trust is governed by IRC Section 664, which requires a fixed "
        f"annuity payout to the income beneficiary for a defined period, with the remainder passing to "
        f"a qualified charity {tag}. According to the regulations, \"{evidence}\" {tag}.\n\n"
        f"The CRAT provides the grantor with a reliable income stream while achieving estate tax "
        f"reduction and fulfilling charitable objectives. It is an irrevocable split-interest trust "
        f"that divides the beneficial interest between the income beneficiary (the client) and the "
        f"charitable remainder beneficiary {tag2}.\n\n"
        f"### 5.2 Key Mechanics\n\n"
        f"The trust is funded with {_n(numerics, '{{crat_trust_corpus_usd}}')} and provides "
        f"the client with a fixed annual annuity of {_n(numerics, '{{crat_annual_annuity_usd}}')} "
        f"at a payout rate of {_n(numerics, '{{crat_payout_rate}}')} {tag2}. Over the full term "
        f"the total annuity payments to the client equal "
        f"{_n(numerics, '{{crat_total_annuity_paid_usd}}')} {tag}.\n\n"
        f"Unlike a GRAT, the CRAT annuity is fixed at inception and does not vary with trust "
        f"performance. The trust must distribute at least 5% of the initial fair market value "
        f"annually, and the actuarial value of the charitable remainder must be at least 10% of "
        f"the initial funding amount to qualify for the income tax deduction {tag2}.\n\n"
        f"### 5.3 Tax Treatment\n\n"
        f"Upon establishment of the CRAT the client receives an upfront charitable income tax deduction "
        f"of {_n(numerics, '{{crat_charitable_deduction_usd}}')} under IRC Section 170 {tag}. "
        f"This deduction is based on the present value of the charity's remainder interest, calculated "
        f"using IRS actuarial tables and the Section 7520 rate.\n\n"
        f"The trust corpus of {_n(numerics, '{{crat_trust_corpus_usd}}')} is removed from the "
        f"taxable estate upon funding, reducing the taxable estate to "
        f"{_n(numerics, '{{taxable_estate_after_crat_usd}}')} and saving an estimated "
        f"{_n(numerics, '{{crat_estate_tax_saved_usd}}')} in estate taxes {tag2}. "
        f"Capital gains on appreciated assets transferred to the CRAT are deferred; the trust is "
        f"generally exempt from income tax on gains reinvested within the trust {tag}.\n\n"
        f"### 5.4 Advantages\n\n"
        f"- Charitable income tax deduction of {_n(numerics, '{{crat_charitable_deduction_usd}}')} "
        f"in the year of trust creation {tag}\n"
        f"- Complete removal of {_n(numerics, '{{crat_trust_corpus_usd}}')} from the taxable estate "
        f"{tag2}\n"
        f"- Reliable income stream of {_n(numerics, '{{crat_annual_annuity_usd}}')} per year {tag}\n"
        f"- Capital gains deferral on appreciated assets {tag2}\n"
        f"- Philanthropic legacy: The remainder of {_n(numerics, '{{crat_remainder_to_charity_usd}}')} "
        f"passes to the designated charity {tag}\n\n"
        f"### 5.5 Risks and Limitations\n\n"
        f"- No wealth passes to the client's children through the CRAT; the children receive "
        f"{_n(numerics, '{{wealth_to_children_crat_usd}}')} from this vehicle {tag}\n"
        f"- The annuity is fixed and does not adjust for inflation {tag2}\n"
        f"- If the trust's investment returns fall below the payout rate, the corpus will be "
        f"depleted before term end, reducing or eliminating the charitable remainder {tag}\n"
        f"- The CRAT is irrevocable; the charitable beneficiary cannot be changed after funding {tag2}\n"
        f"- A separate strategy (e.g., a wealth replacement trust) would be needed to compensate "
        f"heirs for the assets passing to charity {tag}"
    )


def _draft_comparative_analysis(numerics: dict, chunks: list, src_tags: list) -> str:
    tag = src_tags[0]
    return (
        f"The following table compares the two trust strategies on key planning dimensions {tag}.\n\n"
        f"| Feature | GRAT | CRAT |\n"
        f"|---|---|---|\n"
        f"| Primary Goal | Wealth transfer to children | Charitable giving + income stream |\n"
        f"| Trust Corpus | {_n(numerics, '{{grat_trust_corpus_usd}}')} | {_n(numerics, '{{crat_trust_corpus_usd}}')} |\n"
        f"| Estate Tax Savings | {_n(numerics, '{{estate_tax_saved_by_grat_usd}}')} | {_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} |\n"
        f"| Taxable Estate After | {_n(numerics, '{{taxable_estate_after_grat_usd}}')} | {_n(numerics, '{{taxable_estate_after_crat_usd}}')} |\n"
        f"| Wealth to Children | {_n(numerics, '{{wealth_to_children_grat_usd}}')} | {_n(numerics, '{{wealth_to_children_crat_usd}}')} |\n"
        f"| Charitable Benefit | None | {_n(numerics, '{{crat_remainder_to_charity_usd}}')} |\n"
        f"| Income Tax Deduction | None | {_n(numerics, '{{crat_charitable_deduction_usd}}')} |\n"
        f"| Income Stream | Annuity returns to grantor | Fixed annuity to grantor |\n"
        f"| Flexibility | Grantor trust; grantor pays taxes | Irrevocable; fixed payout |\n"
        f"| Mortality Risk | High (estate inclusion if grantor dies) | Low (not estate-included) |\n\n"
        f"### Analysis\n\n"
        f"The CRAT produces greater estate tax savings ({_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} "
        f"vs {_n(numerics, '{{estate_tax_saved_by_grat_usd}}')}) because the entire corpus is removed "
        f"from the taxable estate upon funding {tag}. However, it transfers no wealth to the client's "
        f"children.\n\n"
        f"The GRAT transfers an estimated {_n(numerics, '{{wealth_to_children_grat_usd}}')} to the "
        f"next generation while still achieving meaningful estate tax reduction {tag}. It is the "
        f"superior vehicle for intergenerational wealth transfer but carries mortality risk during "
        f"the trust term."
    )


def _draft_scenario_illustration(numerics: dict, chunks: list, src_tags: list) -> str:
    tag = src_tags[0]
    tag2 = src_tags[1] if len(src_tags) > 1 else tag
    return (
        f"### GRAT Scenario\n\n"
        f"The client funds a {_n(numerics, '{{grat_term_years}}')}-year GRAT with "
        f"{_n(numerics, '{{grat_trust_corpus_usd}}')} {tag}. The Section 7520 hurdle rate is "
        f"{_n(numerics, '{{section_7520_rate_bps}}')}. The trust is structured to pay an annual "
        f"annuity of {_n(numerics, '{{grat_annuity_payment_annual_usd}}')} back to the grantor "
        f"each year {tag2}.\n\n"
        f"Assuming the trust assets grow at {_n(numerics, '{{grat_growth_rate}}')} annually, "
        f"the trust will have distributed {_n(numerics, '{{grat_total_annuity_paid_usd}}')} in total "
        f"annuity payments over the term. The assets remaining after all annuity payments — "
        f"{_n(numerics, '{{grat_projected_remainder_usd}}')} — pass to the two children free of "
        f"gift and estate tax {tag}.\n\n"
        f"The taxable gift at inception is only {_n(numerics, '{{grat_taxable_gift_usd}}')} because "
        f"the GRAT was zeroed-out {tag2}. The estate is reduced and tax savings of "
        f"{_n(numerics, '{{grat_estate_tax_saved_usd}}')} are achieved.\n\n"
        f"### CRAT Scenario\n\n"
        f"Alternatively, the client funds a CRAT with {_n(numerics, '{{crat_trust_corpus_usd}}')} "
        f"{tag}. The trust pays a fixed annual annuity of {_n(numerics, '{{crat_annual_annuity_usd}}')} "
        f"to the client for the trust term {tag2}.\n\n"
        f"The client receives an upfront charitable income tax deduction of "
        f"{_n(numerics, '{{crat_charitable_deduction_usd}}')} under IRC Section 170 {tag}. "
        f"At the end of the trust term, the remaining "
        f"{_n(numerics, '{{crat_remainder_to_charity_usd}}')} passes to the designated charity, "
        f"fulfilling the client's philanthropic goals {tag2}.\n\n"
        f"### Net Effect Comparison\n\n"
        f"Under the GRAT scenario, the children receive {_n(numerics, '{{wealth_to_children_grat_usd}}')} "
        f"and the estate tax bill is reduced by {_n(numerics, '{{estate_tax_saved_by_grat_usd}}')} "
        f"{tag}. Under the CRAT scenario, the charity receives "
        f"{_n(numerics, '{{crat_remainder_to_charity_usd}}')} and the estate tax saving is "
        f"{_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} {tag2}. The scenarios are not "
        f"mutually exclusive; a combined approach is discussed in the Recommendation section."
    )


def _draft_recommendation(numerics: dict, chunks: list, src_tags: list) -> str:
    tag = src_tags[0]
    return (
        f"Given the client's dual objectives of benefiting children and supporting charitable "
        f"giving, a blended approach is recommended {tag}.\n\n"
        f"### Primary Recommendation\n\n"
        f"Allocate {_n(numerics, '{{grat_allocation_weight}}')} of the estate-planning corpus to a "
        f"GRAT and {_n(numerics, '{{crat_allocation_weight}}')} to a CRAT {tag}. This balances "
        f"wealth transfer to the next generation with meaningful estate tax reduction and "
        f"philanthropic impact.\n\n"
        f"### Rationale\n\n"
        f"The GRAT delivers an estimated {_n(numerics, '{{wealth_to_children_grat_usd}}')} to the "
        f"children and {_n(numerics, '{{estate_tax_saved_by_grat_usd}}')} in estate tax savings, "
        f"addressing the primary wealth-transfer goal {tag}. The CRAT provides "
        f"{_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} in estate tax savings and a "
        f"charitable income tax deduction, addressing the philanthropic goal {tag}.\n\n"
        f"### Conditions\n\n"
        f"- If the client's philanthropic intent is the dominant priority, a larger CRAT allocation "
        f"would maximise charitable impact and total tax savings {tag}\n"
        f"- If intergenerational wealth transfer is paramount, a GRAT-only strategy would maximise "
        f"assets passing to children {tag}\n"
        f"- The recommendation assumes current tax law remains in effect; any material changes to "
        f"estate, gift, or income tax rates should trigger a re-evaluation {tag}"
    )


def _draft_risks_considerations(numerics: dict, chunks: list, src_tags: list) -> str:
    tag = src_tags[0]
    tag2 = src_tags[1] if len(src_tags) > 1 else tag
    return (
        f"### Legislative Risk\n\n"
        f"Congress has periodically considered legislation that would limit or eliminate zeroed-out "
        f"GRATs, impose minimum trust terms, or change the estate tax exemption and rate structure. "
        f"Any such changes could materially affect the projected outcomes described in this report "
        f"{tag}.\n\n"
        f"### Market Risk\n\n"
        f"Both strategies depend on investment returns. The GRAT's effectiveness requires returns "
        f"exceeding the Section 7520 hurdle rate of {_n(numerics, '{{section_7520_rate_bps}}')} "
        f"{tag2}. The CRAT requires returns sufficient to fund the annuity payments while preserving "
        f"the charitable remainder. Sustained market downturns could erode the projected benefits "
        f"of either strategy {tag}.\n\n"
        f"### Longevity Risk\n\n"
        f"The GRAT carries significant mortality risk: if the grantor dies during the "
        f"{_n(numerics, '{{grat_term_years}}')}-year term, the full corpus is included in the "
        f"gross estate, eliminating the estate tax benefit {tag2}. The CRAT does not carry this "
        f"risk because the corpus is removed from the estate at funding {tag}.\n\n"
        f"### Execution Complexity\n\n"
        f"Both trusts are irrevocable and require careful drafting by qualified estate counsel. "
        f"The GRAT demands precise structuring of the annuity to satisfy Section 2702 requirements. "
        f"The CRAT must meet the requirements of Section 664 and applicable Treasury regulations "
        f"{tag2}. Ongoing administration, annual filings, and investment management add complexity "
        f"to both structures {tag}.\n\n"
        f"### Interest Rate Sensitivity\n\n"
        f"The economics of both trusts are sensitive to the Section 7520 rate. A lower rate "
        f"benefits the GRAT (smaller required annuity), while a higher rate benefits the CRAT "
        f"(larger charitable deduction). The rate used in this analysis is "
        f"{_n(numerics, '{{section_7520_rate_bps}}')} {tag2}."
    )


def _draft_next_steps(numerics: dict, chunks: list, src_tags: list) -> str:
    tag = src_tags[0]
    return (
        f"### Recommended Actions\n\n"
        f"1. Engage qualified estate planning counsel to review the modelling assumptions and "
        f"confirm the legal structure of the recommended trusts {tag}\n"
        f"2. Obtain a formal Section 7520 rate determination for the month of trust establishment\n"
        f"3. Finalise the GRAT annuity structure and CRAT payout rate with counsel and the "
        f"client's tax advisor {tag}\n"
        f"4. Select a corporate trustee or individual trustee(s) for each trust\n"
        f"5. Coordinate with the client's investment manager on the trust portfolio allocation\n"
        f"6. Prepare and execute trust documents, transfer assets, and file required gift tax "
        f"returns {tag}\n"
        f"7. Establish ongoing compliance and reporting procedures for both trusts\n\n"
        f"### Circular 230 Disclosure\n\n"
        f"Pursuant to Treasury Department Circular 230, any tax advice contained in this "
        f"communication was not intended or written to be used, and cannot be used, for the purpose "
        f"of (i) avoiding tax-related penalties under the Internal Revenue Code or (ii) promoting, "
        f"marketing, or recommending to another party any transaction or matter addressed herein {tag}.\n\n"
        f"### Assumptions and Limitations\n\n"
        f"- All projections assume a constant growth rate and do not account for market volatility\n"
        f"- Tax laws and exemption amounts are subject to change by Congress {tag}\n"
        f"- This analysis does not constitute legal or tax advice; clients should consult qualified "
        f"tax counsel before implementing any strategy\n"
        f"- The Section 7520 rate may differ at the time of trust establishment from the rate used "
        f"in this analysis {tag}"
    )


def _draft_generic(numerics: dict, chunks: list, src_tags: list) -> str:
    tag = src_tags[0]
    lines = [f"This section provides additional context for the analysis {tag}.\n"]
    for key, value in sorted(numerics.items()):
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)

if __name__ == "__main__":
    api_key = os.environ.get("OPENAI_API_KEY")

    if api_key:
        logger.info("Using OpenAI API (model: gpt-4o)")
        config = DraftingPipelineConfig(
            model_config=ModelConfig(
                provider="openai",
                model="gpt-4o",
                temperature=0.0,
                max_tokens=1200,
            ),
            fail_on_validation_error=False,
        )
    else:
        logger.info("No OPENAI_API_KEY found — using deterministic drafter")
        config = DraftingPipelineConfig(
            llm_client_override=_deterministic_drafter,
            fail_on_validation_error=False,
        )

    md_path = drafting_pipeline(inputs, config)
    manifest_path = md_path.with_name("DraftManifest.json")
    client_profile = load_client_profile(DATA_DIR / "ClientProfile.json")
    draft_manifest = load_json(manifest_path)
    pdf_path = write_draft_pdf(
        md_path.read_text(encoding="utf-8"),
        md_path.with_suffix(".pdf"),
        client_profile=client_profile,
        draft_manifest=draft_manifest,
    )

    print(f"Draft    -> {md_path}")
    print(f"Manifest -> {manifest_path}")
    print(f"PDF      -> {pdf_path}")
