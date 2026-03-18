from __future__ import annotations

import pytest

from output.references import append_global_references


def test_append_global_references_deduplicates_used_citations() -> None:
    assembled = (
        "## Table of Contents\n"
        "- [Executive Summary](#executive-summary)\n\n"
        "---\n\n"
        "## Executive Summary\n"
        "Summary text.\n\n"
        "### References\n"
        "- [SRC-2] Ref two\n"
        "- [SRC-1] Ref one\n\n"
        "---\n\n"
        "## GRAT Analysis\n"
        "Further text with repeated source [SRC-2].\n"
    )
    manifest = {
        "citations": [
            {"author": "Author One", "title": "Title One", "year": 2021},
            {"author": "Author Two", "title": "Title Two", "year": 2022},
        ]
    }

    result = append_global_references(assembled, manifest)

    assert result.endswith("\n")
    assert "## Global References" in result
    assert result.count("- [SRC-2]") == 2
    assert result.count("- [SRC-1]") == 2
    assert "- [SRC-2] Author Two. Title Two. (2022)." in result
    assert "- [SRC-1] Author One. Title One. (2021)." in result


def test_append_global_references_handles_no_citations_detected() -> None:
    assembled = "## Intro\n\nNo citation tags in this document."
    manifest = {"citations": [{"author": "A", "title": "T", "year": 2020}]}

    result = append_global_references(assembled, manifest)

    assert "## Global References" in result
    assert "No citations detected" in result


def test_append_global_references_raises_for_unknown_tag() -> None:
    assembled = "Body with unknown tag [SRC-9]."
    manifest = {"citations": [{"author": "A", "title": "T", "year": 2020}]}

    with pytest.raises(ValueError, match=r"No citation manifest entry found for \[SRC-9\]"):
        append_global_references(assembled, manifest)
