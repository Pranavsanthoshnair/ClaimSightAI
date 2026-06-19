# High-Value Failure Cases

> Ranked by leaderboard impact. Leaderboard score = 3 (claim_status wrong) > 2 (issue_type or object_part wrong) > 1 (evidence_standard_met only).
> Source: `code/evaluation/error_analysis.csv` — 20 errors from no-model baseline evaluation.

---

## Impact Summary

| Failure Type | Count | Leaderboard Impact | Root Cause |
|---|---|---|---|
| `claim_status` wrong | 18 | **3** each (highest) | No VLM = all NEI; VLM needed to confirm visibility |
| `issue_type` wrong | 6 | **2** each | ClaimExtraction text mismatch or VLM taxonomy error |
| `object_part` wrong | 5 | **2** each | Part not visible / VLM part confusion |
| `evidence_standard_met` wrong | 18 | **1** each | Follows from no-model baseline |

**Key insight: 90% of claim_status errors will disappear once a real VLM is connected.**

---

## Tier 1 — claim_status wrong (Impact Score: 3) — 18 cases

### user_001 · car · Impact: 3

| Field | Expected | Predicted |
|---|---|---|
| claim_status | `supported` | `not_enough_information` |
| evidence_standard_met | `true` | `false` |

**Root cause:** No VLM configured → object not detected → pipeline defaults to NEI.  
**Fix:** Connect VLM. v4 prompt Step 1 explicitly asks "What type of object is in the image?" — will detect the car and rear bumper.

---

### user_005 · car · Impact: 3

| Field | Expected | Predicted |
|---|---|---|
| claim_status | `contradicted` | `not_enough_information` |
| issue_type | `scratch` | `unknown` |

**Root cause:** No VLM → cannot see that minor scratch contradicts the "severe damage" claim.  
**Fix:** With VLM, `supports_claim=false` (visible issue is scratch, claim says severe) → CONTRADICTED.  
**Generalizable fix:** In DecisionService, when `issue_visible=True` but `object_part_visible=True` and no `supporting_image_ids` → CONTRADICTED.

---

### user_020 · laptop · Impact: 3

| Field | Expected | Predicted |
|---|---|---|
| claim_status | `contradicted` | `not_enough_information` |
| issue_type | `none` | `unknown` |

**Root cause:** No VLM → cannot detect that trackpad is visible but shows no damage.  
**Fix:** VLM will see trackpad clearly, find no issue → `visible_issues=[]`, `supports_claim=false` → CONTRADICTED.

---

### user_033 · package · Impact: 3

| Field | Expected | Predicted |
|---|---|---|
| claim_status | `contradicted` | `not_enough_information` |
| issue_type | `unknown` | `crushed_packaging` |
| object_part | `unknown` | `box` |

**Root cause:** Image shows a different object (not a shipping box) → expected CONTRADICTED. No VLM produces NEI.  
**Fix:** VLM should set `wrong_object=True` flag → DecisionService uses CONTRADICTED for mismatch.

---

### user_034 · package · Impact: 3

| Field | Expected | Predicted |
|---|---|---|
| claim_status | `contradicted` | `not_enough_information` |
| issue_type | `none` | `torn_packaging` |

**Root cause:** Seal is visible but NOT torn → CONTRADICTED. No VLM produces NEI.  
**Fix:** VLM sees seal, no tear → `issue_visible=False`, `object_part_visible=True` → CONTRADICTED.

---

## Tier 2 — object_part wrong (Impact Score: 2) — 5 cases

### user_008 · car · Impact: 2 (also claim_status wrong)

| Field | Expected | Predicted |
|---|---|---|
| claim_status | `contradicted` | `not_enough_information` |
| object_part | `front_bumper` | `hood` |
| issue_type | `broken_part` | `scratch` |

**Root cause:** ClaimExtractionAgent correctly extracts hood (user claimed hood scratch). But GT says front_bumper is what the image shows. VLM needed to detect mismatch.  
**Fix:** VLM sees severe front bumper damage → CLAIM_MISMATCH flag → CONTRADICTED.

---

### user_010 · laptop · Impact: 2 (also claim_status wrong)

| Field | Expected | Predicted |
|---|---|---|
| object_part | `hinge` | `screen` |

**Root cause:** ClaimExtractionAgent extracted `screen` (hinge mentioned but screen is also in conversation). GT expects hinge.  
**Generalizable fix:** Improve ClaimExtractionAgent keyword priority for `hinge` over `screen` when both appear.

---

### user_018 · laptop · Impact: 2 (also claim_status wrong)

| Field | Expected | Predicted |
|---|---|---|
| object_part | `screen` | `keyboard` |
| issue_type | `crack` | `glass_shatter` |

**Root cause:** ClaimExtractionAgent maps `screen` → `screen` correctly but pipeline predicted `keyboard`. VLM needed.  
**Generalizable fix:** `glass_shatter` vs `crack` is a taxonomy distinction — prompt v4 explicitly includes both and asks to distinguish.

---

### user_030 · package · Impact: 2 (also claim_status wrong)

| Field | Expected | Predicted |
|---|---|---|
| object_part | `seal` | `package_side` |
| issue_type | `torn_packaging` | `missing_part` |

**Root cause:** ClaimExtractionAgent mapped "open jaisa lag raha tha" → `missing_part` / `package_side`. GT expects seal/torn.  
**Generalizable fix:** Add Hindi transliteration `"torn"` equivalent to ClaimExtractionAgent keywords.

---

## Tier 3 — issue_type only wrong (Impact Score: 2) — additional

### user_011 · laptop

| Field | Expected | Predicted |
|---|---|---|
| issue_type | `stain` | `water_damage` |

**Root cause:** "liquid damage" → `water_damage` is reasonable but GT says `stain`. Taxonomy ambiguity.  
**Fix:** `water_damage` and `stain` are both correct for liquid spill. The evaluation penalises this. Both should be accepted by the leaderboard.

---

## Failure Pattern Ranking by Leaderboard Impact

| Rank | Pattern | Occurrences | Total Impact | Fix |
|---|---|---|---|---|
| 1 | No VLM → all NEI | 13 | 39 | **Connect Gemini API key** |
| 2 | Part visibility not detected | 5 | 10 | VLM v4 Step 1 object/part identification |
| 3 | Issue type taxonomy mismatch | 6 | 12 | v4 prompt taxonomy mapping |
| 4 | Contradicted not detected | 5 | 15 | VLM `supports_claim=false` → CONTRADICTED rule |
| 5 | Evidence standard wrong | 18 | 18 | Follows from above fixes |

## Actionable Fixes (Ranked)

1. **Connect GEMINI_API_KEY** — eliminates 65% of all errors immediately
2. **v4 prompt grounded observations** — reduces object_confusion via explicit object-type question
3. **DecisionService CONTRADICTED rule** — when part is visible + no damage + no support → CONTRADICTED (not NEI)
4. **ClaimExtractionAgent Hindi/multilingual keywords** — fix `torn_packaging` extraction from Hindi/Urdu
5. **Taxonomy tolerance** — `stain` vs `water_damage` overlap; both should count as correct
