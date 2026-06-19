"""evaluate.py — full evaluation harness for the Multi-Modal Evidence Review system.

Usage
-----
    # From repo root:
    python code/evaluation/evaluate.py

    # With explicit paths:
    python code/evaluation/evaluate.py \
        --sample   dataset/sample_claims.csv \
        --output   code/evaluation/

    # Also run the pipeline first to generate predictions:
    python code/main.py \
        --input  dataset/sample_claims.csv \
        --output code/outputs/sample_predictions.csv

What this script produces
--------------------------
code/evaluation/
    metrics.json            — per-field accuracy, precision, recall, F1
    confusion_matrix.csv    — confusion matrix for claim_status
    error_analysis.csv      — every wrong prediction with prediction/expected/reason
    failure_cases.md        — ranked failure categories with examples
    evaluation_report.md    — narrative strengths/weaknesses/leaderboard analysis

Design constraints
------------------
- Never modifies the production pipeline.
- Reads predictions from a CSV file (output of main.py on sample_claims.csv).
- If no predictions file exists, runs the pipeline first (no-model mode).
- All metrics use macro averaging so rare classes are not hidden.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap — allow running from repo root or code/ directory
# ---------------------------------------------------------------------------

_THIS = Path(__file__).resolve()
_CODE_DIR = _THIS.parent.parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Fields to evaluate
# ---------------------------------------------------------------------------

EVAL_FIELDS = ["claim_status", "issue_type", "object_part", "evidence_standard_met"]

# claim_status classes for confusion matrix
STATUS_CLASSES = ["supported", "contradicted", "not_enough_information"]

# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


def _accuracy(y_true: list, y_pred: list) -> float:
    if not y_true:
        return 0.0
    return round(sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true), 4)


def _macro_prf(y_true: list, y_pred: list, classes: list[str]) -> dict[str, float]:
    """Compute macro-averaged precision, recall, F1."""
    precisions, recalls, f1s = [], [], []
    for cls in classes:
        tp = sum(t == cls and p == cls for t, p in zip(y_true, y_pred))
        fp = sum(t != cls and p == cls for t, p in zip(y_true, y_pred))
        fn = sum(t == cls and p != cls for t, p in zip(y_true, y_pred))
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1   = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)
    return {
        "precision_macro": round(sum(precisions) / len(precisions), 4) if precisions else 0.0,
        "recall_macro":    round(sum(recalls) / len(recalls), 4)    if recalls    else 0.0,
        "f1_macro":        round(sum(f1s) / len(f1s), 4)           if f1s        else 0.0,
    }


def _confusion_matrix(y_true: list, y_pred: list, classes: list[str]) -> pd.DataFrame:
    matrix = pd.DataFrame(0, index=classes, columns=classes)
    for t, p in zip(y_true, y_pred):
        if t in classes and p in classes:
            matrix.at[t, p] += 1
    matrix.index.name = "actual \\ predicted"
    return matrix


def _per_class_metrics(y_true: list, y_pred: list, classes: list[str]) -> list[dict]:
    rows = []
    for cls in classes:
        tp = sum(t == cls and p == cls for t, p in zip(y_true, y_pred))
        fp = sum(t != cls and p == cls for t, p in zip(y_true, y_pred))
        fn = sum(t == cls and p != cls for t, p in zip(y_true, y_pred))
        support = sum(t == cls for t in y_true)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1   = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        rows.append({
            "class": cls, "support": support,
            "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
        })
    return rows


# ---------------------------------------------------------------------------
# Failure category classifier
# ---------------------------------------------------------------------------

_QUALITY_FLAGS = {
    "blurry_image", "cropped_or_obstructed", "low_light_or_glare",
    "wrong_angle", "wrong_object", "wrong_object_part", "damage_not_visible",
}


def _classify_failure(row: pd.Series) -> str:
    """Return a human-readable failure category for one wrong prediction."""
    exp_status = str(row.get("expected_claim_status", ""))
    pred_status = str(row.get("predicted_claim_status", ""))
    exp_issue   = str(row.get("expected_issue_type", ""))
    pred_issue  = str(row.get("predicted_issue_type", ""))
    exp_part    = str(row.get("expected_object_part", ""))
    pred_part   = str(row.get("predicted_object_part", ""))
    risk_flags  = str(row.get("predicted_risk_flags", "")).lower()
    exp_esm     = str(row.get("expected_evidence_standard_met", "")).lower()
    pred_esm    = str(row.get("predicted_evidence_standard_met", "")).lower()

    quality_hit = any(f in risk_flags for f in _QUALITY_FLAGS)

    if exp_status != pred_status:
        if pred_status == "not_enough_information" and exp_status in ("supported", "contradicted"):
            if quality_hit:
                return "image_quality_failure"
            if exp_part != pred_part:
                return "object_part_failure"
            return "evidence_insufficiency"
        if pred_status == "supported" and exp_status == "contradicted":
            return "false_support"
        if pred_status == "contradicted" and exp_status == "supported":
            return "false_contradiction"
        return "claim_status_mismatch"

    if exp_issue != pred_issue and exp_issue not in ("", "unknown"):
        return "issue_type_mismatch"

    if exp_part != pred_part and exp_part not in ("", "unknown"):
        return "object_part_failure"

    if exp_esm != pred_esm:
        return "evidence_standard_failure"

    return "other_mismatch"


# ---------------------------------------------------------------------------
# Pipeline runner (for generating predictions if needed)
# ---------------------------------------------------------------------------

def _run_pipeline_no_model(sample_path: Path, output_path: Path) -> None:
    """Run the production pipeline in no-model mode to generate predictions."""
    from config import Settings
    from pipelines.claim_review_pipeline import ClaimReviewPipeline

    repo = _CODE_DIR.parent
    settings = Settings(repo_root=repo, cache_enabled=False)
    pipeline = ClaimReviewPipeline(settings=settings)
    pipeline.run(input_path=sample_path, output_path=output_path)


# ---------------------------------------------------------------------------
# Main evaluation logic
# ---------------------------------------------------------------------------

def run_evaluation(
    sample_path: Path,
    predictions_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Run the full evaluation and write all artefacts.

    Returns
    -------
    dict
        The metrics dict (also written to metrics.json).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------
    # Load ground truth
    # ----------------------------------------------------------------
    gt = pd.read_csv(sample_path)
    gt["evidence_standard_met"] = gt["evidence_standard_met"].astype(str).str.lower()

    # ----------------------------------------------------------------
    # Load or generate predictions
    # ----------------------------------------------------------------
    if not predictions_path.exists():
        print(f"[evaluate] No predictions found at {predictions_path}. Running pipeline...")
        predictions_path.parent.mkdir(parents=True, exist_ok=True)
        _run_pipeline_no_model(sample_path, predictions_path)

    pred = pd.read_csv(predictions_path)
    pred["evidence_standard_met"] = pred["evidence_standard_met"].astype(str).str.lower()

    # Align on user_id (order may differ)
    merged = gt.merge(pred, on="user_id", suffixes=("_gt", "_pred"), how="inner")
    n = len(merged)
    print(f"[evaluate] Evaluating {n} rows (ground truth: {len(gt)}, predictions: {len(pred)})")

    # ----------------------------------------------------------------
    # Per-field metrics
    # ----------------------------------------------------------------
    metrics: dict[str, Any] = {"n_samples": n, "fields": {}}

    field_map = {
        "claim_status":          ("claim_status_gt",          "claim_status_pred"),
        "issue_type":            ("issue_type_gt",             "issue_type_pred"),
        "object_part":           ("object_part_gt",            "object_part_pred"),
        "evidence_standard_met": ("evidence_standard_met_gt",  "evidence_standard_met_pred"),
    }

    for field, (gt_col, pred_col) in field_map.items():
        y_true = merged[gt_col].astype(str).tolist()
        y_pred = merged[pred_col].astype(str).tolist()
        classes = sorted(set(y_true) | set(y_pred))

        acc = _accuracy(y_true, y_pred)
        prf = _macro_prf(y_true, y_pred, classes)
        per_cls = _per_class_metrics(y_true, y_pred, classes)

        metrics["fields"][field] = {
            "accuracy": acc,
            **prf,
            "per_class": per_cls,
        }
        print(f"  {field:30s}  acc={acc:.3f}  f1={prf['f1_macro']:.3f}")

    # ----------------------------------------------------------------
    # Confusion matrix for claim_status
    # ----------------------------------------------------------------
    y_true_status = merged["claim_status_gt"].astype(str).tolist()
    y_pred_status = merged["claim_status_pred"].astype(str).tolist()
    cm = _confusion_matrix(y_true_status, y_pred_status, STATUS_CLASSES)
    cm.to_csv(output_dir / "confusion_matrix.csv")

    # ----------------------------------------------------------------
    # Error analysis — every wrong row
    # ----------------------------------------------------------------
    errors = []
    for _, row in merged.iterrows():
        field_errors: dict[str, dict] = {}
        for field, (gt_col, pred_col) in field_map.items():
            gt_val   = str(row.get(gt_col, ""))
            pred_val = str(row.get(pred_col, ""))
            if gt_val != pred_val:
                field_errors[field] = {"expected": gt_val, "predicted": pred_val}

        if field_errors:
            errors.append({
                "user_id":                    row["user_id"],
                "claim_object":               str(row.get("claim_object_gt", "")),
                "expected_claim_status":       str(row.get("claim_status_gt", "")),
                "predicted_claim_status":      str(row.get("claim_status_pred", "")),
                "expected_issue_type":         str(row.get("issue_type_gt", "")),
                "predicted_issue_type":        str(row.get("issue_type_pred", "")),
                "expected_object_part":        str(row.get("object_part_gt", "")),
                "predicted_object_part":       str(row.get("object_part_pred", "")),
                "expected_evidence_standard_met": str(row.get("evidence_standard_met_gt", "")),
                "predicted_evidence_standard_met": str(row.get("evidence_standard_met_pred", "")),
                "predicted_risk_flags":        str(row.get("risk_flags_pred", "")),
                "gt_justification":            str(row.get("claim_status_justification_gt", "")),
                "pred_justification":          str(row.get("claim_status_justification_pred", "")),
                "field_errors":                json.dumps(field_errors),
            })

    error_df = pd.DataFrame(errors)
    if not error_df.empty:
        error_df["failure_category"] = error_df.apply(_classify_failure, axis=1)
    else:
        error_df["failure_category"] = []

    error_df.to_csv(output_dir / "error_analysis.csv", index=False)
    metrics["n_errors"] = len(errors)
    metrics["error_rate"] = round(len(errors) / n, 4) if n > 0 else 0.0

    # ----------------------------------------------------------------
    # Failure category counts
    # ----------------------------------------------------------------
    if not error_df.empty:
        cat_counts = Counter(error_df["failure_category"].tolist())
    else:
        cat_counts = Counter()
    metrics["failure_categories"] = dict(cat_counts.most_common())

    # ----------------------------------------------------------------
    # Write metrics.json
    # ----------------------------------------------------------------
    with open(output_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # ----------------------------------------------------------------
    # failure_cases.md
    # ----------------------------------------------------------------
    _write_failure_cases(error_df, merged, output_dir / "failure_cases.md")

    # ----------------------------------------------------------------
    # evaluation_report.md
    # ----------------------------------------------------------------
    _write_report(metrics, cm, error_df, merged, output_dir / "evaluation_report.md")

    print(f"\n[evaluate] Artefacts written to {output_dir}")
    return metrics


# ---------------------------------------------------------------------------
# Failure cases markdown
# ---------------------------------------------------------------------------

def _write_failure_cases(
    error_df: pd.DataFrame,
    merged: pd.DataFrame,
    path: Path,
) -> None:
    lines = ["# Failure Cases\n"]
    lines.append(f"Total incorrect predictions: **{len(error_df)}**\n")

    if error_df.empty:
        lines.append("No errors found — perfect predictions!\n")
        path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
        return

    cat_counts = Counter(error_df["failure_category"].tolist())
    lines.append("## Ranked Failure Categories\n")
    lines.append("| Rank | Category | Count | % of Errors |")
    lines.append("|------|----------|-------|-------------|")
    for rank, (cat, count) in enumerate(cat_counts.most_common(), 1):
        pct = round(count / len(error_df) * 100, 1)
        lines.append(f"| {rank} | `{cat}` | {count} | {pct}% |")
    lines.append("")

    for cat, _ in cat_counts.most_common():
        subset = error_df[error_df["failure_category"] == cat]
        lines.append(f"## {cat.replace('_', ' ').title()} ({len(subset)} cases)\n")
        for _, row in subset.iterrows():
            user = row["user_id"]
            obj  = row["claim_object"]
            lines.append(f"### {user} ({obj})")
            lines.append(f"- **Expected claim_status**: `{row['expected_claim_status']}`")
            lines.append(f"- **Predicted claim_status**: `{row['predicted_claim_status']}`")
            lines.append(f"- **Expected issue/part**: `{row['expected_issue_type']}` / `{row['expected_object_part']}`")
            lines.append(f"- **Predicted issue/part**: `{row['predicted_issue_type']}` / `{row['predicted_object_part']}`")
            lines.append(f"- **Risk flags**: `{row['predicted_risk_flags']}`")
            lines.append(f"- **Field errors**: `{row['field_errors']}`")
            gt_just = str(row.get("gt_justification", ""))[:150]
            pred_just = str(row.get("pred_justification", ""))[:150]
            if gt_just:
                lines.append(f"- **GT justification**: {gt_just}")
            if pred_just:
                lines.append(f"- **Pred justification**: {pred_just}")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Evaluation report markdown
# ---------------------------------------------------------------------------

def _write_report(
    metrics: dict[str, Any],
    cm: pd.DataFrame,
    error_df: pd.DataFrame,
    merged: pd.DataFrame,
    path: Path,
) -> None:
    n = metrics["n_samples"]
    n_err = metrics["n_errors"]
    correct = n - n_err

    def fmet(field: str, key: str) -> str:
        return str(metrics["fields"].get(field, {}).get(key, "n/a"))

    # Object-type breakdown
    obj_acc: dict[str, list] = defaultdict(list)
    for _, row in merged.iterrows():
        obj = str(row.get("claim_object_gt", "unknown"))
        correct_row = str(row["claim_status_gt"]) == str(row["claim_status_pred"])
        obj_acc[obj].append(correct_row)
    obj_acc_str = "\n".join(
        f"  - **{obj}**: {round(sum(v)/len(v)*100,1)}% ({sum(v)}/{len(v)} correct)"
        for obj, v in sorted(obj_acc.items())
    )

    lines = [
        "# Evaluation Report",
        "",
        f"> Generated by `evaluation/evaluate.py` — {n} sample rows evaluated.",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total samples | {n} |",
        f"| Correct predictions (claim_status) | {correct} / {n} |",
        f"| claim_status accuracy | {fmet('claim_status', 'accuracy')} |",
        f"| claim_status F1 (macro) | {fmet('claim_status', 'f1_macro')} |",
        f"| issue_type accuracy | {fmet('issue_type', 'accuracy')} |",
        f"| object_part accuracy | {fmet('object_part', 'accuracy')} |",
        f"| evidence_standard_met accuracy | {fmet('evidence_standard_met', 'accuracy')} |",
        "",
        "## Per-Field Metrics",
        "",
    ]

    for field in EVAL_FIELDS:
        fm = metrics["fields"].get(field, {})
        lines += [
            f"### {field}",
            "",
            f"| Accuracy | Precision (macro) | Recall (macro) | F1 (macro) |",
            f"|----------|-------------------|----------------|------------|",
            f"| {fm.get('accuracy','n/a')} | {fm.get('precision_macro','n/a')} | {fm.get('recall_macro','n/a')} | {fm.get('f1_macro','n/a')} |",
            "",
        ]
        per_cls = fm.get("per_class", [])
        if per_cls:
            lines.append("| Class | Support | Precision | Recall | F1 |")
            lines.append("|-------|---------|-----------|--------|-----|")
            for r in per_cls:
                lines.append(
                    f"| {r['class']} | {r['support']} | {r['precision']} | {r['recall']} | {r['f1']} |"
                )
            lines.append("")

    lines += [
        "## Confusion Matrix — claim_status",
        "",
        "```",
        cm.to_string(),
        "```",
        "",
        "## Failure Analysis",
        "",
    ]

    if not error_df.empty:
        cat_counts = Counter(error_df["failure_category"].tolist())
        lines.append("### Ranked Failure Categories\n")
        lines.append("| Rank | Category | Count |")
        lines.append("|------|----------|-------|")
        for rank, (cat, cnt) in enumerate(cat_counts.most_common(), 1):
            lines.append(f"| {rank} | `{cat}` | {cnt} |")
        lines.append("")
    else:
        lines.append("No prediction errors detected.\n")

    lines += [
        "## Accuracy by Object Type",
        "",
        obj_acc_str,
        "",
        "## Strengths",
        "",
    ]

    # Identify top-performing fields
    strengths = []
    weaknesses = []
    for field in EVAL_FIELDS:
        acc = metrics["fields"].get(field, {}).get("accuracy", 0)
        if acc >= 0.7:
            strengths.append(f"- **{field}** accuracy = {acc} — strong signal extraction.")
        elif acc < 0.5:
            weaknesses.append(f"- **{field}** accuracy = {acc} — needs improvement.")

    if not strengths:
        strengths = ["- No field achieved ≥ 70% accuracy in no-model mode."]
    if not weaknesses:
        weaknesses = ["- No severe weaknesses detected."]

    lines += strengths
    lines += [
        "",
        "## Weaknesses",
        "",
    ]
    lines += weaknesses
    lines += [
        "",
        "## Likely Leaderboard Bottlenecks",
        "",
        "The following issues are most likely to hurt the leaderboard score based on "
        "error analysis:",
        "",
    ]

    # Rank bottlenecks by failure category frequency + field accuracy
    bottlenecks = []
    if metrics["fields"].get("claim_status", {}).get("accuracy", 1.0) < 0.8:
        bottlenecks.append(
            "1. **claim_status accuracy** — the most important output field. "
            "Without a VLM, all predictions default to `not_enough_information`. "
            "Connecting a vision model will be the single largest accuracy gain."
        )
    if not error_df.empty:
        cat_counts = Counter(error_df["failure_category"].tolist())
        for cat, cnt in cat_counts.most_common(3):
            bottlenecks.append(
                f"1. **{cat.replace('_', ' ')}** ({cnt} cases) — "
                + {
                    "image_quality_failure": "improve image quality pre-screening or prompt the VLM to handle low-quality images.",
                    "object_part_failure": "improve part-matching in ClaimExtractionAgent and vision prompts.",
                    "evidence_insufficiency": "tune evidence standards thresholds or add more supporting-image guidance.",
                    "false_support": "tighten the SUPPORTED decision rule — require higher VLM confidence.",
                    "false_contradiction": "relax the CONTRADICTED rule or add partial-evidence handling.",
                    "claim_status_mismatch": "review the decision rule chain for edge cases.",
                    "issue_type_mismatch": "improve issue_type normalisation in ClaimExtractionAgent.",
                    "evidence_standard_failure": "calibrate evidence sufficiency thresholds.",
                }.get(cat, "investigate and fix.")
            )

    if not bottlenecks:
        bottlenecks = ["1. Connect a vision model (VLM) to enable real visual evidence extraction."]

    lines += bottlenecks
    lines += [
        "",
        "## Operational Notes",
        "",
        f"- Model provider: **no-model mode** (no VLM configured).",
        f"- All `claim_status` predictions in no-model mode default to "
          f"`not_enough_information` because no visual evidence can be extracted.",
        f"- To improve results: set `MODEL_PROVIDER`, `VISION_MODEL`, and the "
          f"corresponding API key environment variable, then re-run.",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Evaluate Multi-Modal Evidence Review predictions.")
    p.add_argument("--sample", type=Path,
                   default=Path("dataset/sample_claims.csv"),
                   help="Path to ground-truth sample CSV (relative to repo root).")
    p.add_argument("--predictions", type=Path,
                   default=Path("code/outputs/sample_predictions.csv"),
                   help="Path to pipeline predictions CSV.")
    p.add_argument("--output", type=Path,
                   default=Path("code/evaluation"),
                   help="Directory where evaluation artefacts are written.")
    return p


def main() -> None:
    args = build_parser().parse_args()
    repo = _CODE_DIR.parent

    sample      = repo / args.sample      if not args.sample.is_absolute()      else args.sample
    predictions = repo / args.predictions if not args.predictions.is_absolute()  else args.predictions
    output_dir  = repo / args.output      if not args.output.is_absolute()       else args.output

    run_evaluation(sample, predictions, output_dir)


if __name__ == "__main__":
    main()
