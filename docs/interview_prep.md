# Interview Prep — Multi-Modal Evidence Review

> Suitable for a 30-minute AI judge interview. Each section answers a likely question.

---

## 1. Architecture Overview

The pipeline has 4 sequential stages with clean separation of concerns:

- **Stage 1 — Claim Extraction** (`ClaimExtractionAgent`): Parses the user's free-text conversation using an LLM. Extracts `claim_object`, `claimed_part`, `claimed_issue_type` into a validated Pydantic schema. Detects prompt-injection attempts in the conversation text.
- **Stage 2 — Vision Review** (`VisionReviewAgent`): Analyses each submitted image using a VLM (Gemini 2.5 Flash). Returns per-image findings (visible parts, visible issues, supports_claim) and aggregates them into a single `VisionReviewResult`. No claim decision is made here — only "what is visible?".
- **Stage 3 — Evidence Standards** (`EvidenceStandardsEngine`): Applies rule-based thresholds from `evidence_requirements.csv`. Checks whether the visual evidence meets minimum standards (object visible, part visible, issue visible, no trust-breaking flags). Returns `FULLY_MET`, `PARTIALLY_MET`, or `NOT_MET`.
- **Stage 4 — Decision** (`DecisionService`): Combines claim extraction + visual evidence + evidence standard result + user history to produce the final `claim_status` (supported / contradicted / not_enough_information), confidence, risk flags, and justification.
- **Data flow**: `claims.csv` → Stage 1 → `ParsedClaim` → Stage 2 → `VisionReviewResult` → Stage 3 → `EvidenceStandardResult` → Stage 4 → `output.csv`.

---

## 2. Why Images Are Primary Evidence

- The claim conversation tells us what the customer *says* happened — it is self-reported and unverifiable by text alone.
- Images provide objective, ground-truth visual evidence of the object state at claim time.
- Without images, any claim could be fabricated or exaggerated; image analysis is the only source of independent verification.
- The system treats image findings as authoritative: if the images contradict the text claim, the claim is `contradicted`, not `supported`.
- If no model is configured, the pipeline runs in preflight-only mode — image files are read and quality-checked locally, but without VLM analysis, all claims fall back to `not_enough_information`. This is the correct, conservative default.

---

## 3. Why User History Never Overrides Visual Evidence

- User history (prior claim counts, rejection rates, risk tier) informs *risk flags* but never changes the visual evidence outcome.
- This separation prevents two failure modes: (a) legitimate claimants with bad history being unfairly rejected, and (b) fraudulent claimants with good history being approved despite bad images.
- The DecisionService applies history as a modifier to confidence and risk flags after the visual evidence verdict is fixed — it cannot flip `not_enough_information` to `supported`.
- This design also future-proofs the system: history signals can be tuned or removed without touching the vision pipeline.
- From a fraud-prevention angle: a fraudster who "games" their history score still cannot override a VLM that says the claimed object is not visible.

---

## 4. Why Hybrid AI + Rules

- Pure LLM decisions are non-deterministic, hard to audit, and can hallucinate outcomes (e.g., approve a claim with no supporting image).
- The vision model handles the hard perceptual task (identifying objects, parts, damage types from images) where rules alone cannot operate.
- The evidence standards engine handles the decision logic using deterministic rules from `evidence_requirements.csv` — the same threshold applies every time, for every claim.
- This hybrid approach means the system is fully auditable: every decision traces back to specific evidence requirements that were satisfied or failed.
- It also allows non-ML engineers to modify business rules (thresholds, new object types) without retraining a model.

---

## 5. Why Evidence Standards Exist

- `REQ_GENERAL_OBJECT_PART` enforces that the claimed object part must be visible in at least one image. Without this, a car dent claim could be "supported" by a photo of an unrelated car.
- Evidence standards make implicit acceptance criteria explicit and configurable per object type / claim type.
- They prevent false positives: a claim where only the object is visible (but not the claimed part or damage) is `PARTIALLY_MET`, not `FULLY_MET`.
- `REQ_REVIEW_TRUST` blocks claims where images contain manipulation flags (`POSSIBLE_MANIPULATION`, `TEXT_INSTRUCTION_PRESENT`) — a critical anti-fraud control.
- The requirements are loaded from a CSV, making them easy to update without code changes when business rules evolve.

---

## 6. Cost Optimization Strategy

