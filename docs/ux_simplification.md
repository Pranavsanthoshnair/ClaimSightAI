# UX Simplification Report

**ClaimSight AI — v1.0 UX Simplification**
Generated: 2026-06-20

---

## Objective

Transform ClaimSight AI from an engineering dashboard into a product-grade
interface understandable by a non-technical judge within 30 seconds, while
preserving full observability for engineers via a Debug Mode toggle.

---

## Terminology Changes

### Decision Status Labels

| Before (technical) | After (user-facing) |
|--------------------|---------------------|
| `supported` | **Claim Verified** |
| `contradicted` | **Claim Does Not Match Evidence** |
| `not_enough_information` | **More Evidence Needed** |

### Evidence Sufficiency Labels

| Before | After |
|--------|-------|
| `fully_met` | **Evidence Verified** |
| `partially_met` | **Evidence Incomplete** |
| `not_met` | **Evidence Missing** |
| `unverifiable` | **Unable to Verify** |

### Pipeline Stage Names

| Before | After |
|--------|-------|
| Claim Extraction | **Understanding the Claim** |
| Vision Review | **Image Analysis** |
| Evidence Standards | **Evidence Verification** |
| Decision Engine | **Final Decision** |

### Results Page KPI Labels

| Before | After |
|--------|-------|
| Claim Status | **Decision** |
| Issue Type | **Damage Found** |
| Object Part | **Location** |
| Evidence Std. | **Evidence Status** |

### Stage Detail Language

| Before | After |
|--------|-------|
| `Object visible: True` | ✅ Vehicle / item detected: Yes |
| `Part visible: True` | ✅ Affected area identified: Yes |
| `Issue visible: True` | ✅ Damage detected: Yes |
| `Best issue: dent` | Damage type found: Dent |
| `Best part: rear_bumper` | Area found: Rear Bumper |
| `EVIDENCE STANDARD` card | EVIDENCE STATUS card |
| `● MET` chip | `● Verified` chip |
| `● NOT MET` chip | `● Not Verified` chip |
| `RISK FLAGS` card | QUALITY SIGNALS card |

### Image Evidence

| Before | After |
|--------|-------|
| `tmp2m1_e9g_` | **Image #1** |
| `tmp4k9_abc_` | **Image #2** |
| `✓ Supporting` badge | **✓ Supports Claim** badge |
| `Not primary` badge | **Does Not Support** badge |

### Provider / Model Visibility

| Before | After |
|--------|-------|
| `openrouter/llama-3.2-11b...` (shown in KPI) | Removed from user view |
| `Powered by OpenRouter (Qwen2.5-VL...)` (footer) | **AI Vision Analysis** |
| Model name in success card | `AI Model: Active ✓` |

---

## Natural Language Explanations

Replaced raw justification strings with human-friendly explanations:

**Claim Verified:**
> "The uploaded images clearly show damage that matches the reported claim.
> The affected area was identified and the damage type confirmed."

**Claim Does Not Match Evidence:**
> "The images do not show the damage described in the claim.
> The affected area was visible, but the reported damage was not found."

**More Evidence Needed:**
> "The submitted evidence is insufficient to confirm or deny the reported damage.
> Additional photos or clearer images may be required."

---

## Debug Mode

A **🔬 Debug Mode** toggle was added to the sidebar (bottom of the model panel).

### Hidden by default (shown in Debug Mode only):
- Multi-part claim flag
- Injection detected flag
- REQ_* requirement IDs
- Supporting image IDs (raw temp filenames)
- Raw confidence percentages
- Provider/model names
- Raw risk flag names (show friendly labels by default)
- Internal justification text
- Per-image quality flags and raw confidence scores
- Internal claim status enum value

### Always visible (even without Debug Mode):
- Decision verdict (user-friendly label)
- Damage type and location
- Evidence status (friendly label)
- Quality signals (friendly flag labels)
- Image observations (descriptions)
- Per-image support/not-support indication
- Severity
- Natural language explanation

---

## Loading Progress Steps

Replaced internal-sounding step names:

| Before | After |
|--------|-------|
| "Claim Extraction — Parsing conversation…" | "Understanding the Claim — Reading the conversation and identifying the reported damage…" |
| "Vision Analysis — Per-image VLM review via…" | "Analysing Images — AI is reviewing the submitted evidence photos…" |
| "Evidence Validation — Rule-based sufficiency…" | "Verifying Evidence — Checking if the evidence meets the required standards…" |
| "Risk Assessment — Decision rules · quality flags…" | "Assessing Risk — Reviewing image quality and claim history…" |
| "Decision Generation — Supported / Contradicted / NEI" | "Finalising Decision — Generating the claim decision…" |

---

## What Was NOT Removed

All technical details remain fully accessible via Debug Mode:
- REQ_* requirement IDs with gap descriptions
- Raw confidence calculations
- Provider and model names
- Supporting image IDs
- Per-image quality flags
- Internal claim status enums
- Raw justification text
- Injection detection results
- Multi-part claim flags

The observability pipeline (Decision Trace tab) is entirely preserved.
Debug Mode simply controls the visibility of these details.

---

## Files Modified

| File | Changes |
|------|---------|
| `code/demo/app.py` | All label changes, debug toggle, humanised IDs, natural language explanations, friendly flag labels |

---

## Remaining Considerations

- The `_humanise_image_id()` function identifies temp files by `tmp` prefix.
  Files with meaningful names (≤20 chars) keep their original names.
- The Debug Mode state persists within the Streamlit session but resets on refresh.
- Risk flag friendly labels cover all known flags; unknown flags fall back to
  `flag.replace("_", " ").title()` which is still more readable than raw enums.
