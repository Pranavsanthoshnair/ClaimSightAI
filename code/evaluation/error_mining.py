"""error_mining.py — mine error_analysis.csv for root-cause patterns.

Usage
-----
    python code/evaluation/error_mining.py

    # Generate error_analysis.csv first if missing:
    python code/evaluation/error_mining.py --regen

What it produces
----------------
code/evaluation/top_failure_patterns.md
    - Summary table of failure categories with counts and %
    - 2-3 example cases per category with expected/predicted/reasoning/root_cause
    - Actionable recommendations per category

Failure categories (rule-based)
--------------------------------
object_confusion        — wrong object detected
object_part_confusion   — right object, wrong part
issue_type_confusion    — right object/part, wrong issue type
severity_confusion      — right everything else, wrong severity
evidence_failure        — evidence_standard_met wrong
image_quality_failure   — quality flags caused wrong prediction
no_model_baseline       — all predictions are not_enough_information (no VLM)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

_THIS = Path(__file__).resolve()
_CODE_DIR = _THIS.parent.parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

# Load .env from repo root if present
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_CODE_DIR.parent / ".env")
except ImportError:
    pass

_ERROR_CSV = _CODE_DIR / "evaluation" / "error_analysis.csv"
_OUTPUT_MD = _CODE_DIR / "evaluation" / "top_failure_patterns.md"

# Quality flags that indicate image quality issues
_QUALITY_FLAGS = {
    "blurry_image", "cropped_or_obstructed", "low_light_or_glare",
    "wrong_angle", "wrong_object", "wrong_object_part", "damage_not_visible",
}


# ---------------------------------------------------------------------------
# Root-cause classifier
# ---------------------------------------------------------------------------

def _classify_root_cause(row: pd.Series) -> dict[str, Any]:
    """Return a dict with failure_category and root_cause string."""
    exp_status = str(row.get("expected_claim_status", ""))
    pred_status = str(row.get("predicted_claim_status", ""))
    exp_issue = str(row.get("expected_issue_type", ""))
    pred_issue = str(row.get("predicted_issue_type", ""))
    exp_part = str(row.get("expected_object_part", ""))
    pred_part = str(row.get("predicted_object_part", ""))
    exp_obj = str(row.get("claim_object", ""))
    exp_esm = str(row.get("expected_evidence_standard_met", "")).lower()
    pred_esm = str(row.get("predicted_evidence_standard_met", "")).lower()
    risk_flags = str(row.get("predicted_risk_flags", "")).lower()
    pred_just = str(row.get("pred_justification", "")).lower()

    # Parse field_errors if present
    field_errors: dict = {}
    try:
        fe_raw = row.get("field_errors", "{}")
        if isinstance(fe_raw, str) and fe_raw.strip():
            field_errors = json.loads(fe_raw)
    except (json.JSONDecodeError, TypeError):
        pass

    quality_hit = any(f in risk_flags for f in _QUALITY_FLAGS)
    no_model = "not visible in any image" in pred_just or "no valid images" in pred_just

    # Check if all predictions are NEI (no-model baseline)
    all_nei = pred_status == "not_enough_information" and pred_issue in ("unknown", "")

    # ----------------------------------------------------------------
    # Classify category
    # ----------------------------------------------------------------

    # No model at all — VLM returned nothing useful
    if no_model and all_nei:
        cat = "no_model_baseline"
        cause = (
            "The VLM returned no visible objects. "
            "The pipeline fell back to not_enough_information for all fields. "
            "Likely cause: image is empty/unreadable, wrong object type, or model not configured."
        )
        return {"failure_category": cat, "root_cause": cause}

    # Wrong object detected
    wrong_obj_in_flags = "wrong_object" in risk_flags
    obj_not_visible = (
        "not visible in any image" in pred_just
        or f"{exp_obj} not visible" in pred_just
    )
    if wrong_obj_in_flags or (obj_not_visible and exp_issue != "unknown"):
        cat = "object_confusion"
        if wrong_obj_in_flags:
            cause = (
                f"The WRONG_OBJECT flag indicates a different object type was detected "
                f"instead of '{exp_obj}'. The VLM may have seen a different scene or the "
                f"image shows a different item entirely."
            )
        else:
            cause = (
                f"The claimed '{exp_obj}' was not found visible in any submitted image. "
                f"Possible reasons: image shows a different scene, wrong image submitted, "
                f"or VLM failed to identify the object."
            )
        return {"failure_category": cat, "root_cause": cause}

    # Object part confusion — right object, wrong part
    part_wrong = "object_part" in field_errors and exp_part != pred_part
    if part_wrong and exp_part not in ("unknown", ""):
        cat = "object_part_confusion"
        cause = (
            f"The claimed part '{exp_part}' was not identified; model predicted '{pred_part}'. "
            f"Possible reasons: (1) image focuses on a different part than claimed, "
            f"(2) claim extraction mapped the wrong part from the conversation, "
            f"(3) VLM confused adjacent parts (e.g. bumper vs fender)."
        )
        return {"failure_category": cat, "root_cause": cause}

    # Issue type confusion — right object/part, wrong issue type
    issue_wrong = "issue_type" in field_errors and exp_issue != pred_issue
    part_ok = exp_part == pred_part or exp_part in ("unknown", "")
    if issue_wrong and part_ok and exp_issue not in ("unknown", ""):
        cat = "issue_type_confusion"
        cause = (
            f"The claimed issue type '{exp_issue}' was not confirmed; model predicted "
            f"'{pred_issue}'. Possible reasons: (1) damage type is ambiguous in the image "
            f"(e.g. deep scratch vs dent), (2) similar-looking damage misclassified, "
            f"(3) VLM vocabulary mismatch between taxonomy values."
        )
        return {"failure_category": cat, "root_cause": cause}

    # Image quality failure
    if quality_hit:
        cat = "image_quality_failure"
        bad_flags = [f for f in risk_flags.split(";") if any(qf in f for qf in _QUALITY_FLAGS)]
        cause = (
            f"Quality flags detected: {', '.join(bad_flags) or risk_flags}. "
            f"These reduced confidence below the evidence threshold. "
            f"Recommendations: submit clearer, well-lit images from the correct angle."
        )
        return {"failure_category": cat, "root_cause": cause}

    # Evidence failure — evidence_standard_met disagrees
    if exp_esm != pred_esm:
        cat = "evidence_failure"
        cause = (
            f"Evidence standard met: expected={exp_esm}, predicted={pred_esm}. "
            f"The pipeline may have failed to confirm all required evidence conditions "
            f"(object visible + part visible + issue visible) even though the image "
            f"contained relevant evidence. Tuning: review evidence_standards_engine thresholds."
        )
        return {"failure_category": cat, "root_cause": cause}

    # Severity confusion — everything else matches but severity wrong
    # (severity is not a direct output field in current CSV, so treat as fallback)
    cat = "evidence_failure"
    cause = (
        f"Claim status expected='{exp_status}' but predicted='{pred_status}'. "
        f"The VLM analysis or evidence standards engine produced an incorrect outcome. "
        f"Review the per-image VLM responses and confidence scores for this claim."
    )
    return {"failure_category": cat, "root_cause": cause}


# ---------------------------------------------------------------------------
# Category recommendations
# ---------------------------------------------------------------------------

_RECOMMENDATIONS: dict[str, list[str]] = {
    "no_model_baseline": [
        "Configure OPENROUTER_API_KEY to enable VLM vision analysis.",
        "Groq is only used for text reasoning fallback when all OpenRouter vision tiers fail.",
        "Ensure the 4-tier OpenRouter chain is operational: Qwen2.5-VL → Llama Vision → Pixtral Large → Groq.",
    ],
    "object_confusion": [
        "Add explicit object-type verification in Step 1 of the vision prompt.",
        "Use the WRONG_OBJECT flag to filter out images showing the wrong scene.",
        "Ensure v4 prompt's grounded observations step asks 'what type of object is in the image?' first.",
        "Consider prompting the model to explicitly compare observed object type to claimed type.",
    ],
    "object_part_confusion": [
        "Improve part-matching in vision_agent._aggregate(): track per-image object_present votes separately.",
        "Tune VISION_EVIDENCE_USER to include labeled examples of each object_part.",
        "Re-examine ClaimExtractionAgent: ensure claimed_part maps to the taxonomy correctly.",
        "Filter supporting images: only include images where supports_claim=True AND no WRONG_OBJECT flag.",
    ],
    "issue_type_confusion": [
        "Add disambiguation examples to the prompt for commonly confused pairs (dent/scratch, crack/glass_shatter).",
        "Use the step1_observations field (v4 prompt) to audit what the model actually saw.",
        "Consider adding severity thresholds: a deep scratch may be confused with a dent at low resolution.",
    ],
    "severity_confusion": [
        "Calibrate severity thresholds in vision_agent using damage extent descriptions from Step 1.",
        "Add severity examples to the VISION_EVIDENCE_USER prompt.",
    ],
    "evidence_failure": [
        "Review evidence_standards_engine thresholds for the relevant claim object/part combinations.",
        "Check that VLM confidence calibration is correct — low confidence pushes to NOT_MET incorrectly.",
        "Increase coverage bonus in _aggregate() for multi-image claims where partial evidence exists.",
    ],
    "image_quality_failure": [
        "Add a pre-screening step that rejects unreadable images before VLM analysis.",
        "Prompt v4 explicitly asks about image quality — use step1_observations to surface quality issues.",
        "Reduce WRONG_ANGLE penalty if any other image in the claim set is clean.",
        "Consider client-side image quality requirements (minimum resolution, lighting guidelines).",
    ],
}


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _write_report(
    error_df: pd.DataFrame,
    cat_counts: Counter,
    output_path: Path,
) -> None:
    total = len(error_df)
    lines = [
        "# Top Failure Patterns",
        "",
        f"> Generated by `evaluation/error_mining.py` — {total} error rows analysed.",
        "",
        "## Summary Table",
        "",
        "| Rank | Failure Category | Count | % of Errors |",
        "|------|-----------------|-------|-------------|",
    ]

    for rank, (cat, count) in enumerate(cat_counts.most_common(), 1):
        pct = round(count / total * 100, 1) if total > 0 else 0.0
        lines.append(f"| {rank} | `{cat}` | {count} | {pct}% |")

    lines += ["", "---", ""]

    # Per-category details
    for cat, count in cat_counts.most_common():
        subset = error_df[error_df["failure_category"] == cat].head(3)
        pct = round(count / total * 100, 1) if total > 0 else 0.0

        lines += [
            f"## {cat.replace('_', ' ').title()} ({count} cases, {pct}%)",
            "",
        ]

        for _, row in subset.iterrows():
            user_id = row.get("user_id", "?")
            obj = row.get("claim_object", "?")
            exp_status = row.get("expected_claim_status", "?")
            pred_status = row.get("predicted_claim_status", "?")
            exp_issue = row.get("expected_issue_type", "?")
            pred_issue = row.get("predicted_issue_type", "?")
            exp_part = row.get("expected_object_part", "?")
            pred_part = row.get("predicted_object_part", "?")
            root_cause = row.get("root_cause", "")
            pred_just = str(row.get("pred_justification", ""))[:200]
            gt_just = str(row.get("gt_justification", ""))[:150]

            lines += [
                f"### Example: {user_id} ({obj})",
                "",
                "| Field | Expected | Predicted |",
                "|-------|----------|-----------|",
                f"| claim_status | `{exp_status}` | `{pred_status}` |",
                f"| issue_type | `{exp_issue}` | `{pred_issue}` |",
                f"| object_part | `{exp_part}` | `{pred_part}` |",
                "",
            ]
            if gt_just:
                lines.append(f"**GT justification:** {gt_just}")
                lines.append("")
            if pred_just:
                lines.append(f"**Model justification:** {pred_just}")
                lines.append("")
            if root_cause:
                lines.append(f"**Root cause:** {root_cause}")
                lines.append("")

        # Recommendations
        recs = _RECOMMENDATIONS.get(cat, ["Review the model output and evidence standards for this category."])
        lines += [
            "**Actionable recommendations:**",
            "",
        ]
        for rec in recs:
            lines.append(f"- {rec}")
        lines += ["", "---", ""]

    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"[error_mining] Report written to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Mine error_analysis.csv for root-cause patterns.")
    p.add_argument("--error-csv", type=Path,
                   default=_ERROR_CSV,
                   help="Path to error_analysis.csv (default: code/evaluation/error_analysis.csv)")
    p.add_argument("--output", type=Path,
                   default=_OUTPUT_MD,
                   help="Output path for top_failure_patterns.md")
    p.add_argument("--regen", action="store_true",
                   help="Regenerate error_analysis.csv by running evaluate.py first")
    return p


def main() -> None:
    args = build_parser().parse_args()

    error_csv = args.error_csv
    output_md = args.output

    # Generate error_analysis.csv if missing or --regen requested
    if args.regen or not error_csv.exists():
        print(f"[error_mining] {error_csv} not found or --regen requested. Running evaluation...")
        from evaluation.evaluate import run_evaluation
        repo = _CODE_DIR.parent
        sample_path = repo / "dataset" / "sample_claims.csv"
        pred_path = repo / "code" / "outputs" / "sample_predictions.csv"
        output_dir = _CODE_DIR / "evaluation"
        run_evaluation(sample_path, pred_path, output_dir)

    if not error_csv.exists():
        print(f"[error_mining] ERROR: {error_csv} still not found after running evaluation.")
        sys.exit(1)

    # Load error CSV
    df = pd.read_csv(error_csv)
    print(f"[error_mining] Loaded {len(df)} error rows from {error_csv}")

    if df.empty:
        print("[error_mining] No errors found — perfect predictions!")
        output_md.write_text(
            "# Top Failure Patterns\n\nNo prediction errors found.\n",
            encoding="utf-8", newline="\n"
        )
        return

    # Apply root-cause analysis
    root_cause_data = df.apply(_classify_root_cause, axis=1)
    df["failure_category"] = [d["failure_category"] for d in root_cause_data]
    df["root_cause"] = [d["root_cause"] for d in root_cause_data]

    # Count categories
    cat_counts: Counter = Counter(df["failure_category"].tolist())

    # Print summary
    print("\n[error_mining] Failure category distribution:")
    total = len(df)
    for cat, count in cat_counts.most_common():
        pct = round(count / total * 100, 1)
        print(f"  {cat:35s} {count:3d} ({pct}%)")

    # Write report
    output_md.parent.mkdir(parents=True, exist_ok=True)
    _write_report(df, cat_counts, output_md)


if __name__ == "__main__":
    main()
