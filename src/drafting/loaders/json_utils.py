"""Compatibility wrapper for legacy loader imports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.io import load_json


def load_json_file(path: Path) -> dict[str, Any]:
    """Backward-compatible alias for utils.io.load_json."""
    return load_json(path)
