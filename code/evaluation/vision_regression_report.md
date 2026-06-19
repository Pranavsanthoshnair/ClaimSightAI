# Vision Regression Report

> 10 test cases · Pass rate: **100.0%** (10/10)

## Summary

| Metric | Value |
|--------|-------|
| Total cases | 10 |
| Passed | 10 |
| Failed | 0 |
| Pass rate | 100.0% |
| Avg latency | 0.1s |
| Provider distribution | {'none': 10} |
| Fallback usage | 0/10 |
| Confidence (min/mean/max) | 0.00 / 0.00 / 0.00 |

## Per-Case Results

| ID | Description | Status | Confidence | Latency |
|----|-------------|--------|-----------|---------|
| `TC01_dented_car` | Dented car — rear bumper with visible dent | ✅ PASS | 0.00 | 0.51s |
| `TC02_scratched_car_bumper` | Car with front bumper scratch — supported | ✅ PASS | 0.00 | 0.0s |
| `TC03_cracked_windshield` | Cracked windshield — clear crack lines visibl | ✅ PASS | 0.00 | 0.17s |
| `TC04_wrong_angle_car` | Car but wrong angle — headlight not visible ( | ✅ PASS | 0.00 | 0.02s |
| `TC05_blurry_evidence` | Blurry door image — evidence quality issue | ✅ PASS | 0.00 | 0.21s |
| `TC06_cracked_laptop_screen` | Cracked laptop screen — supported | ✅ PASS | 0.00 | 0.05s |
| `TC07_laptop_no_visible_damage` | Laptop trackpad — no physical damage visible  | ✅ PASS | 0.00 | 0.05s |
| `TC08_torn_package` | Torn package seal — supported | ✅ PASS | 0.00 | 0.01s |
| `TC09_wrong_object` | Wrong object in image — not a shipping box | ✅ PASS | 0.00 | 0.01s |
| `TC10_multiple_damages` | Laptop hinge + screen — multiple damage types | ✅ PASS | 0.00 | 0.01s |

## Failure Details

No failures. All test cases passed.
## Passing Cases

- ✅ `TC01_dented_car` — Dented car — rear bumper with visible dent (conf=0.00, latency=0.51s, provider=none)
- ✅ `TC02_scratched_car_bumper` — Car with front bumper scratch — supported (conf=0.00, latency=0.0s, provider=none)
- ✅ `TC03_cracked_windshield` — Cracked windshield — clear crack lines visible (conf=0.00, latency=0.17s, provider=none)
- ✅ `TC04_wrong_angle_car` — Car but wrong angle — headlight not visible (partial visibility) (conf=0.00, latency=0.02s, provider=none)
- ✅ `TC05_blurry_evidence` — Blurry door image — evidence quality issue (conf=0.00, latency=0.21s, provider=none)
- ✅ `TC06_cracked_laptop_screen` — Cracked laptop screen — supported (conf=0.00, latency=0.05s, provider=none)
- ✅ `TC07_laptop_no_visible_damage` — Laptop trackpad — no physical damage visible (contradicted) (conf=0.00, latency=0.05s, provider=none)
- ✅ `TC08_torn_package` — Torn package seal — supported (conf=0.00, latency=0.01s, provider=none)
- ✅ `TC09_wrong_object` — Wrong object in image — not a shipping box (conf=0.00, latency=0.01s, provider=none)
- ✅ `TC10_multiple_damages` — Laptop hinge + screen — multiple damage types (conf=0.00, latency=0.01s, provider=none)

## Regression Gate

Pass rate threshold: **80%** (8/10 cases must pass).
Current pass rate: **100.0%**

**PASSED**

> Re-run after any prompt, provider, or parser change to detect regressions.