"""generate_output.py — run the full pipeline on claims.csv and write output.csv.

Usage (from repo root):
    python code/generate_output.py

    # Explicit paths:
    python code/generate_output.py --input dataset/claims.csv --output output.csv

The script loads .env automatically.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Load .env before anything else
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Settings
from pipelines.claim_review_pipeline import ClaimReviewPipeline
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate output.csv from claims.csv")
    p.add_argument("--input", type=Path, default=Path("dataset/claims.csv"))
    p.add_argument("--output", type=Path, default=Path("output.csv"))
    p.add_argument("--no-cache", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    repo = Path(__file__).resolve().parent.parent
    settings = Settings(repo_root=repo, cache_enabled=not args.no_cache)

    print(f"[generate_output] Input:  {repo / args.input}")
    print(f"[generate_output] Output: {repo / args.output}")
    print(f"[generate_output] Model provider: {settings.model_provider}")
    print(f"[generate_output] VLM available: {settings.has_vision_model}")

    pipeline = ClaimReviewPipeline(settings=settings)
    pipeline.run(input_path=args.input, output_path=args.output)

    import pandas as pd
    out_path = repo / args.output
    if out_path.exists():
        df = pd.read_csv(out_path)
        print(f"\n[generate_output] ✓ Written {len(df)} rows to {out_path}")
        print(f"[generate_output] Columns: {list(df.columns)}")
        status_counts = df["claim_status"].value_counts().to_dict()
        print(f"[generate_output] claim_status distribution: {status_counts}")
    else:
        print("[generate_output] ERROR: output file not found")
        sys.exit(1)


if __name__ == "__main__":
    main()
