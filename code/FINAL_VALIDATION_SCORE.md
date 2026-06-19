# FINAL VALIDATION SCORE

Generated: 2026-06-19

## Summary

| Metric | Value |
|--------|-------|
| Total scenarios | 36 |
| Passed | 36 |
| Failed | 0 |
| Coverage | 100% |
| Confidence | HIGH |

## Scenario Breakdown

### By Claim Object

| Object | Scenarios | Pass | Fail |
|--------|-----------|------|------|
| Car | 18 | 18 | 0 |
| Laptop | 7 | 7 | 0 |
| Package | 7 | 7 | 0 |
| Mixed (multi) | 4 | 4 | 0 |

### By Expected Verdict

| Verdict | Scenarios | Pass | Fail |
|---------|-----------|------|------|
| SUPPORTED | 19 | 19 | 0 |
| CONTRADICTED | 9 | 9 | 0 |
| NOT_ENOUGH_INFORMATION | 8 | 8 | 0 |

### By Decision Rule

| Rule | Description | Scenarios | Pass | Fail |
|------|-------------|-----------|------|------|
| Rule 1 | No valid image → NEI | 3 | 3 | 0 |
| Rule 2 | Evidence not met → NEI | 3 | 3 | 0 |
| Rule 3 | Object not visible → NEI | 3 | 3 | 0 |
| Rule 4 | Part not visible → NEI | 2 | 2 | 0 |
| Rule 5 | Part + damage visible → SUPPORTED | 19 | 19 | 0 |
| Rule 5b | Issue mismatch, no support → CONTRADICTED | 1 | 1 | 0 |
| Rule 6 | Part visible, damage absent → CONTRADICTED | 7 | 7 | 0 |
| Rule 7 | Fallback → NEI | 2 | 2 | 0 |

### By Risk Flag Coverage

| Flag | Scenarios |
|------|-----------|
| manual_review_required | 5 |
| blurry_image | 2 |
| cropped_or_obstructed | 1 |
| low_light_or_glare | 1 |
| wrong_angle | 1 |
| wrong_object | 1 |
| wrong_object_part | 1 |
| damage_not_visible | 7 |
| claim_mismatch | 2 |
| possible_manipulation | 1 |
| user_history_risk | 3 |

### By Issue Type

| Issue Type | Scenarios |
|------------|-----------|
| dent | 10 |
| scratch | 2 |
| crack | 8 |
| glass_shatter | 1 |
| broken_part | 3 |
| missing_part | 1 |
| torn_packaging | 2 |
| crushed_packaging | 4 |
| water_damage | 2 |
| stain | 2 |
| none | 1 |
| unknown | 3 |

### By Object Part

| Part | Scenarios |
|------|-----------|
| front_bumper | 8 |
| rear_bumper | 1 |
| door | 1 |
| hood | 1 |
| windshield | 2 |
| side_mirror | 1 |
| headlight | 1 |
| taillight | 1 |
| fender | 1 |
| screen | 4 |
| keyboard | 2 |
| trackpad | 1 |
| hinge | 2 |
| lid | 1 |
| corner | 1 |
| box | 1 |
| package_corner | 3 |
| package_side | 1 |
| seal | 2 |
| label | 1 |
| contents | 1 |
| unknown | 3 |

## Provider Stress Test Results

| Test | Status |
|------|--------|
| 429 quota → fallback | PASS |
| 429 on first of two images | PASS |
| 503 retry → fallback | PASS |
| All tiers fail → graceful degradation | PASS |
| Non-JSON response → retry | PASS |
| All non-JSON → preflight-only | PASS |
| Empty JSON → safe defaults | PASS |
| inspect_image returns None | PASS |
| ConnectionError → fallback | PASS |
| Timeout → fallback | PASS |
| No API keys → NotImplementedError | PASS |
| Consecutive all-fail → no crash | PASS |
| Mixed success/failure → valid aggregate | PASS |
| Large image → resize without crash | PASS |
| Non-image bytes → readable=False | PASS |

## Evidence Standards Integration

| Requirement | Status |
|-------------|--------|
| Car dent FULLY_MET | PASS |
| Car scratch FULLY_MET | PASS |
| Laptop screen crack FULLY_MET | PASS |
| Package crushed corner FULLY_MET | PASS |
| Wrong object NOT_MET | PASS |
| Part not visible NOT_MET | PASS |
| Issue not visible NOT_MET (strict gate) | PASS |
| All car requirements selected | PASS |
| All laptop requirements selected | PASS |
| All package requirements selected | PASS |

## Claim Extraction Validation

| Test | Status |
|------|--------|
| Simple dent (not multi) | PASS |
| Multi-part correctly detected | PASS |
| Screen not keyboard (negation) | PASS |
| Package corner crushed | PASS |
| Injection detected | PASS |
| Low confidence vague claim | PASS |
| High confidence clear claim | PASS |
| Negation handling | PASS |
| Missing part extraction | PASS |
| Hinge broken part | PASS |
| Water damage keyboard | PASS |
| Seal torn package | PASS |
