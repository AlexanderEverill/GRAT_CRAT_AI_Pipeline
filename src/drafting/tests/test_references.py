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
        "- [S002] Ref two\n"
        "- [S001] Ref one\n\n"
        "---\n\n"
        "## GRAT Analysis\n"
        "Further text with repeated source [S002].\n"
    )
    manifest = {
        "citations": [
            {"cite_key": "[S001]", "author": "Author One", "title": "Title One", "year": 2021},
            {"cite_key": "[S002]", "author": "Author Two", "title": "Title Two", "year": 2022},
        ]
    }

    result = append_global_references(assembled, manifest)

    assert result.endswith("\n")
    assert "## Global References" in result
    assert result.count("- [S002]") == 2
    assert result.count("- [S001]") == 2
    assert "- [S002] Author Two. Title Two. (2022)." in result
    assert "- [S001] Author One. Title One. (2021)." in result


def test_append_global_references_handles_no_citations_detected() -> None:
    assembled = "## Intro\n\nNo citation tags in this document."
    manifest = {"citations": [{"cite_key": "[S001]", "author": "A", "title": "T", "year": 2020}]}

    result = append_global_references(assembled, manifest)

    assert "## Global References" in result
    assert "No citations detected" in result


def test_append_global_references_raises_for_unknown_tag() -> None:
    assembled = "Body with unknown tag [S099]."
    manifest = {"citations": [{"cite_key": "[S001]", "author": "A", "title": "T", "year": 2020}]}

    with pytest.raises(ValueError, match=r"No citation manifest entry found for \[S099\]"):
        append_global_references(assembled, manifest)
