# FINAL OUTPUT VALIDATION

> Comprehensive validation report for `output.csv` — HackerRank Orchestrate multi-modal evidence review system.

---

## 1. How output.csv Was Generated

**Generation command:** `python code/generate_output.py`

**Pipeline entry point:** `code/pipelines/claim_review_pipeline.py` — `ClaimReviewPipeline.run()`

**Pipeline mode:** Preflight-only (no API-based vision model)

The pipeline ran in **preflight-only mode** (`MODEL_PROVIDER=none`), meaning no actual VLM/LLM API calls were made for vision review. The claim extraction agent performed rule-based parsing of the conversation transcript, and the evidence standards engine applied deterministic checks against `evidence_requirements.csv`. All vision review fields (`valid_image`, `confidence`, `supporting_image_ids`) were populated without real image inference.

The pipeline log (`code/logs/pipeline_events.jsonl`) shows two runs:
- **Run 1** (17:16–17:19 UTC, 6 claims processed): Early preview using Gemini — produced `confidence=1.0`, some `evidence_standard_met=true`, with meaningful risk flags like `manual_review_required`.
- **Run 2** (17:21–17:22 UTC, all 44 claims): Final output — **zero-confidence preflight mode** across all rows.

Pipeline stages (per row):
1. **A — Claim Extraction** (`ClaimExtractionAgent`): Parsed `user_claim` transcript to extract `issue_type` and `object_part`.
2. **B — Vision Review** (`VisionReviewAgent`): Not invoked (no model available), returned default preflight result.
3. **C — Evidence Standards** (`EvidenceStandardsEngine`): Checked `evidence_requirements.csv` against submitted image count; all failed with gap "claimed object not visible in any image".
4. **D — Decision** (`DecisionService`): Combined extraction + evidence + user history into final output row.

**Output written:** `output.csv` at `2026-06-19T22:51:20` local time.

---

## 2. Row Count & Match with claims.csv

| Metric | Value |
|---|---|
| output.csv rows | **44** |
| claims.csv rows | **44** |
| Match | ✅ Exact match |
| Unique users (output) | 36 |
| Unique users (claims) | 36 |

---

## 3. All 13 Validation Checks — Pass/Fail

Validated by `code/evaluation/submission_validator.py` (see `code/evaluation/submission_validation_report.md`):

| # | Check | Status |
|---|---|---|
| 1 | Row count matches claims.csv | ✅ PASS |
| 2 | All 14 required columns present | ✅ PASS |
| 3 | Column order matches problem statement | ✅ PASS |
| 4 | No null values in required columns | ✅ PASS |
| 5 | `claim_status` values are allowed (`supported`/`contradicted`/`not_enough_information`) | ✅ PASS |
| 6 | `issue_type` values are allowed | ✅ PASS |
| 7 | `object_part` values valid for their `claim_object` | ✅ PASS |
| 8 | `risk_flags` values are allowed | ✅ PASS |
| 9 | `valid_image` values are `true`/`false` | ✅ PASS |
| 10 | `evidence_standard_met` values are `true`/`false` | ✅ PASS |
| 11 | `severity` values are allowed | ✅ PASS |
| 12 | `supporting_image_ids` are valid image ID stems or `none` | ✅ PASS |
| 13 | No empty justification/reason fields | ✅ PASS |

**Result: 13/13 checks pass.** Schema-level validation is clean.

---

## 4. Column-by-Column Quality Assessment

