"""Top-level orchestration entry point for Stage 4 drafting."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from context import bind_numeric_values, build_section_context, format_client_context_block
from drafting import draft_all_sections
from llm.client import DraftingError, ModelConfig, raw_completion
from loaders import (
    load_client_profile,
    load_model_outputs,
    load_outline,
    load_retrieval_bundle,
)
from output import (
    append_global_references,
    assemble_draft,
    build_draft_manifest,
    write_draft_manifest,
    write_draft_md,
)
from postprocessing import (
    ValidationResult,
    insert_citations,
    substitute_numerics,
    validate_section_output,
)
from prompts import section_draft_prompt_builder, system_prompt_template
from prompts.citation_instructions import citation_instruction_block
from utils.io import load_json


logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"


@dataclass(frozen=True)
class DraftingInputPaths:
    """Filesystem paths for inputs required by the drafting stage."""

    client_profile_path: str | Path
    retrieval_bundle_path: str | Path
    model_outputs_path: str | Path
    outline_path: str | Path
    citation_manifest_path: str | Path | None = None


@dataclass(frozen=True)
class DraftingPipelineConfig:
    """Runtime controls for drafting orchestration."""

    output_path: str | Path = _OUTPUT_DIR / "Draft.md"
    model_config: ModelConfig | None = None
    llm_client_override: Callable[[str], str] | None = None
    llm_api_client: Any | None = None
    system_prompt: str | None = None
    section_token_budget: int = 1400
    enable_self_critique: bool = False
    parallel_sections: bool = False
    max_concurrency: int = 4
    append_global_references: bool = True
    fail_on_validation_error: bool = True
    token_counts: Mapping[str, int] | None = None
    section_token_usage: Mapping[str, Mapping[str, int]] | None = None
    manifest_output_path: str | Path | None = None


def _as_path(path: str | Path) -> Path:
    return path if isinstance(path, Path) else Path(path)


def _extract_citation_manifest(
    input_paths: DraftingInputPaths,
) -> dict[str, Any]:
    if input_paths.citation_manifest_path is not None:
        return load_json(_as_path(input_paths.citation_manifest_path))

    retrieval_payload = load_json(_as_path(input_paths.retrieval_bundle_path))
    embedded_manifest = retrieval_payload.get("citation_manifest")
    if isinstance(embedded_manifest, dict):
        return embedded_manifest

    # Fallback keeps pipeline runnable even when bundle has no manifest details.
    return {"citations": []}


def _build_llm_client(config: DraftingPipelineConfig) -> Callable[[str], str]:
    if config.llm_client_override is not None:
        return config.llm_client_override

    if config.model_config is None:
        raise ValueError(
            "model_config is required when llm_client_override is not provided"
        )

    system_prompt = config.system_prompt or system_prompt_template()

    def _call(prompt: str) -> str:
        return raw_completion(
            prompt=prompt,
            model_config=config.model_config,
            system_prompt=system_prompt,
            client=config.llm_api_client,
        )

    return _call


def _build_section_prompts(
    section_context_map: Mapping[str, list[Any]],
    client_context_block: str,
    numeric_substitutions: Mapping[str, str],
    outline: Any,
    token_budget: int,
) -> dict[str, str]:
    prompts: dict[str, str] = {}
    for section in outline.sections:
        section_chunks = section_context_map.get(section.section_id, [])
        section_prompt = section_draft_prompt_builder(
            section=section,
            client_context_block=client_context_block,
            chunks=section_chunks,
            numeric_substitution_map=dict(numeric_substitutions),
            token_budget=token_budget,
        )

        source_ids = [chunk.source_id for chunk in section_chunks]
        citation_block = citation_instruction_block(source_ids)
        prompts[section.section_id] = f"{section_prompt}\n\n{citation_block}"
    return prompts


def drafting_pipeline(
    input_paths: DraftingInputPaths,
    config: DraftingPipelineConfig,
) -> Path:
    """Run the full drafting stage and write a final Draft.md artifact."""
    logger.info("loading drafting inputs")
    client_profile = load_client_profile(_as_path(input_paths.client_profile_path))
    retrieval_bundle = load_retrieval_bundle(_as_path(input_paths.retrieval_bundle_path))
    model_outputs = load_model_outputs(_as_path(input_paths.model_outputs_path))
    outline = load_outline(_as_path(input_paths.outline_path))
    citation_manifest = _extract_citation_manifest(input_paths)

    logger.info("building drafting context")
    client_context_block = format_client_context_block(client_profile)
    section_context_map = build_section_context(outline, retrieval_bundle)
    numeric_substitutions = bind_numeric_values(model_outputs, outline)

    logger.info("building section prompts")
    section_prompts = _build_section_prompts(
        section_context_map=section_context_map,
        client_context_block=client_context_block,
        numeric_substitutions=numeric_substitutions,
        outline=outline,
        token_budget=config.section_token_budget,
    )

    logger.info("drafting sections")
    llm_client = _build_llm_client(config)
    raw_sections = draft_all_sections(
        outline=outline,
        section_prompts=section_prompts,
        llm_client=llm_client,
        enable_self_critique=config.enable_self_critique,
        parallel=config.parallel_sections,
        max_concurrency=config.max_concurrency,
    )

    logger.info("postprocessing drafted sections")
    finalized_sections: dict[str, str] = {}
    validation_results_by_section: dict[str, ValidationResult] = {}
    for section in outline.sections:
        section_id = section.section_id
        try:
            annotated = insert_citations(raw_sections[section_id], citation_manifest)
            finalized = substitute_numerics(annotated, numeric_substitutions)
            validation = validate_section_output(finalized, section)
        except Exception as exc:
            raise DraftingError(f"Postprocessing failed for section '{section_id}'") from exc

        if not validation.is_valid:
            message = (
                f"Validation failed for section '{section_id}': "
                + " | ".join(validation.errors)
            )
            if config.fail_on_validation_error:
                raise DraftingError(message)
            logger.warning(message)

        finalized_sections[section_id] = finalized
        validation_results_by_section[section_id] = validation

    logger.info("assembling final draft markdown")
    assembled = assemble_draft(finalized_sections, outline)
    if config.append_global_references:
        assembled = append_global_references(assembled, citation_manifest)

    source_hash_inputs: list[Path] = [
        _as_path(input_paths.client_profile_path),
        _as_path(input_paths.retrieval_bundle_path),
        _as_path(input_paths.model_outputs_path),
        _as_path(input_paths.outline_path),
    ]
    if input_paths.citation_manifest_path is not None:
        source_hash_inputs.append(_as_path(input_paths.citation_manifest_path))

    model_used = (
        config.model_config.model
        if config.model_config is not None
        else "llm_client_override"
    )
    output_path = write_draft_md(
        final_assembled_markdown=assembled,
        output_path=_as_path(config.output_path),
        model_used=model_used,
        token_counts=config.token_counts,
        source_file_paths=source_hash_inputs,
    )
    logger.info("draft markdown written to %s", output_path)

    manifest_output_path = (
        _as_path(config.manifest_output_path)
        if config.manifest_output_path is not None
        else _as_path(config.output_path).with_name("DraftManifest.json")
    )
    manifest_payload = build_draft_manifest(
        client_profile=client_profile,
        retrieval_bundle=retrieval_bundle,
        model_outputs=model_outputs,
        outline=outline,
        validation_results_by_section=validation_results_by_section,
        section_markdown_map=finalized_sections,
        numeric_substitution_map=numeric_substitutions,
        section_prompts=section_prompts,
        token_usage_by_section=config.section_token_usage,
    )
    write_draft_manifest(manifest_payload, manifest_output_path)
    logger.info("draft manifest written to %s", manifest_output_path)

    return output_path
