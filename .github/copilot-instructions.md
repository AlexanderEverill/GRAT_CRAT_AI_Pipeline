# Copilot Workspace Instructions — GRAT/CRAT AI Pipeline

## Project Purpose

This pipeline produces a single client-facing PDF (≤12 pages) that presents and compares a **Grantor Retained Annuity Trust (GRAT)** and a **Charitable Remainder Annuity Trust (CRAT)** for a specific client.

Every stage is deterministic or strictly controlled. The pipeline must never hallucinate numbers, invent citations, or produce unsupported legal claims.

---

## Client Context

Defined in [`pipeline_artifacts/intake/ClientProfile_v1.json`](../pipeline_artifacts/intake/ClientProfile_v1.json).

| Field | Value |
|---|---|
| Age | 62 |
| Marital status | Married |
| Children | 2 adult children |
| Liquidity event | Sold advertising agency, 2015, $16 million cash |
| Estate tax context (2015) | Individual exemption $5.43M, married $10.86M, 40% top rate |
| Goals | Minimise estate tax, benefit children, philanthropic interest |
| Deliverable | PDF ≤ 12 pages |

---

## 8-Stage Pipeline

### Stage 1 — Client Intake
- **Input:** Manual entry / advisor questionnaire
- **Output:** `pipeline_artifacts/intake/ClientProfile_v1.json`
- **Rule:** All downstream stages must read client facts only from this file. Never hard-code client data in code.

### Stage 2 — RAG Retrieval (Allowlisted Sources Only)
- **Input:** `RetrievalPlan_v1.json` (topics + queries + allowlist)
- **Outputs:**
  - `pipeline_artifacts/retrieval/raw/` — raw HTML/PDF + `.meta.json` per source
  - `pipeline_artifacts/retrieval/parsed/` — `.txt` + `_chunks.json` per source
  - `pipeline_artifacts/retrieval/index/index.pkl` — TF-IDF vector index (scikit-learn)
  - `pipeline_artifacts/retrieval/bundle/RetrievalBundle_v1.json` — top chunks grouped by topic
  - `pipeline_artifacts/retrieval/bundle/CitationsManifest_v1.json` — cite-key → URL mapping
  - `pipeline_artifacts/retrieval/bundle/RetrievalCoverageReport_v1.json` — GREEN/YELLOW/RED per topic
- **Allowlist (strict):** `irs.gov`, `treasury.gov`, `law.cornell.edu` + internal `FirmKB`
- **Rule:** Fetcher must reject any URL not matching the allowlist. Coverage report RED = pipeline must halt or warn before proceeding to drafting.

#### Current source corpus (11 documents — last updated 2026-03-01)

| ID | URL | Subject |
|---|---|---|
| S001 | law.cornell.edu/uscode/text/26/2702 | IRC §2702 — GRAT core statute |
| S002 | law.cornell.edu/cfr/text/26/25.2702-3 | CFR §25.2702-3 — GRAT qualified interest regulations |
| S003 | law.cornell.edu/uscode/text/26/664 | IRC §664 — CRAT core statute |
| S004 | law.cornell.edu/cfr/text/26/1.664-2 | CFR §1.664-2 — CRAT annuity trust regulations |
| S005 | law.cornell.edu/uscode/text/26/2501 | IRC §2501 — Gift tax imposition |
| S006 | law.cornell.edu/uscode/text/26/2033 | IRC §2033 — Estate inclusion |
| S007 | law.cornell.edu/uscode/text/26/7520 | IRC §7520 — Hurdle rate / valuation tables |
| S008 | law.cornell.edu/uscode/text/26/671 | IRC §671 — Grantor trust income tax rules (GRAT term taxation) |
| S009 | law.cornell.edu/uscode/text/26/170 | IRC §170 — Charitable income tax deduction (CRAT upfront deduction) |
| S010 | irs.gov/businesses/small-businesses-self-employed/estate-tax | IRS estate tax — 2015 exemption $5.43M individual / $10.86M married / 40% rate |
| S011 | law.cornell.edu/cfr/text/31/part-10 | 31 CFR Part 10 — Circular 230 written tax advice standards (disclosures page) |

#### Coverage report (2026-03-01) — 7/7 GREEN, 0 RED, 0 YELLOW — PASS

