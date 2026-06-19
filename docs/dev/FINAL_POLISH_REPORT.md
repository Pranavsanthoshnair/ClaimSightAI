# Final Polish Report — ClaimSight AI

**Date:** 2026-06-19
**Target:** `code/demo/app.py` (1315 lines)
**Assessment:** UX, visual design, interaction flow, judge impression

---

## 1. Inline Success State Design

After a pipeline completes (`app.py:826-835`), a **success card** (`app.py:412-426`, CSS class `.cs-success-card`) renders inline on the Claim Review tab:

- **Verdict icon** (✓ / ✗ / ~) and **status label** ("Claim Verified" / "Claim Contradicted" / "Insufficient Evidence") — color-coded green/red/amber.
- **Three metrics** in a `.cs-success-metrics` flex row:
  - **Confidence** (e.g., "95%")
  - **Provider** (e.g., "gemini/gemini-2.5-flash")
  - **Latency** (e.g., "3200ms")
- Green gradient border background via `.cs-success-card` (`app.py:240-252`).

**Design strengths:**
- Info-dense but scannable — the metric row satisfies the judge's immediate questions: "What was the verdict? How sure? How fast? What model?"
- The inline placement means the user sees results without navigating away from the input form, reducing cognitive friction.

**Potential improvement:** The `success_card_html()` function inlines color values as comma-separated RGB tuples (line 417) — brittle string formatting. A `style` dict lookup would be cleaner.

---

## 2. CTA Buttons and User Flow

After the success card, two CTAs appear (`app.py:838-847`):

| Button | Text | Style | Action |
|---|---|---|---|
| Primary | "◈ View Results →" | `type="primary"` (purple gradient) | Sets `_focus_results = True`, calls `st.rerun()` |
| Secondary | "◉ View Decision Trace →" | Default button | Sets `_focus_trace = True`, calls `st.rerun()` |

**Flow:** Submit → progress animation → inline success card → CTAs → click → tab auto-switch.

**Tab focus management:**
- `_focus_results` and `_focus_trace` are consumed at the start of each tab block (`app.py:869-871`, `app.py:996-998`) and reset to `False` after one rerun.
- Tab auto-switch is a well-known Streamlit pattern. It works because `st.tabs()` reads session state each rerun, and the user's click triggers a rerun before the tab rendering code evaluates.
- **Risks:** If the user manually switches tabs before the CTA rerun completes, the focus flag may be consumed by the wrong tab. In practice, `st.rerun()` is fast enough that this race is unlikely.

**Toast feedback:** Both the inline success card and tab switches fire `st.toast()` (`app.py:836`, `app.py:871`, `app.py:998`), providing lightweight non-blocking confirmation.

---

## 3. Professional Error Cards vs Raw Tracebacks

### Current Design

Every error path renders via `error_card_html()` (`app.py:429-435`), producing:

```html
<div class="cs-error-card">
  <div class="cs-error-icon">⚠️</div>
  <div class="cs-error-title">Pipeline Error</div>
  <div class="cs-error-detail">An error occurred during analysis: ...</div>
</div>
```

Styling: `rgba(239,68,68,0.06)` background, red border (`rgba(239,68,68,0.3)`), red title, muted detail text (`app.py:255-261`).

### Error Classification

| Card Type | User-Facing Message | Raw Traceback Exposed? |
|---|---|---|
| Dataset Error | "A required data file could not be found..." | No — path redacted |
| Missing Dependency | "Run: pip install -r requirements.txt" | No — package name only |
| Provider Auth Error | "Please check your API key configuration." | No — key never logged |
| Image Processing Error | Specific error message passed through | Partial — err_msg shown |
| Pipeline Error | Truncated to 200 chars | Partial — generic |
| Unexpected Error | Type name only | No — message omitted |

**This is professional-grade.** No raw Python tracebacks reach the user. Error messages are actionable. The `[:200]` truncation on the pipeline error card (`app.py:860`) prevents message overflow.

**Gap:** The decision to pass through certain error messages verbatim (image processing errors) risks exposing filesystem paths on some platforms.

---

## 4. Demo Mode UX

Gated by `DEMO_MODE=true` environment variable (`app.py:657`).

### Three One-Click Scenarios (`app.py:783-792`)

| Scenario | Object | Part | Expected Verdict |
|---|---|---|---|
| Rear bumper dent | car | rear_bumper | supported |
| Front bumper crack | car | front_bumper | contradicted |
| Laptop screen damage | laptop | screen | not_enough_information |

### UX Flow

1. User clicks a scenario button → `_demo_claim` + `_demo_object` set → `st.rerun()`
2. On rerun, `_demo_claim` is detected → loaded into `user_claim` + `claim_object` selectbox → `_demo_claim` cleared → `analyze_demo = True`.
3. Pipeline runs automatically with no additional button click.

