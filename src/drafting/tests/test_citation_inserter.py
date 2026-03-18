from __future__ import annotations

import pytest

from postprocessing.citation_inserter import insert_citations


def test_insert_citations_replaces_inline_tags_and_appends_references() -> None:
    markdown = "Projected outcomes improved under GRAT [SRC-1], while CRAT rules also apply [SRC-2]. Repeat [SRC-1]."
    manifest = {
        "citations": [
            {
                "short_id": "[SRC-1]",
                "author": "IRS",
                "title": "Grantor Retained Annuity Trust Guidance",
                "year": 2024,
            },
            {
                "short_id": "[SRC-2]",
                "author": "Treasury",
                "title": "Charitable Remainder Annuity Trust Regulation",
                "year": 2023,
            },
        ]
    }

    annotated = insert_citations(markdown, manifest)

    body = annotated.split("### References")[0]
    assert "[SRC-1]" not in body
    assert "[SRC-2]" not in body
    assert "(IRS, Grantor Retained Annuity Trust Guidance, 2024)" in annotated
    assert "(Treasury, Charitable Remainder Annuity Trust Regulation, 2023)" in annotated
    assert "### References" in annotated
    assert annotated.count("- [SRC-1]") == 1
    assert annotated.count("- [SRC-2]") == 1


def test_insert_citations_raises_for_unknown_source_tag() -> None:
    markdown = "Unsupported cite key appears here [SRC-3]."
    manifest = {
        "citations": [
            {"short_id": "[SRC-1]", "author": "A", "title": "T1", "year": 2022},
            {"short_id": "[SRC-2]", "author": "B", "title": "T2", "year": 2021},
        ]
    }

    with pytest.raises(ValueError, match=r"No citation manifest entry found for \[SRC-3\]"):
        insert_citations(markdown, manifest)


def test_insert_citations_uses_manifest_order_when_short_ids_missing() -> None:
    markdown = "First fact [SRC-1]."
    manifest = {
        "citations": [
            {"author": "Author One", "title": "Source One", "year": 2020},
        ]
    }

    annotated = insert_citations(markdown, manifest)

    assert "(Author One, Source One, 2020)" in annotated
    assert "- [SRC-1] Author One. Source One. (2020)." in annotated