| Topic | Key points found | Status |
|---|---|---|
| GRAT_core_mechanics | 17 | GREEN |
| CRAT_core_mechanics | 14 | GREEN |
| gift_estate_tax_treatment | 20 | GREEN |
| section_7520_rate | 13 | GREEN |
| CRT_taxation_basics | 11 | GREEN |
| risks_limitations | 22 | GREEN |
| required_disclosures_limitations_language | 13 | GREEN |

#### Retrieval gaps — all resolved ✅

All 4 previously identified gaps (§170, §671, IRS exemption table, Circular 230) were fetched on 2026-03-01 as S008–S011. No outstanding retrieval gaps remain.

### Stage 3 — Deterministic Trust Modeler
- **Entry point:** `run_deterministic_model()` in `src/model/engine.py` (re-exported from `src/model/__init__.py`)
- **Input:** `ClientProfile_v1.json` + §7520 rate looked up from `pipeline_artifacts/config/section_7520_rates.json` (sourced from RAG S007)
- **Configuration:**
  - `pipeline_artifacts/config/model_assumptions.json` — growth rates, term lengths, payout rates (no hardcoded financial constants in code)
  - `pipeline_artifacts/config/section_7520_rates.json` — historical IRS §7520 rates by year/month
- **Outputs:**
  - `pipeline_artifacts/model_outputs/TrustComparison_v1.json` — all scenario numbers (see schema below)
  - `pipeline_artifacts/model_outputs/ModelRunReport.json` — input hashes, model version, timestamp, §7520 rate source
- **Rules:**
  - All numbers in the final PDF must originate from `TrustComparison_v1.json`. The LLM must never compute or invent numeric values.
  - Model must be fully deterministic — no random state; same inputs always produce identical outputs.
  - All client financial figures must be read from `ClientProfile_v1.json`. No hard-coded numeric literals in model code.
  - All modeling assumptions (growth rates, term years, payout rates) must be read from `model_assumptions.json`.
  - §7520 rate is dynamically looked up from `section_7520_rates.json` based on the client's liquidity event year.
  - SHA-256 of `ClientProfile_v1.json` must be written into `ModelRunReport.json`.
  - `append_notes_log()` must be called before and after the model runs.
  - All dataclasses are frozen (`@dataclass(frozen=True)`) for immutability.
  - All monetary values are rounded to 2 decimal places.

#### Key modeling decisions

- **Zeroed-out GRAT (IRC §2702):** Annuity is set so PV of annuity ≈ PV of corpus → `taxable_gift_usd = 0.0`. Remainder transfers to children at term end.
- **CRAT IRC §2036 treatment:** Grantor's retained income interest is included in estate at death. Only the charitable remainder deduction reduces the taxable estate — `estate_reduction = charitable_deduction_estimate` (not full corpus).
- **Separate CRAT deduction growth rate:** `crat_deduction_growth_rate` (conservative 4%) is used for charitable deduction calculation; `crat_growth_rate` (5%) is used for remainder simulation.

#### Current model assumptions (`model_assumptions.json`)

| Assumption | Value | Used by |
|---|---|---|
| `grat.growth_rate` | 0.05 (5%) | GRAT remainder simulation |
| `grat.term_years` | 10 | GRAT annuity term |
| `crat.payout_rate` | 0.05 (5%) | CRAT annual distribution (corpus × rate) |
| `crat.growth_rate` | 0.05 (5%) | CRAT remainder simulation |
| `crat.term_years` | 20 | CRAT payout term |
| `crat.deduction_growth_rate` | 0.04 (4%) | CRAT charitable deduction (conservative) |

#### `TrustComparison_v1.json` schema

