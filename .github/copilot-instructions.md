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
- **Input:** `ClientProfile_v1.json` + §7520 rate extracted from `pipeline_artifacts/retrieval/parsed/S007_chunks.json`
- **Outputs:**
  - `pipeline_artifacts/model_outputs/ModelOutputs.json` — all scenario numbers (see required schema below)
  - `pipeline_artifacts/model_outputs/ModelRunReport.json` — input hashes, model version, timestamp
- **Rules:**
  - All numbers in the final PDF must originate from `ModelOutputs.json`. The LLM must never compute or invent numeric values.
  - Model must be fully deterministic — no random state; same inputs always produce identical outputs.
  - All client financial figures must be read from `ClientProfile_v1.json`. No hard-coded numeric literals in model code.
  - SHA-256 of `ClientProfile_v1.json` must be written into `ModelRunReport.json`.
  - `append_notes_log()` must be called before and after the model runs.

#### Required `ModelOutputs.json` schema (minimum fields)

```json
{
  "model_version": "1.0",
  "section_7520_rate": "<float — from S007 retrieval>",
  "grat": {
    "trust_corpus_usd": "<from ClientProfile>",
    "term_years": "<int>",
    "annuity_payment_usd": "<float>",
    "section_7520_rate_used": "<float>",
    "remainder_value_at_term_usd": "<float>",
    "gift_tax_value_of_remainder_usd": "<float>",
    "estate_tax_saving_usd": "<float>"
  },
  "crat": {
    "trust_corpus_usd": "<from ClientProfile>",
    "annuity_rate_pct": "<float>",
    "annuity_payment_annual_usd": "<float>",
    "charitable_deduction_usd": "<float>",
    "estate_removal_usd": "<float>",
    "income_stream_years": "<int>"
  },
  "comparison": {
    "taxable_estate_before_usd": "<from ClientProfile>",
    "taxable_estate_after_grat_usd": "<float>",
    "taxable_estate_after_crat_usd": "<float>",
    "estate_tax_saving_grat_usd": "<float>",
    "estate_tax_saving_crat_usd": "<float>"
  }
}
```

### Stage 4 — Single-Writer LLM (Section-by-section drafting)
- **Model:** `gpt-5` via `src/llm.py` (`call_llm(system_prompt, user_prompt)`)
- **Input context:** `ClientProfile_v1.json` + `RetrievalBundle_v1.json` + `ModelOutputs.json` + section outline
- **Output:** `pipeline_artifacts/drafts/Draft.md` with inline citation keys (e.g. `[S3]`) and numeric placeholders bound to `ModelOutputs.json` keys
- **Rules:**
  - Every factual claim must carry a citation key from `CitationsManifest_v1.json`
  - Numbers must reference a named field from `ModelOutputs.json`, not be written freehand
  - Temperature = 0; audit record written to `NotesLog.jsonl` for every call

### Stage 5 — Validator Pack (2 automated gates)
- **Gate 1 — Citation validator:** Every claim sentence must contain at least one `[Sx]` cite key. Uncited claims = validation failure.
- **Gate 2 — Numeric binding validator:** Every number in the draft must match a value in `ModelOutputs.json`. Freehand numbers = validation failure.
- **Output:** `pipeline_artifacts/validation/ValidationReport.json`
- **Rule:** Pipeline must not proceed to Stage 6 if ValidationReport contains any `"status": "FAIL"` entries.

### Stage 6 — Human Review & Sign-off
- **Participants:** Advisor + Compliance officer
- **Output:** `pipeline_artifacts/signoff/Signoff.json` — records reviewer identity, timestamp, approve/reject decision, and any required revisions
- **Rule:** PDF assembly must not run without a `Signoff.json` with `"decision": "approved"`.

### Stage 7 — PDF Assembler
- **Input:** Approved `Draft.md` + `CitationsManifest_v1.json` + `Signoff.json` + fixed template
- **Output:** `pipeline_artifacts/final_pdf/ClientDeliverable.pdf`
- **Rules:**
  - Hard page budget: ≤ 12 pages. Assembler must fail loudly if exceeded.
  - Disclosures section (Circular 230 language) must be present on final page.
  - Citation list must be auto-generated from `CitationsManifest_v1.json` — not hand-edited.

