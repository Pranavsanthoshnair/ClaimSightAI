"""submission_validator.py — validate output.csv against the problem statement.

Usage (from repo root):
    python code/evaluation/submission_validator.py
    python code/evaluation/submission_validator.py --output path/to/output.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_THIS = Path(__file__).resolve()
_CODE_DIR = _THIS.parent.parent
_REPO_DIR = _CODE_DIR.parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_DIR / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Allowed value sets from problem_statement.md
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = [
    "user_id", "image_paths", "user_claim", "claim_object",
    "evidence_standard_met", "evidence_standard_met_reason",
    "risk_flags", "issue_type", "object_part", "claim_status",
    "claim_status_justification", "supporting_image_ids", "valid_image", "severity",
]

ALLOWED_CLAIM_STATUS = {"supported", "contradicted", "not_enough_information"}

ALLOWED_ISSUE_TYPE = {
    "dent", "scratch", "crack", "glass_shatter", "broken_part",
    "missing_part", "torn_packaging", "crushed_packaging",
    "water_damage", "stain", "none", "unknown",
}

ALLOWED_OBJECT_PART_CAR = {
    "front_bumper", "rear_bumper", "door", "hood", "windshield",
    "side_mirror", "headlight", "taillight", "fender",
    "quarter_panel", "body", "unknown",
}
ALLOWED_OBJECT_PART_LAPTOP = {
    "screen", "keyboard", "trackpad", "hinge", "lid",
    "corner", "port", "base", "body", "unknown",
}
ALLOWED_OBJECT_PART_PACKAGE = {
    "box", "package_corner", "package_side", "seal",
    "label", "contents", "item", "unknown",
}
ALLOWED_OBJECT_PART = (
    ALLOWED_OBJECT_PART_CAR | ALLOWED_OBJECT_PART_LAPTOP | ALLOWED_OBJECT_PART_PACKAGE
)

ALLOWED_RISK_FLAGS = {
    "none", "blurry_image", "cropped_or_obstructed", "low_light_or_glare",
    "wrong_angle", "wrong_object", "wrong_object_part", "damage_not_visible",
    "claim_mismatch", "possible_manipulation", "non_original_image",
    "text_instruction_present", "user_history_risk", "manual_review_required",
}

ALLOWED_SEVERITY = {"none", "low", "medium", "high", "unknown"}
ALLOWED_BOOL_STR = {"true", "false"}


def _check_semicolon_field(value: str, allowed: set[str], field: str) -> list[str]:
    """Check a semicolon-separated field against an allowed values set."""
    errors = []
    parts = [p.strip().lower() for p in str(value).split(";") if p.strip()]
    for part in parts:
        if part not in allowed:
            errors.append(f"{field}: invalid value '{part}'")
    return errors


def validate(output_path: Path, claims_path: Path) -> tuple[bool, list[str]]:
    """Run all validation checks. Returns (passed, list_of_issues)."""
    issues: list[str] = []
    passed_checks: list[str] = []

    # ----------------------------------------------------------------
    # Load files
    # ----------------------------------------------------------------
    if not output_path.exists():
        return False, [f"output.csv not found at {output_path}"]

    out = pd.read_csv(output_path)
    claims = pd.read_csv(claims_path)

    # ----------------------------------------------------------------
    # Check 1: row count
    # ----------------------------------------------------------------
    if len(out) == len(claims):
        passed_checks.append(f"✅ Row count: {len(out)} rows (matches claims.csv)")
    else:
        issues.append(f"❌ Row count: {len(out)} rows in output vs {len(claims)} in claims.csv")

    # ----------------------------------------------------------------
    # Check 2: required columns present
    # ----------------------------------------------------------------
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in out.columns]
    if not missing_cols:
        passed_checks.append(f"✅ All {len(REQUIRED_COLUMNS)} required columns present")
    else:
        issues.append(f"❌ Missing columns: {missing_cols}")

    # ----------------------------------------------------------------
    # Check 3: column order
    # ----------------------------------------------------------------
    actual_order = list(out.columns)
    expected_order = REQUIRED_COLUMNS
    if actual_order[:len(expected_order)] == expected_order:
        passed_checks.append("✅ Column order matches problem statement")
    else:
        issues.append(f"❌ Column order mismatch. Expected: {expected_order[:5]}... Got: {actual_order[:5]}...")

    # Stop early if missing critical columns
    if missing_cols:
        return False, issues

    # ----------------------------------------------------------------
    # Check 4: no null values
    # ----------------------------------------------------------------
    null_counts = out[REQUIRED_COLUMNS].isnull().sum()
    null_cols = {c: int(n) for c, n in null_counts.items() if n > 0}
    if not null_cols:
        passed_checks.append("✅ No null values in required columns")
    else:
        issues.append(f"❌ Null values found: {null_cols}")

    # ----------------------------------------------------------------
    # Check 5: claim_status allowed values
    # ----------------------------------------------------------------
    bad_status = out[~out["claim_status"].str.lower().isin(ALLOWED_CLAIM_STATUS)]
    if bad_status.empty:
        passed_checks.append(f"✅ claim_status: all values are allowed")
    else:
        bad_vals = bad_status["claim_status"].unique().tolist()
        issues.append(f"❌ claim_status: invalid values at rows {bad_status.index.tolist()[:5]}: {bad_vals}")

    # ----------------------------------------------------------------
    # Check 6: issue_type allowed values
    # ----------------------------------------------------------------
    bad_issue = out[~out["issue_type"].str.lower().isin(ALLOWED_ISSUE_TYPE)]
    if bad_issue.empty:
        passed_checks.append("✅ issue_type: all values are allowed")
    else:
        bad_vals = bad_issue["issue_type"].unique().tolist()
        issues.append(f"❌ issue_type: invalid values {bad_vals} at rows {bad_issue.index.tolist()[:5]}")

    # ----------------------------------------------------------------
    # Check 7: object_part per claim_object
    # ----------------------------------------------------------------
    part_errors: list[str] = []
    for _, row in out.iterrows():
        obj = str(row.get("claim_object", "")).lower()
        part = str(row.get("object_part", "")).lower()
        allowed = {
            "car": ALLOWED_OBJECT_PART_CAR,
            "laptop": ALLOWED_OBJECT_PART_LAPTOP,
            "package": ALLOWED_OBJECT_PART_PACKAGE,
        }.get(obj, ALLOWED_OBJECT_PART)
        if part not in allowed:
            part_errors.append(f"row {row.name}: object_part='{part}' not valid for claim_object='{obj}'")
    if not part_errors:
        passed_checks.append("✅ object_part: all values valid for their claim_object")
    else:
        issues.append(f"❌ object_part: {len(part_errors)} invalid values (first 3: {part_errors[:3]})")

    # ----------------------------------------------------------------
    # Check 8: risk_flags (semicolon-separated)
    # ----------------------------------------------------------------
    flag_errors: list[str] = []
    for idx, row in out.iterrows():
        errs = _check_semicolon_field(row["risk_flags"], ALLOWED_RISK_FLAGS, f"row {idx} risk_flags")
        flag_errors.extend(errs)
    if not flag_errors:
        passed_checks.append("✅ risk_flags: all values are allowed")
    else:
        issues.append(f"❌ risk_flags: {len(flag_errors)} invalid values (first 3: {flag_errors[:3]})")

    # ----------------------------------------------------------------
    # Check 9: valid_image boolean string
    # ----------------------------------------------------------------
    bad_valid = out[~out["valid_image"].astype(str).str.lower().isin(ALLOWED_BOOL_STR)]
    if bad_valid.empty:
        passed_checks.append("✅ valid_image: all values are true/false")
    else:
        issues.append(f"❌ valid_image: invalid values at rows {bad_valid.index.tolist()[:5]}")

    # ----------------------------------------------------------------
    # Check 10: evidence_standard_met boolean string
    # ----------------------------------------------------------------
    bad_esm = out[~out["evidence_standard_met"].astype(str).str.lower().isin(ALLOWED_BOOL_STR)]
    if bad_esm.empty:
        passed_checks.append("✅ evidence_standard_met: all values are true/false")
    else:
        issues.append(f"❌ evidence_standard_met: invalid values at rows {bad_esm.index.tolist()[:5]}")

    # ----------------------------------------------------------------
    # Check 11: severity allowed values
    # ----------------------------------------------------------------
    bad_sev = out[~out["severity"].str.lower().isin(ALLOWED_SEVERITY)]
    if bad_sev.empty:
        passed_checks.append("✅ severity: all values are allowed")
    else:
        bad_vals = bad_sev["severity"].unique().tolist()
        issues.append(f"❌ severity: invalid values {bad_vals}")

    # ----------------------------------------------------------------
    # Check 12: supporting_image_ids format (none or valid stems)
    # ----------------------------------------------------------------
    img_id_errors: list[str] = []
    for idx, row in out.iterrows():
        val = str(row["supporting_image_ids"]).strip().lower()
        if val == "none":
            continue
        for part in val.split(";"):
            part = part.strip()
            if not part:
                continue
            # Image ID should be a filename stem — no slashes, no extension
            if "/" in part or "\\" in part or "." in part:
                img_id_errors.append(f"row {idx}: supporting_image_ids contains path-like value '{part}'")
    if not img_id_errors:
        passed_checks.append("✅ supporting_image_ids: all values are valid image ID stems or 'none'")
    else:
        issues.append(f"❌ supporting_image_ids: {len(img_id_errors)} malformed IDs (first 3: {img_id_errors[:3]})")

    # ----------------------------------------------------------------
    # Check 13: no empty string fields
    # ----------------------------------------------------------------
    empty_errors: list[str] = []
    for col in ["evidence_standard_met_reason", "claim_status_justification"]:
        empty_rows = out[out[col].astype(str).str.strip() == ""]
        if not empty_rows.empty:
            empty_errors.append(f"{col}: {len(empty_rows)} empty rows")
    if not empty_errors:
        passed_checks.append("✅ No empty justification/reason fields")
    else:
        issues.append(f"❌ Empty required text fields: {empty_errors}")

    all_passed = len(issues) == 0
    return all_passed, passed_checks + ([""] + issues if issues else [])


def write_report(
    output_path: Path,
    claims_path: Path,
    report_path: Path,
) -> bool:
    passed, results = validate(output_path, claims_path)

    lines = [
        "# Submission Validation Report",
        "",
        f"> Validating `{output_path.name}` against problem statement requirements.",
        "",
        "## Checks",
        "",
    ]

    for r in results:
        if r:
            lines.append(r)

    lines += [
        "",
        "## Verdict",
        "",
        "### ✅ READY TO SUBMIT" if passed else "### ❌ ISSUES FOUND — fix before submitting",
        "",
    ]

    if not passed:
        issues = [r for r in results if r.startswith("❌")]
        lines.append(f"**{len(issues)} check(s) failed.** Resolve before submitting.")
    else:
        passed_count = sum(1 for r in results if r.startswith("✅"))
        lines.append(f"All {passed_count} checks passed. Output is ready for leaderboard submission.")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return passed


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate output.csv for submission")
    p.add_argument("--output", type=Path, default=Path("output.csv"))
    p.add_argument("--claims", type=Path, default=Path("dataset/claims.csv"))
    p.add_argument("--report", type=Path,
                   default=Path("code/evaluation/submission_validation_report.md"))
    return p


def main() -> None:
    args = build_parser().parse_args()
    repo = _REPO_DIR

    output_path = repo / args.output if not args.output.is_absolute() else args.output
    claims_path = repo / args.claims if not args.claims.is_absolute() else args.claims
    report_path = repo / args.report if not args.report.is_absolute() else args.report

    print(f"[validator] Validating {output_path}")
    passed = write_report(output_path, claims_path, report_path)

    # Print summary to console
    passed_ok, results = validate(output_path, claims_path)
    for r in results:
        if r:
            print(r.encode("ascii", errors="replace").decode("ascii"))

    print(f"\n[validator] Report: {report_path}")
    print(f"[validator] Verdict: {'READY TO SUBMIT' if passed else 'ISSUES FOUND'}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
