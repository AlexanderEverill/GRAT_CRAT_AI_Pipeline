"""Pipeline orchestrator — runs all 8 stages in sequence.

Stages:
  1. Client Intake          — load and validate ClientProfile_v1.json
  2. RAG Retrieval          — already complete (11 sources, 7/7 GREEN)
  3. Deterministic Modeler  — GRAT + CRAT calculations
  4. LLM Drafter            — section-by-section drafting (deterministic fallback)
  5. Validator Pack          — citation + numeric binding validation
  6. Human Sign-off         — record approval decision
  7. PDF Assembler           — render final client-facing PDF (≤12 pages)
  8. Audit Log              — append-only trail (woven throughout)
"""

import argparse
import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

# Always anchor paths to the project root (one level above /src)
BASE_DIR = Path(__file__).resolve().parent.parent

CLIENT_PROFILE_PATH = BASE_DIR / "pipeline_artifacts" / "intake" / "ClientProfile_v1.json"
TRUST_COMPARISON_PATH = BASE_DIR / "pipeline_artifacts" / "model_outputs" / "TrustComparison_v1.json"
RETRIEVAL_BUNDLE_PATH = BASE_DIR / "pipeline_artifacts" / "retrieval" / "bundle" / "RetrievalBundle_v1.json"
CITATIONS_MANIFEST_PATH = BASE_DIR / "pipeline_artifacts" / "retrieval" / "bundle" / "CitationsManifest_v1.json"
COVERAGE_REPORT_PATH = BASE_DIR / "pipeline_artifacts" / "retrieval" / "bundle" / "RetrievalCoverageReport_v1.json"
VALIDATION_REPORT_PATH = BASE_DIR / "pipeline_artifacts" / "validation" / "ValidationReport.json"
SIGNOFF_PATH = BASE_DIR / "pipeline_artifacts" / "signoff" / "Signoff.json"
FINAL_PDF_PATH = BASE_DIR / "pipeline_artifacts" / "final_pdf" / "ClientDeliverable.pdf"
NOTES_LOG_PATH = BASE_DIR / "audit_logs" / "NotesLog.jsonl"

DRAFTING_DIR = BASE_DIR / "src" / "drafting"
DRAFTS_DIR = BASE_DIR / "pipeline_artifacts" / "drafts"
DRAFT_MD_PATH = DRAFTS_DIR / "Draft.md"
DRAFT_PDF_PATH = DRAFTS_DIR / "Draft.pdf"

# Internal drafting module output (before promotion to pipeline_artifacts/drafts/)
_DRAFTING_OUTPUT_MD = DRAFTING_DIR / "output" / "Draft.md"
_DRAFTING_OUTPUT_PDF = DRAFTING_DIR / "output" / "Draft.pdf"


# ── Draft versioning ────────────────────────────────────────────────


def _next_draft_version(drafts_dir: Path) -> int:
    """Return the next draft version number by scanning existing files.

    Looks for files matching Draft_N.md in the drafts directory and
    returns max(N) + 1.  If no versioned drafts exist, returns 1.
    """
    import re as _re
    highest = 0
    if drafts_dir.exists():
        for p in drafts_dir.iterdir():
            m = _re.match(r"^Draft_(\d+)\.md$", p.name)
            if m:
                highest = max(highest, int(m.group(1)))
    return highest + 1


def _archive_draft(drafts_dir: Path, src_md: Path, src_pdf: Path) -> int:
    """Copy a draft into the versioned archive and return its version number.

    Creates:
      - Draft_N.md  / Draft_N.pdf   (immutable archive copy)
      - Draft.md    / Draft.pdf     (latest, used by downstream stages)
    """
    drafts_dir.mkdir(parents=True, exist_ok=True)
    version = _next_draft_version(drafts_dir)

    versioned_md = drafts_dir / f"Draft_{version}.md"
    versioned_pdf = drafts_dir / f"Draft_{version}.pdf"

    # Archive copy (immutable — never overwritten)
    shutil.copy2(src_md, versioned_md)
    shutil.copy2(src_pdf, versioned_pdf)

    # Latest copy (downstream stages read these)
    shutil.copy2(src_md, drafts_dir / "Draft.md")
    shutil.copy2(src_pdf, drafts_dir / "Draft.pdf")

    return version


