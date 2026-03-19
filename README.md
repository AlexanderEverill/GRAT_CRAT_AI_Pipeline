# GRAT/CRAT AI Pipeline

An automated pipeline that produces a client-facing PDF (≤ 12 pages) presenting and comparing a **Grantor Retained Annuity Trust (GRAT)** and a **Charitable Remainder Annuity Trust (CRAT)** for estate-planning purposes.

Given a client profile — age, marital status, estate size, tax context, and planning goals — the pipeline retrieves authoritative legal sources, runs deterministic trust calculations, drafts a professional advisory memo with LLM assistance, validates every claim against its sources, collects human sign-off, and assembles a final deliverable PDF. The entire process is audited end-to-end.

## What It Produces

The pipeline produces a single PDF (`pipeline_artifacts/final_pdf/ClientDeliverable.pdf`) containing:

- **Executive Summary** — client situation, key figures, and a clear primary/complementary strategy recommendation
- **GRAT Analysis** — annuity structure, §7520 hurdle rate mechanics, mortality risk, projected wealth transfer to children
- **CRAT Analysis** — fixed annuity structure, charitable deduction, remainder to charity, estate tax implications
- **Comparison & Recommendation** — side-by-side table across six planning dimensions with a consistent professional recommendation
- **Citations & Disclosures** — sourced references to IRC/CFR statutes and a Circular 230 compliance notice

Every number in the document originates from a deterministic model. Every legal claim is traced to an allowlisted source. Nothing is hallucinated.

## Pipeline Structure

The pipeline executes 8 stages in sequence. Each stage reads from and writes to `pipeline_artifacts/`, creating a verifiable chain of artifacts from intake to deliverable.

```
Stage 1          Stage 2           Stage 3            Stage 4
Client Intake → RAG Retrieval → Trust Modeler → LLM Drafter
                                                      ↓
Stage 8          Stage 7           Stage 6          Stage 5
Audit Log    ← PDF Assembly   ← Human Signoff  ← Validator Pack
```

### Stage 1 — Client Intake
Loads and validates the client profile (`ClientProfile_v1.json`). All downstream stages read client facts exclusively from this file — no client data is hard-coded anywhere in the codebase.

### Stage 2 — RAG Retrieval
Fetches legal sources from a strict allowlist (`irs.gov`, `treasury.gov`, `law.cornell.edu`) and internal firm knowledge. Raw HTML is parsed into text, chunked, and indexed with TF-IDF. A coverage report grades each topic GREEN/YELLOW/RED — the pipeline halts on RED gaps. Currently 11 sources, 7/7 topics GREEN.

### Stage 3 — Deterministic Trust Modeler
Calculates GRAT and CRAT projections using frozen, immutable dataclasses. The §7520 rate is looked up from a configuration file by year; growth rates, term lengths, and payout rates are read from `model_assumptions.json`. The model is fully deterministic — same inputs always produce identical outputs. All monetary values are rounded to 2 decimal places.

### Stage 4 — LLM Drafter
Drafts each section of the memo individually using GPT-4o (temperature 0) with section-specific prompts containing the client context, retrieval chunks, and numeric bindings. A consistency mechanism extracts the executive summary's recommendation after it is drafted and injects it into the comparison section's prompt, ensuring the primary/complementary strategy framing is aligned across the document. A deterministic fallback drafter runs when no API key is available.

### Stage 5 — Validator Pack
Two automated gates must pass before the draft can proceed:
1. **Citation validator** — every `[Sxxx]` cite key in the draft must exist in the citations manifest
2. **Numeric binding validator** — key financial figures from the trust model must appear in the draft text

Additional checks catch unresolved `{{placeholder}}` tokens, dangling citations, and citation-claim relevance mismatches.

### Stage 6 — Human Review & Sign-off
By default, the pipeline opens the draft PDF and prompts the reviewer for their name, role, and approval decision. Rejected drafts halt the pipeline. An `--auto-approve` flag is available for CI/testing only.

### Stage 7 — PDF Assembly
Promotes the approved draft PDF to `ClientDeliverable.pdf` after verifying the sign-off decision and enforcing the 12-page hard limit. The Circular 230 disclosure must be present. Page count and SHA-256 hash are logged.