| Column | Quality | Notes |
|---|---|---|
| `user_id` | ✅ GOOD | All populated, matches claims.csv. 36 unique users. |
| `image_paths` | ✅ GOOD | Exact copy from claims.csv. Semicolon-separated paths preserved. |
| `user_claim` | ✅ GOOD | Exact copy from claims.csv. Transcripts preserved verbatim. |
| `claim_object` | ✅ GOOD | 18 car, 13 laptop, 13 package. Matches expected distribution. |
| `evidence_standard_met` | ⚠️ ALL FALSE | 44/44 = `False`. Preflight mode could not verify images. Never `True`. |
| `evidence_standard_met_reason` | ⚠️ REPETITIVE | 41/44 rows say "claimed object not visible in any image" — accurate for preflight but lacks per-image specificity. |
| `risk_flags` | ⚠️ SKEWED | 13/44 "none" despite having user history; `blurry_image` only flagged 5× despite likely more quality issues. |
| `issue_type` | ✅ GOOD | All 12 allowed values used. Reasonable distribution. `unknown` used 5× where extraction was ambiguous. |
| `object_part` | ✅ GOOD | All values valid per claim_object. Reasonable distribution. |
| `claim_status` | ⚠️ ALL `not_enough_information` | 44/44 = `not_enough_information`. Zero `supported` or `contradicted` predictions. |
| `claim_status_justification` | ⚠️ REPETITIVE | Mirrors evidence_standard_met_reason. Repeats gap details without image-specific grounding. |
| `supporting_image_ids` | ⚠️ ALL `none` | 44/44 = `none`. No image was identified as supporting any claim. |
| `valid_image` | ⚠️ 42/44 TRUE | Two rows (user_008, user_037) correctly flagged `False` for blurry images. The 42 `True` values may be overly optimistic given no actual image review. |
| `severity` | ⚠️ MANUAL-ONLY | 25 medium, 11 high, 3 low, 5 unknown. Distribution is plausible but determined without image inspection. |

---

## 5. Claim Status Distribution

| Status | Count | % |
|---|---|---|
| `not_enough_information` | **44** | 100.0% |
| `supported` | 0 | 0.0% |
| `contradicted` | 0 | 0.0% |

**Data quality concern:** The model never found enough evidence to support or contradict any claim. This is consistent with preflight-only mode where no actual image analysis was performed. A production system with a real VLM would be expected to produce a mix of `supported` and `not_enough_information` verdicts, especially for clear visual evidence.

---

## 6. Provider Summary

| Field | Value |
|---|---|
| `MODEL_PROVIDER` env var | `none` |
| Pipeline mode | **Preflight-only** (no API VLM calls made) |
| Vision model used | None |
| VLM calls for output.csv | **0** |
| VLM calls for sample_claims.csv | **0** (also preflight) |
| Cache hits | 0 |
| Fallback chain triggered | No |

The system is designed to support Gemini (primary), OpenRouter (Tier 1: `google/gemini-2.5-flash`, Tier 2: `qwen/qwen2.5-vl-72b-instruct`, Tier 3: `meta-llama/llama-3.2-90b-vision-instruct`), OpenAI, and Anthropic providers, but **none were configured or used** for the final output generation.

---

## 7. Evidence Standard Met Distribution

| Evidence Standard Met | Count | % |
|---|---|---|
| `False` | **44** | 100.0% |
| `True` | 0 | 0.0% |

Reason breakdown:
- `1/4 evidence requirement(s) satisfied`: **29** rows (13 laptop + 10 package + 6 car)
- `1/5 evidence requirement(s) satisfied`: **10** rows (all car)
- `No valid images were available for assessment`: **2** rows (user_008 case_006, user_037 case_037)
- `1/6 evidence requirement(s) satisfied`: **1** row (user_042 car)
- `1/3 evidence requirement(s) satisfied`: **1** row (user_043 car)
- `2/4 evidence requirement(s) satisfied`: **1** row (user_039 package)

The dominant gap ("claimed object not visible in any image") is a direct consequence of preflight mode — no image content inspection occurred to verify presence of the claimed object.

---

## 8. Risk Flag Distribution

| Risk Flag | Count |
|---|---|
| `user_history_risk` | **24** |
| `none` | **13** |
| `manual_review_required` | **13** |
| `blurry_image` | **5** |

Composite risk flag pattern breakdown:
- `user_history_risk` alone: **16**
- `none`: **13**
- `user_history_risk;manual_review_required`: **6**
- `manual_review_required` alone: **4**
- `blurry_image;user_history_risk;manual_review_required`: **2**
- `blurry_image` alone: **2**
- `blurry_image;manual_review_required`: **1**