**Strengths:**
- Zero-click analysis after preset selection.
- The selectbox visibly updates to match the scenario's `claim_object`, creating a clear cause-and-effect.
- The `.cs-demo-grid` CSS (line 264) renders three equal-width cards with icons, labels, and sub-labels.

**Weaknesses:**
- No image files are auto-loaded for demo scenarios — they run without images, which means the vision stage defaults to "no images uploaded" (`app.py:518-522`). The demo scenarios' verdicts are determined entirely by the rule engine, not by actual VLM analysis. This is acceptable for a demo but should be clearly documented.
- No "reset" button to clear state and start fresh.

### Debug Tab (DEMO_MODE only, `app.py:1124-1315`)

A full 4th tab exposing:
- Stage-by-stage expanders (Claim Extraction, Vision Review, Evidence Standards, Decision Service)
- Input/output dumps for each stage
- **Root Cause Analysis** at the bottom (`app.py:1284-1315`) — an auto-generated list of detected issues (NO_MODEL_CONFIGURED, FALSE_MULTI_PART, OBJECT_INVISIBLE_DESPITE_VALID_IMAGE, EVIDENCE_NOT_MET)
- Color-coded chips for every boolean flag (green=True, red=False)

**This is a judge-pleaser.** The Debug tab transforms the app from a black-box demo into an auditable, transparent system. The Root Cause Analysis section specifically helps judges understand why a particular verdict was reached.

---

## 5. Loading / Progress Animations

Two-phase progress:

### Phase 1: Animated Pipeline (`show_progress()`, `app.py:583-600`)
- 5 stages, each with icon, title, detail, and `st.progress(pct)` indicator.
- 0.5s per stage → ~2.5s total.
- Gradient progress bar via CSS (`app.py:280-282`).
- Rendered into a placeholder that is `.empty()`'d before Phase 2.

### Phase 2: Streamlit Spinner (`app.py:820`)
- `st.spinner("")` with empty label wraps the actual `run_pipeline()` call.
- Default Streamlit infinite spinner with purple dots.

**Reliability:** The progress animation completes even if the pipeline crashes during Phase 2, since `show_progress()` runs synchronously before the spinner block.

**UX note:** The empty spinner label (`st.spinner("")`) is intentional — it avoids text duplication with the progress animation. However, Streamlit renders a minimal spinner even with an empty label, which is clean.

---

## 6. Session State Persistence

| Scenario | Behavior |
|---|---|
| Tab switch | Result persists — `st.session_state["result"]` is preserved across tab rerenders |
| Rerun analysis | Old result overwritten — no warning, no undo |
| Page refresh (browser) | **Result lost** — Streamlit resets memory state; user must re-upload images and re-enter claim |
| Demo scenario click | Previous result overwritten immediately |

**Strengths:** Tab persistence works perfectly. The empty-state cards on Results (`app.py:874-880`) and Trace (`app.py:1001-1007`) provide clear guidance when no result exists.

**Weakness:** No `st.query_params` or `st.experimental_dialog` for confirming before overwriting a previous result. Acceptable for a demo.

---

## 7. Tab Focus Management

| Action | Tab Switched To | Mechanism |
|---|---|---|
| "Analyse →" button | Stays on Claim Review (inline success shown) | No tab switch |
| "◈ View Results →" CTA | Results tab | `_focus_results = True` + `st.rerun()` |
| "◉ View Decision Trace →" CTA | Decision Trace tab | `_focus_trace = True` + `st.rerun()` |
| Demo preset click | Stays on Claim Review (auto-analysis) | Session state + `st.rerun()` |

The focus flags use a **consume-once** pattern:
```python
# app.py:869-871
if st.session_state.get("_focus_results"):
    st.session_state["_focus_results"] = False
    st.toast("✓ Results ready", icon="◈")
```

This is a standard Streamlit pattern and works reliably across all tested scenarios.

---

## 8. Streamlit Limitations and Workarounds

| Limitation | Workaround in App | Line(s) |
|---|---|---|
| No native tab focus change | Session state flag (`_focus_results`, `_focus_trace`) + `st.rerun()` | 649-653, 841-847 |
| No dark theme by default | 243 lines of custom CSS with `!important` overrides | 91-334 |
| Secrets only available in Cloud | `_inject_secrets()` with `.env` fallback via `load_dotenv()` | 29-52 |
| No built-in toast on Cloud < 1.36 | Uses `st.toast()` — requires Streamlit ≥1.36 | 836 |
| `st.progress()` resets on rerun | Single-shot `show_progress()` with placeholder swap | 583-600 |
| No multi-page state sharing | Single-page app with tabs approach (no `st.Page` usage) | 659-667 |
| `st.cache_data` does not persist across sessions | `ttl=3600` on `_cached_claim_extraction` | 440-441 |
| No async support in core loop | Synchronous `time.sleep(0.5)` in progress; acceptable for ≤3s | 600 |
| File uploader resets on rerun | `f.seek(0)` before each thumbnail render | 691, 693 |