### Stage 8 — Audit Log
An append-only JSONL file (`audit_logs/NotesLog.jsonl`) records every stage transition, artifact SHA-256 hashes, LLM prompt hashes, model versions, and reviewer identity. Entries are never edited or deleted.

## Why It Was Designed This Way

### No Hallucinated Numbers
LLMs are unreliable at arithmetic. The pipeline separates computation from prose: Stage 3 runs all calculations deterministically in Python, and Stage 4 substitutes pre-computed values into the draft via `{{placeholder}}` tokens. The LLM never performs or invents a calculation.

### No Hallucinated Citations
Every legal claim must be grounded in a retrieved source. The fetcher enforces a domain allowlist so no off-list content enters the pipeline, and the validator confirms that every cite key in the draft maps to a real source in the manifest. The LLM cannot fabricate a citation that passes validation.

### Section-by-Section Drafting with Consistency Enforcement
Drafting sections independently keeps prompts focused and token-efficient, but risks cross-section contradictions. The pipeline solves this by extracting the executive summary's recommendation after drafting it and injecting that text as a binding constraint into the comparison section's prompt. This ensures the document speaks with one voice without requiring a monolithic prompt.

### Deterministic Reproducibility
The trust model uses frozen dataclasses, reads all assumptions from configuration files, and contains no random state. Running the pipeline twice on the same inputs produces identical model outputs. This is essential for audit defensibility — regulators and compliance reviewers can verify that the numbers in the PDF correspond exactly to the model's inputs and logic.

### Human-in-the-Loop
Automated validation catches structural errors (missing citations, wrong numbers, unresolved placeholders), but professional judgment requires human review. Stage 6 defaults to interactive sign-off where a named reviewer approves or rejects the draft. The reviewer's identity, decision, and timestamp are recorded in the audit trail. Auto-approval exists only for development and CI.

### Append-Only Audit Trail
Every stage writes to `NotesLog.jsonl` before and after execution, recording SHA-256 hashes of all artifacts. This creates an immutable provenance chain: given the final PDF, you can trace backward through every intermediate artifact to the original client profile and source documents. No log entry is ever modified or deleted.

### Configuration Over Code
Financial constants (growth rates, §7520 rates, payout rates, exemption thresholds) live in JSON configuration files, not in source code. This means assumptions can be reviewed and updated by non-engineers, and the codebase doesn't need modification when rates change.

## Running the Pipeline

```bash
# Full pipeline with manual review (production)
python src/run_pipeline.py

# Full pipeline with auto-approval (CI/testing)
python src/run_pipeline.py --auto-approve
```

### Requirements
- Python 3.11+
- Dependencies: `openai`, `requests`, `scikit-learn`, `fpdf2`
- An OpenAI API key (set `OPENAI_API_KEY`) for LLM drafting, or the pipeline falls back to a deterministic drafter

### Tests
```bash
# Core pipeline tests
pytest tests/

# Drafting subpackage tests
cd src/drafting && pytest tests/
```

## Repository Layout

```
src/
  run_pipeline.py          # Orchestrator — runs all 8 stages
  model/                   # Stage 3: deterministic GRAT/CRAT calculations
  retrieval/               # Stage 2: fetch, parse, index, bundle, coverage
  drafting/                # Stage 4: self-contained drafting subpackage
    prompts/               #   LLM prompt templates
    drafting/              #   Section drafting with consistency enforcement
    postprocessing/        #   Citation, numeric, and validation checks
    output/                #   Markdown assembly and PDF rendering

pipeline_artifacts/
  intake/                  # ClientProfile_v1.json
  config/                  # model_assumptions.json, section_7520_rates.json
  retrieval/               # Raw sources, parsed chunks, index, bundle
  model_outputs/           # TrustComparison_v1.json, ModelRunReport.json
  drafts/                  # Draft_1.md through Draft_N.md (iterative history)
  validation/              # ValidationReport.json
  signoff/                 # Signoff.json
  final_pdf/               # ClientDeliverable.pdf

audit_logs/
  NotesLog.jsonl           # Append-only audit trail

tests/                     # Core pipeline tests
```
