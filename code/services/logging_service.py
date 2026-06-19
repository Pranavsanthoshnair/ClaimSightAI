"""Runtime JSONL logging service skeleton."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import Settings


class LoggingService:
    """Writes redacted machine-readable pipeline logs."""

    def __init__(self, settings: Settings) -> None:
        self.log_dir = settings.resolve_path(settings.logs_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def write_event(self, filename: str, payload: dict[str, Any]) -> None:
        """Append one JSON event to a runtime log file."""
        event = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            **payload,
        }
        path = self.log_dir / filename
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=True) + "\n")
