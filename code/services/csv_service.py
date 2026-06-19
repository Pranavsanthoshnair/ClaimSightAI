"""CSV loading and writing service skeleton."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from models.records import ClaimInput, ClaimOutput, OUTPUT_COLUMNS


class CsvService:
    """Handles Pandas-based CSV IO and schema boundaries."""

    input_columns: tuple[str, ...] = (
        "user_id",
        "image_paths",
        "user_claim",
        "claim_object",
    )

    def read_claims(self, path: Path) -> list[ClaimInput]:
        """Read claim inputs from a CSV file."""
        frame = pd.read_csv(path)
        self._validate_columns(frame=frame, required=self.input_columns)
        return [
            ClaimInput.model_validate(record)
            for record in frame[list(self.input_columns)].to_dict(orient="records")
        ]

    def write_outputs(self, path: Path, outputs: list[ClaimOutput]) -> None:
        """Write claim outputs in the required column order."""
        frame = pd.DataFrame([output.to_output_dict() for output in outputs])
        self._validate_columns(frame=frame, required=OUTPUT_COLUMNS)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)

    @staticmethod
    def _validate_columns(frame: pd.DataFrame, required: tuple[str, ...]) -> None:
        """Validate that a DataFrame contains all required columns."""
        missing = [column for column in required if column not in frame.columns]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing required CSV columns: {joined}")