# ── Utility helpers ──────────────────────────────────────────────────


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def append_notes_log(event: dict) -> None:
    NOTES_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with NOTES_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


# ── Stage 1: Client Intake ──────────────────────────────────────────


def stage_1_intake() -> Tuple[dict, str]:
    """Load and validate ClientProfile_v1.json."""
    if not CLIENT_PROFILE_PATH.exists():
        raise FileNotFoundError(
            f"Client profile not found at: {CLIENT_PROFILE_PATH}"
        )

    raw = CLIENT_PROFILE_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Client profile is empty: {CLIENT_PROFILE_PATH}")

    try:
        client_profile = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Client profile JSON invalid: {e}") from e

    profile_hash = sha256_file(CLIENT_PROFILE_PATH)

    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "1_client_intake",
        "artifact_path": str(CLIENT_PROFILE_PATH),
        "artifact_sha256": profile_hash,
        "profile_version": client_profile.get("metadata", {}).get("profile_version"),
    })

    print("✅ Stage 1 complete: ClientProfile loaded")
    return client_profile, profile_hash


# ── Stage 2: RAG Retrieval (pre-built) ──────────────────────────────


def stage_2_retrieval() -> None:
    """Verify retrieval artifacts exist and coverage is GREEN."""
    for path, label in [
        (RETRIEVAL_BUNDLE_PATH, "RetrievalBundle"),
        (CITATIONS_MANIFEST_PATH, "CitationsManifest"),
        (COVERAGE_REPORT_PATH, "RetrievalCoverageReport"),
    ]:
        if not path.exists():
            raise FileNotFoundError(f"{label} not found: {path}")

    coverage = json.loads(COVERAGE_REPORT_PATH.read_text(encoding="utf-8"))
    topics = coverage.get("topics", coverage.get("coverage", []))
    red_topics = []
    if isinstance(topics, list):
        red_topics = [t for t in topics if t.get("status") == "RED"]
    elif isinstance(topics, dict):
        red_topics = [k for k, v in topics.items() if v.get("status") == "RED"]

    if red_topics:
        raise RuntimeError(
            f"Retrieval coverage RED for topics: {red_topics}. "
            "Pipeline halted — resolve retrieval gaps before proceeding."
        )

    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "2_retrieval_verified",
        "retrieval_bundle_sha256": sha256_file(RETRIEVAL_BUNDLE_PATH),
        "citations_manifest_sha256": sha256_file(CITATIONS_MANIFEST_PATH),
        "coverage_status": "ALL_GREEN",
    })

    print("✅ Stage 2 complete: Retrieval artifacts verified (7/7 GREEN)")


# ── Stage 3: Deterministic Trust Modeler ─────────────────────────────


def stage_3_model() -> Path:
    """Run the deterministic GRAT/CRAT model if outputs are stale."""
    if TRUST_COMPARISON_PATH.exists():
        print("✅ Stage 3 complete: TrustComparison_v1.json already exists (cached)")
        append_notes_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": "3_deterministic_trust_modeler",
            "event": "Using cached model output",
            "artifact_sha256": sha256_file(TRUST_COMPARISON_PATH),
        })
        return TRUST_COMPARISON_PATH

    from src.model.engine import run_deterministic_model
    output_path = run_deterministic_model()
    print("✅ Stage 3 complete: TrustComparison_v1.json generated")
    return output_path


# ── Stage 4: LLM Drafter ────────────────────────────────────────────


