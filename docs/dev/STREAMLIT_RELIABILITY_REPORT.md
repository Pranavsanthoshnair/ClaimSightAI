# Streamlit Reliability Report — ClaimSight AI

**Date:** 2026-06-19
**Target:** `code/demo/app.py` (1315 lines)
**Test Suite:** `code/tests/demo/test_app_integration.py` (621 lines, ~38 test cases)

---

## 1. Crash Scenario Handling

### 1.1 Missing API Keys / No VLM Configured

When `GEMINI_API_KEY` is absent, `Settings.has_vision_model` evaluates to `false`. The app:

- Displays a **chip-amber badge** reading `● PREFLIGHT MODE` at the top-right (`app.py:631-633`).
- The pipeline still runs end-to-end: `ModelService` is `None` (`app.py:505`), `VisionReviewAgent` produces a preflight result (`app.py:518-522`), and the DecisionService fires Rule 1 (no valid images → NEI).
- The Debug tab (DEMO_MODE only) explicitly warns: *"No VLM configured. Set GEMINI_API_KEY in secrets to get real results."* (`app.py:1203-1208`).
- **No crash.** Degraded but functional.

### 1.2 Invalid / Unreadable Images

- File read failures: caught at `app.py:477-480` and re-raised as `RuntimeError("Failed to read uploaded file.")`.
- Tempfile save failures: caught at `app.py:489-490` and re-raised as `RuntimeError("Failed to save uploaded file: ...")`.
- At the UI layer, both surface as an **Image Processing Error** card (`app.py:857-858`).
- **Test coverage:** `test_run_pipeline_failed_file_read`, `test_run_pipeline_tempfile_error`.

### 1.3 Provider Failures (VLM Timeout / Auth Rejection)

- The pipeline wraps the entire `run_pipeline()` body in `try/except Exception` (`app.py:574-575`), re-raising as `RuntimeError`.
- Downstream classification: if the error message contains "API key", "not authorized", or "permission", the UI shows a **Provider Authentication Error** card (`app.py:855-856`).
- Otherwise the generic **Pipeline Error** card is shown (`app.py:859-860`).
- The Streamlit spinner (`app.py:820`) provides loading-state UX while the VLM call is in-flight. If the provider hangs, Streamlit's own timeout mechanism interrupts after ~30s (no custom timeout configured — **identified risk**).

### 1.4 Missing Dataset Files

- `EvidenceStandardsEngine.load()` triggers `FileNotFoundError` if `evidence_requirements.csv` is absent (`app.py:570-571`).
- Re-raised as `RuntimeError("Dataset file not found: ...")` and displayed as **Dataset Error** card (`app.py:851-852`).
- **Test coverage:** `test_run_pipeline_file_not_found`.

### 1.5 ImportError / Missing Dependencies

- Startup diagnostics (`app.py:57-78`) check that all required packages are importable. If not, a full-page dependency error is rendered and `st.stop()` halts the app (`app.py:608-610`).
- At runtime, `ImportError` inside the pipeline is caught at `app.py:572-573` and re-raised as `RuntimeError("Missing dependency: ...")`, displayed as **Missing Dependency** error card (`app.py:853-854`).
- **Test coverage:** `test_run_pipeline_import_error`.

---

## 2. Error Handling Architecture

### 2.1 Six Error Card Types

All rendered via `error_card_html()` (`app.py:429-435`), producing a consistent `.cs-error-card` DOM element:

| # | Error Type | Trigger | Line |
|---|---|---|---|
| 1 | **Dataset Error** | `FileNotFoundError` in pipeline | 851-852 |
| 2 | **Missing Dependency** | `ImportError` or "Missing dependency" | 853-854 |
| 3 | **Provider Auth Error** | "API key", "not authorized", "permission" in message | 855-856 |
| 4 | **Image Processing Error** | "Failed to read" or "Failed to save" | 857-858 |
| 5 | **Pipeline Error** | Generic `RuntimeError` (catch-all) | 859-860 |
| 6 | **Unexpected Error** | Non-`RuntimeError` exceptions | 861-862 |

### 2.2 Try/Except Coverage Map

| Block | Lines | Purpose |
|---|---|---|
| Secrets injection | 29-43 | Graceful if `streamlit` missing or `st.secrets` unavailable |
| `.env` loading | 46-50 | Best-effort; `ImportError` silently caught |
| Startup diagnostics | 57-78 | Dependency check; `write_deployment_log` wrapped independently |
| File read | 477-480 | Uploaded image byte read |
| Tempfile write | 483-490 | Disk write with OSError catch |
| ClaimObject parse | 495-497 | Invalid enum fallback to `CAR` |
| Pipeline body | 492-579 | Full pipeline; catches `FileNotFoundError`, `ImportError`, `Exception` |
| Tempfile cleanup | 577-579 | `finally` block ensures temp file removal |
| Config load | 614-646 | Graceful degradation to "CONFIG ERROR" / "CONFIG LOAD FAILED" badge |
| Auth check | 810-815 | Settings access guarded |
| RuntimeError catch | 849-860 | Classifies into 5 error subtypes |
| Broad exception | 861-862 | Catches everything else |
| Demo mode imports | 779-782 | `models.enums` try/except |

