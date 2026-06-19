# AI Judge Interview Cheatsheet
## Multi-Modal Evidence Review

---

## 30-Second Elevator Pitch

"We built a 4-stage AI pipeline that verifies damage claims from insurance customers.
Given a claim conversation and submitted photos, the system extracts what the customer
actually claims, analyses every image with a vision model, checks whether the image set
meets minimum evidence standards, and produces a structured verdict — supported,
contradicted, or not enough information — with an auditable justification."

---

## Architecture (ASCII)

```
claims.csv + images
      │
      ▼
┌─────────────────────────┐
│  Stage 1                │
│  ClaimExtractionAgent   │  ← Text-only, LLM fast-path + regex
│  claimed_part,          │
│  claimed_issue,         │
│  injection_detected     │
└─────────┬───────────────┘
          │ ExtractedClaim
          ▼
┌─────────────────────────┐
│  Stage 2                │
│  VisionReviewAgent      │  ← VLM per-image → aggregate
│  object_visible,        │
│  issue_visible,         │
│  supporting_image_ids   │
└─────────┬───────────────┘
          │ VisionReviewResult
          ▼
┌─────────────────────────┐
│  Stage 3                │
│  EvidenceStandardsEngine│  ← Rule-based CSV-driven checks
│  evidence_standard_met, │
│  sufficiency_level      │
└─────────┬───────────────┘
          │ EvidenceStandardResult
          ▼
┌─────────────────────────┐
│  Stage 4                │
│  DecisionService        │  ← Deterministic rules
│  claim_status,          │
│  risk_flags, severity   │
└─────────────────────────┘
          │
          ▼
      output.csv
```

---

## Why Images Are Primary Evidence

- Customer conversations are self-reported and unverifiable by text alone — anyone can claim anything
- Images provide an independent, objective snapshot of the object's state at claim time
- The pipeline's decision rules are anchored to `object_visible`, `issue_visible`, and `supporting_image_ids` — all VLM-derived, not conversation-derived
- If images contradict the text claim, the verdict is `contradicted` regardless of how convincing the conversation sounds

---

## Why User History Never Overrides Images

- History (rejection rate, claim count) informs **risk flags only** — it adds `user_history_risk` to `risk_flags` but cannot change `claim_status`
- Two fraud failure modes are prevented: (a) legitimate users with bad history unfairly rejected, (b) fraudsters with clean history approved despite bad images
- DecisionService applies history **after** the visual verdict is fixed — it is additive, never overriding
- Architecturally: `UserHistory` is never passed to `VisionReviewAgent` or `EvidenceStandardsEngine`

---

## Caching Strategy

- **Key**: `SHA-256(prompt_version | image_bytes_sha256 | claim_object | claimed_part | claimed_issue)`
- Same image appearing in two different claims with the same context → single VLM call, result reused
- Different claim context (different claimed part) → separate cache entry (correct: context affects VLM output)
- Prompt version included → bumping `v4 → v5` auto-invalidates all cached entries for that prompt
- Persistent JSONL file at `code/.cache/benchmark_cache.jsonl` for cross-run reuse
- No cache for failed calls — only successful VLM responses are stored

---

## Fallback Strategy (3-tier)

| Tier | Provider | Model | Trigger |
|------|----------|-------|---------|
| 1 | Gemini | gemini-2.5-flash | Primary |
| 2 | OpenRouter | qwen/qwen2.5-vl-72b | Gemini 429/503/timeout |
| 3 | OpenRouter | llama-3.2-90b-vision | Tier 2 failure |
| None | Preflight-only | — | All tiers fail |

- Tier failures are logged with `provider_used`, `fallback_reason`, `latency_ms`
- Pipeline **never crashes** — always produces `not_enough_information` + `manual_review_required` when all tiers fail
- Free-tier throttle: 12–13 seconds between Gemini calls (respects 5 req/min limit)
- Retry-after parsing: reads `"retry in Xs"` from 429 error messages and sleeps accordingly

---

## Evaluation Methodology

- Ground truth: `dataset/sample_claims.csv` (20 labeled rows)
- Metrics: accuracy, precision, recall, F1 (macro) for `claim_status`, `issue_type`, `object_part`, `evidence_standard_met`
- Macro averaging ensures rare classes (e.g. `contradicted` = 5 cases) are not hidden by majority class
- Confusion matrix generated for `claim_status`
- Error mining classifies failures into 7 root-cause categories ranked by leaderboard impact