### Stage 8 — Notes Log (Append-only Audit Trail)
- **File:** `audit_logs/NotesLog.jsonl` — one JSON object per line, append-only, never edited
- **Captures:** every stage transition, artifact SHA-256 hashes, LLM prompt hashes, model version, human reviewer identity and timestamp
- **Helper:** `append_notes_log(event: dict)` in `src/run_pipeline.py`
- **Rule:** Every stage must write a log entry before and after execution. Log is immutable — entries must never be deleted or modified.

---

## Repository Structure

```
src/
  run_pipeline.py        # Orchestrator — runs all stages in sequence
  llm.py                 # Single LLM call wrapper (gpt-5, temperature=0, audited)
  retrieval/
    allowlist.py         # URL/domain allowlist enforcement
    plan.py              # Load + validate RetrievalPlan JSON
    fetch.py             # HTTP fetch with allowlist check, SHA-256, meta.json
    parse.py             # HTML/PDF → plain text → chunks (1200 char, 200 overlap)
    index.py             # TF-IDF index build + search (scikit-learn)
    bundle.py            # Query index per topic → RetrievalBundle + CitationsManifest
    coverage.py          # Coverage report (GREEN/YELLOW/RED per topic)

pipeline_artifacts/
  intake/                # ClientProfile_v1.json
  retrieval/
    raw/                 # S001.html … S011.html + *.meta.json
    parsed/              # S001.txt … S011.txt + *_chunks.json
    index/               # index.pkl
    plan/                # RetrievalPlan_v1.json
    bundle/              # RetrievalBundle_v1.json, CitationsManifest_v1.json, RetrievalCoverageReport_v1.json
  model_outputs/         # ModelOutputs.json, ModelRunReport.json (Stage 3 — not yet built)
  drafts/                # Draft.md (Stage 4 — not yet built)
  validation/            # ValidationReport.json (Stage 5 — not yet built)
  signoff/               # Signoff.json (Stage 6 — not yet built)
  final_pdf/             # ClientDeliverable.pdf (Stage 7 — not yet built)

audit_logs/
  NotesLog.jsonl         # Append-only audit trail
```

---

## Implementation Status

| Stage | Status |
|---|---|
| 1 — Client Intake | ✅ Complete — `ClientProfile_v1.json` exists |
| 2 — RAG Retrieval | ✅ Complete — 11 sources fetched, indexed, bundle built, 7/7 GREEN coverage |
| 3 — Trust Modeler | 🔲 Not yet built |
| 4 — LLM Drafter | 🔲 Not yet built (`llm.py` wrapper exists) |
| 5 — Validator Pack | 🔲 Not yet built |
| 6 — Human Sign-off | 🔲 Not yet built |
| 7 — PDF Assembler | 🔲 Not yet built |
| 8 — Audit Log | ✅ Partial — `NotesLog.jsonl` + `append_notes_log()` exist |

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
- **No freehand numbers:** No numeric literals representing client financial data or legal thresholds may appear in source code. Read them from `ClientProfile_v1.json` or `ModelOutputs.json`.

---

## Hard Constraints (Never Violate)

1. **No hallucinated citations.** Every cite key used in the draft must exist in `CitationsManifest_v1.json`.
2. **No hallucinated numbers.** Every financial figure in the draft must originate from `ModelOutputs.json`.
3. **No off-allowlist sources.** The fetcher must reject any domain not in `["irs.gov", "treasury.gov", "law.cornell.edu"]` plus `FirmKB`.
4. **No unsigned PDF.** `Signoff.json` with `"decision": "approved"` must exist before PDF assembly runs.
5. **12-page hard limit.** The assembler must raise an error if the rendered PDF exceeds 12 pages.
6. **Audit log is immutable.** `NotesLog.jsonl` is append-only. No entry may ever be edited or deleted.
