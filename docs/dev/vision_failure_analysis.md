# Vision Pipeline — Root Cause Analysis

## Summary

The "car not visible / confidence 0" output was **NOT a code bug** in the vision pipeline itself.
The direct Gemini API call (diagnose_vision.py) returned correct results:
- `object_present: true`
- `visible_parts: ["rear_bumper", "taillight", "body"]`
- `visible_issues: ["missing_part", "broken_part", "dent"]`
- `confidence: 1.0`
- `supports_claim: true`

## Root Cause: Free-Tier 429 Rate Limit

The pipeline was hitting Gemini's free-tier quota (5 req/min) and the retry logic was
waiting 40-60s per retry, causing timeouts. After exhausting all retries, the provider
returned `None`, which caused `_preflight_only_result()` to be used — producing
`confidence=0`, `object_visible=False`.

**Failure path:**
```
Gemini 429 → retry(wait 46s) → Gemini 429 → retry(wait 59s) → RuntimeError("exhausted")
→ ModelService returns None → VisionReviewAgent uses preflight-only → confidence=0
```

## Fixes Applied

### Fix 1: Fast 429 fallback
`GeminiProvider.analyze_image()` now raises `RuntimeError("429 quota exhausted")` immediately
on quota errors instead of sleeping and retrying. This triggers the OpenRouter fallback instantly.

### Fix 2: OpenRouter fallback chain
`ModelService._inspect_with_fallback()` catches the RuntimeError and tries OpenRouter
Tier 2 (Qwen2.5-VL) → Tier 3 (LLaMA-3.2-Vision) before returning None.

### Fix 3: `_FALLBACK_TRIGGERS` updated
Added `"quota"` to the fallback trigger keywords so `_should_fallback()` returns True
for quota exhaustion errors.

### Fix 4: Enum normalization
`_safe_enum_list()` now normalises values before coercion:
`"rear bumper"` → `"rear_bumper"`, `"REAR_BUMPER"` → `"rear_bumper"`.
This prevents valid Gemini outputs being silently discarded.

### Fix 5: quality_flags "none" filter
`_coerce_per_image()` now skips bare `"none"` in quality_flags lists (not a real flag).

### Fix 6: Debug logging
Every VLM call now logs:
- `PREFLIGHT-ONLY` when no model is configured
- Raw response length + preview before parsing
- All coerced fields after parsing

## To Reproduce Full Vision (requires API)
```bash
python diagnose_vision.py  # Direct Gemini test — bypasses throttle
```

## Verification
When Gemini quota is available, the pipeline returns correct results.
When quota is exhausted, OpenRouter fallback handles it automatically.
When all providers fail, preflight-only mode returns `not_enough_information` (correct conservative default).
