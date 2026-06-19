"""ClaimSight AI — unified entry point.

Usage
-----
# Launch the interactive web UI (default when no args given)
python code/main.py
python code/main.py --ui

# Run the batch pipeline on a CSV
python code/main.py --input dataset/claims.csv --output output.csv
python code/main.py --input dataset/sample_claims.csv --output code/outputs/sample_predictions.csv --no-cache
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Load .env if present (never errors if missing)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "ClaimSight AI — run with no arguments to launch the web UI, "
            "or pass --input/--output to run the batch pipeline."
        )
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        default=False,
        help="Launch the Streamlit web UI (default when no arguments given).",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to the input claims CSV  (batch mode).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output.csv"),
        help="Path where predictions should be written  (batch mode).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable cache reads and writes for this run  (batch mode).",
    )
    return parser


def launch_ui() -> None:
    """Start the Streamlit demo app."""
    app_path = Path(__file__).resolve().parent / "demo" / "app.py"
    print(f"🚀  Starting ClaimSight AI UI → {app_path}")
    print("   Open http://localhost:8501 in your browser  (Ctrl+C to stop)\n")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path),
         "--server.headless", "false"],
        check=False,
    )


def run_pipeline(args: argparse.Namespace) -> None:
    """Run the batch claim review pipeline."""
    # Imports here so UI launch stays fast
    from config import Settings
    from pipelines.claim_review_pipeline import ClaimReviewPipeline

    input_path  = args.input  or Path("dataset/claims.csv")
    output_path = args.output or Path("output.csv")

    print(f"📋  Input  : {input_path}")
    print(f"💾  Output : {output_path}")
    print(f"🗄️  Cache  : {'disabled' if args.no_cache else 'enabled'}\n")

    settings = Settings(cache_enabled=not args.no_cache)
    pipeline = ClaimReviewPipeline(settings=settings)
    pipeline.run(input_path=input_path, output_path=output_path)


def main() -> None:
    args = build_parser().parse_args()

    # No arguments at all → launch UI (most intuitive default)
    if args.input is None and not args.ui:
        launch_ui()
    elif args.ui:
        launch_ui()
    else:
        run_pipeline(args)


if __name__ == "__main__":
    main()