```json
{
  "model_version": "1.0",
  "client_age": 62,
  "marital_status": "Married",
  "metadata": {
    "generated_timestamp": "<ISO 8601 UTC>",
    "model_version": "1.0",
    "pipeline_stage": "Stage 3 — Deterministic Trust Modeler"
  },
  "inputs": {
    "age": "<from ClientProfile>",
    "marital_status": "<from ClientProfile>",
    "liquidity_event_amount_usd": "<from ClientProfile>",
    "estate_tax_rate": "<from ClientProfile>",
    "individual_exemption_usd": "<from ClientProfile>",
    "married_exemption_usd": "<from ClientProfile>"
  },
  "assumptions": {
    "section_7520_rate": "<float — from section_7520_rates.json>",
    "grat_growth_rate": "<float — from model_assumptions.json>",
    "grat_term_years": "<int>",
    "crat_payout_rate": "<float>",
    "crat_growth_rate": "<float>",
    "crat_term_years": "<int>",
    "crat_deduction_growth_rate": "<float>"
  },
  "grat": {
    "trust_corpus_usd": "<from ClientProfile>",
    "term_years": "<int>",
    "section_7520_rate": "<float>",
    "growth_rate": "<float>",
    "annuity_payment_annual_usd": "<float>",
    "total_annuity_paid_usd": "<float>",
    "projected_remainder_to_children_usd": "<float>",
    "taxable_gift_usd": "<float — always 0.0 for zeroed-out GRAT>",
    "estate_reduction_usd": "<float>",
    "estate_tax_saved_usd": "<float>"
  },
  "crat": {
    "trust_corpus_usd": "<from ClientProfile>",
    "payout_rate": "<float>",
    "growth_rate": "<float>",
    "annual_annuity_usd": "<float>",
    "total_annuity_paid_usd": "<float>",
    "remainder_to_charity_usd": "<float>",
    "charitable_deduction_estimate_usd": "<float>",
    "estate_reduction_usd": "<float — equals charitable_deduction, not corpus>",
    "estate_tax_saved_usd": "<float>"
  },
  "comparison": {
    "taxable_estate_before_usd": "<from ClientProfile>",
    "taxable_estate_after_grat_usd": "<float>",
    "taxable_estate_after_crat_usd": "<float>",
    "estate_tax_saved_by_grat_usd": "<float>",
    "estate_tax_saved_by_crat_usd": "<float>",
    "estate_tax_saving_difference_usd": "<float>",
    "wealth_to_children_grat_usd": "<float>",
    "wealth_to_children_crat_usd": "<float — always 0.0>",
    "wealth_to_children_difference_usd": "<float>",
    "charitable_component_grat_usd": "<float — always 0.0>",
    "charitable_component_crat_usd": "<float>",
    "charitable_component_difference_usd": "<float>"
  }
}
```

### Stage 4 — LLM Drafter (Section-by-section drafting)
- **Subpackage:** `src/drafting/` — self-contained Python package with its own `pyproject.toml`, `run.py` entry point, and test suite
- **Entry point:** `src/drafting/run.py` (invoked as a subprocess by `stage_4_drafting()` in `src/run_pipeline.py`)
- **Model:** GPT-4o via `src/drafting/llm/client.py` — `raw_completion()` with frozen `ModelConfig` (temperature 0, 1200 max tokens)
- **Input data:** `src/drafting/data/` — stage-specific JSON files (`ClientProfile.json`, `ModelOutputs.json`, `Outline.json`, `RetrievalBundle.json`) created by `scripts/build_drafting_data.py` from canonical pipeline artifacts
- **Outline:** `src/drafting/data/Outline.json` — 5 sections: `executive_summary`, `grat_analysis`, `crat_analysis`, `comparison_recommendation`, `citations_disclosures`
- **Outputs:**
  - `src/drafting/output/Draft.md` + `Draft.pdf` + `DraftManifest.json`
  - Promoted to `pipeline_artifacts/drafts/` by the orchestrator
- **Pipeline flow** (`src/drafting/pipeline/orchestrate.py` → `drafting_pipeline()`):
  1. Load inputs → build client context → map retrieval chunks to sections by `section_tags`
  2. Bind `{{placeholder}}` tokens to model output values → build per-section prompts
  3. Draft all sections → postprocess (citations, numerics, validation)
  4. Assemble markdown with TOC → write `Draft.md` + `Draft.pdf`
- **Rules:**
  - Every factual claim must carry a citation key from `CitationsManifest_v1.json`
  - Numbers must use `{{placeholder}}` substitution from `TrustComparison_v1.json`, not be written freehand
  - The drafting subpackage uses its own import root (`src/drafting/`). Do not import from `src.run_pipeline` or `src.model` — use the `data/` JSON files as the interface
  - System prompt enforces: no hallucinated figures, no fabricated citations, state uncertainty when support is missing

