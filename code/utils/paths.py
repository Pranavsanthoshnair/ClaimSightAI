"""Path helper functions."""

from __future__ import annotations

from pathlib import Path


def image_id_from_path(path: Path | str) -> str:
    """Return the image ID, defined as the filename without extension."""
    return Path(path).stem