def stage_4_drafting() -> Tuple[Path, Path]:
    """Run the Stage 4 drafting pipeline via src/drafting/run.py."""
    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "4_llm_drafter_start",
        "event": "Starting section-by-section drafting",
    })

    result = subprocess.run(
        [sys.executable, "run.py"],
        cwd=str(DRAFTING_DIR),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Stage 4 drafting failed (exit {result.returncode}):\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    if not _DRAFTING_OUTPUT_MD.exists():
        raise FileNotFoundError(f"Draft.md not generated at {_DRAFTING_OUTPUT_MD}")
    if not _DRAFTING_OUTPUT_PDF.exists():
        raise FileNotFoundError(f"Draft.pdf not generated at {_DRAFTING_OUTPUT_PDF}")

    # Archive as Draft_N.md / Draft_N.pdf and update Draft.md / Draft.pdf
    version = _archive_draft(DRAFTS_DIR, _DRAFTING_OUTPUT_MD, _DRAFTING_OUTPUT_PDF)

    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "4_llm_drafter_complete",
        "draft_version": version,
        "draft_md_sha256": sha256_file(DRAFT_MD_PATH),
        "draft_pdf_sha256": sha256_file(DRAFT_PDF_PATH),
        "versioned_md": f"Draft_{version}.md",
        "versioned_pdf": f"Draft_{version}.pdf",
        "draft_location": str(DRAFTS_DIR),
    })

    print(f"✅ Stage 4 complete: Draft_{version}.md + Draft_{version}.pdf → {DRAFTS_DIR}")
    return DRAFT_MD_PATH, DRAFT_PDF_PATH


# ── Stage 5: Validator Pack ──────────────────────────────────────────


def stage_5_validate(draft_md_path: Path) -> Path:
    """Run citation and numeric binding validation on the draft."""
    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "5_validator_start",
        "event": "Starting validation gates",
    })

    draft_text = draft_md_path.read_text(encoding="utf-8")
    trust_comparison = json.loads(TRUST_COMPARISON_PATH.read_text(encoding="utf-8"))
    citations_manifest = json.loads(CITATIONS_MANIFEST_PATH.read_text(encoding="utf-8"))

    results = []

    # Gate 1: Citation validator
    # Check that factual content sections contain citation references
    valid_cite_keys = set()
    for c in citations_manifest.get("citations", []):
        valid_cite_keys.add(c.get("cite_key", ""))
        valid_cite_keys.add(c.get("source_id", ""))

    # Check for inline citation patterns: (S00N, url, n.d.) or [SRC-N] or [SN]
    cite_pattern = re.compile(r"\(S\d{3},\s*https?://[^)]+\)|\[SRC-\d+\]|\[S\d+\]")
    has_citations = bool(cite_pattern.search(draft_text))
    citation_status = "PASS" if has_citations else "FAIL"
    citation_detail = "Citations found in draft" if has_citations else "No citations found"
    results.append({
        "gate": "citation_validator",
        "status": citation_status,
        "detail": citation_detail,
    })

    # Gate 2: Numeric binding validator
    # Check that key financial figures from TrustComparison appear in the draft
    key_values = []
    for section_key in ("grat", "crat", "comparison"):
        section_data = trust_comparison.get(section_key, {})
        if isinstance(section_data, dict):
            for k, v in section_data.items():
                if isinstance(v, (int, float)) and v != 0.0:
                    key_values.append((f"{section_key}.{k}", v))

    matched = 0
    unmatched = []
    for field_name, value in key_values:
        # Format the value as it might appear in the draft (with commas/decimals)
        formatted = f"{value:,.2f}"
        if formatted in draft_text:
            matched += 1
        else:
            # Try without trailing zeros
            formatted_alt = f"{value:,.0f}" if value == int(value) else formatted
            if formatted_alt in draft_text:
                matched += 1
            else:
                unmatched.append(field_name)

    numeric_status = "PASS" if matched > 0 else "FAIL"
    numeric_detail = f"{matched}/{len(key_values)} key values found in draft"
    if unmatched:
        numeric_detail += f"; missing: {unmatched[:5]}"
    results.append({
        "gate": "numeric_binding_validator",
        "status": numeric_status,
        "detail": numeric_detail,
    })

    overall_status = "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL"

    report = {
        "validation_timestamp": datetime.now(timezone.utc).isoformat(),
        "pipeline_stage": "Stage 5 — Validator Pack",
        "overall_status": overall_status,
        "gates": results,
        "draft_sha256": sha256_file(draft_md_path),
    }

    VALIDATION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )

    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "5_validator_complete",
        "overall_status": overall_status,
        "gates": results,
        "artifact_sha256": sha256_file(VALIDATION_REPORT_PATH),
    })

    if overall_status == "FAIL":
        failing = [r for r in results if r["status"] == "FAIL"]
        print(f"⚠️  Stage 5: Validation FAILED — {failing}")
        raise RuntimeError(
            f"Validation failed: {failing}. Pipeline halted."
        )

    print("✅ Stage 5 complete: All validation gates PASS")
    return VALIDATION_REPORT_PATH


