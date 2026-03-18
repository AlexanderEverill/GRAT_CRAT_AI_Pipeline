"""Section-level context assembly for drafting stage."""

from __future__ import annotations

from loaders.outline import Outline
from loaders.retrieval_bundle import RetrievalBundle, RetrievalChunk


GENERAL_BUCKET_ID = "general"


def build_section_context(
    outline: Outline,
    retrieval_bundle: RetrievalBundle,
    general_bucket_id: str = GENERAL_BUCKET_ID,
) -> dict[str, list[RetrievalChunk]]:
    """Map retrieval chunks to outline sections using chunk section tags."""
    section_ids = [section.section_id for section in outline.sections]
    section_id_set = set(section_ids)

    mapped: dict[str, list[RetrievalChunk]] = {
        section_id: [] for section_id in section_ids
    }
    mapped[general_bucket_id] = []

    for chunk in retrieval_bundle.chunks:
        tags = chunk.extra.get("section_tags")
        if tags is None:
            mapped[general_bucket_id].append(chunk)
            continue

        if not isinstance(tags, list) or not all(
            isinstance(tag, str) and tag.strip() for tag in tags
        ):
            raise ValueError(
                "Retrieval chunk field 'section_tags' must be a list of non-empty strings"
            )

        assigned = False
        for tag in dict.fromkeys(tags):
            if tag in section_id_set:
                mapped[tag].append(chunk)
                assigned = True

        if not assigned:
            mapped[general_bucket_id].append(chunk)

    return mapped