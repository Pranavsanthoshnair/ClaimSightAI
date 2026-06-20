# ClaimSight AI — Evaluation & Operational Analysis Report

## System Overview

ClaimSight AI is a multi-modal evidence review pipeline that processes damage claims
using vision language models (VLMs), structured prompting, evidence standards, and
a rule-based decision engine. The system evaluates each claim across four stages:

1. **Claim Extraction** — LLM extracts structured claim from conversation
2. **Vision Review** — VLM analyses each submitted image against the claim
3. **Evidence Standards** — rule engine checks minimum image evidence requirements
4. **Decision Engine** — combines all outputs into a final verdict

---

## Sample Set Evaluation (`dataset/sample_claims.csv`)

| Metric | Score |
|--------|-------|
| Claim status accuracy | 55% (pre-fix baseline) |
| Supported precision | 90% |
| Supported recall | 69% |
| Contradicted recall | 20% → improved with fixes |
| Evidence standard accuracy | 85% |
| Object part accuracy | 65% |
| Issue type accuracy | 50% |

**Key accuracy improvements applied after baseline measurement:**
- Bug fix: `issue_visible` no longer triggers on any damage — only the specifically claimed type
- New Rule 2c: wrong damage type in image → CONTRADICTED + CLAIM_MISMATCH flag
- Bug fix: Rule 5 now returns CONTRADICTED (not SUPPORTED) when visible type ≠ claimed type
- Rule 2a moved before evidence gate: part visible + claimed damage absent → CONTRADICTED

---

## Model Call Counts

### Sample set (20 claims, ~38 images)
| Stage | Calls per claim | Total calls |
|-------|----------------|-------------|
| Claim extraction | 1 LLM call | ~20 |
| Vision review | 1 VLM call per image | ~38 |
| Evidence standards | 0 (rule-based) | 0 |
| Decision engine | 0 (rule-based) | 0 |
| **Total** | | **~58 calls** |

### Test set (44 claims, ~82 images)
| Stage | Calls per claim | Total calls |
|-------|----------------|-------------|
| Claim extraction | 1 LLM call | ~44 |
| Vision review | 1 VLM call per image | ~82 |
| Evidence standards | 0 (rule-based) | 0 |
| Decision engine | 0 (rule-based) | 0 |
| **Total** | | **~126 calls** |

---

## Token Usage Estimates

### Claim Extraction (per call)
- System prompt: ~350 tokens
- User prompt (claim + taxonomy): ~250 tokens
- Response (JSON): ~150 tokens
- **Per call: ~750 tokens** | **Total (44 claims): ~33,000 tokens**

### Vision Review (per image)
- System prompt: ~450 tokens
- User prompt (claim context + taxonomies): ~300 tokens
- Image: billed as ~1,000–2,000 tokens depending on size (auto-resized to ≤1536px)
- Response (JSON): ~200 tokens
- **Per image: ~2,200–3,200 tokens** | **Total (82 images): ~215,000 tokens**

### Combined estimate
| | Input tokens | Output tokens |
|--|-------------|--------------|
| Claim extraction (44) | ~26,000 | ~7,000 |
| Vision review (82 images) | ~180,000 | ~16,000 |
| **Total** | **~206,000** | **~23,000** |

---

## Cost Estimate (Test Set, 44 claims / 82 images)

Pricing based on OpenRouter published rates (June 2026):

| Model | Role | Input $/1M | Output $/1M | Est. Cost |
|-------|------|-----------|------------|----------|
| Llama 3.2 11B Vision (T1) | Vision primary | $0.055 | $0.055 | ~$0.013 |
| Claude 3 Haiku (T2) | Vision fallback | $0.25 | $1.25 | ~$0.08 |
| Qwen 2.5 VL 72B (T3) | Vision fallback | $0.40 | $0.40 | ~$0.12 |
| GPT-4o Mini (optional) | Claim extraction | $0.15 | $0.60 | ~$0.03 |
| **Total (nominal T1 path)** | | | | **~$0.05–0.25** |
| **Total (all-fallback path)** | | | | **< $0.50** |

> During the test run, T1 (Llama) and T2 (Claude Haiku) credits were exhausted on the
> primary keys, causing the pipeline to fall through to T3 (Qwen) and free-tier models.
> This increased latency but did not increase cost beyond the fallback tier pricing.

---

## Latency & Runtime

| Phase | Per claim | Total (44 claims) |
|-------|-----------|------------------|
| Claim extraction | ~2–4s | ~2 min |
| Vision review (1 image, T1) | ~3–6s | — |
| Vision review (1 image, T2/T3) | ~6–12s | — |
| Evidence + decision | <0.1s | negligible |
| **Total (nominal, T1 path)** | ~8–15s | **~7–11 min** |
| **Total (with key exhaustion)** | ~20–40s | **~17–25 min** |

**Observed runtime:** ~17 minutes for 44 claims with exhausted T1/T2 keys.

---

## TPM / RPM Considerations

| Model | OpenRouter RPM limit | Our usage | Strategy |
|-------|---------------------|-----------|----------|
| Llama 3.2 11B Vision | ~20 RPM | ~3–5 RPM | Sequential; no batching needed |
| Claude 3 Haiku | ~50 RPM | ~3–5 RPM | Well within limits |
| Qwen 2.5 VL 72B | ~10 RPM | ~3–5 RPM | Sequential |

---

## Caching Strategy

- **Content-addressed cache** in `code/services/cache_service.py`: keyed on
  `(prompt_hash, image_hash, model_slug, prompt_version)`.
- Cache is in-memory (dict-backed) per process run. Shared across images within
  a single pipeline run to avoid re-analysing identical images.
- `--no-cache` flag bypasses all cache reads and writes for fresh evaluation runs.
- **PROMPT_VERSION** is embedded in every cache key — bumping the version
  automatically invalidates stale entries without manual cleanup.

---

## Retry & Fallback Strategy

```
Tier 1: meta-llama/llama-3.2-11b-vision-instruct
  └─ rotate across all keys in pool instantly on 402/429
Tier 2: anthropic/claude-3-haiku  
  └─ rotate across all keys in pool instantly on 402/429
Tier 3: qwen/qwen2.5-vl-72b-instruct
  └─ rotate across all keys
Tier 4: free-tier models (Gemma 4 26B, Nemotron VL 12B)
  └─ last resort; no credit cost
```

- On `402 Payment Required` (credits exhausted): instant key rotation, no wait.
- On `429 Too Many Requests`: exponential backoff with jitter (0.5s → 1s → 2s → 4s).
- On `5xx` or timeout: retry up to 3 times before falling to next tier.
- If all tiers fail: claim is marked `not_enough_information` with
  `MANUAL_REVIEW_REQUIRED` flag; pipeline continues to next row.

---

## Images Processed

| Dataset | Claims | Images |
|---------|--------|--------|
| Sample (sample_claims.csv) | 20 | ~38 |
| Test (claims.csv) | 44 | 82 |
| **Total** | **64** | **~120** |

All images auto-resized to ≤ 1536px on longest edge before encoding to base64
to reduce token cost and avoid model context limits.

---

## Batching Notes

The current implementation processes claims **sequentially** (one at a time).
Multiple images within a single claim are processed sequentially within the
Vision Review stage. This was intentional for:

1. **Determinism** — sequential ordering is reproducible
2. **Rate limit safety** — avoids burst spikes on free/low-tier keys
3. **Simplicity** — easier to trace and debug

Parallel batching (e.g., `asyncio.gather`) would reduce total runtime by ~3×
for T1 models but would require higher RPM allowances.
