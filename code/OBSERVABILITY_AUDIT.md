# Observability & Traceability Audit

> **System:** ClaimSight AI — Multi-Modal Evidence Review Pipeline  
> **Date:** 2026-06-19  
> **Files audited:** `logging_service.py`, `claim_review_pipeline.py`, `vision_agent.py`, `model_service.py`, `decision_service.py`, `pipeline_events.jsonl`, `debug_pipeline_report.json`

---

## 1. LoggingService Implementation

**Class:** `services/logging_service.py:13` — `LoggingService`

| Property | Detail |
|---|---|
| **Log directory** | `code/logs/`, resolved from `Settings.logs_dir` via `Settings.resolve_path()` |
| **Directory creation** | `mkdir(parents=True, exist_ok=True)` at `__init__` (line 18) |
| **Write method** | `write_event(filename, payload)` at line 20 |
| **Format** | JSONL — one JSON object per line, `utf-8`, `\n` line endings |
| **Timestamp** | Prepended by service: `{"timestamp": "2026-06-19T17:21:09.038111+00:00", ...}` |
| **Append mode** | `path.open("a", ...)` — never truncates |

**Key code** (`logging_service.py:20-28`):
```python
def write_event(self, filename: str, payload: dict[str, Any]) -> None:
    event = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        **payload,
    }
    path = self.log_dir / filename
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=True) + "\n")
```

---

## 2. pipeline_events.jsonl Content Analysis

**File:** `code/logs/pipeline_events.jsonl` — 50 events logged.

### Fields per event

| Field | Type | Source | Example |
|---|---|---|---|
| `timestamp` | ISO-8601 | `LoggingService.write_event()` | `2026-06-19T17:21:09.038111+00:00` |
| `event` | string | Hardcoded in pipeline | `claim_processed` |
| `user_id` | string | `claim.user_id` | `user_002` |
| `claim_index` | int | Loop counter | `0` |
| `status` | string | `output.claim_status.value` | `not_enough_information` |
| `evidence_met` | bool | `output.evidence_standard_met` | `true` |
| `issue_type` | string | `output.issue_type.value` | `dent` |
| `object_part` | string | `output.object_part.value` | `front_bumper` |
| `severity` | string | `output.severity.value` | `medium` |
| `risk_flags` | string | `output.risk_flags` | `manual_review_required;user_history_risk` |
| `valid_image` | bool | `output.valid_image` | `true` |
| `supporting_count` | int | `len(vision_result.supporting_image_ids)` | `0` |
| `confidence` | float | `vision_result.confidence` | `0.0` |

### Event structure (from `pipeline.py:108-121`)

```python
self.logging_service.write_event("pipeline_events.jsonl", {
    "event": "claim_processed",
    "user_id": claim.user_id,
    "claim_index": i,
    "status": output.claim_status.value,
    "evidence_met": output.evidence_standard_met,
    "issue_type": output.issue_type.value,
    "object_part": output.object_part.value,
    "severity": output.severity.value,
    "risk_flags": output.risk_flags,
    "valid_image": output.valid_image,
    "supporting_count": len(vision_result.supporting_image_ids),
    "confidence": vision_result.confidence,
})
```

### Observed data quality

- All 50 events have `null`-free payloads.
- Two distinct runs visible: first run (lines 1-6) with preflight+partial VLM, second run (lines 7-50) with full batch of 44 claims.
- `risk_flags` is written as a flat string (`semicolons`), not a list — consistent with the output column format.

---

## 3. Log Coverage by Pipeline Stage

| Stage | Component | Logged in pipeline_events.jsonl | Logged via `logger.*` | Details |
|---|---|---|---|---|
| **A — Claim Extraction** | `ClaimExtractionAgent` | ✅ Status, issue_type, object_part | ❌ Not in pipeline.py logger | Extraction details logged only via the output fields |
| **B — Vision Review** | `VisionReviewAgent` | ✅ confidence, supporting_count, valid_image | ✅ `vision_agent.py:692-703` per-image INFO | Per-image readable/valid/supports_claim/issues/parts/flags/confidence logged |
| **C — Evidence Standards** | `EvidenceStandardsEngine` | ✅ evidence_met | ❌ Not logged via `logger.*` | Only the boolean passes through |
| **D — Decision** | `DecisionService` | ✅ status, severity, risk_flags | ✅ `decision_service.py:266-272` INFO | Full decision summary per claim |

### Additional debug logging in VisionReviewAgent

`vision_agent.py` contains extensive `logger.debug()` calls:

- **Line 237:** Enum coercion failures logged at DEBUG
- **Lines 269-280:** Raw VLM response fields for each image (object_present, visible_parts, visible_issues, quality_flags, supports_claim, confidence, severity)
- **Lines 305-313:** Coerced PerImageAnalysis fields after normalization
- **Lines 797:** Cache hit/miss per image
- **Lines 806-809:** Preflight-only mode notification
- **Lines 830-831:** VLM response received with key list
- **Lines 872-874:** VLM call attempt failure warnings

### Debug logging in ModelService

`model_service.py`:

- **Line 114:** Tier 1 provider initialization
- **Lines 127, 139:** Tier 2/3 provider init
- **Lines 218-233:** Tier 1 failure with latency_ms and fallback_reason
- **Lines 242-245:** Tier success with provider_used and latency_ms
- **Lines 249-252:** Tier failure per fallback
- **Lines 255:** All providers exhausted
- **Lines 316, 325:** Gemini retry attempts

---

## 4. Traceability: End-to-End Claim Tracing

**Question:** Can you trace a single claim from input → extraction → vision → evidence → decision?

### Current trace path

```
Claim CSV row
  └── claim_index (0-based loop position)
        ├── Pipeline loop iteration (pipeline.py:55)
        │     └── Logged in pipeline_events.jsonl with claim_index
        ├── ClaimExtractionAgent.extract()
        │     └── No event emitted for extraction substage
        ├── VisionReviewAgent.review()
        │     └── logger.info per image (vision_agent.py:692)
        │     └── logger.info aggregate (vision_agent.py:706)
        │     └── No pipeline_events.jsonl entry for this substage
        ├── EvidenceStandardsEngine.evaluate_from_vision()
        │     └── No logger calls (silent)
        ├── DecisionService.decide()
        │     └── logger.info final decision (decision_service.py:266)
        └── LoggingService.write_event() — single event per claim
```

### Traceability verdict

| Criterion | Status | Notes |
|---|---|---|
| Unique claim ID across all logs | ❌ | Only `claim_index` (resets per run) |
| Input captured in log | ✅ | `user_id` in pipeline_events.jsonl |
| Extraction result in log | ⚠️ Partial | Only output-level fields (issue_type, object_part) |
| Vision result in log | ✅ | confidence, supporting_count, valid_image |
| Evidence result in log | ✅ | evidence_met boolean |
| Decision in log | ✅ | status, severity, risk_flags |
| Per-image VLM response | ✅ | In `logger.debug()` statements (not in pipeline_events.jsonl) |
| Latency per stage | ❌ | Not logged anywhere |
| Provider fallback info | ⚠️ Partial | Logged via `logger.*` but not in pipeline_events.jsonl |

**There is no `trace_id` or `correlation_id`** that follows a claim across all components. The `claim_index` is positional and resets per run.

---

## 5. Missing Observability Gaps

| # | Gap | Severity | Impact |
|---|---|---|---|
| 1 | **No correlation/trace ID** | High | Cannot correlate events across services/agents for a single claim |
| 2 | **No per-stage latency logging** | High | Cannot identify slow stages in the pipeline |
| 3 | **EvidenceEngine has zero logging** | Medium | No debug visibility into requirement matching |
| 4 | **ClaimExtractionAgent has no logging** | Medium | No visibility into extraction decisions |
| 5 | **No log rotation** | Medium | Long-running runs will grow `pipeline_events.jsonl` unbounded |
| 6 | **`log_level` in Settings not consumed by LoggingService** | Low | `Settings.log_level` exists but LoggingService always writes events regardless |
| 7 | **No JSON schema for pipeline_events** | Low | Consumers must infer fields from code |
| 8 | **No structured error events** | Low | Exceptions are logged via `logger.exception` but not written to pipeline_events.jsonl |
| 9 | **`provider_used` not in pipeline_events.jsonl** | Medium | No record of which provider (Gemini/Qwen/Llama) handled each claim |
| 10 | **`model_name` not in pipeline_events.jsonl** | Low | Only logged in debug; not per-event |

---

## 6. Log Format, Rotation & Persistence

### Format
- **Primary log path:** `code/logs/pipeline_events.jsonl`
- **Format:** JSONL — one object per line, `\n` terminated
- **Encoding:** UTF-8
- **Timestamp format:** ISO-8601 with UTC timezone (`2026-06-19T17:21:09.038111+00:00`)
- **Other log files in `code/logs/`:** `debug_pipeline_report.json` (single JSON object), `.gitkeep`

### Rotation
- **None implemented.** `LoggingService` opens files in append mode (`"a"`) with no size check, no rollover, no archival.
- A full run of 44 test claims + 6 sample claims generated 50 lines (~8 KB). Not critical at hackathon scale, but would grow unbounded in production.

