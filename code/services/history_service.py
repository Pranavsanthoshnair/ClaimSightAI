"""User history lookup service skeleton."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from models.records import UserHistory


class UserHistoryService:
    """Loads historical user risk context."""

    def __init__(self) -> None:
        self._by_user_id: dict[str, UserHistory] = {}

    def load(self, path: Path) -> None:
        """Load user history records from CSV."""
        frame = pd.read_csv(path)
        histories = [
            UserHistory.model_validate(record)
            for record in frame.to_dict(orient="records")
        ]
        self._by_user_id = {history.user_id: history for history in histories}

    def get(self, user_id: str) -> UserHistory | None:
        """Return history context for a user, if available."""
        return self._by_user_id.get(user_id)