---

## Cost Analysis

| Scenario | Images | Calls | Cost (Gemini Flash est.) | Time |
|----------|--------|-------|--------------------------|------|
| Sample (20 rows) | ~32 | 32 | ~$0.003 | ~7 min |
| Test (44 rows) | ~70 | 70 | ~$0.007 | ~15 min |
| With 100% cache hit | any | 0 | $0 | <1 min |

- Gemini 2.5 Flash pricing: ~$0.075/M input tokens, ~$0.30/M output tokens
- Each image call: ~1,500 input tokens + ~400 output tokens ≈ $0.0001/image
- Cache makes second runs free — the benchmark JSONL cache persists across sessions

---

## Scaling Strategy

1. **Parallelism**: On paid tier, replace sequential loop with `ThreadPoolExecutor(max_workers=10)` — each image is independent
2. **Rate limit management**: Token bucket or semaphore to cap at provider's TPM limit
3. **Distributed cache**: Replace in-memory/JSONL cache with Redis for multi-worker deployments
4. **Horizontal sharding**: Pipeline is stateless — shard by `user_id` range across workers
5. **Queue-based**: Replace CSV input with SQS/Pub-Sub message queue for production

---

## Top 10 Likely Judge Questions

**Q1: Why use a VLM instead of a classifier?**
A: Damage claims span 12 issue types × 27 object parts = 324 combinations, plus free-form damage descriptions. A VLM can reason across this space without needing labeled training data for every combination. A classifier would require thousands of labeled examples per class and wouldn't generalize to new damage types.

**Q2: What happens if Gemini is unavailable?**
A: The 3-tier fallback chain tries OpenRouter Qwen2.5-VL, then LLaMA-3.2-Vision. If all fail, the pipeline returns `not_enough_information` with `manual_review_required` flag — it never crashes and always produces valid output.

**Q3: How do you prevent prompt injection from images?**
A: The v4/v5/v6 prompts explicitly instruct the model to flag any text overlays as `TEXT_INSTRUCTION_PRESENT` and ignore them. The evidence standards engine treats this flag as a trust violation — claims with this flag fail `REQ_REVIEW_TRUST`.

**Q4: Why not just use GPT-4o?**
A: The system is provider-agnostic by design. We use Gemini as the primary for cost and speed (free tier available). The OpenRouter fallback can route to any vision model including GPT-4o. Switching is a single env var change.

**Q5: How do you handle multilingual claims?**
A: ClaimExtractionAgent has keyword maps for Spanish (pantalla, parachoques) and Hindi transliterations (dab gaya, toot gaya). For claims the fast-path can't resolve, it falls back to the LLM which handles multilingual text natively.

**Q6: How is this different from just asking the VLM "is this claim supported?"**
A: We separate concerns: the VLM only answers "what is visible?" — it never decides the claim outcome. The decision logic is deterministic rules in `DecisionService`. This makes the system auditable and lets us tune decision rules without touching the VLM prompt.

**Q7: What's your evaluation methodology?**
A: We run the pipeline on `sample_claims.csv` (labeled ground truth), compare predictions to expected outputs, and compute accuracy/F1 macro for each output field. Error mining classifies failures into 7 categories ranked by leaderboard impact.

**Q8: How do you handle images that show the wrong object?**
A: The VLM is instructed to set `object_present=false` and add `WRONG_OBJECT` to `quality_flags`. The aggregation layer excludes wrong-object images from the visible parts/issues union. The evidence standards engine's `REQ_REVIEW_TRUST` check fails, and `DecisionService` returns `not_enough_information`.

**Q9: Why a two-step reasoning prompt?**
A: Step 1 forces the model to describe what it sees without anchor bias from the claim. Step 2 then maps those observations to taxonomy values. Without the separation, the model tends to confirm whatever the claim says — a classic anchoring failure.

**Q10: What would you do with more time?**
A: (1) Run full benchmark with VLM to get real accuracy numbers. (2) Fine-tune a smaller vision model on the labeled sample data. (3) Add multi-image joint analysis (send all images in one call for better contradiction detection). (4) Implement active learning from manual review decisions.