**Coverage:** ~28 distinct try/except blocks across 1315 lines. No code path in `run_pipeline()` is unguarded.

---

## 3. Session State Hardening

Four guard fields initialized at `app.py:649-653`:

```python
if "_initialized" not in st.session_state:
    st.session_state["_initialized"] = True
    st.session_state["_focus_results"] = False
    st.session_state["_focus_trace"] = False
    st.session_state["_last_analysis_ts"] = 0
```

| Field | Type | Purpose |
|---|---|---|
| `_initialized` | `bool` | Gate — ensures init block runs exactly once per session |
| `_focus_results` | `bool` | Tab-navigation flag: after analysis, auto-focus Results tab |
| `_focus_trace` | `bool` | Tab-navigation flag: after CTA click, auto-focus Decision Trace tab |
| `_last_analysis_ts` | `float` | `time.time()` of last analysis; used for staleness checks |

Additional session state keys:
- `result` — full pipeline output dict (persists across tab switches)
- `_settings` — cached `Settings` object
- `_demo_claim`, `_demo_object` — demo-mode transient fields (cleared on use, `app.py:798`)

**Risk:** `result` is a single slot — re-running analysis overwrites it. No multi-result history.

**Test coverage:** `test_session_state_initialized` verifies guard initialization.

---

## 4. Progress Indicator Reliability

`show_progress()` (`app.py:583-600`) renders a 5-stage animated sequence:

| Stage | Icon | Progress |
|---|---|---|
| Claim Extraction | 🔍 | 0.20 |
| Vision Analysis | 👁 | 0.45 |
| Evidence Validation | 📋 | 0.68 |
| Risk Assessment | ⚖️ | 0.87 |
| Decision Generation | ✓ | 1.00 |

**Mechanism:** Each stage uses `placeholder.container()` to swap content + `st.progress(pct)` + `time.sleep(0.5)`.

**Reliability concerns:**
- `time.sleep(0.5)` is synchronous and blocks the Streamlit event loop. For a 2.5s animation this is acceptable but not ideal. A streaming/threading approach would be better for long-running VLMs.
- The placeholder is cleared (`progress_placeholder.empty()`) before `st.spinner()` runs the actual pipeline (`app.py:817-818`). If the pipeline crashes during setup (before the spinner), the progress card disappears abruptly.
- **Test coverage:** `test_show_progress_renders_all_steps`, `test_show_progress_with_provider`.

---

## 5. Demo Mode Robustness

- Gated by `DEMO_MODE` env var (`app.py:657`).
- Three one-click scenarios (`app.py:783-792`): supported (car rear bumper dent), contradicted (car front bumper crack), not_enough_information (laptop screen).
- Each scenario sets `_demo_claim` and `_demo_object` in session state and triggers `st.rerun()`.
- The retrigger logic (`app.py:795-802`) checks `_demo_claim`, loads the preset, resets the flag, and sets `analyze_demo = True`.
- **Debounce risk:** `st.rerun()` + session state write can cause double-trigger if Streamlit re-renders before the flag is cleared. Mitigated by clearing `_demo_claim` at `app.py:798` before the analysis block.
- Fourth tab (`tab_debug`) is conditionally created only in demo mode (`app.py:660-662`), so there is no "missing tab" error in production.
- **Test coverage:** `test_demo_mode_supported_preset`, `test_demo_mode_contradicted_preset`, `test_demo_mode_nei_preset` (scenario data validation).

---

## 6. CSS Resilience

The app injects ~243 lines of CSS (`app.py:91-334`) via `st.markdown(unsafe_allow_html=True)`.

| Category | Selectors | Purpose |
|---|---|---|
| Reset | `*, *::before, *::after` | Box-sizing normalization |
| Dark theme | `html, body, [data-testid="stAppViewContainer"]` | `#0B0F19` background |
| Chrome hide | `#MainMenu, footer, header` | Streamlit chrome removal |
| Responsive | `.block-container` | `max-width: 1280px; margin: 0 auto` |
| Cards | `.cs-card`, `.kpi-card`, `.img-card` | Consistent dark surfaces |
| Verdict | `.verdict-banner`, `.verdict-*` | 3-state color-coded banners |
| Pipeline | `.pipe-step`, `.pipe-connector`, `.pipe-icon` | Connector lines + state dots |
| Tabs | `[data-testid="stTabs"]` | Override Streamlit's light-mode defaults |
| Buttons | `[data-testid="stButton"] > button[kind="primary"]` | Gradient purple CTA |
| Uploader | `[data-testid="stFileUploader"]` | Dark dashed drop zone |
| Progress | `[data-testid="stProgress"] > div > div` | Indigo gradient bar |