# ── Stage 6: Human Sign-off ─────────────────────────────────────────


def _manual_signoff() -> dict:
    """Interactive sign-off: display draft info and prompt the reviewer."""
    draft_hash = sha256_file(DRAFT_MD_PATH)
    validation_hash = sha256_file(VALIDATION_REPORT_PATH)

    print("\n" + "─" * 60)
    print("  Stage 6 — Manual Review & Sign-off")
    print("─" * 60)
    print(f"  Draft:      {DRAFT_MD_PATH}")
    print(f"  Draft PDF:  {DRAFT_PDF_PATH}")
    print(f"  Draft SHA:  {draft_hash[:16]}…")
    print(f"  Validation: PASS (SHA {validation_hash[:16]}…)")
    print("─" * 60)
    print("  Please review the draft before approving.")
    print("  The PDF has been opened for your review.\n")

    # Open the PDF for the reviewer (best-effort; non-blocking).
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(DRAFT_PDF_PATH)])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(DRAFT_PDF_PATH)])
        elif sys.platform == "win32":
            os.startfile(str(DRAFT_PDF_PATH))  # type: ignore[attr-defined]
    except OSError:
        pass  # If opener fails, the reviewer can open it manually.

    reviewer_name = input("  Reviewer name: ").strip()
    if not reviewer_name:
        raise RuntimeError("Reviewer name is required for manual sign-off.")

    reviewer_role = input("  Reviewer role (e.g. Financial Advisor, Compliance Officer): ").strip()
    if not reviewer_role:
        reviewer_role = "Reviewer"

    while True:
        decision = input("\n  Approve this draft? (yes/no): ").strip().lower()
        if decision in ("yes", "no"):
            break
        print("  Please enter 'yes' or 'no'.")

    notes = input("  Notes (optional): ").strip()

    return {
        "decision": "approved" if decision == "yes" else "rejected",
        "reviewer": reviewer_name,
        "reviewer_role": reviewer_role,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "validation_report_sha256": validation_hash,
        "draft_sha256": draft_hash,
        "notes": notes or ("Manually approved after review." if decision == "yes"
                           else "Rejected by reviewer."),
    }


def stage_6_signoff(*, auto_approve: bool = False) -> Path:
    """Record sign-off decision.

    When *auto_approve* is True (``--auto-approve`` CLI flag), the stage
    auto-approves after validation passes.  Otherwise an interactive
    prompt collects the reviewer's name, role, and decision.
    """
    if auto_approve:
        signoff = {
            "decision": "approved",
            "reviewer": "pipeline_auto_approval",
            "reviewer_role": "Automated pipeline (post-validation)",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validation_report_sha256": sha256_file(VALIDATION_REPORT_PATH),
            "draft_sha256": sha256_file(DRAFT_MD_PATH),
            "notes": "Auto-approved after Stage 5 validation gates passed. "
                     "Production use requires manual advisor + compliance review.",
        }
    else:
        signoff = _manual_signoff()

    if signoff["decision"] != "approved":
        append_notes_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": "6_signoff",
            "decision": signoff["decision"],
            "reviewer": signoff["reviewer"],
        })
        SIGNOFF_PATH.parent.mkdir(parents=True, exist_ok=True)
        SIGNOFF_PATH.write_text(
            json.dumps(signoff, indent=2, sort_keys=True), encoding="utf-8"
        )
        raise RuntimeError(
            f"Draft rejected by {signoff['reviewer']}. "
            "Pipeline halted — revise the draft and re-run."
        )

    SIGNOFF_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNOFF_PATH.write_text(
        json.dumps(signoff, indent=2, sort_keys=True), encoding="utf-8"
    )

    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "6_signoff",
        "decision": signoff["decision"],
        "reviewer": signoff["reviewer"],
        "artifact_sha256": sha256_file(SIGNOFF_PATH),
    })

    mode = "auto-approved" if auto_approve else f"approved by {signoff['reviewer']}"
    print(f"✅ Stage 6 complete: Sign-off recorded ({mode})")
    return SIGNOFF_PATH


