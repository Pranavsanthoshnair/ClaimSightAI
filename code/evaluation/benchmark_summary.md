# Benchmark Summary

> Multi-Modal Evidence Review — vision prompt benchmark on `dataset/sample_claims.csv` (20 rows)

## Provider Chain

| Tier | Provider | Model | Trigger |
|------|----------|-------|---------|
| 1 | GeminiProvider | `gemini-2.5-flash` | Primary |
| 2 | OpenRouterProvider | `qwen/qwen2.5-vl-72b-instruct` | Gemini 429/503/timeout |
| 3 | OpenRouterProvider | `meta-llama/llama-3.2-90b-vision-instruct` | Tier 2 failure |

## No-Model Baseline (current state without VLM)

| Metric | Value | Notes |
|--------|-------|-------|
| claim_status accuracy | **0.10** | All predictions are `not_enough_information` |
| issue_type accuracy | **0.45** | From ClaimExtractionAgent text parsing |
| object_part accuracy | **0.70** | From ClaimExtractionAgent text parsing |
| evidence_standard_met accuracy | **0.10** | Always False without VLM |
| mean confidence | 0.0 | No VLM calls |
| cache hit rate | 0% | Cold start |
| fallback frequency | n/a | No model calls |

## Expected With VLM (v4 prompt)

| Metric | Expected Range | Improvement from Baseline |
|--------|---------------|--------------------------|
| claim_status accuracy | 0.65–0.85 | +55–75 percentage points |
| issue_type accuracy | 0.55–0.75 | +10–30 pp |
| object_part accuracy | 0.70–0.85 | 0–15 pp |
| evidence_standard_met accuracy | 0.60–0.80 | +50–70 pp |

## Key Failure Mode (Pre-VLM)

**65% of errors are `object_confusion`** — the pipeline cannot confirm object visibility without a VLM.
The v4 prompt directly addresses this: Step 1 explicitly asks "What type of object is in the image?
(car, laptop, package, or something else entirely)" before any claim context is shown.

## Operational Stats

| Stat | Sample (20 rows) | Test (44 rows) |
|------|-----------------|----------------|
| Total images | ~32 | ~70 |
| Model calls | ~32 | ~70 |
| Free-tier throttle | 13s/call | 13s/call |
| Est. runtime | ~7 min | ~15 min |
| Est. cost (Gemini Flash) | ~$0.003 | ~$0.007 |
| Cache benefit | 100% hit rate on 2nd run | 100% hit rate |

## How to Run

```bash
# Benchmark v4 prompt (default):
python code/evaluation/benchmark_vision.py --version v4

# Compare all prompt versions (slow on free tier):
python code/evaluation/benchmark_vision.py --version both

# No-model dry run:
python code/evaluation/benchmark_vision.py --no-model
```

## Prompt Versions

| Version | Description | Status |
|---------|-------------|--------|
| v2 | Single-step (legacy) | Deprecated |
| v3 | Two-step reasoning | Superseded |
| v4 | Grounded observations + 3-condition supports_claim | **Active** |
| v5 | Object-first variant (addresses object_confusion) | Experimental |
| v6 | Confidence-calibrated variant | Experimental |
