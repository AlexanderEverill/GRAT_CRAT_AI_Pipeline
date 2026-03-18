"""I/O helpers shared across drafting modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> dict[str, Any]:
    """Load a JSON file and return its object payload as a dictionary."""
    file_path = Path(path)

    try:
        raw = file_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"JSON file not found: {file_path}") from exc
    except OSError as exc:
        raise OSError(f"Unable to read JSON file {file_path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            (
                f"Malformed JSON in {file_path} "
                f"(line {exc.lineno}, column {exc.colno}): {exc.msg}"
            )
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected top-level JSON object in {file_path}, got {type(data).__name__}"
        )

    return data