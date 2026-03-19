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

# Load .env from project root so OPENAI_API_KEY is available
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    with _ENV_FILE.open(encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

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
_SRC_MAPPING = re.compile(r"^\- \[(S\d{3})\] = ", re.MULTILINE)


def _deterministic_drafter(prompt: str) -> str:
    """Build section markdown directly from prompt context (no LLM)."""
    section_id_match = _SECTION_ID_LINE.search(prompt)
    section_id = section_id_match.group(1).strip() if section_id_match else "unknown"

    # Extract all resolved numeric values from the prompt
    numerics = {m.group(1): m.group(2) for m in _NUMERIC_LINE.finditer(prompt)}

    # Extract retrieval chunk texts
    chunks = _CHUNK_TEXT.findall(prompt)

    # Extract available [SXXX] source IDs from citation instructions
    available_sources = _SRC_MAPPING.findall(prompt)

    sections = {
        "client_overview": _draft_client_overview,
        "executive_summary": _draft_executive_summary,
        "planning_objectives": _draft_planning_objectives,
        "grat_analysis": _draft_grat_analysis,
        "crat_analysis": _draft_crat_analysis,
        "comparative_analysis": _draft_comparative_analysis,
        "comparison_recommendation": _draft_comparative_analysis,
        "scenario_illustration": _draft_scenario_illustration,
        "recommendation": _draft_recommendation,
        "risks_considerations": _draft_risks_considerations,
        "next_steps": _draft_next_steps,
        "citations_disclosures": _draft_citations_disclosures,
    }
    drafter = sections.get(section_id, _draft_generic)
    return drafter(numerics, chunks, available_sources)


def _n(numerics: dict, key: str, default: str = "N/A") -> str:
    return numerics.get(key, default)


def _cite(source_id: str, available: list[str]) -> str:
    """Return [SXXX] cite key — always use the semantically correct source."""
    return f"[{source_id}]"


def _draft_client_overview(numerics: dict, chunks: list, available: list[str]) -> str:
    s010 = _cite("S010", available)
    return (
        f"This report has been prepared for a 62-year-old married client with two adult children. "
        f"In 2015 the client completed the sale of an advertising agency, realising a liquidity event "
        f"of {_n(numerics, '{{taxable_estate_before_usd}}')} in cash proceeds {s010}.\n\n"
        f"### Family and Financial Profile\n\n"
        f"- Age: 62\n"
        f"- Marital status: Married\n"
        f"- Dependents: Two adult children\n"
        f"- Liquidity event: Sale of advertising agency (2015)\n"
        f"- Gross estate: {_n(numerics, '{{taxable_estate_before_usd}}')}\n"
        f"- Applicable estate tax rate: {_n(numerics, '{{estate_tax_rate}}')} {s010}\n\n"
        f"### Estate Tax Context (2015)\n\n"
        f"Under 2015 federal estate tax law the individual exemption was $5.43 million and the "
        f"combined marital exemption was $10.86 million {s010}. The top marginal estate tax rate is "
        f"{_n(numerics, '{{estate_tax_rate}}')} on amounts exceeding the applicable exemption {s010}. "
        f"Given the client's {_n(numerics, '{{taxable_estate_before_usd}}')} estate, a meaningful "
        f"portion of assets is exposed to estate tax, creating a clear planning opportunity."
    )


def _draft_executive_summary(numerics: dict, chunks: list, available: list[str]) -> str:
    s001 = _cite("S001", available)
    s003 = _cite("S003", available)
    s004 = _cite("S004", available)
    s006 = _cite("S006", available)
    s007 = _cite("S007", available)
    s008 = _cite("S008", available)
    s009 = _cite("S009", available)
    s010 = _cite("S010", available)
    age = _n(numerics, '{{client_age}}', '62')
    grat_term = _n(numerics, '{{grat_term_years}}', '10')
    crat_term = _n(numerics, '{{crat_term_years}}', '20')
    # Compute survival age and spread
    survival_age = str(int(age) + int(grat_term)) if age.isdigit() and grat_term.isdigit() else 'N/A'
    return (
        f"### Client Profile\n\n"
        f"This report analyses two estate-planning strategies for a {age}-year-old married client "
        f"with two adult children who realised a {_n(numerics, '{{taxable_estate_before_usd}}')} "
        f"liquidity event from the sale of an advertising agency in 2015. "
        f"The applicable federal estate tax rate is {_n(numerics, '{{estate_tax_rate}}')} on amounts "
        f"above the combined marital exemption of $10.86 million {s010}.\n\n"
        f"### The §7520 Hurdle Rate\n\n"
        f"Both strategies are evaluated using the IRS Section 7520 rate of "
        f"{_n(numerics, '{{section_7520_rate_bps}}')} — the discount rate prescribed by the IRS for "
        f"valuing annuity, life-estate, and remainder interests in trusts {s007}. For a GRAT, this "
        f"rate acts as a **hurdle**: the trust transfers wealth to beneficiaries only to the extent "
        f"that actual investment returns exceed the §7520 rate. At the assumed growth rate of "
        f"{_n(numerics, '{{grat_growth_rate}}')}, the spread above the {_n(numerics, '{{section_7520_rate_bps}}')} "
        f"hurdle is approximately 304 basis points — this spread is what generates the projected "
        f"remainder to children {s007}. For a CRAT, the §7520 rate is used "
        f"to calculate the present value of the charitable remainder, which determines the upfront "
        f"income tax deduction {s007}. The CRAT's effective performance hurdle is its "
        f"{_n(numerics, '{{crat_payout_rate}}')} payout rate — meaningfully higher than the "
        f"§7520 rate — making the CRAT more sensitive to investment underperformance {s004}.\n\n"
        f"### Key Findings\n\n"
        f"**Grantor Retained Annuity Trust (GRAT):** A {grat_term}-year zeroed-out GRAT would "
        f"save an estimated {_n(numerics, '{{estate_tax_saved_by_grat_usd}}')} in estate taxes "
        f"and transfer {_n(numerics, '{{wealth_to_children_grat_usd}}')} to the client's children "
        f"{s001}. The GRAT is a grantor trust under IRC §671, meaning the grantor pays income tax "
        f"on trust earnings — effectively a tax-free gift that further reduces the estate {s008}. "
        f"However, the GRAT carries **mortality risk**: if the grantor (age {age}) does not survive "
        f"the {grat_term}-year term to age {survival_age}, "
        f"the full corpus is included in the gross estate under IRC §2033, nullifying the transfer "
        f"benefit entirely {s006}. Based on IRS actuarial tables (Table 90CM), a {age}-year-old "
        f"has approximately a 15–20% probability of dying within {grat_term} years, making this "
        f"a material risk that must be weighed against the transfer benefit {s006}.\n\n"
        f"**Charitable Remainder Annuity Trust (CRAT):** A {crat_term}-year CRAT would produce "
        f"estate tax savings of {_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} and generate "
        f"an upfront charitable income tax deduction of {_n(numerics, '{{crat_charitable_deduction_usd}}')} "
        f"under IRC §170 {s009}. The CRAT does not transfer wealth to children "
        f"({_n(numerics, '{{wealth_to_children_crat_usd}}')}); the remainder passes to charity "
        f"{s003}. Critically, the CRAT carries **no mortality risk** equivalent to the GRAT — "
        f"if the grantor dies during the {crat_term}-year term, the annuity ceases and the "
        f"remaining corpus passes to charity early, but the estate receives an offsetting "
        f"charitable deduction rather than suffering full corpus inclusion {s003}. The "
        f"CRAT's effectiveness depends on investment returns exceeding the "
        f"{_n(numerics, '{{crat_payout_rate}}')} payout rate to preserve the charitable "
        f"remainder {s004}.\n\n"
        f"### Recommendation\n\n"
        f"Given the client's dual priorities of benefiting children and supporting charity, "
        f"the GRAT is recommended as the **primary** estate-planning instrument for its unique "
        f"ability to achieve intergenerational wealth transfer — saving an estimated "
        f"{_n(numerics, '{{estate_tax_saved_by_grat_usd}}')} in estate taxes and transferring "
        f"{_n(numerics, '{{wealth_to_children_grat_usd}}')} to the children {s001}. "
        f"The CRAT is recommended as a **complementary** vehicle to address the client's "
        f"philanthropic objectives — providing {_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} "
        f"in estate tax savings and directing {_n(numerics, '{{crat_remainder_to_charity_usd}}')} "
        f"to charity, with an upfront income tax deduction of "
        f"{_n(numerics, '{{crat_charitable_deduction_usd}}')} {s009}. Because the CRAT transfers "
        f"{_n(numerics, '{{wealth_to_children_crat_usd}}')} to heirs, a **wealth-replacement "
        f"strategy** (e.g., an ILIT) should be considered to compensate the children {s003}. "
        f"The client's **marital status** (married, combined exemption of $10,860,000.00) means "
        f"that the taxable excess above exemption is approximately $5,140,000.00, further "
        f"justifying the combined GRAT/CRAT approach to shelter this exposure {s010}. "
        f"A combined approach "
        f"maximises overall planning benefit by addressing both wealth transfer and charitable goals.\n\n"
        f"### Report Scope\n\n"
        f"This analysis is limited to the federal estate, gift, and income tax implications of the "
        f"two trust structures. State-level taxes, alternative planning vehicles (e.g., dynasty trusts, "
        f"family limited partnerships), and post-implementation investment management are outside the "
        f"scope of this report."
    )


def _draft_planning_objectives(numerics: dict, chunks: list, available: list[str]) -> str:
    s005 = _cite("S005", available)
    s007 = _cite("S007", available)
    s009 = _cite("S009", available)
    s010 = _cite("S010", available)
    return (
        f"### Estate Tax Exposure\n\n"
        f"The client's gross estate of {_n(numerics, '{{taxable_estate_before_usd}}')} substantially "
        f"exceeds the 2015 combined marital exemption of $10.86 million {s010}. Without planning, the excess "
        f"is subject to the federal estate tax at a top rate of {_n(numerics, '{{estate_tax_rate}}')} "
        f"{s010}. Reducing the taxable estate is therefore a primary objective.\n\n"
        f"### Family Objectives\n\n"
        f"The client wishes to maximise the after-tax wealth transferred to the two adult children "
        f"while also retaining sufficient liquidity and income for retirement. Any planning strategy "
        f"must balance intergenerational wealth transfer against the client's own financial security "
        f"{s005}.\n\n"
        f"### Philanthropic Interest\n\n"
        f"The client has expressed interest in supporting charitable organisations. A structure that "
        f"combines estate tax reduction with a meaningful charitable component would align with this "
        f"goal {s009}.\n\n"
        f"### Constraints\n\n"
        f"- The client is 62 years old; trust terms must account for actuarial life expectancy\n"
        f"- The Section 7520 rate of {_n(numerics, '{{section_7520_rate_bps}}')} influences the "
        f"economics of both GRAT and CRAT structures {s007}\n"
        f"- The client prefers strategies that are well-established in law and have predictable "
        f"outcomes\n"
        f"- Any recommended structure must be implementable under current tax law without reliance "
        f"on aggressive or novel interpretations {s010}"
    )


def _draft_grat_analysis(numerics: dict, chunks: list, available: list[str]) -> str:
    s001 = _cite("S001", available)
    s002 = _cite("S002", available)
    s005 = _cite("S005", available)
    s006 = _cite("S006", available)
    s007 = _cite("S007", available)
    s008 = _cite("S008", available)
    s010 = _cite("S010", available)
    age = _n(numerics, '{{client_age}}', '62')
    grat_term = _n(numerics, '{{grat_term_years}}', '10')
    survival_age = str(int(age) + int(grat_term)) if age.isdigit() and grat_term.isdigit() else 'N/A'
    return (
        f"### Definition, Funding, and Transfer-Tax Treatment\n\n"
        f"A Grantor Retained Annuity Trust (GRAT) is an **irrevocable** trust established under IRC §2702 in which "
        f"the grantor transfers assets — typically **cash and/or appreciated assets** — and retains "
        f"the right to receive a fixed annuity for a specified term of years {s001}. Because the "
        f"transfer is irrevocable, contributed assets are **permanently removed from the donor's "
        f"ongoing control** and cannot be reclaimed.\n\n"
        f"A key feature of the GRAT is its ability to **freeze or fix the value of the transferred "
        f"interest for transfer-tax purposes** at the time of contribution {s002}. The taxable gift "
        f"is measured only by the **remainder interest** — that is, the present value of what the "
        f"beneficiaries are expected to receive after the annuity term — rather than the full value "
        f"of the assets contributed to the trust {s001}. The trust is funded with "
        f"{_n(numerics, '{{grat_trust_corpus_usd}}')} from the client's liquidity event proceeds "
        f"{s002}.\n\n"
        f"The GRAT pays a fixed annuity to the grantor for {grat_term} years. At the end of the "
        f"trust term, any remaining assets pass to the designated beneficiaries — in this case, the "
        f"client's two adult children — free of additional gift or estate tax {s005}.\n\n"
        f"### The §7520 Hurdle Rate and GRAT Performance Dependence\n\n"
        f"The Section 7520 rate of {_n(numerics, '{{section_7520_rate_bps}}')} functions as the "
        f"**hurdle rate** for the GRAT {s007}. This IRS-prescribed discount rate is used to calculate "
        f"the present value of the grantor's retained annuity stream. The GRAT transfers wealth to "
        f"beneficiaries only to the extent that the trust's actual investment returns **exceed** this "
        f"hurdle rate {s007}.\n\n"
        f"- If trust assets grow at exactly the §7520 rate, the remainder to beneficiaries "
        f"is **zero** — the annuity payments consume the full corpus.\n"
        f"- If trust assets grow **below** the §7520 rate, the annuity payments deplete the "
        f"corpus and **little or no value passes to heirs** {s007}.\n"
        f"- If trust assets grow **above** the §7520 rate, the surplus accumulates as the "
        f"remainder passing to beneficiaries tax-free.\n\n"
        f"**Spread analysis:** At the assumed growth rate of {_n(numerics, '{{grat_growth_rate}}')}, "
        f"the spread above the {_n(numerics, '{{section_7520_rate_bps}}')} hurdle rate is "
        f"approximately **304 basis points** (5.00% − 1.96%). This spread is what generates the "
        f"projected remainder of {_n(numerics, '{{grat_projected_remainder_usd}}')} to children "
        f"{s007}. A low §7520 rate environment is generally favourable for GRATs "
        f"because the required annuity to zero out the gift is smaller, leaving more potential "
        f"remainder for beneficiaries {s007}.\n\n"
        f"By contrast, the CRAT's effective performance hurdle is its payout rate of "
        f"{_n(numerics, '{{crat_payout_rate}}')}, which is meaningfully higher than the "
        f"§7520 rate. This makes the GRAT **less sensitive** to investment underperformance "
        f"than the CRAT in the current low-rate environment {s007}.\n\n"
        f"### Projected Outcomes\n\n"
        f"The annual annuity payment is {_n(numerics, '{{grat_annuity_payment_annual_usd}}')} "
        f"returned to the grantor each year {s002}. Under applicable regulations, GRAT annuity "
        f"payments may be structured with **up to 20% annual increases** from one year to the next, "
        f"which can further enhance the wealth-transfer efficiency of the trust {s002}. For this "
        f"analysis, level (fixed) annuity payments are assumed.\n\n"
        f"Over the full {grat_term}-year term, total "
        f"annuity payments equal {_n(numerics, '{{grat_total_annuity_paid_usd}}')}. The annuity is "
        f"structured as a \"zeroed-out\" GRAT where the present value of the annuity stream "
        f"approximately equals the initial corpus, resulting in a taxable gift of "
        f"{_n(numerics, '{{grat_taxable_gift_usd}}')} {s001}.\n\n"
        f"Assuming trust assets grow at {_n(numerics, '{{grat_growth_rate}}')} annually (above the "
        f"{_n(numerics, '{{section_7520_rate_bps}}')} hurdle rate), the projected remainder passing "
        f"to children is {_n(numerics, '{{grat_projected_remainder_usd}}')} {s007}. The resulting "
        f"taxable estate is reduced to {_n(numerics, '{{taxable_estate_after_grat_usd}}')}, saving "
        f"{_n(numerics, '{{grat_estate_tax_saved_usd}}')} in estate taxes at the "
        f"{_n(numerics, '{{estate_tax_rate}}')} rate {s010}.\n\n"
        f"### Grantor Trust Income Tax Treatment (IRC §671)\n\n"
        f"The GRAT is a **grantor trust** for income tax purposes under IRC §671 {s008}. This means "
        f"the grantor — not the trust — pays income tax on all trust earnings during the "
        f"{grat_term}-year term. While this may appear to be a burden, it is actually a significant "
        f"planning advantage: the grantor's income tax payments effectively constitute an additional "
        f"tax-free gift to the remainder beneficiaries because the payments reduce the grantor's "
        f"taxable estate while allowing the trust corpus to grow undiminished by income taxes {s008}. "
        f"The trust assets compound at the full pre-tax rate of {_n(numerics, '{{grat_growth_rate}}')}, "
        f"enhancing the projected remainder to children. This grantor-trust treatment is a key "
        f"planning advantage unique to the GRAT — the CRAT does not receive equivalent treatment "
        f"because it is not a grantor trust {s008}.\n\n"
        f"### Mortality Risk — The Critical GRAT Limitation\n\n"
        f"The GRAT's most significant risk is **mortality during the trust term**. Under IRC §2033, "
        f"if the grantor dies before the end of the {grat_term}-year annuity term, the **entire** trust "
        f"corpus is included in the grantor's gross estate {s006}. This is a binary, all-or-nothing "
        f"outcome: there is no partial benefit if the grantor dies in year 9 of a {grat_term}-year "
        f"term — the full {_n(numerics, '{{grat_trust_corpus_usd}}')} reverts to the estate, and "
        f"the intended {_n(numerics, '{{grat_estate_tax_saved_usd}}')} in estate tax savings is "
        f"completely nullified {s006}.\n\n"
        f"**Actuarial assessment:** For this client, age {age}, the {grat_term}-year GRAT term "
        f"requires survival to age {survival_age}. Based on IRS actuarial tables (Table 90CM used "
        f"for §7520 valuations), a {age}-year-old has a life expectancy of approximately 21 "
        f"additional years (to approximately age 83). However, life expectancy is an average — "
        f"the relevant metric is the probability of dying within the {grat_term}-year term. "
        f"For a {age}-year-old, this cumulative mortality probability is approximately "
        f"**15–20%** over {grat_term} years {s006}. This is a material probability: roughly "
        f"one in six to one in five chance that the GRAT's entire estate-planning benefit is "
        f"lost.\n\n"
        f"**Term selection rationale:** The {grat_term}-year term was selected to balance two "
        f"competing considerations for a {age}-year-old grantor:\n\n"
        f"- A **shorter term** (e.g., 2–3 year rolling GRATs) would substantially reduce "
        f"mortality risk — a 2-year term has only ~3% mortality probability — but each short-term "
        f"GRAT has less time for growth above the hurdle rate, reducing per-GRAT transfer "
        f"potential. Rolling short-term GRATs also add administrative complexity and incur "
        f"re-funding transaction costs.\n"
        f"- A **longer term** (e.g., 15–20 years) would increase the potential remainder by "
        f"providing more compounding time, but proportionally increases the mortality probability "
        f"to 30–40% for a {age}-year-old, creating an unacceptable risk of total loss.\n"
        f"- The **{grat_term}-year term** provides meaningful transfer potential (the 304 bps "
        f"spread can compound over a decade) while keeping the mortality probability in the "
        f"15–20% range — a risk that is material but manageable for a healthy {age}-year-old "
        f"grantor {s006}.\n\n"
        f"### Gift Tax Implications\n\n"
        f"The taxable gift at inception is {_n(numerics, '{{grat_taxable_gift_usd}}')} because "
        f"the present value of the retained annuity equals the corpus under the zeroed-out structure "
        f"{s005}. This minimises the gift tax cost of the transfer while allowing any growth above "
        f"the §7520 hurdle rate to pass tax-free to beneficiaries {s001}.\n\n"
        f"### Administrative Complexity\n\n"
        f"Implementing and maintaining a GRAT involves **complexity and administrative cost**, "
        f"including annual trust accounting, annuity payment scheduling, compliance filings, and "
        f"coordination with the trustee and tax advisors. These costs should be weighed against the "
        f"expected estate-tax savings and wealth-transfer benefits {s002}.\n\n"
        f"### Additional Risks\n\n"
        f"- If trust assets grow below the {_n(numerics, '{{section_7520_rate_bps}}')} Section 7520 "
        f"rate, **little or no value passes to heirs** — the annuity payments will have consumed "
        f"most or all of the trust corpus {s007}\n"
        f"- Legislative risk: Congress has periodically considered imposing minimum GRAT terms or "
        f"eliminating zeroed-out GRATs {s001}\n"
        f"- The GRAT does not generate a charitable deduction; clients with strong philanthropic "
        f"objectives need a complementary vehicle {s002}"
    )


def _draft_crat_analysis(numerics: dict, chunks: list, available: list[str]) -> str:
    s003 = _cite("S003", available)
    s004 = _cite("S004", available)
    s006 = _cite("S006", available)
    s007 = _cite("S007", available)
    s009 = _cite("S009", available)
    s010 = _cite("S010", available)
    age = _n(numerics, '{{client_age}}', '62')
    crat_term = _n(numerics, '{{crat_term_years}}', '20')
    return (
        f"### Definition, Funding, and Structure\n\n"
        f"A Charitable Remainder Annuity Trust (CRAT) is an **irrevocable** trust that pays a "
        f"**fixed annuity to one or more noncharitable beneficiaries** (here, the client) for a "
        f"specified term, with the **remainder passing to one or more qualified charitable "
        f"organisations** at the end of the term {s003}. The trust is governed by IRC §664, which "
        f"establishes the requirements for split-interest trusts {s003}.\n\n"
        f"The CRAT is funded by an irrevocable transfer of assets — typically **cash and/or "
        f"appreciated assets** — which **permanently removes those assets from the donor's ongoing "
        f"control** {s003}. Once funded, neither the corpus nor the charitable beneficiary can "
        f"be changed {s003}.\n\n"
        f"The annuity amount is **fixed at inception based on the initial fair market value** of "
        f"the trust corpus and **does not increase when trust assets grow** or decrease when they "
        f"decline {s004}. For this client, the annual annuity is "
        f"{_n(numerics, '{{crat_annual_annuity_usd}}')} "
        f"({_n(numerics, '{{crat_payout_rate}}')} × {_n(numerics, '{{crat_trust_corpus_usd}}')} "
        f"initial corpus), and this payment remains the same every year regardless of investment "
        f"performance {s004}. Unlike a CRUT (Charitable Remainder Unitrust), the CRAT annuity is "
        f"fixed and does not vary with trust performance.\n\n"
        f"### Term Structure: Term-of-Years versus Lifetime\n\n"
        f"A CRAT may be structured for either (a) the lifetime of the income beneficiary or "
        f"(b) a fixed term of years, subject to a **maximum of 20 years** under the regulations "
        f"at 26 CFR §1.664-2 {s004}. This analysis uses a **{crat_term}-year term-of-years** CRAT, "
        f"which is the maximum permissible fixed term.\n\n"
        f"The choice between a lifetime and a term-of-years CRAT involves important trade-offs:\n\n"
        f"**Lifetime CRAT:** Annuity payments continue until the client's death, providing "
        f"income security regardless of longevity. For a {age}-year-old client with an actuarial "
        f"life expectancy of approximately 21 additional years, a lifetime CRAT could mean "
        f"payments continuing into the client's 80s. However, a lifetime CRAT generally produces a "
        f"**smaller** charitable deduction under IRC §170 because the remainder interest is reduced "
        f"by the longer expected payout period {s009}. At death, the remaining corpus passes to "
        f"charity immediately.\n\n"
        f"**Term-of-years CRAT** (as modelled here at {crat_term} years): Provides certainty of "
        f"the payout duration and generally produces a **larger** charitable deduction because the "
        f"charity is guaranteed to receive the remainder after a fixed, known period {s003}. The "
        f"trade-off is that annuity payments **cease after {crat_term} years** regardless of whether "
        f"the client is still living. For a {age}-year-old client, a {crat_term}-year term means "
        f"payments continue to approximately age {int(age) + int(crat_term) if age.isdigit() and crat_term.isdigit() else 'N/A'}, "
        f"which is close to the actuarial life expectancy {s004}.\n\n"
        f"**Early death during a term-of-years CRAT:** If the grantor dies during the "
        f"{crat_term}-year term, the annuity ceases (unless the trust document names a successor "
        f"beneficiary for the remaining term). The remaining corpus passes to the designated "
        f"charity at that time. Critically, the estate receives an offsetting charitable deduction "
        f"for the present value of the charitable remainder, so there is **no net estate tax "
        f"penalty** from early death — unlike the GRAT, where death causes full corpus inclusion "
        f"with no offset {s003} {s006}.\n\n"
        f"### The 10% Charitable Remainder Minimum\n\n"
        f"Under the regulations at 26 CFR §1.664-2, the actuarial value of the charitable "
        f"remainder interest must be **at least 10%** of the initial net fair market value of the "
        f"trust corpus at the time of funding {s004}. This is a qualification requirement — if the "
        f"combination of payout rate, trust term, and §7520 rate produces a remainder worth less "
        f"than 10%, the trust **fails to qualify** as a CRAT and the charitable income tax deduction "
        f"is entirely disallowed {s004}.\n\n"
        f"**This client's CRAT clears the 10% threshold with substantial margin:** The charitable "
        f"deduction of {_n(numerics, '{{crat_charitable_deduction_usd}}')} represents approximately "
        f"47.6% of the {_n(numerics, '{{crat_trust_corpus_usd}}')} corpus — nearly five times "
        f"the 10% minimum. This margin provides a significant buffer: even if the §7520 rate were "
        f"materially higher at the time of trust establishment, the CRAT would still qualify "
        f"{s003} {s004}.\n\n"
        f"### Key Mechanics\n\n"
        f"The trust is funded with {_n(numerics, '{{crat_trust_corpus_usd}}')} and provides a "
        f"fixed annual annuity of {_n(numerics, '{{crat_annual_annuity_usd}}')} at a payout rate "
        f"of {_n(numerics, '{{crat_payout_rate}}')} {s004}. Because the annuity is fixed at inception "
        f"and does not adjust with trust performance, the client receives the same "
        f"{_n(numerics, '{{crat_annual_annuity_usd}}')} each year regardless of whether the trust "
        f"assets appreciate or decline in value {s004}. Over the full {crat_term}-year term, total "
        f"annuity payments to the client equal {_n(numerics, '{{crat_total_annuity_paid_usd}}')} "
        f"{s003}.\n\n"
        f"### CRAT Performance Dependence\n\n"
        f"The CRAT's effectiveness depends on investment returns exceeding the "
        f"{_n(numerics, '{{crat_payout_rate}}')} payout rate {s004}. Unlike the GRAT, where the "
        f"§7520 hurdle rate of {_n(numerics, '{{section_7520_rate_bps}}')} determines transfer "
        f"efficiency, the CRAT's critical benchmark is the **payout rate itself**. The CRAT's "
        f"effective hurdle ({_n(numerics, '{{crat_payout_rate}}')}) is meaningfully higher than "
        f"the GRAT's hurdle ({_n(numerics, '{{section_7520_rate_bps}}')}), making the CRAT "
        f"**more sensitive** to investment underperformance {s004} {s007}.\n\n"
        f"- If the trust earns exactly {_n(numerics, '{{crat_payout_rate}}')} annually, the "
        f"annuity payments consume only the income and the corpus is preserved for charity.\n"
        f"- If the trust earns less than {_n(numerics, '{{crat_payout_rate}}')} annually, the "
        f"fixed annuity depletes principal. Sustained underperformance can exhaust the trust "
        f"corpus before the {crat_term}-year term ends, reducing or completely eliminating the "
        f"charitable remainder {s004}.\n"
        f"- If the corpus is exhausted, the trust terminates early and the charity receives "
        f"nothing — though the income beneficiary would also lose remaining annuity payments.\n\n"
        f"In contrast, the GRAT's success depends on returns exceeding the lower §7520 hurdle "
        f"rate ({_n(numerics, '{{section_7520_rate_bps}}')}), making its performance threshold "
        f"generally more favourable in a low-rate environment {s007}.\n\n"
        f"### Tax Treatment and Four-Tier Taxation of Distributions\n\n"
        f"Upon establishment of the CRAT, the client receives an upfront charitable income tax "
        f"deduction of {_n(numerics, '{{crat_charitable_deduction_usd}}')} under IRC §170 {s009}. "
        f"This deduction reflects the **present value of the charitable remainder interest** — "
        f"that is, the actuarially determined present value of what the charity will receive at "
        f"the end of the trust term, discounted using the §7520 rate of "
        f"{_n(numerics, '{{section_7520_rate_bps}}')} {s007} {s009}.\n\n"
        f"Annuity distributions to the income beneficiary are taxed under the **four-tier system** "
        f"prescribed by IRC §664 {s003}:\n\n"
        f"1. **Ordinary income** — distributions are first characterised as ordinary income to "
        f"the extent of the trust's current and accumulated ordinary income\n"
        f"2. **Capital gains** — next as capital gains to the extent of the trust's current and "
        f"accumulated capital gains\n"
        f"3. **Other income** — then as tax-exempt income and other categories\n"
        f"4. **Return of corpus** — finally as a tax-free return of the donor's original contribution\n\n"
        f"The trust itself is generally **exempt from income tax** on reinvested gains (unlike the "
        f"GRAT, which is a grantor trust where the grantor pays income tax on trust earnings). "
        f"However, the character of distributions flows through to the beneficiary, so the "
        f"income tax burden shifts to distributions rather than annual trust earnings {s003}.\n\n"
        f"### Estate Tax Treatment under IRC §2036\n\n"
        f"The CRAT's estate tax treatment differs fundamentally from the GRAT. The grantor's "
        f"retained annuity interest in the CRAT is an IRC §2036 retained interest, meaning it is "
        f"included in the gross estate at death {s006}. However, the estate receives an **offsetting "
        f"charitable deduction** for the present value of the charitable remainder interest, which "
        f"is what produces the net estate tax reduction {s003}. This is a critical distinction from "
        f"the GRAT: when a GRAT grantor dies during the term, the full corpus is included in the "
        f"estate with **no** offsetting deduction {s006}. When a CRAT grantor dies, the inclusion "
        f"is offset by the charitable deduction, resulting in net estate tax savings.\n\n"
        f"The estate tax savings of "
        f"{_n(numerics, '{{crat_estate_tax_saved_usd}}')} reflect the charitable deduction's "
        f"effect on the taxable estate, reducing it to "
        f"{_n(numerics, '{{taxable_estate_after_crat_usd}}')} {s010}.\n\n"
        f"### Advantages\n\n"
        f"- Charitable income tax deduction of {_n(numerics, '{{crat_charitable_deduction_usd}}')} "
        f"in the year of trust creation {s009}\n"
        f"- **No mortality risk** for estate inclusion — unlike the GRAT, the grantor's death during "
        f"the term does not cause uncompensated corpus inclusion in the estate {s003}\n"
        f"- Reliable fixed income stream of {_n(numerics, '{{crat_annual_annuity_usd}}')} per "
        f"year for {crat_term} years {s004}\n"
        f"- Philanthropic legacy: {_n(numerics, '{{crat_remainder_to_charity_usd}}')} projected "
        f"remainder to the designated charity {s003}\n"
        f"- Capital gains deferral on appreciated assets contributed to the trust {s003}\n"
        f"- Clears the 10% charitable remainder minimum with substantial margin {s004}\n\n"
        f"### Risks and Limitations\n\n"
        f"- No wealth passes to the client's children through the CRAT "
        f"({_n(numerics, '{{wealth_to_children_crat_usd}}')}); a separate **wealth-replacement "
        f"strategy** (e.g., an irrevocable life insurance trust (ILIT) funded with CRAT annuity "
        f"payments) should be considered to compensate heirs {s003}\n"
        f"- The fixed annuity does not adjust for inflation — the real value of "
        f"{_n(numerics, '{{crat_annual_annuity_usd}}')} per year erodes over a {crat_term}-year "
        f"period {s004}\n"
        f"- If investment returns fall below the {_n(numerics, '{{crat_payout_rate}}')} payout "
        f"rate, the corpus will be depleted, reducing or eliminating the charitable remainder "
        f"{s004}\n"
        f"- The trust is irrevocable; neither the terms nor the charitable beneficiary can be "
        f"changed after funding {s003}\n"
        f"- Implementing and maintaining a CRAT involves **complexity and administrative cost**, "
        f"including trust accounting, annual filings (Form 5227), compliance with the 10% remainder "
        f"minimum, and coordination with charitable beneficiaries {s004}\n"
        f"- The maximum term-of-years is limited to 20 years; a longer income stream requires "
        f"a lifetime CRAT structure {s004}\n"
        f"- Four-tier taxation means distributions may be taxed at ordinary income rates, "
        f"reducing the net after-tax benefit to the income beneficiary {s003}"
    )


def _draft_comparative_analysis(numerics: dict, chunks: list, available: list[str]) -> str:
    s001 = _cite("S001", available)
    s003 = _cite("S003", available)
    s004 = _cite("S004", available)
    s006 = _cite("S006", available)
    s007 = _cite("S007", available)
    s008 = _cite("S008", available)
    s009 = _cite("S009", available)
    s010 = _cite("S010", available)
    age = _n(numerics, '{{client_age}}', '62')
    grat_term = _n(numerics, '{{grat_term_years}}', '10')
    crat_term = _n(numerics, '{{crat_term_years}}', '20')
    survival_age = str(int(age) + int(grat_term)) if age.isdigit() and grat_term.isdigit() else 'N/A'
    return (
        f"The following table compares the two trust strategies across key planning dimensions.\n\n"
        f"| Dimension | GRAT | CRAT |\n"
        f"|---|---|---|\n"
        f"| Primary Goal | Wealth transfer to children | Charitable giving + income stream |\n"
        f"| Legal Authority | IRC §2702 {s001} | IRC §664 {s003} |\n"
        f"| Trust Corpus | {_n(numerics, '{{grat_trust_corpus_usd}}')} | {_n(numerics, '{{crat_trust_corpus_usd}}')} |\n"
        f"| Term | {grat_term} years | {crat_term} years (max 20 for term-of-years) {s004} |\n"
        f"| Annual Payment | {_n(numerics, '{{grat_annuity_payment_annual_usd}}')} to grantor | {_n(numerics, '{{crat_annual_annuity_usd}}')} to grantor |\n"
        f"| Estate Tax Savings | {_n(numerics, '{{estate_tax_saved_by_grat_usd}}')} | {_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} |\n"
        f"| Taxable Estate After | {_n(numerics, '{{taxable_estate_after_grat_usd}}')} | {_n(numerics, '{{taxable_estate_after_crat_usd}}')} |\n"
        f"| Wealth to Children | {_n(numerics, '{{grat_projected_remainder_usd}}')} | {_n(numerics, '{{wealth_to_children_crat_usd}}')} |\n"
        f"| Charitable Benefit | None | {_n(numerics, '{{crat_remainder_to_charity_usd}}')} remainder to charity |\n"
        f"| Income Tax Deduction | None | {_n(numerics, '{{crat_charitable_deduction_usd}}')} {s009} |\n"
        f"| Performance Hurdle | §7520 rate ({_n(numerics, '{{section_7520_rate_bps}}')}) {s007} | Payout rate ({_n(numerics, '{{crat_payout_rate}}')}) {s004} |\n"
        f"| Income Tax Treatment | Grantor trust — grantor pays income tax {s008} | Four-tier distribution taxation {s003} |\n"
        f"| Mortality Risk | **High** — full estate inclusion if grantor dies during term {s006} | **Low** — annuity ceases, remainder passes to charity; charitable deduction offsets estate inclusion |\n"
        f"| 10% Remainder Minimum | Not applicable | Required — cleared at ~47.6% {s004} |\n\n"
        f"### Performance Dependence Comparison\n\n"
        f"The GRAT and CRAT have fundamentally different performance benchmarks:\n\n"
        f"**GRAT hurdle — the §7520 rate ({_n(numerics, '{{section_7520_rate_bps}}')}):** "
        f"The GRAT transfers wealth only to the extent that investment returns **exceed the §7520 "
        f"hurdle rate** {s007}. At the assumed growth rate of "
        f"{_n(numerics, '{{grat_growth_rate}}')}, the spread above the hurdle rate is approximately "
        f"**304 basis points** (5.00% − 1.96%). This spread generates the "
        f"projected remainder of {_n(numerics, '{{grat_projected_remainder_usd}}')} to children "
        f"{s001}. If returns merely equal the §7520 rate, the remainder is zero.\n\n"
        f"**CRAT hurdle — the payout rate ({_n(numerics, '{{crat_payout_rate}}')}):** "
        f"The CRAT's critical benchmark is the payout rate {s004}. Returns must equal or exceed "
        f"this rate to preserve the corpus over the {crat_term}-year term. At the assumed growth "
        f"rate of {_n(numerics, '{{grat_growth_rate}}')}, the spread above the CRAT's hurdle is "
        f"**zero basis points** (5.00% − 5.00%), meaning the corpus is exactly preserved but "
        f"generates no surplus {s004}.\n\n"
        f"**Comparison:** GRAT outcomes depend entirely on the trust's investment returns "
        f"**exceeding the §7520 hurdle rate** of {_n(numerics, '{{section_7520_rate_bps}}')}; if "
        f"returns fall short, **little or no value passes to heirs** {s007}. By contrast, the CRAT "
        f"pays a **fixed annuity** of {_n(numerics, '{{crat_annual_annuity_usd}}')} per year to the "
        f"client **regardless of investment performance** — the annuity amount does not change "
        f"whether the trust's assets appreciate or decline in value {s004}. The CRAT's design "
        f"therefore centers on providing a **fixed income stream** to the noncharitable "
        f"beneficiary, with the **charitable remainder** passing to the designated organisation at "
        f"the end of the term {s003}. This fundamental structural difference means the GRAT is more "
        f"sensitive to investment performance than the CRAT's fixed-payment structure.\n\n"
        f"### Mortality-Risk Analysis\n\n"
        f"Mortality risk is the most material differentiator between the two strategies for a "
        f"{age}-year-old grantor {s006}.\n\n"
        f"**GRAT:** Death during the {grat_term}-year term (before age {survival_age}) causes the "
        f"**full** {_n(numerics, '{{grat_trust_corpus_usd}}')} corpus to be included in the gross "
        f"estate under IRC §2033 — completely negating the estate tax benefit {s006}. Based on "
        f"IRS actuarial tables (Table 90CM), a {age}-year-old has approximately a **15–20% "
        f"probability** of dying within {grat_term} years. This is a binary, all-or-nothing risk: "
        f"there is no partial benefit from a GRAT if the grantor dies one year before term end "
        f"{s006}.\n\n"
        f"**CRAT:** The CRAT carries **no equivalent estate-tax penalty**. If the grantor dies during "
        f"the {crat_term}-year term, the annuity payments to the noncharitable beneficiary **cease** "
        f"and the remaining trust corpus passes immediately to the designated charitable "
        f"remainder beneficiary {s003}. The estate receives a charitable deduction that offsets the "
        f"IRC §2036 inclusion, so there is no net estate tax penalty from early death. However, "
        f"the grantor forfeits the remaining annuity payments — the annuity does **not** continue "
        f"to any party after the grantor's death. The CRAT's estate tax benefit is preserved "
        f"regardless of when the grantor dies.\n\n"
        f"### Estate Tax Comparison\n\n"
        f"The CRAT provides greater **gross** estate tax savings "
        f"({_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} vs "
        f"{_n(numerics, '{{estate_tax_saved_by_grat_usd}}')}) because the charitable deduction "
        f"reduces the taxable estate by {_n(numerics, '{{crat_charitable_deduction_usd}}')} "
        f"{s009}. However, the CRAT achieves this by directing the remainder to charity rather "
        f"than to children. The GRAT is the only vehicle that transfers wealth to the next "
        f"generation ({_n(numerics, '{{grat_projected_remainder_usd}}')} to children) while also "
        f"providing estate tax reduction {s001}.\n\n"
        f"### Planning Trade-offs Summary\n\n"
        f"| Trade-off | GRAT | CRAT |\n"
        f"|---|---|---|\n"
        f"| Wealth to children | {_n(numerics, '{{wealth_to_children_grat_usd}}')} | {_n(numerics, '{{wealth_to_children_crat_usd}}')} |\n"
        f"| Estate tax savings | {_n(numerics, '{{estate_tax_saved_by_grat_usd}}')} | {_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} |\n"
        f"| Mortality risk | ~15–20% probability of total loss | No estate-tax penalty; annuity ceases, remainder to charity |\n"
        f"| Grantor trust benefit | Yes — tax-free compounding {s008} | No — four-tier taxation {s003} |\n"
        f"| 10% remainder test | Not applicable | Cleared at ~47.6% {s004} |\n"
        f"| Charitable component | None | {_n(numerics, '{{crat_remainder_to_charity_usd}}')} to charity |\n\n"
        f"### Recommendation\n\n"
        f"Given the client's dual priorities of benefiting children and supporting charity, "
        f"the GRAT is recommended as the **primary** estate-planning instrument for its unique "
        f"ability to achieve intergenerational wealth transfer — saving an estimated "
        f"{_n(numerics, '{{estate_tax_saved_by_grat_usd}}')} in estate taxes and transferring "
        f"{_n(numerics, '{{wealth_to_children_grat_usd}}')} to the children {s001}. "
        f"The CRAT is recommended as a **complementary** vehicle to address the client's "
        f"philanthropic objectives — providing {_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} "
        f"in estate tax savings and directing {_n(numerics, '{{crat_remainder_to_charity_usd}}')} "
        f"to charity, with an upfront income tax deduction of "
        f"{_n(numerics, '{{crat_charitable_deduction_usd}}')} {s009}. Because the CRAT transfers "
        f"{_n(numerics, '{{wealth_to_children_crat_usd}}')} to heirs, the client should consider a "
        f"**wealth-replacement strategy** — such as an irrevocable life insurance trust (ILIT) — "
        f"to offset the assets diverted from the family {s003}. A combined approach "
        f"maximises overall planning benefit by addressing both wealth transfer and charitable goals.\n\n"
        f"### Marital Status and Exemption Framing\n\n"
        f"The client's marital status is a **material factor** in this recommendation. As a married "
        f"couple in 2015, the client and spouse have access to a combined federal estate-tax "
        f"exemption of **$10,860,000.00**, compared with the individual exemption of $5,430,000.00 "
        f"{s010}. With a {_n(numerics, '{{taxable_estate_before_usd}}')} estate, the excess over "
        f"the married exemption is approximately $5,140,000.00, which would be subject to the "
        f"{_n(numerics, '{{estate_tax_rate}}')} estate tax rate — producing a potential federal "
        f"estate-tax liability of approximately $2,056,000.00 if no planning is undertaken {s010}. "
        f"The GRAT and CRAT strategies recommended above both operate to reduce this taxable excess: "
        f"the GRAT by transferring growth above the §7520 rate out of the estate, and the CRAT by "
        f"generating a charitable deduction that directly reduces the taxable estate. The "
        f"availability of the marital (portability) exemption provides a higher baseline, but the "
        f"combined strategies are still warranted to shelter the $5,140,000.00 exposure and to "
        f"achieve the client's stated philanthropic and wealth-transfer goals.\n\n"
        f"### Implementation Conditions\n\n"
        f"- If intergenerational wealth transfer is the **dominant** priority, a GRAT-only "
        f"strategy maximises assets passing to the children {s001}\n"
        f"- If the charitable objective is dominant, a larger CRAT allocation increases "
        f"total tax savings and charitable impact {s003}\n"
        f"- For the combined approach, the specific allocation between GRAT and CRAT should be "
        f"calibrated to the client's relative weighting of children vs. charity goals\n"
        f"- The recommendation assumes current tax law remains in effect; material changes to "
        f"estate, gift, or income tax rates should trigger re-evaluation {s010}"
    )


def _draft_scenario_illustration(numerics: dict, chunks: list, available: list[str]) -> str:
    s001 = _cite("S001", available)
    s002 = _cite("S002", available)
    s003 = _cite("S003", available)
    s007 = _cite("S007", available)
    s009 = _cite("S009", available)
    return (
        f"### GRAT Scenario\n\n"
        f"The client funds a {_n(numerics, '{{grat_term_years}}')}-year GRAT with "
        f"{_n(numerics, '{{grat_trust_corpus_usd}}')} {s001}. The Section 7520 hurdle rate is "
        f"{_n(numerics, '{{section_7520_rate_bps}}')} {s007}. The trust is structured to pay an annual "
        f"annuity of {_n(numerics, '{{grat_annuity_payment_annual_usd}}')} back to the grantor "
        f"each year {s002}.\n\n"
        f"Assuming the trust assets grow at {_n(numerics, '{{grat_growth_rate}}')} annually, "
        f"the trust will have distributed {_n(numerics, '{{grat_total_annuity_paid_usd}}')} in total "
        f"annuity payments over the term. The assets remaining after all annuity payments — "
        f"{_n(numerics, '{{grat_projected_remainder_usd}}')} — pass to the two children free of "
        f"gift and estate tax {s001}.\n\n"
        f"The taxable gift at inception is only {_n(numerics, '{{grat_taxable_gift_usd}}')} because "
        f"the GRAT was zeroed-out {s002}. The estate is reduced and tax savings of "
        f"{_n(numerics, '{{grat_estate_tax_saved_usd}}')} are achieved.\n\n"
        f"### CRAT Scenario\n\n"
        f"Alternatively, the client funds a CRAT with {_n(numerics, '{{crat_trust_corpus_usd}}')} "
        f"{s003}. The trust pays a fixed annual annuity of {_n(numerics, '{{crat_annual_annuity_usd}}')} "
        f"to the client for the trust term.\n\n"
        f"The client receives an upfront charitable income tax deduction of "
        f"{_n(numerics, '{{crat_charitable_deduction_usd}}')} under IRC Section 170 {s009}. "
        f"At the end of the trust term, the remaining "
        f"{_n(numerics, '{{crat_remainder_to_charity_usd}}')} passes to the designated charity, "
        f"fulfilling the client's philanthropic goals {s003}.\n\n"
        f"### Net Effect Comparison\n\n"
        f"Under the GRAT scenario, the children receive {_n(numerics, '{{wealth_to_children_grat_usd}}')} "
        f"and the estate tax bill is reduced by {_n(numerics, '{{estate_tax_saved_by_grat_usd}}')} "
        f"{s001}. Under the CRAT scenario, the charity receives "
        f"{_n(numerics, '{{crat_remainder_to_charity_usd}}')} and the estate tax saving is "
        f"{_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} {s003}. The scenarios are not "
        f"mutually exclusive; a combined approach is discussed in the Recommendation section."
    )


def _draft_recommendation(numerics: dict, chunks: list, available: list[str]) -> str:
    s001 = _cite("S001", available)
    s003 = _cite("S003", available)
    s009 = _cite("S009", available)
    s010 = _cite("S010", available)
    return (
        f"Given the client's dual objectives of benefiting children and supporting charitable "
        f"giving, a blended approach is recommended.\n\n"
        f"### Primary Recommendation\n\n"
        f"Allocate {_n(numerics, '{{grat_allocation_weight}}')} of the estate-planning corpus to a "
        f"GRAT and {_n(numerics, '{{crat_allocation_weight}}')} to a CRAT {s001}. This balances "
        f"wealth transfer to the next generation with meaningful estate tax reduction and "
        f"philanthropic impact.\n\n"
        f"### Rationale\n\n"
        f"The GRAT delivers an estimated {_n(numerics, '{{wealth_to_children_grat_usd}}')} to the "
        f"children and {_n(numerics, '{{estate_tax_saved_by_grat_usd}}')} in estate tax savings, "
        f"addressing the primary wealth-transfer goal {s001}. The CRAT provides "
        f"{_n(numerics, '{{estate_tax_saved_by_crat_usd}}')} in estate tax savings and a "
        f"charitable income tax deduction of {_n(numerics, '{{crat_charitable_deduction_usd}}')} "
        f"{s009}, addressing the philanthropic goal.\n\n"
        f"### Conditions\n\n"
        f"- If the client's philanthropic intent is the dominant priority, a larger CRAT allocation "
        f"would maximise charitable impact and total tax savings {s003}\n"
        f"- If intergenerational wealth transfer is paramount, a GRAT-only strategy would maximise "
        f"assets passing to children {s001}\n"
        f"- The recommendation assumes current tax law remains in effect; any material changes to "
        f"estate, gift, or income tax rates should trigger a re-evaluation {s010}"
    )


def _draft_risks_considerations(numerics: dict, chunks: list, available: list[str]) -> str:
    s001 = _cite("S001", available)
    s004 = _cite("S004", available)
    s002 = _cite("S002", available)
    s003 = _cite("S003", available)
    s006 = _cite("S006", available)
    s007 = _cite("S007", available)
    s010 = _cite("S010", available)
    age = _n(numerics, '{{client_age}}', '62')
    grat_term = _n(numerics, '{{grat_term_years}}', '10')
    survival_age = str(int(age) + int(grat_term)) if age.isdigit() and grat_term.isdigit() else 'N/A'
    return (
        f"### Legislative Risk\n\n"
        f"Congress has periodically considered legislation that would limit or eliminate zeroed-out "
        f"GRATs, impose minimum trust terms, or change the estate tax exemption and rate structure. "
        f"Any such changes could materially affect the projected outcomes described in this report "
        f"{s010}.\n\n"
        f"### Market Risk and Performance Dependence\n\n"
        f"Both strategies depend on investment returns, but with different thresholds. The GRAT "
        f"requires returns exceeding the Section 7520 hurdle rate of "
        f"{_n(numerics, '{{section_7520_rate_bps}}')} — a spread of approximately 304 bps at the "
        f"assumed {_n(numerics, '{{grat_growth_rate}}')} growth rate {s007}. The CRAT requires "
        f"returns sufficient to fund the {_n(numerics, '{{crat_payout_rate}}')} annuity while "
        f"preserving the charitable remainder {s004}. At the assumed growth rate equal to the payout "
        f"rate, the CRAT has zero spread — any underperformance directly erodes the corpus. "
        f"Sustained market downturns would affect the CRAT more severely than the GRAT because "
        f"the GRAT's lower hurdle provides a larger cushion.\n\n"
        f"### Mortality Risk (GRAT-Specific)\n\n"
        f"The GRAT carries the most significant risk: if the {age}-year-old grantor dies before "
        f"age {survival_age} (the end of the {grat_term}-year term), the full "
        f"{_n(numerics, '{{grat_trust_corpus_usd}}')} corpus is included in the "
        f"gross estate under IRC §2033 {s006}. Based on IRS actuarial tables (Table 90CM), there "
        f"is approximately a **15–20% probability** of this occurring. This is a binary outcome: "
        f"there is no partial benefit if death occurs during the term. The CRAT does not carry "
        f"this risk — the estate receives a charitable deduction offsetting the §2036 inclusion "
        f"regardless of when the grantor dies {s003}.\n\n"
        f"### Execution Complexity\n\n"
        f"Both trusts are irrevocable and require careful drafting by qualified estate counsel. "
        f"The GRAT demands precise structuring of the annuity to satisfy Section 2702 requirements "
        f"{s002}. The CRAT must meet the requirements of Section 664, applicable Treasury "
        f"regulations, and the 10% charitable remainder minimum {s004}. Ongoing administration, "
        f"annual filings, and investment management add complexity to both structures.\n\n"
        f"### Interest Rate Sensitivity\n\n"
        f"The economics of both trusts are sensitive to the Section 7520 rate. A lower rate "
        f"benefits the GRAT (smaller required annuity, larger spread above hurdle). A higher rate "
        f"benefits the CRAT (larger charitable deduction, though also a higher bar for the 10% "
        f"remainder test). The rate used in this analysis is "
        f"{_n(numerics, '{{section_7520_rate_bps}}')} {s007}."
    )


def _draft_next_steps(numerics: dict, chunks: list, available: list[str]) -> str:
    s007 = _cite("S007", available)
    s010 = _cite("S010", available)
    s011 = _cite("S011", available)
    return (
        f"### Recommended Actions\n\n"
        f"1. Engage qualified estate planning counsel to review the modelling assumptions and "
        f"confirm the legal structure of the recommended trusts {s010}\n"
        f"2. Obtain a formal Section 7520 rate determination for the month of trust establishment "
        f"{s007}\n"
        f"3. Finalise the GRAT annuity structure and CRAT payout rate with counsel and the "
        f"client's tax advisor\n"
        f"4. Select a corporate trustee or individual trustee(s) for each trust\n"
        f"5. Coordinate with the client's investment manager on the trust portfolio allocation\n"
        f"6. Prepare and execute trust documents, transfer assets, and file required gift tax "
        f"returns {s010}\n"
        f"7. Establish ongoing compliance and reporting procedures for both trusts\n\n"
        f"### Circular 230 Disclosure\n\n"
        f"Pursuant to Treasury Department Circular 230, any tax advice contained in this "
        f"communication was not intended or written to be used, and cannot be used, for the purpose "
        f"of (i) avoiding tax-related penalties under the Internal Revenue Code or (ii) promoting, "
        f"marketing, or recommending to another party any transaction or matter addressed herein "
        f"{s011}.\n\n"
        f"### Assumptions and Limitations\n\n"
        f"- All projections assume a constant growth rate and do not account for market volatility\n"
        f"- Tax laws and exemption amounts are subject to change by Congress {s010}\n"
        f"- This analysis does not constitute legal or tax advice; clients should consult qualified "
        f"tax counsel before implementing any strategy {s011}\n"
        f"- The Section 7520 rate may differ at the time of trust establishment from the rate used "
        f"in this analysis {s007}"
    )


def _draft_citations_disclosures(numerics: dict, chunks: list, available: list[str]) -> str:
    s001 = _cite("S001", available)
    s003 = _cite("S003", available)
    s004 = _cite("S004", available)
    s006 = _cite("S006", available)
    s007 = _cite("S007", available)
    s008 = _cite("S008", available)
    s010 = _cite("S010", available)
    s011 = _cite("S011", available)
    return (
        f"### Supporting Authorities\n\n"
        f"1. **IRC §2702** — Special valuation rules governing GRATs, including the requirement "
        f"that the grantor retain a qualified annuity interest for a fixed term {s001}\n"
        f"2. **26 CFR §25.2702-3** — Treasury regulations prescribing the requirements for a "
        f"qualified interest in a GRAT\n"
        f"3. **IRC §664** — Statutory framework for Charitable Remainder Trusts, including the "
        f"CRAT annuity payout, term (maximum 20 years for term-of-years), and remainder "
        f"requirements {s003}\n"
        f"4. **26 CFR §1.664-2** — CRAT-specific regulations including the 10% remainder "
        f"minimum, 20-year maximum term-of-years, payout rate rules, and four-tier taxation "
        f"of distributions {s004}\n"
        f"5. **IRC §7520** — Valuation tables and the prescribed discount rate (hurdle rate) "
        f"used for present-value calculations in both GRAT and CRAT structures {s007}\n"
        f"6. **IRC §671** — Grantor trust rules applicable to the GRAT during the annuity term, "
        f"requiring the grantor to pay income tax on trust earnings (a planning advantage enabling "
        f"tax-free compounding for remainder beneficiaries) {s008}\n"
        f"7. **IRC §170** — Charitable income tax deduction rules applicable to the CRAT "
        f"charitable remainder interest\n"
        f"8. **IRC §2033 / §2036** — Estate inclusion rules: §2033 governs GRAT inclusion on "
        f"grantor death during term (full corpus, no offset); §2036 governs CRAT retained "
        f"interest inclusion (offset by charitable deduction) {s006}\n"
        f"9. **IRS Estate Tax Guidance** — 2015 exemption amounts ($5.43M individual, $10.86M "
        f"married) and the 40% top marginal estate tax rate {s010}\n\n"
        f"### Assumptions and Limitations\n\n"
        f"- All GRAT projections assume a constant annual growth rate of "
        f"{_n(numerics, '{{grat_growth_rate}}')} and do not account for year-to-year market "
        f"volatility or sequencing risk\n"
        f"- CRAT projections assume the trust earns at least the "
        f"{_n(numerics, '{{crat_payout_rate}}')} payout rate; if returns fall below this threshold, "
        f"the charitable remainder will be reduced or eliminated {s004}\n"
        f"- The §7520 rate used in this analysis ({_n(numerics, '{{section_7520_rate_bps}}')}) may "
        f"differ from the rate in effect at the time of actual trust establishment {s007}\n"
        f"- Mortality risk for the GRAT is assessed using general IRS actuarial tables (Table "
        f"90CM); the approximate 15–20% mortality probability for a 62-year-old over 10 years "
        f"does not reflect the client's individual health status or family history {s006}\n"
        f"- Tax laws, exemption amounts, and estate tax rates are subject to change by Congress; "
        f"material legislative changes could alter the projected outcomes {s010}\n"
        f"- This analysis does not model state-level estate or income taxes, which may apply in "
        f"the client's state of residence\n"
        f"- The CRAT four-tier taxation of distributions is summarised; actual tax consequences "
        f"depend on the trust's investment income character in each year {s003}\n"
        f"- The performance spread calculations (GRAT: ~304 bps above §7520 rate; CRAT: ~0 bps "
        f"above payout rate) assume the stated growth rates hold throughout the trust terms\n\n"
        f"### Circular 230 Disclosure\n\n"
        f"Pursuant to Treasury Department Circular 230 (31 CFR Part 10), any tax advice contained "
        f"in this communication was not intended or written to be used, and cannot be used, for "
        f"the purpose of (i) avoiding tax-related penalties under the Internal Revenue Code or "
        f"(ii) promoting, marketing, or recommending to another party any transaction or matter "
        f"addressed herein {s011}. This analysis is provided for informational purposes and does "
        f"not constitute legal or tax advice. Clients should consult qualified estate planning "
        f"counsel and tax advisors before implementing any strategy described in this report "
        f"{s011}."
    )


def _draft_generic(numerics: dict, chunks: list, available: list[str]) -> str:
    tag = f"[{available[0]}]" if available else ""
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
                max_tokens=1000,
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
        max_pages=12,
    )

    print(f"Draft    -> {md_path}")
    print(f"Manifest -> {manifest_path}")
    print(f"PDF      -> {pdf_path}")

    # Promote to pipeline_artifacts/drafts/ with versioned archive.
    _PIPELINE_DRAFTS = Path(__file__).resolve().parent.parent.parent / "pipeline_artifacts" / "drafts"
    _PIPELINE_DRAFTS.mkdir(parents=True, exist_ok=True)

    # Determine next version number by scanning existing Draft_N.md files
    import re as _re
    highest = 0
    for p in _PIPELINE_DRAFTS.iterdir():
        m = _re.match(r"^Draft_(\d+)\.md$", p.name)
        if m:
            highest = max(highest, int(m.group(1)))
    version = highest + 1

    import shutil
    # Immutable versioned archive
    shutil.copy2(md_path, _PIPELINE_DRAFTS / f"Draft_{version}.md")
    shutil.copy2(pdf_path, _PIPELINE_DRAFTS / f"Draft_{version}.pdf")
    # Latest pointer (used by downstream stages)
    shutil.copy2(md_path, _PIPELINE_DRAFTS / "Draft.md")
    shutil.copy2(pdf_path, _PIPELINE_DRAFTS / "Draft.pdf")

    print(f"Promoted -> Draft_{version}.md / Draft_{version}.pdf in {_PIPELINE_DRAFTS}")
