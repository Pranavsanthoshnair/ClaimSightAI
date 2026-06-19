# Vision Prompt Benchmark Report

Comparison of v2 (single-step) vs v3 (two-step reasoning) vision prompts.

## Results Summary

| Metric | v2 | v3 |
|--------|------|------|
| issue_type accuracy | 0.15 | 0.15 |
| object_part accuracy | 0.05 | 0.05 |
| claim_status accuracy | 0.1 | 0.1 |
| evidence_standard_met accuracy | 0.1 | 0.1 |
| mean confidence | 0.0 | 0.0 |

## Per-Row Comparison

| user_id | GT status | pred (v2) | pred (v3) |
|---------|-----------|------|------|
| user_001 ✗ | supported | not_enough_information | not_enough_information |
| user_002 ✗ | supported | not_enough_information | not_enough_information |
| user_004 ✗ | supported | not_enough_information | not_enough_information |
| user_007 ✗ | supported | not_enough_information | not_enough_information |
| user_005 ✗ | contradicted | not_enough_information | not_enough_information |
| user_006 ✓ | not_enough_information | not_enough_information | not_enough_information |
| user_003 ✗ | supported | not_enough_information | not_enough_information |
| user_008 ✗ | contradicted | not_enough_information | not_enough_information |
| user_009 ✗ | supported | not_enough_information | not_enough_information |
| user_010 ✗ | supported | not_enough_information | not_enough_information |
| user_011 ✗ | supported | not_enough_information | not_enough_information |
| user_012 ✗ | supported | not_enough_information | not_enough_information |
| user_018 ✗ | supported | not_enough_information | not_enough_information |
| user_020 ✗ | contradicted | not_enough_information | not_enough_information |
| user_015 ✗ | supported | not_enough_information | not_enough_information |
| user_030 ✗ | supported | not_enough_information | not_enough_information |
| user_031 ✗ | supported | not_enough_information | not_enough_information |
| user_032 ✓ | not_enough_information | not_enough_information | not_enough_information |
| user_033 ✗ | contradicted | not_enough_information | not_enough_information |
| user_034 ✗ | contradicted | not_enough_information | not_enough_information |

## Analysis

- **issue_type accuracy**: 0.15 → 0.15 (→0.0)
- **object_part accuracy**: 0.05 → 0.05 (→0.0)
- **claim_status accuracy**: 0.1 → 0.1 (→0.0)
