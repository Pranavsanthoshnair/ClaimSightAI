"""benchmark_vision.py — compare vision prompts on sample_claims.csv.

Usage
-----
    # With a real model (set OPENROUTER_API_KEY first):
    python code/evaluation/benchmark_vision.py

    # Default: only v3 prompt (faster)
    python code/evaluation/benchmark_vision.py --version v3

    # Compare both versions:
    python code/evaluation/benchmark_vision.py --version both

    # Dry-run without a model:
    python code/evaluation/benchmark_vision.py --no-model

What this script measures
--------------------------
For each prompt version it runs:
    ClaimExtractionAgent → VisionReviewAgent (per-image) → aggregate

It does NOT run the full pipeline (no EvidenceStandards, no DecisionService).
It compares the VisionReviewResult directly against ground-truth labels.

Metrics reported per prompt version:
    - issue_type accuracy
    - object_part accuracy
    - claim_status accuracy  (derived from vision result using simple rules)
    - evidence_standard_met accuracy
    - cache_hit_rate, avg_latency, provider_used distribution, fallback_frequency

Output files:
    code/evaluation/benchmark_results.json
    code/evaluation/benchmark_report.md

Cache:
    code/.cache/benchmark_cache.jsonl
    Key: SHA-256 of (prompt_version + image_bytes_hash + claim_object + claimed_part + claimed_issue)
    Never re-analyzes identical images with the same prompt version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

_THIS = Path(__file__).resolve()
_CODE_DIR = _THIS.parent.parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

logging.basicConfig(level=logging.WARNING)

# Load .env from repo root if present
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_CODE_DIR.parent / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_CACHE_FILE = _CODE_DIR / ".cache" / "benchmark_cache.jsonl"


def _cache_key(
    prompt_version: str,
    image_bytes: bytes,
    claim_object: str,
    claimed_part: str,
    claimed_issue: str,
) -> str:
    """SHA-256 of (prompt_version + image_bytes_hash + claim fields)."""
    img_hash = hashlib.sha256(image_bytes).hexdigest()
    payload = f"{prompt_version}|{img_hash}|{claim_object}|{claimed_part}|{claimed_issue}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _load_cache() -> dict[str, Any]:
    """Load the persistent JSONL cache into a dict keyed by cache_key."""
    cache: dict[str, Any] = {}
    if not _CACHE_FILE.exists():
        return cache
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    cache[entry["key"]] = entry["value"]
                except (json.JSONDecodeError, KeyError):
                    pass
    except OSError:
        pass
    return cache


def _save_cache_entry(key: str, value: Any) -> None:
    """Append one entry to the persistent JSONL cache."""
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({"key": key, "value": value}, ensure_ascii=False)
    with open(_CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


# ---------------------------------------------------------------------------
# Prompt version definitions
# ---------------------------------------------------------------------------

# v2 = single-step prompt (previous)
# v3 = two-step reasoning prompt (current/improved)
# v4 = grounded observations + taxonomy mapping (latest)

_PROMPT_VERSIONS = ["v2", "v3", "v4", "v5", "v6"]

# ---------------------------------------------------------------------------
# Simple claim-status derivation from VisionReviewResult (no DecisionService)
# ---------------------------------------------------------------------------

def _derive_status(vision_result: Any) -> str:  # type: ignore[return]
    """Derive a claim_status string from VisionReviewResult for benchmarking."""
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


# ---------------------------------------------------------------------------
# Accuracy helpers
# ---------------------------------------------------------------------------

def _accuracy(y_true: list, y_pred: list) -> float:
    if not y_true:
        return 0.0
    return round(sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true), 4)


# ---------------------------------------------------------------------------
# Retry-after parsing
# ---------------------------------------------------------------------------

def _parse_retry_after(exc_str: str) -> int:
    """Parse 'retry in Xs' from a 429 error message. Returns seconds to sleep."""
    m = re.search(r"retry[_ ](?:in|after)[_ ](\d+)", exc_str, re.IGNORECASE)
    if m:
        return int(m.group(1)) + 2
    return 13  # conservative default


# ---------------------------------------------------------------------------
# Runner for one prompt version
# ---------------------------------------------------------------------------

def _run_one_version(
    prompt_version: str,
    sample_df: pd.DataFrame,
    repo_root: Path,
    model_service: Any | None,
    persistent_cache: dict[str, Any],
) -> dict[str, Any]:
    """Run VisionReviewAgent for all sample rows with a specific prompt version."""
    import prompts.templates as tmpl

    # Patch the PROMPT_VERSION at module level so cache keys differ per version
    original_version = tmpl.PROMPT_VERSION
    tmpl.PROMPT_VERSION = prompt_version

    # Patch prompts used by the agent based on version
    if prompt_version == "v2":
        tmpl.VISION_EVIDENCE_SYSTEM = tmpl.VISION_EVIDENCE_SYSTEM_V2
        tmpl.VISION_EVIDENCE_USER = tmpl.VISION_EVIDENCE_USER_V2
    elif prompt_version == "v3":
        tmpl.VISION_EVIDENCE_SYSTEM = tmpl.VISION_EVIDENCE_SYSTEM_V3
        tmpl.VISION_EVIDENCE_USER = tmpl.VISION_EVIDENCE_USER_V3
    elif prompt_version == "v5":
        tmpl.VISION_EVIDENCE_SYSTEM = tmpl.VISION_EVIDENCE_SYSTEM_V5
        tmpl.VISION_EVIDENCE_USER = tmpl.VISION_EVIDENCE_USER_V5
    elif prompt_version == "v6":
        tmpl.VISION_EVIDENCE_SYSTEM = tmpl.VISION_EVIDENCE_SYSTEM_V6
        tmpl.VISION_EVIDENCE_USER = tmpl.VISION_EVIDENCE_USER_V6
    # v4 is the current default (already set in templates.py)

    from agents.vision_agent import VisionReviewAgent
    from models.claim_extraction import ClaimExtractionInput
    from models.enums import ClaimObject
    from models.vision_review import VisionReviewInput
    from agents.claim_agent import ClaimExtractionAgent

    claim_agent = ClaimExtractionAgent()

    # Build in-memory cache bridging persistent JSONL and per-session dict
    # The persistent_cache is read-only here; we add new entries via _save_cache_entry
    session_cache: dict[str, Any] = dict(persistent_cache)

    vision_agent = VisionReviewAgent(model_service=model_service, cache=session_cache)

    rows: list[dict[str, Any]] = []
    cache_hits = 0
    latencies: list[float] = []
    provider_counts: Counter = Counter()
    fallback_count = 0

    for _, row in sample_df.iterrows():
        user_id = row["user_id"]
        image_paths_raw = str(row["image_paths"]).split(";")
        claim_object_str = str(row["claim_object"])
        user_claim = str(row["user_claim"])

        # Ground truth
        gt_issue = str(row.get("issue_type", "unknown"))
        gt_part = str(row.get("object_part", "unknown"))
        gt_status = str(row.get("claim_status", "not_enough_information"))
        gt_esm = str(row.get("evidence_standard_met", "false")).lower()

        # Resolve image paths
        image_paths = []
        for raw in image_paths_raw:
            raw = raw.strip()
            direct = repo_root / raw
            if direct.exists():
                image_paths.append(direct)
            else:
                with_ds = repo_root / "dataset" / raw
                if with_ds.exists():
                    image_paths.append(with_ds)
                else:
                    image_paths.append(direct)

        # Claim extraction
        try:
            claim_obj = ClaimObject(claim_object_str)
        except ValueError:
            claim_obj = ClaimObject.CAR

        try:
            extraction = claim_agent.extract(
                ClaimExtractionInput(user_claim=user_claim, claim_object=claim_obj)
            )
        except Exception as exc:  # noqa: BLE001
            logging.warning("Claim extraction failed for %s: %s", user_id, exc)
            rows.append({
                "user_id": user_id,
                "gt_issue": gt_issue, "pred_issue": "unknown",
                "gt_part": gt_part, "pred_part": "unknown",
                "gt_status": gt_status, "pred_status": "not_enough_information",
                "gt_esm": gt_esm, "pred_esm": "false",
                "confidence": 0.0, "reasoning": f"extraction_error: {exc}",
                "elapsed_s": 0.0, "cache_hit": False, "error": True,
            })
            continue

        if not image_paths:
            rows.append({
                "user_id": user_id,
                "gt_issue": gt_issue, "pred_issue": "unknown",
                "gt_part": gt_part, "pred_part": "unknown",
                "gt_status": gt_status, "pred_status": "not_enough_information",
                "gt_esm": gt_esm, "pred_esm": "false",
                "confidence": 0.0, "reasoning": "no images",
                "elapsed_s": 0.0, "cache_hit": False, "error": False,
            })
            continue

        # Check persistent cache for each image before calling VLM
        # (VisionReviewAgent handles the in-memory cache; we pre-populate it here)
        cache_hit_this_row = False
        for img_path in image_paths:
            if img_path.exists():
                try:
                    img_bytes = img_path.read_bytes()
                    key = _cache_key(
                        prompt_version, img_bytes,
                        str(claim_obj),
                        str(extraction.claimed_object_part),
                        str(extraction.claimed_issue_type),
                    )
                    if key in persistent_cache and key not in session_cache:
                        session_cache[key] = persistent_cache[key]
                        cache_hit_this_row = True
                except OSError:
                    pass

        if cache_hit_this_row:
            cache_hits += 1

        # Vision review
        t0 = time.time()
        try:
            result = vision_agent.review(VisionReviewInput(
                image_paths=image_paths,
                claim_object=claim_obj,
                claimed_part=extraction.claimed_object_part,
                claimed_issue=extraction.claimed_issue_type,
                is_multi_part=extraction.is_multi_part,
            ))
        except Exception as exc:  # noqa: BLE001
            logging.warning("Vision review failed for %s: %s", user_id, exc)
            rows.append({
                "user_id": user_id,
                "gt_issue": gt_issue, "pred_issue": "unknown",
                "gt_part": gt_part, "pred_part": "unknown",
                "gt_status": gt_status, "pred_status": "not_enough_information",
                "gt_esm": gt_esm, "pred_esm": "false",
                "confidence": 0.0, "reasoning": f"error: {exc}",
                "elapsed_s": round(time.time() - t0, 2),
                "cache_hit": cache_hit_this_row, "error": True,
            })
            continue

        elapsed = round(time.time() - t0, 2)
        latencies.append(elapsed)

        # Throttle between API calls — only when model was actually called
        if model_service is not None and not cache_hit_this_row:
            throttle = max(0.0, 13.0 - elapsed)
            if throttle > 0:
                time.sleep(throttle)

        # Track provider stats
        if model_service is not None and hasattr(model_service, "provider_name"):
            provider_counts[model_service.provider_name] += 1
            if hasattr(model_service, "fallback_count"):
                fallback_count = model_service.fallback_count

        # Persist new cache entries (check which keys were added to session_cache)
        for img_path in image_paths:
            if img_path.exists():
                try:
                    img_bytes = img_path.read_bytes()
                    key = _cache_key(
                        prompt_version, img_bytes,
                        str(claim_obj),
                        str(extraction.claimed_object_part),
                        str(extraction.claimed_issue_type),
                    )
                    if key in session_cache and key not in persistent_cache:
                        _save_cache_entry(key, session_cache[key])
                        persistent_cache[key] = session_cache[key]
                except OSError:
                    pass

        pred_status = _derive_status(result)
        pred_esm = "true" if result.valid_image and result.supporting_image_ids else "false"

        rows.append({
            "user_id": user_id,
            "gt_issue": gt_issue,
            "pred_issue": result.issue_type.value,
            "gt_part": gt_part,
            "pred_part": result.object_part.value,
            "gt_status": gt_status,
            "pred_status": pred_status,
            "gt_esm": gt_esm,
            "pred_esm": pred_esm,
            "confidence": result.confidence,
            "reasoning": result.reasoning[:200],
            "elapsed_s": elapsed,
            "cache_hit": cache_hit_this_row,
            "error": False,
        })

    # Restore
    tmpl.PROMPT_VERSION = original_version

    # Compute metrics
    y_issue_t = [r["gt_issue"] for r in rows]
    y_issue_p = [r["pred_issue"] for r in rows]
    y_part_t = [r["gt_part"] for r in rows]
    y_part_p = [r["pred_part"] for r in rows]
    y_status_t = [r["gt_status"] for r in rows]
    y_status_p = [r["pred_status"] for r in rows]
    y_esm_t = [r["gt_esm"] for r in rows]
    y_esm_p = [r["pred_esm"] for r in rows]

    n = len(rows)
    total_cache_hits = sum(1 for r in rows if r.get("cache_hit"))
    cache_hit_rate = round(total_cache_hits / n, 4) if n > 0 else 0.0
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
    fallback_frequency = round(fallback_count / n, 4) if n > 0 else 0.0

    # Print stats
    print(f"\n[benchmark v{prompt_version}] Stats:")
    print(f"  cache_hit_rate={cache_hit_rate}  avg_latency={avg_latency}s")
    print(f"  provider_used={dict(provider_counts)}  fallback_frequency={fallback_frequency}")
    print(f"  errors={sum(1 for r in rows if r.get('error'))}")

    return {
        "prompt_version": prompt_version,
        "n": n,
        "issue_type_accuracy": _accuracy(y_issue_t, y_issue_p),
        "object_part_accuracy": _accuracy(y_part_t, y_part_p),
        "claim_status_accuracy": _accuracy(y_status_t, y_status_p),
        "evidence_standard_met_accuracy": _accuracy(y_esm_t, y_esm_p),
        "mean_confidence": round(sum(r["confidence"] for r in rows) / max(n, 1), 4),
        "cache_hit_rate": cache_hit_rate,
        "avg_latency_s": avg_latency,
        "provider_distribution": dict(provider_counts),
        "fallback_frequency": fallback_frequency,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _write_report(results: list[dict], path: Path) -> None:
    lines = [
        "# Vision Prompt Benchmark Report",
        "",
        "Comparison of vision prompt versions on sample_claims.csv.",
        "",
        "## Results Summary",
        "",
        "| Metric | " + " | ".join(r["prompt_version"] for r in results) + " |",
        "|--------|" + "|".join("------" for _ in results) + "|",
    ]

    metrics = [
        ("issue_type_accuracy", "issue_type accuracy"),
        ("object_part_accuracy", "object_part accuracy"),
        ("claim_status_accuracy", "claim_status accuracy"),
        ("evidence_standard_met_accuracy", "evidence_standard_met accuracy"),
        ("mean_confidence", "mean confidence"),
        ("cache_hit_rate", "cache hit rate"),
        ("avg_latency_s", "avg latency (s)"),
        ("fallback_frequency", "fallback frequency"),
    ]

    for key, label in metrics:
        vals = " | ".join(str(r.get(key, "n/a")) for r in results)
        lines.append(f"| {label} | {vals} |")

    lines += ["", "## Per-Row Comparison", ""]
    lines.append("| user_id | GT status | " + " | ".join(f"pred ({r['prompt_version']})" for r in results) + " |")
    lines.append("|---------|-----------|" + "|".join("------" for _ in results) + "|")

    if results:
        for i, row in enumerate(results[0]["rows"]):
            uid = row["user_id"]
            gt = row["gt_status"]
            preds = " | ".join(results[v]["rows"][i]["pred_status"] for v in range(len(results)))
            match = "✓" if all(results[v]["rows"][i]["pred_status"] == gt for v in range(len(results))) else "✗"
            lines.append(f"| {uid} {match} | {gt} | {preds} |")

    lines += [
        "",
        "## Analysis",
        "",
    ]

    if len(results) >= 2:
        r_old = results[0]
        r_new = results[1]
        for key, label in metrics[:4]:
            old_v = r_old.get(key, 0)
            new_v = r_new.get(key, 0)
            delta = round(new_v - old_v, 4)
            sign = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
            lines.append(f"- **{label}**: {old_v} → {new_v} ({sign}{abs(delta)})")
        lines.append("")

    if not any(r.get("rows", [{}])[0].get("elapsed_s") for r in results if r.get("rows")):
        lines.append(
            "> Note: Benchmark ran in no-model mode. "
            "All vision results are preflight-only (confidence=0). "
            "Set `OPENROUTER_API_KEY` to enable real VLM analysis."
        )

    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Benchmark vision prompts on sample_claims.csv")
    p.add_argument("--sample", type=Path, default=Path("dataset/sample_claims.csv"))
    p.add_argument("--output", type=Path, default=Path("code/evaluation"))
    p.add_argument("--no-model", action="store_true",
                   help="Skip model calls (measures extraction quality only)")
    p.add_argument("--version", choices=["v2", "v3", "v4", "both"], default="v3",
                   help="Which prompt version to run (default: v3)")
    return p


def main() -> None:
    args = build_parser().parse_args()
    repo = _CODE_DIR.parent

    sample_path = repo / args.sample if not args.sample.is_absolute() else args.sample
    output_dir = repo / args.output if not args.output.is_absolute() else args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(sample_path)
    print(f"[benchmark] {len(df)} sample rows loaded from {sample_path}")

    # Determine which versions to run
    if args.version == "both":
        versions = _PROMPT_VERSIONS
    else:
        versions = [args.version]

    # Load persistent cache
    persistent_cache = _load_cache()
    print(f"[benchmark] Loaded {len(persistent_cache)} cached entries from {_CACHE_FILE}")

    # Build model service
    model_service = None
    if not args.no_model:
        from config import Settings
        from services.model_service import ModelService
        settings = Settings(repo_root=repo)
        if settings.has_vision_model:
            model_service = ModelService(settings=settings)
            print(f"[benchmark] Using provider chain: {settings.provider_summary}")
            uncached_rows = len(df) - len([k for k in persistent_cache])
            if len(versions) * len(df) > 5:
                est_min = round(len(versions) * len(df) * 2 / 60, 1)
                print(f"[benchmark] Estimated max time: {est_min} min")
        else:
            print("[benchmark] No model configured — running in no-model mode.")

    results = []
    for version in versions:
        print(f"[benchmark] Running prompt version {version} ({len(df)} rows)...")
        result = _run_one_version(version, df, repo, model_service, persistent_cache)
        results.append(result)
        print(f"  issue_type={result['issue_type_accuracy']}  "
              f"object_part={result['object_part_accuracy']}  "
              f"claim_status={result['claim_status_accuracy']}")

    # Save JSON
    out = {v["prompt_version"]: {k: val for k, val in v.items() if k != "rows"} for v in results}
    with open(output_dir / "benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    # Save report
    _write_report(results, output_dir / "benchmark_report.md")

    print(f"\n[benchmark] Results written to {output_dir}")
    print("[benchmark] Files: benchmark_results.json, benchmark_report.md")


if __name__ == "__main__":
    main()