### Stage 5 — Validator Pack (2 automated gates)
- **Implementation:** `stage_5_validate()` in `src/run_pipeline.py` + `src/drafting/postprocessing/validator.py`
- **Gate 1 — Citation validator:** Draft must contain `[Sxxx]` cite keys. Uncited claims = validation failure.
- **Gate 2 — Numeric binding validator:** Key values from `TrustComparison_v1.json` must appear in the draft. Reports found/missing counts.
- **Additional checks** (in `src/drafting/postprocessing/validator.py`):
  - Unresolved `{{placeholder}}` tokens
  - Dangling `[Sxxx]` citations not in manifest
  - Citation relevance map — semantic validation linking claim keywords to acceptable source IDs (e.g. "IRC §2702 | GRAT" → {S001, S002})
  - Section length constraints (optional, via outline metadata)
- **Output:** `pipeline_artifacts/validation/ValidationReport.json` — `overall_status` + per-gate `status`/`detail`
- **Rule:** Pipeline must not proceed to Stage 6 if `ValidationReport` contains any `"status": "FAIL"` entries.

### Stage 6 — Human Review & Sign-off
- **Implementation:** `stage_6_signoff(auto_approve=False)` in `src/run_pipeline.py`
- **Default mode (manual):** Opens the draft PDF, prompts the reviewer for name, role, and approval decision. Rejected drafts halt the pipeline.
- **Auto-approve mode:** Pass `--auto-approve` CLI flag to skip interactive review (intended for CI/testing only).
- **Output:** `pipeline_artifacts/signoff/Signoff.json` — records `decision`, `reviewer`, `reviewer_role`, `timestamp`, `validation_report_sha256`, `draft_sha256`, `notes`
- **Rule:** PDF assembly must not run without a `Signoff.json` with `"decision": "approved"`.

### Stage 7 — PDF Assembler
- **Implementation:** `stage_7_pdf_assembly()` in `src/run_pipeline.py`
- **Input:** Approved `Draft.pdf` (styled PDF from Stage 4) + `Signoff.json`
- **Output:** `pipeline_artifacts/final_pdf/ClientDeliverable.pdf` — promoted from `pipeline_artifacts/drafts/Draft.pdf`
- **Rules:**
  - Verifies `Signoff.json` has `"decision": "approved"` before proceeding
  - Hard page budget: ≤ 12 pages. Assembler must fail loudly if exceeded.
  - Disclosures section (Circular 230 language) must be present on final page.
  - Citation list is auto-generated from `CitationsManifest_v1.json` — not hand-edited.
  - Logs page count + SHA-256 to `NotesLog.jsonl`

### Stage 8 — Notes Log (Append-only Audit Trail)
- **File:** `audit_logs/NotesLog.jsonl` — one JSON object per line, append-only, never edited
- **Captures:** every stage transition, artifact SHA-256 hashes, LLM prompt hashes, model version, human reviewer identity and timestamp
- **Helper:** `append_notes_log(event: dict)` in `src/run_pipeline.py`
- **Rule:** Every stage must write a log entry before and after execution. Log is immutable — entries must never be deleted or modified.

---

## Repository Structure

