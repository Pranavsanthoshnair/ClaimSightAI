"""Build deliverables: clean code.zip, validated output.csv, chat transcript copy."""

import zipfile
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent
CODE = ROOT / "code"
DELIVERABLES = ROOT / "deliverables"
DELIVERABLES.mkdir(exist_ok=True)

# ── 1. code.zip ──────────────────────────────────────────────────────────────
EXCLUDE_DIRS  = {"__pycache__", ".pytest_cache", ".cache"}
EXCLUDE_FILES = {"pipeline_events.jsonl", "debug_pipeline_report.json"}
EXCLUDE_EXTS  = {".pyc"}

zip_path = DELIVERABLES / "code.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in CODE.rglob("*"):
        if not f.is_file():
            continue
        # skip excluded dirs
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        if f.name in EXCLUDE_FILES:
            continue
        if f.suffix in EXCLUDE_EXTS:
            continue
        arc = f.relative_to(CODE)
        zf.write(f, arc)

with zipfile.ZipFile(zip_path) as zf:
    entries = zf.namelist()

print(f"[1] code.zip  : {len(entries)} files  |  {zip_path.stat().st_size/1024:.1f} KB")

KEY_FILES = [
    "main.py", "config.py",
    "evaluation/evaluation_report.md", "evaluation/main.py",
    "demo/app.py", "agents/vision_agent.py",
    "services/decision_service.py", "prompts/templates.py",
]
all_ok = True
for k in KEY_FILES:
    found = any(k in e or e.endswith(k) for e in entries)
    status = "OK" if found else "MISSING"
    if not found:
        all_ok = False
    print(f"     {status:7} {k}")

# ── 2. output.csv ─────────────────────────────────────────────────────────────
import pandas as pd

REQUIRED_COLS = [
    "user_id", "image_paths", "user_claim", "claim_object",
    "evidence_standard_met", "evidence_standard_met_reason",
    "risk_flags", "issue_type", "object_part", "claim_status",
    "claim_status_justification", "supporting_image_ids", "valid_image", "severity",
]

df = pd.read_csv(ROOT / "output.csv")
# ensure exact column order
df = df[REQUIRED_COLS]
out_path = DELIVERABLES / "output.csv"
df.to_csv(out_path, index=False)
print(f"\n[2] output.csv : {len(df)} rows  |  columns match spec: {list(df.columns) == REQUIRED_COLS}")
dist = df["claim_status"].value_counts().to_dict()
for k, v in dist.items():
    print(f"     {k}: {v}")

# ── 3. chat_transcript ────────────────────────────────────────────────────────
import os

log_src = pathlib.Path(os.path.expandvars("%USERPROFILE%")) / "hackerrank_orchestrate" / "log.txt"
transcript_dest = DELIVERABLES / "chat_transcript.txt"
if log_src.exists():
    shutil.copy(log_src, transcript_dest)
    print(f"\n[3] chat_transcript.txt : {transcript_dest.stat().st_size/1024:.1f} KB")
else:
    print(f"\n[3] WARN: log not found at {log_src}")
    sys.exit(1)

print("\n=== All deliverables ready in deliverables/ ===")
for f in sorted(DELIVERABLES.iterdir()):
    print(f"  {f.name:30s}  {f.stat().st_size/1024:8.1f} KB")
