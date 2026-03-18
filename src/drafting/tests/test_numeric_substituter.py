from __future__ import annotations

import pytest

from postprocessing.numeric_substituter import (
    MissingPlaceholderError,
    substitute_numerics,
)


def test_substitute_numerics_replaces_all_bound_placeholders() -> None:
    markdown = (
        "Estate tax rate is {{estate_tax_rate}} and projected wealth is "
        "{{taxable_estate_after_grat_usd}}. Repeated {{estate_tax_rate}}."
    )
    substitution_map = {
        "{{estate_tax_rate}}": "40.00%",
        "{{taxable_estate_after_grat_usd}}": "$12,294,873.22",
    }

    final_markdown = substitute_numerics(markdown, substitution_map)

    assert "{{estate_tax_rate}}" not in final_markdown
    assert "{{taxable_estate_after_grat_usd}}" not in final_markdown
    assert "40.00%" in final_markdown
    assert "$12,294,873.22" in final_markdown


def test_substitute_numerics_raises_for_unresolved_placeholder() -> None:
    markdown = "Known {{known_value}} and missing {{missing_value}} placeholders."
    substitution_map = {
        "{{known_value}}": "123",
    }

    with pytest.raises(MissingPlaceholderError, match=r"\{\{missing_value\}\}"):
        substitute_numerics(markdown, substitution_map)


def test_substitute_numerics_accepts_bare_map_keys() -> None:
    markdown = "Weight: {{grat_allocation_weight}}."
    substitution_map = {
        "grat_allocation_weight": "60.00%",
    }

    final_markdown = substitute_numerics(markdown, substitution_map)

    assert final_markdown == "Weight: 60.00%."
