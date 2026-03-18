"""Write assembled draft markdown to disk with generation metadata footer."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Mapping, Sequence


def _default_source_file_paths() -> list[Path]:
    base = Path(__file__).resolve().parents[1] / "data"
    return [
        base / "ClientProfile.json",
        base / "RetrievalBundle.json",
        base / "ModelOutputs.json",
        base / "Outline.json",
    ]


def _path_label(path: Path) -> str:
    cwd = Path.cwd().resolve()
    try:
        return path.resolve().relative_to(cwd).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256_for_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_token_counts(token_counts: Mapping[str, int] | None) -> dict[str, str]:
    defaults = {"input_tokens": "unknown", "output_tokens": "unknown", "total_tokens": "unknown"}
    if token_counts is None:
        return defaults

    normalized = dict(defaults)
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = token_counts.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            continue
        normalized[key] = str(value)
    return normalized


def _build_metadata_footer(
    model_used: str,
    token_counts: Mapping[str, int] | None,
    source_file_paths: Sequence[str | Path] | None,
) -> str:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    token_map = _normalize_token_counts(token_counts)

    if source_file_paths is None:
        source_paths = _default_source_file_paths()
    else:
        source_paths = [Path(path) for path in source_file_paths]

    hash_lines: list[str] = []
    for path in source_paths:
        label = _path_label(path)
        if path.exists() and path.is_file():
            file_hash = _sha256_for_file(path)
        else:
            file_hash = "MISSING"
        hash_lines.append(f"  - {label}: {file_hash}")

    model_text = model_used.strip() if isinstance(model_used, str) and model_used.strip() else "unknown"
    footer_lines = [
        "---",
        "",
        "## Generation Metadata",
        f"- generation_timestamp_utc: {timestamp}",
        f"- model_used: {model_text}",
        "- token_counts:",
        f"  - input_tokens: {token_map['input_tokens']}",
        f"  - output_tokens: {token_map['output_tokens']}",
        f"  - total_tokens: {token_map['total_tokens']}",
        "- source_file_hashes:",
        *hash_lines,
    ]
    return "\n".join(footer_lines)


def write_draft_md(
    final_assembled_markdown: str,
    output_path: str | Path,
    model_used: str = "unknown",
    token_counts: Mapping[str, int] | None = None,
    source_file_paths: Sequence[str | Path] | None = None,
) -> Path:
    """Write final markdown draft to disk with generation metadata footer."""
    if not isinstance(final_assembled_markdown, str) or not final_assembled_markdown.strip():
        raise ValueError("final_assembled_markdown must be a non-empty string")

    path = Path(output_path)
    if path.suffix.lower() != ".md":
        raise ValueError("output_path must point to a .md file")

    footer = _build_metadata_footer(
        model_used=model_used,
        token_counts=token_counts,
        source_file_paths=source_file_paths,
    )
    content = f"{final_assembled_markdown.rstrip()}\n\n{footer}\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path