- **Content-addressed caching**: every VLM call is keyed on SHA-256(prompt_version + image_bytes + claim fields). The same image in multiple claims is analysed only once. Benchmark and pipeline share this cache.
- **Image resizing**: images are resized to max 1536px on the longest side before sending to the VLM. This cuts token cost and latency while preserving detail needed for damage assessment.
- **Prompt version invalidation**: bumping `PROMPT_VERSION` (e.g., v3 → v4) automatically invalidates cached results so stale analyses are never used after a prompt change.
- **Free-tier throttling**: 12–13 seconds between Gemini calls to stay under 5 req/min. The benchmark skips this delay for cached rows.
- **Batch amortisation**: claims sharing images (e.g., the same image ID across rows) benefit from the cache — only the first claim pays the API cost.

---

## 7. Caching Strategy

- **Key design**: `SHA-256(prompt_version | image_bytes_sha256 | claim_object | claimed_part | claimed_issue)`. This means two different claims sharing the same image but different claimed parts produce different cache entries (correct: the VLM response is claim-context-dependent).
- **Storage**: in-memory dict during a pipeline run (fast), backed by a persistent JSONL file at `code/.cache/benchmark_cache.jsonl` for the benchmark. Each line is a `{"key": ..., "value": ...}` JSON entry.
- **Invalidation**: prompt version is part of the key. Incrementing `PROMPT_VERSION` ("v3" → "v4") ensures all prior cache entries are bypassed automatically.
- **Safety**: cache entries are only written after a successful VLM call. A failed call is never cached, so a retry on the next run will re-attempt the API.
- **Cross-run persistence**: the benchmark JSONL cache survives process restarts, so a interrupted run can be resumed without re-paying for already-analysed images.

---

## 8. Retry & Fallback Strategy

- **Primary provider**: GeminiProvider (google-genai SDK). Enforces 12s inter-call delay. Parses "retry in Xs" from 429 responses and sleeps accordingly. Retries up to `max_retries` times with exponential-style backoff.
- **Fallback provider**: OpenRouterProvider (standard `requests` HTTP call to `https://openrouter.ai/api/v1/chat/completions`). Activated automatically when Gemini raises 429, 503, timeout, or `ConnectionError`.
- **Fallback triggers**: HTTP 429 / 503, `TimeoutError`, `ConnectionError`, `RuntimeError` from exhausted retries, or JSON parse failure from the provider layer.
- **Graceful degradation**: if both primary and fallback fail, `inspect_image()` returns `None`. The `VisionReviewAgent` then produces a preflight-only result with `MANUAL_REVIEW_REQUIRED` flag. The pipeline never crashes — it always produces output.
- **Telemetry**: `ModelService` tracks `call_count`, `fallback_count`, `cache_hit_count`. Each fallback is logged with `provider_used`, `fallback_reason`, and `latency_ms`.

---

## 9. Scaling Strategy

- **Parallelism**: on a paid-tier API (no rate limits), vision analysis can be parallelised with `concurrent.futures.ThreadPoolExecutor` — each image is independent. The in-memory cache is thread-safe for reads; writes need a lock.
- **Batch processing**: group claims by image hash (using the cache key) to deduplicate API calls across claims before parallelising.
- **Rate limit management**: implement a token-bucket or semaphore to cap concurrent requests at the provider's TPM limit. Gemini free tier: 5 req/min. Gemini paid tier: up to 360 req/min.
- **Horizontal scaling**: the pipeline reads from CSV and writes to CSV — it is stateless and can be sharded by `user_id` range across multiple workers. The JSONL cache can be replaced with a Redis or DynamoDB cache for distributed runs.
- **Queue-based architecture**: for production, each claim would be a message in a queue (SQS/Pub-Sub). Workers pull from the queue, process, and write to a database. This decouples ingestion from processing.

---

## 10. Future Improvements

- **Multi-image joint analysis**: instead of analysing images independently and aggregating, send all images for a claim together in a single VLM call with a "compare these images" prompt. This would improve contradiction detection and reduce API calls.
- **Fine-tuned vision model**: collect labelled examples (image + correct supports_claim label) and fine-tune a smaller vision model specifically for the damage taxonomy. This would improve accuracy and reduce latency.
- **Active learning from rejected claims**: when a claim is manually reviewed and the reviewer disagrees with the system, log the disagreement as a training signal. Use these examples to refine the evidence standards thresholds or the VLM prompt.
- **Severity calibration**: add a severity regression model trained on accepted/rejected claim pairs to improve confidence calibration across different damage types.
- **Image provenance verification**: use EXIF metadata and perceptual hashing to detect recycled images (same image submitted for multiple claims) as an additional anti-fraud signal.