**No usage** of: `cropped_or_obstructed`, `low_light_or_glare`, `wrong_angle`, `wrong_object`, `wrong_object_part`, `damage_not_visible`, `claim_mismatch`, `possible_manipulation`, `non_original_image`, `text_instruction_present`.

This is a data quality concern — the risk flag vocabulary is underutilized. With real VLM analysis, image-quality flags like `low_light_or_glare`, `wrong_angle`, `wrong_object`, and `text_instruction_present` would likely be triggered for several claims (multiple conversations contain instructions like "approve the claim immediately").

---

## 9. Severity Distribution

| Severity | Count | % |
|---|---|---|
| `medium` | **25** | 56.8% |
| `high` | **11** | 25.0% |
| `unknown` | **5** | 11.4% |
| `low` | **3** | 6.8% |
| `none` | **0** | 0.0% |

The severity distribution shows a reasonable spread, though all values were determined purely from rule-based analysis of the claim transcript (issue type + object part), not from actual image-based damage assessment.

---

## 10. Data Quality Concerns

1. **Zero diversity in `claim_status`** — All 44 rows are `not_enough_information`. This is consistent with preflight mode but means the system produces no actionable `supported` or `contradicted` decisions. The sample_claims.csv evaluation would show 0% accuracy on supported/contradicted rows.

2. **Zero supporting images** — `supporting_image_ids` is `none` for every row. Even for claims with clear damage descriptions, no image could be identified as supporting evidence.

3. **Repetitive justification text** — `evidence_standard_met_reason` and `claim_status_justification` contain formulaic text that differs only by requirement ratio (1/4 vs 1/5) and object type. They lack image-specific grounding.

4. **Underutilized risk flags** — Only 4 of 14 allowed risk flags are used. `blurry_image` (5 instances) is the only image-quality flag. `user_history_risk` (24 instances) and `manual_review_required` (13 instances) dominate.

5. **Overly optimistic `valid_image`** — 42/44 rows marked `True` despite no actual image review. Two rows correctly flagged as `False` (user_008, user_037 — both had explicit blurry-image flags).

6. **Preflight-only execution** — The system's provider architecture is complete and supports Gemini, OpenRouter, OpenAI, and Anthropic with a 3-tier fallback chain, but no provider was configured (`MODEL_PROVIDER=none`). The output reflects rule-based extraction only, not VLM-based evidence review.

---

## 11. Overall Validation Verdict

**⚠️ SCHEMA-READY — NOT SUBMISSION-READY FOR LEADERBOARD**

| Criteria | Status |
|---|---|
| Column schema | ✅ Compliant |
| Row count | ✅ Matches |
| Allowed values | ✅ All valid |
| Null safety | ✅ No nulls |
| Structural validation (13/13 checks) | ✅ PASS |
| Claim status diversity (supported/contradicted present) | ❌ FAIL |
| Supporting image identification | ❌ FAIL |
| Image-grounded justifications | ❌ FAIL |
| VLM-powered evidence review | ❌ FAIL (preflight only) |
| Provider configured | ❌ FAIL (`MODEL_PROVIDER=none`) |

**Why not ready:** The output passes all 13 schema-level checks but does not perform actual evidence review. The system operates entirely in preflight mode with no VLM calls. For a leaderboard submission, the system must be run with a real vision provider (e.g., `MODEL_PROVIDER=gemini` with `GEMINI_API_KEY` set) to produce genuine `supported`/`contradicted` verdicts with image-grounded justifications and supporting image IDs.

**To make submission-ready:**
1. Set `MODEL_PROVIDER=gemini` (or `openai` / `anthropic`) and provide the corresponding API key in `.env`
2. Re-run: `python code/generate_output.py`
3. Re-validate: `python code/evaluation/submission_validator.py`
4. The output should then show a mix of `supported` and `not_enough_information` (and possibly `contradicted`) verdicts with proper supporting image IDs
