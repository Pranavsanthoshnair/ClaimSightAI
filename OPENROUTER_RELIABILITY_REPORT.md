# OpenRouter Reliability Report

**Generated:** 2026-06-19T23:26:25+05:30  
**Migration:** Gemini → OpenRouter-first (4-tier chain)  
**Test Suite:** `code/tests/validation/test_provider_stress.py`

---

## Provider Chain

| Tier | Model | Role | Status |
|------|-------|------|--------|
| T1 | `qwen/qwen2.5-vl-72b-instruct` | Primary vision | ✅ Configured |
| T2 | `meta-llama/llama-3.2-90b-vision-instruct` | Secondary fallback | ✅ Configured |
| T3 | `mistralai/pixtral-large-2411` | Tertiary fallback | ✅ Configured |
| T4 | `groq/llama-3.1-8b-instant` | Text reasoning fallback | ✅ Configured |

---

## Stress Test Results

**Total Tests:** 19  
**Pass Rate:** 19/19 (100%)  
**Test Suite:** `code/tests/validation/test_provider_stress.py`

| Scenario | Test | Result |
|----------|------|--------|
| 429 quota exhaustion → Tier 2 | `test_429_quota_immediate_fallback` | ✅ PASS |
| 429 on image 1 → image 2 still works | `test_429_on_first_of_two_images_second_still_works` | ✅ PASS |
| Consecutive 429s → eventually succeeds | `test_consecutive_429s_different_images` | ✅ PASS |
| 503 retry then fallback | `test_503_retry_then_fallback` | ✅ PASS |
| All tiers fail → preflight degradation | `test_all_tiers_fail_graceful_degradation` | ✅ PASS |
| Non-JSON response → retry | `test_non_json_response_triggers_retry` | ✅ PASS |
| All non-JSON → preflight fallback | `test_all_non_json_no_valid_result` | ✅ PASS |
| Empty JSON dict → safe defaults | `test_empty_json_response_handled` | ✅ PASS |
| ModelService returns None → graceful | `test_inspect_image_returns_none` | ✅ PASS |
| ConnectionError → fallback | `test_connection_error_trigger_fallback` | ✅ PASS |
| TimeoutError → fallback | `test_timeout_triggers_fallback` | ✅ PASS |
| No API keys → returns None | `test_no_api_keys_preflight_mode` | ✅ PASS |
| OpenRouter key → vision enabled | `test_openrouter_api_key_enables_vision` | ✅ PASS |
| No keys → inspect returns None | `test_model_service_init_no_keys` | ✅ PASS |
| OpenRouter key → provider_name works | `test_provider_property_with_openrouter_key` | ✅ PASS |
| 10 consecutive fails → no crash | `test_consecutive_calls_all_fail` | ✅ PASS |
| 2/3 images fail → aggregate valid | `test_mixed_success_failure` | ✅ PASS |
| Large image → resize without crash | `test_large_image_resize` | ✅ PASS |
| Non-image bytes → valid_image=False | `test_non_image_bytes` | ✅ PASS |

---

## Fallback Chain Validation

The `ModelService` implements the following provider hierarchy:

```
Tier 1 (qwen/qwen2.5-vl-72b-instruct)
  ↓ [on RuntimeError, ConnectionError, TimeoutError, or any Exception]
Tier 2 (meta-llama/llama-3.2-90b-vision-instruct)
  ↓ [on failure]
Tier 3 (mistralai/pixtral-large-2411)
  ↓ [on failure]
Tier 4 (groq/llama-3.1-8b-instant) — text reasoning fallback
  ↓ [on failure]
None — VisionReviewAgent applies safe preflight defaults
```

**Key behaviours verified:**
- 429 errors trigger immediate fallback (no retry on quota exhaustion)
- 503 errors allow retry (transient)
- All image analyses proceed even after a per-image failure
- Agent never raises exceptions — always returns a valid `VisionReviewResult`

---

## Key Improvements vs Gemini

| Dimension | Gemini (removed) | OpenRouter (new) |
|-----------|-----------------|------------------|
| Rate limits | Free-tier: 15 req/min, 12s throttle | Pay-per-use: no artificial throttle |
| Model quality | gemini-2.5-flash (avg) | Qwen2.5-VL-72B (frontier class) |
| Fallback depth | 1 tier | 3 vision tiers + 1 reasoning tier |
| Vendor lock-in | Google-only | Multi-model, swap any tier |
| SDK dependency | `google-genai` (removed) | `requests` only (stdlib-adjacent) |

---

## Conclusion

**PROVIDER CHAIN: FULLY OPERATIONAL**  
All 19 stress tests pass. The 4-tier OpenRouter-first chain handles all identified failure modes gracefully with zero crashes and deterministic degradation.