### Persistence
- **Storage:** Local filesystem only.
- **Durability:** Survives process restarts (append mode). Does **not** survive container/image rebuild unless volume-mounted.
- **No remote shipping:** No S3, CloudWatch, DataDog, or any log aggregator integration.

---

## 7. Debug Logging Assessment

### VisionReviewAgent (`vision_agent.py`)

| Log call | Level | Location | Value |
|---|---|---|---|
| Enum coercion failure | DEBUG | Line 237 | Logs `enum_cls.__name__` and rejected value |
| Raw VLM fields | DEBUG | Lines 269-280 | Full raw response before coercion |
| Coerced fields | DEBUG | Lines 305-313 | Normalized values after parsing |
| Cache hit | DEBUG | Line 797 | Cache key prefix |
| Per-image summary | INFO | Lines 692-703 | Readable, valid, supports_claim, issues, parts, flags, confidence |
| Preflight notification | INFO | Lines 806-809 | No model service configured |
| VLM attempt failure | WARNING | Lines 872-874 | Attempt number, image_id, exception |
| Aggregate result | INFO | Lines 706-718 | Full aggregate with visibility, issue, part, severity, confidence |

### ModelService (`model_service.py`)

| Log call | Level | Location | Value |
|---|---|---|---|
| Tier init | DEBUG | Lines 114, 127, 139 | Provider name + model |
| Tier 1 success | DEBUG | Lines 218-222 | provider_used, tier, latency_ms |
| Tier 1 failure | WARNING | Lines 226-233 | provider, latency_ms, fallback_reason |
| Tier N success | INFO | Lines 242-245 | tier, provider, latency_ms |
| Tier N failure | ERROR | Lines 249-252 | tier, provider, latency_ms, error |
| All tiers exhausted | ERROR | Line 255 | Total tier count |
| Gemini retry | WARNING | Line 316 | Attempt number, error |

### DecisionService (`decision_service.py`)

| Log call | Level | Location | Value |
|---|---|---|---|
| Final decision | INFO | Lines 266-272 | user_id, status, evidence_met, valid_image, issue_type, object_part, severity, flags |

**Debug logging verdict:** Thorough in VisionReviewAgent and ModelService. Weak in EvidenceStandardsEngine (nonexistent) and ClaimExtractionAgent (nonexistent).

---

## 8. Recommendations for Production Observability

### Immediate (low effort, high impact)
- [ ] **Add `provider_used` and `model_name` to `pipeline_events.jsonl`** — critical for cost/traceability
- [ ] **Add per-stage latency fields** to `pipeline_events.jsonl` — `extraction_ms`, `vision_ms`, `evidence_ms`, `decision_ms`
- [ ] **Add `trace_id` (UUID per claim)** to pipeline_events — generated once per claim, passed through all stages
- [ ] **Add `logger` calls to `EvidenceStandardsEngine`** — at minimum INFO for which requirements matched/failed

### Medium effort
- [ ] **Implement log rotation** via `logging.handlers.RotatingFileHandler` or a simple size check in `LoggingService.write_event()`
- [ ] **Add JSON schema file** for `pipeline_events.jsonl` so consumers can validate
- [ ] **Log error events** to a separate `pipeline_errors.jsonl` when exceptions occur

### Production-grade
- [ ] **Add structured logging library** (e.g., `structlog`) for richer event schemas
- [ ] **Ship logs to S3 / CloudWatch / DataDog** — add a `LogShipper` service
- [ ] **Add log level filtering** to LoggingService (respect `Settings.log_level`)
- [ ] **Add OpenTelemetry instrumentation** for distributed tracing across providers
- [ ] **Add a `/health` endpoint** returning last pipeline run status and event count

---

## 9. Overall Observability Score

| Category | Score |
|---|---|
| LoggingService implementation | 70/100 |
| pipeline_events.jsonl coverage | 65/100 |
| Pipeline stage coverage | 60/100 |
| End-to-end traceability | 40/100 |
| Debug logging (VisionAgent) | 90/100 |
| Debug logging (ModelService) | 85/100 |
| Debug logging (EvidenceEngine) | 5/100 |
| Debug logging (ClaimAgent) | 5/100 |
| Log rotation & persistence | 15/100 |
| Error & exception logging | 30/100 |

**Overall: 47/100 — Functional but needs investment for production**

### Key strengths
- `pipeline_events.jsonl` captures all final outputs per claim
- VisionReviewAgent has excellent DEBUG-level logging for VLM responses
- ModelService logs all fallback decisions with latency
- DecisionService logs final output for every claim

### Critical weaknesses
- No cross-component trace ID (cannot reliably trace one claim end-to-end)
- EvidenceStandardsEngine and ClaimExtractionAgent have zero observability
- No latency tracking per pipeline stage
- No log rotation or shipping
