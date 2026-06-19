"""Evaluation metric scaffolding."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import Settings


class EvaluationRunner:
    """Compares sample predictions with labeled sample outputs."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self, sample_path: Path, predictions_path: Path, report_path: Path) -> None:
        """Create a placeholder evaluation report."""
        resolved_sample = self.settings.resolve_path(sample_path)
        resolved_predictions = self.settings.resolve_path(predictions_path)
        resolved_report = self.settings.resolve_path(report_path)

        sample_exists = resolved_sample.exists()
        predictions_exists = resolved_predictions.exists()
        sample_rows = len(pd.read_csv(resolved_sample)) if sample_exists else 0

        resolved_report.parent.mkdir(parents=True, exist_ok=True)
        resolved_report.write_text(
            "\n".join(
                [
                    "# Evaluation Report",
                    "",
                    "Business logic and metric computation are not implemented yet.",
                    "",
                    f"- Sample file present: {sample_exists}",
                    f"- Prediction file present: {predictions_exists}",
                    f"- Sample rows detected: {sample_rows}",
                    "",
                ]
            ),
            encoding="utf-8",
            newline="\n",
        )
