from __future__ import annotations

import hashlib
import re
from pathlib import Path

from output.writer import write_draft_md


def test_write_draft_md_writes_footer_with_metadata_and_hashes(tmp_path: Path) -> None:
    source_one = tmp_path / "ClientProfile.json"
    source_two = tmp_path / "ModelOutputs.json"
    source_one.write_text('{"a": 1}\n', encoding="utf-8")
    source_two.write_text('{"b": 2}\n', encoding="utf-8")

    output_path = tmp_path / "Draft.md"
    final_markdown = "## Draft\n\nSection body."

    written_path = write_draft_md(
        final_assembled_markdown=final_markdown,
        output_path=output_path,
        model_used="gpt-5.3-codex",
        token_counts={"input_tokens": 111, "output_tokens": 222, "total_tokens": 333},
        source_file_paths=[source_one, source_two],
    )

    assert written_path == output_path
    contents = output_path.read_text(encoding="utf-8")

    assert contents.startswith("## Draft")
    assert "## Generation Metadata" in contents
    assert "- model_used: gpt-5.3-codex" in contents
    assert "- input_tokens: 111" in contents
    assert "- output_tokens: 222" in contents
    assert "- total_tokens: 333" in contents
    assert re.search(r"- generation_timestamp_utc: \d{4}-\d{2}-\d{2}T", contents)

    source_one_hash = hashlib.sha256(source_one.read_bytes()).hexdigest()
    source_two_hash = hashlib.sha256(source_two.read_bytes()).hexdigest()
    assert f"- {source_one.as_posix()}: {source_one_hash}" in contents
    assert f"- {source_two.as_posix()}: {source_two_hash}" in contents


def test_write_draft_md_marks_missing_source_files(tmp_path: Path) -> None:
    output_path = tmp_path / "Draft.md"
    missing = tmp_path / "does_not_exist.json"

    write_draft_md(
        final_assembled_markdown="## Body\n\nText",
        output_path=output_path,
        source_file_paths=[missing],
    )

    contents = output_path.read_text(encoding="utf-8")
    assert f"- {missing.as_posix()}: MISSING" in contents