```
src/
  __init__.py
  run_pipeline.py        # Orchestrator — runs all 8 stages in sequence
  llm.py                 # Single LLM call wrapper (gpt-4o, temperature=0, audited)
  retrieval/
    __init__.py
    allowlist.py         # URL/domain allowlist enforcement
    plan.py              # Load + validate RetrievalPlan JSON
    fetch.py             # HTTP fetch with allowlist check, SHA-256, meta.json
    parse.py             # HTML/PDF → plain text → chunks (1200 char, 200 overlap)
    index.py             # TF-IDF index build + search (scikit-learn)
    bundle.py            # Query index per topic → RetrievalBundle + CitationsManifest
    coverage.py          # Coverage report (GREEN/YELLOW/RED per topic)
  model/
    __init__.py          # Public API — exports run_deterministic_model()
    schemas.py           # Frozen dataclasses: ClientInput, ModelAssumptions, GRATOutput, CRATOutput, ComparisonOutput, TrustComparisonModel
    io.py                # I/O: load_client_profile(), extract_client_input(), create_default_assumptions(), load_section_7520_rate(), write_model_output()
    grat.py              # GRAT calculations: calculate_annuity_payment(), simulate_trust_value(), calculate_grat()
    crat.py              # CRAT calculations: simulate_crat_trust_value(), calculate_charitable_deduction(), calculate_crat()
    compare.py           # Comparison: calculate_comparison() — estate tax, wealth transfer, charitable dimensions
    engine.py            # Orchestrator: run_deterministic_model() — loads inputs, runs calculations, writes outputs + audit log
  drafting/              # Self-contained Stage 4 subpackage (own pyproject.toml + import root)
    run.py               # Entry point — deterministic fallback drafter when no API key
    fix_draft.py         # Draft repair utility
    pyproject.toml       # Package config (openai, requests, scikit-learn)
    README.md            # Drafting subpackage documentation
    data/                # Stage-specific input JSON files (built by scripts/build_drafting_data.py)
      ClientProfile.json
      ModelOutputs.json
      Outline.json
      RetrievalBundle.json
    loaders/             # Typed input loaders (frozen dataclasses)
      __init__.py        # Re-exports: ClientProfile, ModelOutputs, Outline, RetrievalBundle, etc.
      client_profile.py  # ClientProfile dataclass + load_client_profile()
      model_outputs.py   # ModelOutputs dataclass + load_model_outputs()
      outline.py         # Outline, OutlineSection dataclasses + load_outline()
      retrieval_bundle.py # RetrievalBundle, RetrievalChunk dataclasses + load_retrieval_bundle()
    context/             # Prompt context assembly
      client_context.py  # format_client_context_block() — natural language client summary
      numeric_binder.py  # bind_numeric_values() — {{placeholder}} → formatted values ($, %, bps)
      section_context.py # build_section_context() — map retrieval chunks to outline sections by section_tags
    prompts/             # Prompt templates
      system_prompt.py   # SYSTEM_PROMPT constant — financial advisor persona + operating rules
      section_prompt.py  # section_draft_prompt_builder() — per-section user prompt with token budget
      citation_instructions.py # Available [Sxxx] sources per section
    llm/                 # LLM client
      client.py          # raw_completion() — OpenAI/Anthropic, ModelConfig dataclass, retry logic
    drafting/            # Section drafting logic
      pipeline.py        # draft_all_sections() — serial or parallel section drafting
      section_drafter.py # draft_section() — single section LLM call + optional self-critique
    postprocessing/      # Citation, numeric, validation
      citation_inserter.py  # insert_citations() — resolve [Sxxx] to inline references
      numeric_substituter.py # substitute_numerics() — replace {{placeholder}} with formatted values
      validator.py       # validate_section_output() — unresolved placeholders, dangling cites, relevance map
    output/              # Output writers
      assembler.py       # assemble_draft() — TOC + sections in outline order
      writer.py          # write_draft_md() — markdown with generation metadata footer + SHA-256 hashes
      pdf.py             # write_draft_pdf() — styled A4 PDF (navy/gold, headers/footers)
      references.py      # append_global_references() — deduplicated reference list
      manifest.py        # build_draft_manifest() + write_draft_manifest() — comprehensive audit record
    utils/               # Shared utilities
      io.py              # load_json() with error handling
      token_budget.py    # Token estimation
    tests/               # 21 test files — unit + integration coverage

scripts/
  build_drafting_data.py # Transform pipeline artifacts → src/drafting/data/ (topic→section mapping, chunk selection)
  remap_tags.py          # Remap chunk section_tags to align with outline sections

pipeline_artifacts/
  intake/                # ClientProfile_v1.json
  config/
    model_assumptions.json    # Growth rates, term years, payout rates (no hardcoded constants in code)
    section_7520_rates.json   # Historical IRS §7520 rates by year/month (sourced from RAG S007)
  retrieval/
    raw/                 # S001.html … S011.html + *.meta.json
    parsed/              # S001.txt … S011.txt + *_chunks.json
    index/               # index.pkl
    plan/                # RetrievalPlan_v1.json
    bundle/              # RetrievalBundle_v1.json, CitationsManifest_v1.json, RetrievalCoverageReport_v1.json
  model_outputs/         # TrustComparison_v1.json, ModelRunReport.json
  drafts/                # Draft.md, Draft.pdf (promoted from src/drafting/output/)
  validation/            # ValidationReport.json
  signoff/               # Signoff.json
  final_pdf/             # ClientDeliverable.pdf

tests/                   # Core pipeline tests (7 files)
  test_allowlist.py
  test_fetch_seed.py
  test_index.py
  test_model.py
  test_model_integration.py
  test_parse.py
  test_plan.py

audit_logs/
  NotesLog.jsonl         # Append-only audit trail
```

