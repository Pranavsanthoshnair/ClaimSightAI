"""Command-line entry point for the claim evidence review pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

# Load .env if present (never errors if missing)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import Settings
from pipelines.claim_review_pipeline import ClaimReviewPipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for batch claim review runs."""
    parser = argparse.ArgumentParser(
        description="Run the multi-modal evidence review pipeline."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("dataset/claims.csv"),
        help="Path to the input claims CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output.csv"),
        help="Path where predictions should be written.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable cache reads and writes for this run.",
    )
    return parser


def main() -> None:
    """Run the configured claim review pipeline."""
    args = build_parser().parse_args()
    settings = Settings(cache_enabled=not args.no_cache)
    pipeline = ClaimReviewPipeline(settings=settings)
    pipeline.run(input_path=args.input, output_path=args.output)


if __name__ == "__main__":
    main()
