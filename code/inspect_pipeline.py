"""inspect_pipeline.py — run full pipeline inspection for one claim.

Usage (from repo root):
    python code/inspect_pipeline.py \\
        --claim "Customer: My rear bumper has a dent." \\
        --object car \\
        --image dataset/images/sample/case_001/img_1.jpg

    # Inspect all sample claims:
    python code/inspect_pipeline.py --all-sample
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from config import Settings
from services.pipeline_inspector import PipelineInspector


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Inspect full pipeline for one claim")
    p.add_argument("--claim", type=str, default="Customer: My rear bumper has a dent.")
    p.add_argument("--object", type=str, default="car",
                   choices=["car", "laptop", "package"])
    p.add_argument("--image", type=str, nargs="+",
                   default=["dataset/images/sample/case_001/img_1.jpg"])
    p.add_argument("--output", type=Path,
                   default=Path("code/logs/debug_pipeline_report.json"))
    p.add_argument("--all-sample", action="store_true",
                   help="Inspect all rows from sample_claims.csv")
    return p


def main() -> None:
    args = build_parser().parse_args()
    repo = Path(__file__).resolve().parent.parent
    settings = Settings(repo_root=repo)
    inspector = PipelineInspector(settings=settings)

    if args.all_sample:
        import pandas as pd
        df = pd.read_csv(repo / "dataset" / "sample_claims.csv")
        for _, row in df.iterrows():
            imgs = [
                next(
                    (p for p in [repo / raw.strip(), repo / "dataset" / raw.strip()] if p.exists()),
                    repo / raw.strip()
                )
                for raw in str(row["image_paths"]).split(";")
            ]
            report = inspector.inspect(
                user_claim=str(row["user_claim"]),
                claim_object_str=str(row["claim_object"]),
                image_paths=imgs,
                user_id=str(row["user_id"]),
            )
            report.print_summary()
            out = repo / "code" / "logs" / f"debug_{row['user_id']}.json"
            report.save(out)
    else:
        image_paths = []
        for raw in args.image:
            p = Path(raw)
            if not p.is_absolute():
                p = repo / p
            image_paths.append(p)

        report = inspector.inspect(
            user_claim=args.claim,
            claim_object_str=args.object,
            image_paths=image_paths,
            user_id="debug",
        )
        report.print_summary()

        out = args.output if args.output.is_absolute() else repo / args.output
        report.save(out)
        print(f"\nFull report saved to: {out}")


if __name__ == "__main__":
    main()
