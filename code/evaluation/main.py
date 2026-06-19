"""Evaluation entry point for sample_claims.csv."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Settings
from evaluation.metrics import EvaluationRunner


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for evaluation runs."""
    parser = argparse.ArgumentParser(description="Evaluate predictions on sample data.")
    parser.add_argument(
        "--sample",
        type=Path,
        default=Path("dataset/sample_claims.csv"),
        help="Path to the labeled sample CSV.",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("code/outputs/sample_predictions.csv"),
        help="Path to generated sample predictions.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("code/evaluation/evaluation_report.md"),
        help="Path where the evaluation report should be written.",
    )
    return parser


def main() -> None:
    """Run evaluation scaffolding."""
    args = build_parser().parse_args()
    settings = Settings()
    runner = EvaluationRunner(settings=settings)
    runner.run(
        sample_path=args.sample,
        predictions_path=args.predictions,
        report_path=args.report,
    )


if __name__ == "__main__":
    main()
