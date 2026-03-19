from __future__ import annotations

import pytest

from postprocessing.citation_inserter import insert_citations


def test_insert_citations_replaces_inline_tags_and_appends_references() -> None:
    markdown = "Projected outcomes improved under GRAT [S001], while CRAT rules also apply [S002]. Repeat [S001]."
    manifest = {
        "citations": [
            {
                "cite_key": "[S001]",
                "author": "IRS",
                "title": "Grantor Retained Annuity Trust Guidance",
                "year": 2024,
            },
            {
                "cite_key": "[S002]",
                "author": "Treasury",
                "title": "Charitable Remainder Annuity Trust Regulation",
                "year": 2023,
            },
        ]
    }

    annotated = insert_citations(markdown, manifest)

    # [SXXX] tags are kept inline (PDF renderer converts them to footnotes).
    body = annotated.split("### References")[0]
    assert "[S001]" in body
    assert "[S002]" in body
    assert "### References" in annotated
    assert annotated.count("- [S001]") == 1
    assert annotated.count("- [S002]") == 1


def test_insert_citations_raises_for_unknown_source_tag() -> None:
    markdown = "Unsupported cite key appears here [S099]."
    manifest = {
        "citations": [
            {"cite_key": "[S001]", "author": "A", "title": "T1", "year": 2022},
            {"cite_key": "[S002]", "author": "B", "title": "T2", "year": 2021},
        ]
    }

    with pytest.raises(ValueError, match=r"No citation manifest entry found for \[S099\]"):
        insert_citations(markdown, manifest)


def test_insert_citations_uses_cite_key_lookup() -> None:
    markdown = "First fact [S001]."
    manifest = {
        "citations": [
            {"cite_key": "[S001]", "author": "Author One", "title": "Source One", "year": 2020},
        ]
    }

    annotated = insert_citations(markdown, manifest)

    assert "[S001]" in annotated
    assert "- [S001] Author One. Source One. (2020)." in annotated