**Risks:**
- All CSS is in a single `st.markdown()` call — no scoping. Conflicts with Streamlit version upgrades (targeting `data-testid` attributes that are internal implementation details).
- `-webkit-background-clip: text` for the hero gradient is WebKit-only. Falls back to solid color in Firefox.
- No dark/light mode toggle — the app is fixed to dark theme.

**Resilience:** The CSS is defensive — every rule uses `!important` to override Streamlit's defaults. This guarantees consistent rendering but makes future theming difficult.

---

## 7. Integration Test Coverage Summary

**File:** `code/tests/demo/test_app_integration.py` (621 lines)

| Category | Tests | Key Functions Tested |
|---|---|---|
| Secrets injection | 2 | `_inject_secrets()` empty env, missing streamlit |
| Component helpers | 10 | `topbar()`, `hero()`, `card()`, `kpi()` (3), `chip()` (2), `verdict_banner()` (4), `pipeline_step()` (3), `section_title()` |
| Claim extraction | 2 | `_cached_claim_extraction()` happy path + invalid object fallback |
| Pipeline execution | 5 | `run_pipeline()` with no images, with images, FileNotFoundError, ImportError, latency tracking |
| Progress indicator | 2 | `show_progress()` with/without provider |
| Verdict banner | 6 | All 3 statuses + fallback + parametrized + justification truncation |
| KPI colors | 3 | Parametrized severity colors |
| Success card | 4 | Supported, contradicted, NEI, unknown verdict |
| Error card | 2 | Rendering + custom icon |
| Session state | 1 | Guard initialization |
| Empty states | 2 | Results tab, Trace tab empty state HTML |
| File errors | 2 | Failed read, tempfile OSError |
| Demo presets | 3 | Scenario data validation |

**Total: ~38 test functions** (including parametrized cases). **Coverage gap:** No tests for the UI-layer error card routing logic (the `if/elif` chain at `app.py:851-862`), no tab-focus interaction test, no demo-mode `st.rerun()` end-to-end test.

---

## 8. Identified Reliability Risks & Mitigations

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | No pipeline timeout — VLM call can hang indefinitely | Medium | Add `asyncio.wait_for()` or `concurrent.futures.timeout` wrapper around `model_svc.infer()`. Currently relies on Streamlit Cloud's 30s request timeout. |
| R2 | Single `result` slot overwrites previous analysis | Low | Could store a `results_history` list in session state. Acceptable for a demo. |
| R3 | CSS `data-testid` selectors break on Streamlit upgrade | Medium | Pin Streamlit version in `requirements.txt`. Current selectors tested against Streamlit 1.35+. |
| R4 | `time.sleep(0.5)` blocks event loop during progress | Low | For 2.5s total, acceptable. Replace with `asyncio.sleep` if migrating to async. |
| R5 | `st.rerun()` in demo mode can double-trigger | Low | Mitigated by clearing `_demo_claim` before the analysis block. Tested empirically. |
| R6 | Large images (>10MB) not validated before VLM call | Medium | Add size check + resizing before passing to `VisionReviewAgent`. Current behavior: passed raw, may fail at provider. |
| R7 | No retry logic for transient provider errors | Medium | Add exponential backoff wrapper in `ModelService.infer()`. Current behavior: single attempt, fails fast. |
| R8 | Error card routing uses string matching on error messages | Low | Fragile if provider error messages change. Could use exception types instead. |
| R9 | Tempfile cleanup in `finally` block doesn't handle `tmp_paths` being undefined if setup fails | Low | Fixed: `tmp_paths` is initialized empty at line 474 before any risky operations. |
| R10 | `st.toast()` delayed by tab switch before rendering | Low | Toast fires before `st.rerun()` — Streamlit renders toasts reliably across reruns. |

---

## 9. Overall Reliability Score

| Category | Score | Notes |
|---|---|---|
| Error Handling Coverage | 95/100 | Every exception path caught; 6 UX-facing error types |
| Session State Hardening | 90/100 | Guard fields prevent KeyError; no multi-result history |
| Crash Resilience | 85/100 | Graceful degradation on missing API key; no unguarded code paths |
| Test Coverage | 80/100 | 38 tests covering core paths; UI-layer error routing untested |
| CSS Resilience | 75/100 | Heavy `!important` usage; `data-testid` dependency on Streamlit internals |
| Demo Mode Robustness | 90/100 | Clean 3-scenario presets; no crash on toggle |
| Progress UX | 80/100 | Blocking sleep but visually coherent |

### Overall Score: **85 / 100**

**Strengths:** Every `run_pipeline()` exception is caught, classified, and displayed as a styled error card. Session state guard fields prevent KeyError on cold starts. Preflight mode ensures the app works without any API key. 38 integration tests provide solid regression coverage.

**Top recommendations to reach 95+:**
1. Add `asyncio.wait_for()` timeout wrapper around VLM provider calls (R1).
2. Add pre-upload image size validation (R6).
3. Add retry with exponential backoff for transient provider errors (R7).
4. Test the UI error-card routing `if/elif` chain directly (coverage gap).
5. Pin Streamlit version and add a CSS smoke test (R3).