---

## Implementation Status

| Stage | Status |
|---|---|
| 1 — Client Intake | ✅ Complete — `ClientProfile_v1.json` exists |
| 2 — RAG Retrieval | ✅ Complete — 11 sources fetched, indexed, bundle built, 7/7 GREEN coverage |
| 3 — Trust Modeler | ✅ Complete — `src/model/` package with GRAT, CRAT, comparison; config-driven; `TrustComparison_v1.json` + `ModelRunReport.json` generated; unit + integration tests pass |
| 4 — LLM Drafter | ✅ Complete — `src/drafting/` subpackage with deterministic fallback; `Draft.md` + `Draft.pdf` + `DraftManifest.json` generated; 21 tests |
| 5 — Validator Pack | ✅ Complete — 2/2 gates PASS; `ValidationReport.json` generated |
| 6 — Human Sign-off | ✅ Complete — auto-approval mode; `Signoff.json` generated (production requires manual review) |
| 7 — PDF Assembler | ✅ Complete — `ClientDeliverable.pdf` generated (≤12 pages verified) |
| 8 — Audit Log | ✅ Complete — `NotesLog.jsonl` captures all stage transitions with SHA-256 hashes |

---

## Coding Conventions

- **Language:** Python 3.11+
- **Path handling:** Always use `pathlib.Path`. Never use `os.path`. Anchor to `BASE_DIR = Path(__file__).resolve().parent.parent`.
- **JSON I/O:** Always `encoding="utf-8"`. Use `json.dumps(..., indent=2, sort_keys=True)` for artifact files.
- **Versioning:** Artifact files are named with `_v1` suffix. Increment version on schema changes.
- **Hashing:** SHA-256 every artifact file at write time. Log the hash to `NotesLog.jsonl`.
- **Errors:** Raise specific exception subclasses (e.g. `FetchError`, `ParseError`, `IndexError`). Never use bare `except`.
- **Incremental fetching:** `fetch_many()` in `src/retrieval/fetch.py` is idempotent — it skips URLs already recorded in any `S*.meta.json` and continues numbering from the highest existing source ID. To add new sources, add their URLs to `preferred_primary_urls` in `RetrievalPlan_v1.json` and re-run the fetcher. Never manually assign source IDs.
- **Tests:** Place in `tests/`. Use `pytest`. Tests must not make live HTTP requests — use fixtures or mocks.
- **LLM calls:** Always go through `call_llm()` in `src/llm.py`. Never call the OpenAI client directly from other modules. Always write the returned `audit_record` to `NotesLog.jsonl`.
- **No freehand numbers:** No numeric literals representing client financial data, legal thresholds, or modeling assumptions may appear in source code. Read them from `ClientProfile_v1.json`, `TrustComparison_v1.json`, `model_assumptions.json`, or `section_7520_rates.json`.
- **Frozen dataclasses:** All model dataclasses use `@dataclass(frozen=True)` for immutability. Never mutate a model object after construction.
- **Monetary rounding:** All monetary values must be `round(value, 2)` — 2 decimal places.
- **Model configuration:** All modeling assumptions (growth rates, term lengths, payout rates) must be read from `pipeline_artifacts/config/model_assumptions.json`. §7520 rates are looked up from `pipeline_artifacts/config/section_7520_rates.json` by year/month.

---

## Hard Constraints (Never Violate)

1. **No hallucinated citations.** Every cite key used in the draft must exist in `CitationsManifest_v1.json`.
2. **No hallucinated numbers.** Every financial figure in the draft must originate from `TrustComparison_v1.json`.
3. **No off-allowlist sources.** The fetcher must reject any domain not in `["irs.gov", "treasury.gov", "law.cornell.edu"]` plus `FirmKB`.
4. **No unsigned PDF.** `Signoff.json` with `"decision": "approved"` must exist before PDF assembly runs.
5. **12-page hard limit.** The assembler must raise an error if the rendered PDF exceeds 12 pages.
6. **Audit log is immutable.** `NotesLog.jsonl` is append-only. No entry may ever be edited or deleted.
