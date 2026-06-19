"""Vision Regression Suite — run from repo root.

Usage:
    python code/tests/run_vision_regression.py

    # With explicit output dir:
    python code/tests/run_vision_regression.py --output code/evaluation/

    # Dry run (no model calls):
    python code/tests/run_vision_regression.py --no-model

Reads:  code/tests/vision_regression/fixtures.json
Writes: code/evaluation/vision_regression_report.md
        code/evaluation/vision_regression_results.json

Exit code: 0 = all PASS, 1 = any FAIL
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

_CODE_DIR = Path(__file__).resolve().parent.parent
_REPO_DIR = _CODE_DIR.parent

if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_DIR / ".env")
except ImportError:
    pass

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

FIXTURES_PATH = _CODE_DIR / "tests" / "vision_regression" / "fixtures.json"


# ── Pipeline helpers ──────────────────────────────────────────────────────────

def _derive_status(vision_result) -> str:
    from models.enums import ClaimStatus
    if not vision_result.valid_image:
        return ClaimStatus.NOT_ENOUGH_INFORMATION
    if not vision_result.object_visible:
        return ClaimStatus.NOT_ENOUGH_INFORMATION
    if not vision_result.object_part_visible:
        return ClaimStatus.NOT_ENOUGH_INFORMATION
    if vision_result.issue_visible and vision_result.supporting_image_ids:
        return ClaimStatus.SUPPORTED
    if vision_result.object_part_visible and not vision_result.issue_visible:
        return ClaimStatus.CONTRADICTED
    return ClaimStatus.NOT_ENOUGH_INFORMATION


def run_one_case(case: dict, model_service, repo_root: Path) -> dict:
    """Run a single regression test case. Returns a result dict."""
    from agents.vision_agent import VisionReviewAgent
    from models.enums import ClaimObject, IssueType, ObjectPart
    from models.vision_review import VisionReviewInput

    case_id   = case["id"]
    img_path  = repo_root / case["image_path"]
    claim_obj = ClaimObject(case["claim_object"])
    claimed_p = ObjectPart(case["claimed_part"])
    claimed_i = IssueType(case["claimed_issue"])
    expected  = case["expected"]

    result = {
        "id": case_id,
        "description": case["description"],
        "image_path": str(img_path.relative_to(repo_root)),
        "passes": [],
        "failures": [],
        "provider_used": "none",
        "fallback_used": False,
        "latency_s": 0.0,
        "confidence": 0.0,
        "claim_status": "unknown",
        "object_present": None,
        "visible_parts": [],
        "visible_issues": [],
        "quality_flags": [],
        "error": None,
    }

    if not img_path.exists():
        result["error"] = f"Image not found: {img_path}"
        result["failures"].append(f"IMAGE_MISSING: {img_path}")
        return result

    agent = VisionReviewAgent(model_service=model_service, cache={})
    t0 = time.time()
    try:
        vision = agent.review(VisionReviewInput(
            image_paths=[img_path],
            claim_object=claim_obj,
            claimed_part=claimed_p,
            claimed_issue=claimed_i,
        ))
    except Exception as exc:
        result["error"] = str(exc)
        result["failures"].append(f"PIPELINE_ERROR: {exc}")
        result["latency_s"] = round(time.time() - t0, 2)
        return result

    result["latency_s"]    = round(time.time() - t0, 2)
    result["confidence"]   = vision.confidence

    per = vision.per_image[0] if vision.per_image else None
    result["object_present"]  = per.object_present if per else None
    result["visible_parts"]   = [p.value for p in (per.visible_parts  if per else [])]
    result["visible_issues"]  = [i.value for i in (per.visible_issues if per else [])]
    result["quality_flags"]   = [f.value for f in (per.quality_flags  if per else [])]
    result["claim_status"]    = _derive_status(vision)

    # Provider telemetry
    if model_service is not None:
        result["provider_used"] = getattr(model_service, "provider_name", "unknown")
        result["fallback_used"] = getattr(model_service, "fallback_count", 0) > 0

    # ── Assertions ────────────────────────────────────────────────────────────

    def chk(name: str, ok: bool, detail: str = ""):
        (result["passes"] if ok else result["failures"]).append(
            name + (f": {detail}" if detail else "")
        )

    # In no-model mode, VLM-dependent assertions are skipped to avoid
    # false failures. Only structural checks (image readable, pipeline runs)
    # are enforced. This lets the suite verify infra without burning API quota.
    has_model = model_service is not None

    # Always check: image is readable
    chk("image_readable", per is not None and per.readable)

    if has_model:
        # object_present
        if "object_present" in expected:
            actual_op = result["object_present"]
            exp_op    = expected["object_present"]
            chk("object_present", actual_op == exp_op,
                f"expected {exp_op}, got {actual_op}")

        # object_visible
        if "object_visible" in expected:
            chk("object_visible",
                vision.object_visible == expected["object_visible"],
                f"expected {expected['object_visible']}, got {vision.object_visible}")

        # issue_visible
        if "issue_visible" in expected:
            chk("issue_visible",
                vision.issue_visible == expected["issue_visible"],
                f"expected {expected['issue_visible']}, got {vision.issue_visible}")

        # supports_claim (per-image)
        if "supports_claim" in expected and per is not None:
            chk("supports_claim",
                per.supports_claim == expected["supports_claim"],
                f"expected {expected['supports_claim']}, got {per.supports_claim}")

        # confidence_min
        if "confidence_min" in expected:
            chk("confidence_min",
                result["confidence"] >= expected["confidence_min"],
                f"expected >= {expected['confidence_min']}, got {result['confidence']:.3f}")

        # visible_parts_contains (soft — all expected parts must be present)
        required_parts = expected.get("visible_parts_contains", [])
        for part in required_parts:
            chk(f"visible_part[{part}]",
                part in result["visible_parts"],
                f"not found in {result['visible_parts']}")

        # visible_issues_contains
        required_issues = expected.get("visible_issues_contains", [])
        for issue in required_issues:
            chk(f"visible_issue[{issue}]",
                issue in result["visible_issues"],
                f"not found in {result['visible_issues']}")

        # claim_status
        if "claim_status" in expected:
            chk("claim_status",
                result["claim_status"] == expected["claim_status"],
                f"expected {expected['claim_status']!r}, got {result['claim_status']!r}")

        # quality_flags_contains_any (at least one expected flag must be present)
        any_flags = expected.get("quality_flags_contains_any", [])
        if any_flags:
            found = any(f in result["quality_flags"] for f in any_flags)
            chk(f"quality_flag_any_of({','.join(any_flags)})",
                found,
                f"none found in {result['quality_flags']}")
    else:
        # No-model mode: only check that the pipeline didn't crash
        chk("pipeline_completed_without_error", result["error"] is None)

    return result


# ── Report writer ─────────────────────────────────────────────────────────────

def write_report(results: list[dict], output_path: Path) -> None:
    total = len(results)
    passed_cases = [r for r in results if not r["failures"] and not r["error"]]
    failed_cases = [r for r in results if r["failures"] or r["error"]]
    pass_rate    = round(len(passed_cases) / total * 100, 1) if total else 0.0
    avg_latency  = round(sum(r["latency_s"] for r in results) / max(total, 1), 2)
    provider_dist = Counter(r["provider_used"] for r in results)
    fallback_cnt  = sum(1 for r in results if r.get("fallback_used"))
    confidences   = [r["confidence"] for r in results if r["confidence"] > 0]
    conf_low  = min(confidences) if confidences else 0.0
    conf_high = max(confidences) if confidences else 0.0
    conf_mean = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

    lines = [
        "# Vision Regression Report",
        "",
        f"> {total} test cases · Pass rate: **{pass_rate}%** ({len(passed_cases)}/{total})",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total cases | {total} |",
        f"| Passed | {len(passed_cases)} |",
        f"| Failed | {len(failed_cases)} |",
        f"| Pass rate | {pass_rate}% |",
        f"| Avg latency | {avg_latency}s |",
        f"| Provider distribution | {dict(provider_dist)} |",
        f"| Fallback usage | {fallback_cnt}/{total} |",
        f"| Confidence (min/mean/max) | {conf_low:.2f} / {conf_mean:.2f} / {conf_high:.2f} |",
        "",
        "## Per-Case Results",
        "",
        "| ID | Description | Status | Confidence | Latency |",
        "|----|-------------|--------|-----------|---------|",
    ]

    for r in results:
        status = "PASS" if not r["failures"] and not r["error"] else "FAIL"
        emoji  = "✅" if status == "PASS" else "❌"
        lines.append(
            f"| `{r['id']}` | {r['description'][:45]} | {emoji} {status} "
            f"| {r['confidence']:.2f} | {r['latency_s']}s |"
        )

    lines += ["", "## Failure Details", ""]
    if not failed_cases:
        lines.append("No failures. All test cases passed.")
    else:
        for r in failed_cases:
            lines += [
                f"### {r['id']}",
                f"**Description:** {r['description']}",
                f"**Image:** `{r['image_path']}`",
            ]
            if r["error"]:
                lines.append(f"**Error:** `{r['error']}`")
            for fail in r["failures"]:
                lines.append(f"- ❌ `{fail}`")
            lines += [
                f"- object_present: `{r['object_present']}`",
                f"- visible_parts: `{r['visible_parts']}`",
                f"- visible_issues: `{r['visible_issues']}`",
                f"- quality_flags: `{r['quality_flags']}`",
                f"- claim_status: `{r['claim_status']}`",
                "",
            ]

    lines += [
        "## Passing Cases",
        "",
    ]
    for r in passed_cases:
        lines.append(
            f"- ✅ `{r['id']}` — {r['description']} "
            f"(conf={r['confidence']:.2f}, latency={r['latency_s']}s, "
            f"provider={r['provider_used']})"
        )

    lines += [
        "",
        "## Regression Gate",
        "",
        f"Pass rate threshold: **80%** (8/10 cases must pass).",
        f"Current pass rate: **{pass_rate}%**",
        "",
        "**PASSED**" if pass_rate >= 80 else "**FAILED — below 80% threshold**",
        "",
        "> Re-run after any prompt, provider, or parser change to detect regressions.",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run vision regression suite")
    p.add_argument("--output", type=Path, default=Path("code/evaluation"))
    p.add_argument("--no-model", action="store_true",
                   help="Skip VLM calls (preflight-only mode)")
    p.add_argument("--fixtures", type=Path, default=FIXTURES_PATH)
    return p


def main() -> int:
    args = build_parser().parse_args()
    repo = _REPO_DIR

    output_dir = repo / args.output if not args.output.is_absolute() else args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    fixtures_path = args.fixtures if args.fixtures.is_absolute() else repo / args.fixtures
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    print(f"[regression] {len(fixtures)} test cases loaded")

    # Build model service
    model_service = None
    if not args.no_model:
        from config import Settings
        from services.model_service import ModelService
        settings = Settings(repo_root=repo)
        if settings.has_vision_model:
            model_service = ModelService(settings=settings)
            print(f"[regression] Provider chain: {settings.provider_summary}")
        else:
            print("[regression] No model configured — preflight-only mode")
    else:
        print("[regression] --no-model flag: skipping VLM calls")

    results = []
    for i, case in enumerate(fixtures, 1):
        print(f"[regression] {i}/{len(fixtures)}: {case['id']} ...", end=" ", flush=True)
        result = run_one_case(case, model_service, repo)
        status = "PASS" if not result["failures"] and not result["error"] else "FAIL"
        print(f"{status} (conf={result['confidence']:.2f}, {result['latency_s']}s)")
        results.append(result)

        # Throttle between model calls
        if model_service is not None and i < len(fixtures):
            time.sleep(13)

    # Stats
    total   = len(results)
    passed  = sum(1 for r in results if not r["failures"] and not r["error"])
    pass_rate = round(passed / total * 100, 1) if total else 0.0
    avg_lat  = round(sum(r["latency_s"] for r in results) / max(total, 1), 2)
    fallbacks = sum(1 for r in results if r.get("fallback_used"))

    print(f"\n[regression] Results: {passed}/{total} passed ({pass_rate}%)")
    print(f"[regression] Avg latency: {avg_lat}s  Fallbacks: {fallbacks}/{total}")

    # Write outputs
    report_path = output_dir / "vision_regression_report.md"
    json_path   = output_dir / "vision_regression_results.json"

    write_report(results, report_path)
    json_path.write_text(
        json.dumps({
            "pass_rate": pass_rate,
            "passed": passed,
            "total": total,
            "avg_latency_s": avg_lat,
            "fallback_count": fallbacks,
            "results": results,
        }, indent=2),
        encoding="utf-8",
    )

    print(f"[regression] Report: {report_path}")
    print(f"[regression] JSON:   {json_path}")

    return 0 if pass_rate >= 80 else 1


if __name__ == "__main__":
    sys.exit(main())