**Grade:** The app works effectively _within_ Streamlit's constraints rather than fighting them. The tab-focus hack and custom CSS are idiomatic Streamlit patterns, not anti-patterns.

---

## 9. Judge-Impression Analysis

### What the judge sees in the first 30 seconds:

1. **Dark, polished UI** — gradient hero text, indigo accent color, consistent card system. No Streamlit chrome (MainMenu, footer, header hidden).
2. **Preflight mode badge** (or provider-connected badge) in the top-right — immediate transparency about configuration state.
3. **Clear pipeline visualization** in the right sidebar — 4-step process with numbered icons and connector lines.
4. **One-click demo scenarios** (if `DEMO_MODE=true`) — immediately actionable with zero setup.

### What the judge sees after running analysis:

5. **Animated progress** — 5-stage sequence with gradient progress bar and stage descriptions.
6. **Inline success card** — verdict, confidence, provider, latency at a glance.
7. **Two CTAs** — clear navigation to detailed results and decision trace.
8. **Results tab** — KPI grid with 7 metrics (Claim Status, Issue Type, Object Part, Severity, Evidence Std., Confidence, Latency), evidence assessment, risk flags as colored chips, image evidence cards with supporting/not-supporting badges.
9. **Decision Trace tab** — 4-stage pipeline execution diagram, 4 expandable stage detail panels showing exact inputs and outputs.
10. **Debug tab** (DEMO_MODE) — stage-by-stage inspection with Root Cause Analysis section that auto-diagnoses logic issues.

### Differentiators:

- **No raw tracebacks anywhere.** Every error has a styled card with an actionable message.
- **KPI cards** with colored top-borders and gradient accents give an immediate visual hierarchy.
- **Risk flags** are rendered as colored chips (red=danger, amber=warning, slate=info) with human-readable labels.
- **Decision Trace** provides full observability, not just a verdict. Judges can see exactly which rule fired and why.
- **Footer** ("Powered by Gemini 2.5 Flash · OpenRouter fallback · Pydantic schemas") signals the tech stack professionally.
- The app works **without** any API key in preflight mode — judges can evaluate the full UX even if the VLM is not configured.

### What would impress a judge most:

1. The Debug tab's Root Cause Analysis (`app.py:1284-1315`) — auto-generates actionable diagnostics like "FALSE_MULTI_PART: is_multi_part=True with no secondary parts." This shows deep understanding of the pipeline logic.
2. The 3-tier model fallback mentioned in capabilities (`chip("3-tier fallback", "green")` at line 762) — signals production-grade architecture even if only one tier is configured.
3. The evidence standards engine's per-requirement breakdown in the Decision Trace — shows the rule-based sufficiency system, proving the system is not just an LLM wrapper.

---

## 10. Overall Polish Score

| Category | Score | Notes |
|---|---|---|
| Visual Design | 92/100 | Dark theme, gradient accents, card system, responsive grid. Gradients may clip in Firefox. |
| Interaction Flow | 88/100 | Inline success + CTA buttons + tab auto-switch is fluid. No undo/revert for previous result. |
| Error UX | 90/100 | 6 styled error card types, no tracebacks, actionable messages. Truncation could hide details. |
| Demo Mode UX | 85/100 | 3 one-click scenarios; no auto-loaded images for presets reduces faithfulness. Debug tab is excellent. |
| Progress Feedback | 82/100 | Animated pipeline is lovely; synchronous sleep blocks event loop. |
| Tab Navigation | 90/100 | Focus-flag pattern works reliably. Rare race if user manually switches during `st.rerun()`. |
| Judge Appeal | 95/100 | Debug tab + Root Cause Analysis + preflight fallback are strong differentiators. |
| Code Polish | 88/100 | Well-organized with section markers, consistent helper functions, proper path bootstrap. Inline color string formatting in `success_card_html()` is fragile. |

### Overall Score: **89 / 100**

### Remaining Work (Pre-Submission)

**High priority:**
1. Add image size validation before VLM call (currently no check for >10MB files).
2. Verify Streamlit version compatibility (`st.toast()` requires ≥1.36; `st.tabs()` ≥1.30). Pin in `requirements.txt`.

**Medium priority:**
3. Add a "Clear Results" button or confirmation dialog before overwriting previous session result.
4. Replace inline color string formatting in `success_card_html()` (line 417) with a structured `style` parameter.

**Low priority / Nice to have:**
5. Load actual demo images from `dataset/images/sample/` for each scenario preset so the vision stage has real input.
6. Add a `time_remaining` display (from problem_statement.md) so the judge knows the time context.
7. Print version info in the footer or Debug tab for reproducibility.

**Recommendation:** The app is submission-ready. Focus any remaining effort on (1) image validation and (2) Streamlit version pinning. The preflight fallback ensures the app is demonstrable even without API keys.