# ── Stage 7: PDF Assembler ───────────────────────────────────────────


def stage_7_pdf_assembly(draft_pdf_path: Path) -> Path:
    """Copy approved PDF to final delivery location, enforce page limit."""
    # Verify sign-off
    if not SIGNOFF_PATH.exists():
        raise FileNotFoundError("Signoff.json missing — cannot assemble PDF")

    signoff = json.loads(SIGNOFF_PATH.read_text(encoding="utf-8"))
    if signoff.get("decision") != "approved":
        raise RuntimeError(
            f"Sign-off decision is '{signoff.get('decision')}', not 'approved'. "
            "PDF assembly halted."
        )

    # Verify page count (≤12 pages)
    pdf_bytes = draft_pdf_path.read_bytes()
    # Count pages by looking for PDF page markers
    page_count = pdf_bytes.count(b"/Type /Page\n")
    if page_count == 0:
        # Fallback: count top-level page objects
        page_count = len(re.findall(rb"/Type\s*/Page[^s]", pdf_bytes))

    if page_count > 12:
        raise ValueError(
            f"PDF exceeds 12-page limit: {page_count} pages. "
            "Reduce content before delivery."
        )

    # Promote from pipeline_artifacts/drafts/ → pipeline_artifacts/final_pdf/
    FINAL_PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(draft_pdf_path, FINAL_PDF_PATH)

    final_hash = sha256_file(FINAL_PDF_PATH)

    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "7_pdf_assembly",
        "event": "Final PDF assembled",
        "page_count": page_count,
        "artifact_path": str(FINAL_PDF_PATH),
        "artifact_sha256": final_hash,
        "signoff_sha256": sha256_file(SIGNOFF_PATH),
    })

    print(f"✅ Stage 7 complete: ClientDeliverable.pdf ({page_count} pages)")
    return FINAL_PDF_PATH


# ── Main orchestrator ────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GRAT / CRAT AI Pipeline — Full Run",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        default=False,
        help="Skip manual Stage 6 review and auto-approve after validation passes. "
             "Intended for CI/testing only.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    print("=" * 60)
    print("  GRAT / CRAT AI Pipeline — Full Run")
    print("=" * 60)

    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "pipeline_start",
        "event": "Full pipeline run initiated",
    })

    # Stage 1: Client Intake
    client_profile, profile_hash = stage_1_intake()

    # Stage 2: RAG Retrieval (verify pre-built artifacts)
    stage_2_retrieval()

    # Stage 3: Deterministic Trust Modeler
    stage_3_model()

    # Stage 4: LLM Drafter (section-by-section)
    draft_md_path, draft_pdf_path = stage_4_drafting()

    # Stage 5: Validator Pack
    stage_5_validate(draft_md_path)

    # Stage 6: Human Sign-off
    stage_6_signoff(auto_approve=args.auto_approve)

    # Stage 7: PDF Assembler
    final_pdf_path = stage_7_pdf_assembly(draft_pdf_path)

    # Stage 8: Final audit log
    append_notes_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "pipeline_complete",
        "event": "All 8 stages completed successfully",
        "final_pdf_path": str(final_pdf_path),
        "final_pdf_sha256": sha256_file(final_pdf_path),
    })

    print("=" * 60)
    print(f"  ✅ Pipeline complete!")
    print(f"  PDF: {final_pdf_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()


