from __future__ import annotations

from pathlib import Path

import pytest

from loaders.client_profile import ClientProfile
from output.pdf import write_draft_pdf


def _client_profile() -> ClientProfile:
    return ClientProfile(
        client_id="CLIENT-2015-001",
        risk_tolerance="moderate",
        goals=["Minimize estate tax", "Transfer wealth", "Support charity"],
        horizon=10,
        extra={
            "client_demographics": {
                "age": 62,
                "marital_status": "Married",
                "children": {"details": "Two adult children"},
            },
            "liquidity_event": {
                "year": 2015,
                "gross_proceeds_usd": 16000000,
            },
            "estate_tax_context_2015": {"top_estate_tax_rate": 0.4},
            "constraints": ["Preserve liquidity"],
        },
    )


def test_write_draft_pdf_writes_valid_pdf(tmp_path: Path) -> None:
    markdown = """## Table of Contents
- Executive Summary

---

## Executive Summary

This report compares a GRAT and a CRAT for the current client facts.

### References
- [SRC-1] Internal Source. Test. (2026).

## Global References
- [SRC-1] Internal Source. Test. (2026).

## Generation Metadata
- model_used: gpt-test
"""

    output_path = tmp_path / "Draft.pdf"
    written_path = write_draft_pdf(
        markdown,
        output_path,
        client_profile=_client_profile(),
        draft_manifest={"summary": {"sections_written": 1, "validation_warnings": 0}},
    )

    assert written_path == output_path
    pdf_bytes = output_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"Client Advisory Report" in pdf_bytes
    assert b"Executive Summary" in pdf_bytes
    assert b"Generation Metadata" not in pdf_bytes


def test_write_draft_pdf_enforces_page_budget(tmp_path: Path) -> None:
    paragraph = " ".join(["Long paragraph content."] * 180)
    markdown = "\n\n".join(
        [
            "## Executive Summary\n\n" + paragraph,
            "## GRAT Analysis\n\n" + paragraph,
            "## CRAT Analysis\n\n" + paragraph,
            "## Comparison and Recommendation\n\n" + paragraph,
            "## Citations and Disclosures\n\n" + paragraph,
        ]
    )

    with pytest.raises(ValueError, match="exceeds page budget"):
        write_draft_pdf(
            markdown,
            tmp_path / "Draft.pdf",
            client_profile=_client_profile(),
            max_pages=1,
        )
