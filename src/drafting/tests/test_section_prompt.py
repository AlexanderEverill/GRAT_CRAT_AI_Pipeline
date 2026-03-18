from __future__ import annotations

from pathlib import Path

from context.client_context import format_client_context_block
from context.numeric_binder import bind_numeric_values
from context.section_context import build_section_context
from loaders.client_profile import load_client_profile
from loaders.model_outputs import load_model_outputs
from loaders.outline import load_outline
from loaders.retrieval_bundle import load_retrieval_bundle
from prompts.section_prompt import section_draft_prompt_builder


def test_section_draft_prompt_builder_injects_all_required_blocks() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    outline = load_outline(base_dir / "data" / "Outline.json")
    retrieval_bundle = load_retrieval_bundle(base_dir / "data" / "RetrievalBundle.json")
    model_outputs = load_model_outputs(base_dir / "data" / "ModelOutputs.json")
    client_profile = load_client_profile(base_dir / "data" / "ClientProfile.json")

    section_context = build_section_context(outline, retrieval_bundle)
    numeric_map = bind_numeric_values(model_outputs, outline)
    client_context_block = format_client_context_block(client_profile)

    target_section = next(
        section for section in outline.sections if section.section_id == "grat_analysis"
    )
    prompt = section_draft_prompt_builder(
        section=target_section,
        client_context_block=client_context_block,
        chunks=section_context["grat_analysis"],
        numeric_substitution_map=numeric_map,
        token_budget=1400,
    )

    assert "Section Title: 4. Grantor Retained Annuity Trust (GRAT)" in prompt
    assert "Section Purpose:" in prompt
    assert "Client Context:" in prompt
    assert "Relevant Retrieved Chunks:" in prompt
    assert "source_id=S002" in prompt
    assert "{{taxable_estate_after_grat_usd}}: $12,294,873.22" in prompt


def test_section_draft_prompt_builder_respects_token_budget() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    outline = load_outline(base_dir / "data" / "Outline.json")

    target_section = next(
        section for section in outline.sections if section.section_id == "grat_analysis"
    )

    retrieval_bundle = load_retrieval_bundle(base_dir / "data" / "RetrievalBundle.json")
    chunks = retrieval_bundle.chunks * 20

    prompt = section_draft_prompt_builder(
        section=target_section,
        client_context_block="Short client context.",
        chunks=chunks,
        numeric_substitution_map={"{{x}}": "$1.00"},
        token_budget=120,
    )

    assert "Omitted" in prompt or "TRUNCATED_FOR_TOKEN_BUDGET" in prompt
