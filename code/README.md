# ClaimSight AI — Multi-Modal Evidence Review

**HackerRank Orchestrate Hackathon · June 2026**

ClaimSight AI is a production-grade pipeline that verifies damage claims by cross-referencing
submitted images, claim conversations, user history, and minimum evidence requirements.
It gives a structured verdict: **Supported**, **Contradicted**, or **Not Enough Information**.

---

## System Architecture

```
claims.csv  ──►  ClaimExtractionAgent   (LLM: extract structured claim from conversation)
                        │
                        ▼
                 VisionReviewAgent       (VLM: inspect each image against the claim)
                        │
                        ▼
                 EvidenceStandardsEngine (rules: check minimum evidence requirements)
                        │
                        ▼
                 DecisionService         (rules: final verdict + risk flags)
                        │
                        ▼
              output.csv  +  Streamlit UI
```

### Decision Rules (in priority order)
1. No valid/readable image → `not_enough_information` + `MANUAL_REVIEW_REQUIRED`
2a. Claimed part IS visible but claimed damage is NOT → `contradicted`
2c. A **different** damage type is visible than what was claimed → `contradicted` + `CLAIM_MISMATCH`
2b. Evidence standard not met → `not_enough_information`
3. Claimed object not visible → `not_enough_information` + `WRONG_OBJECT`
4. Claimed part not visible → `not_enough_information` + `WRONG_OBJECT_PART`
5. Claimed part + claimed damage both confirmed → `supported`
6. Fallback → `not_enough_information`

---

## Quick Start

### Requirements
- Python 3.11+
- API key for at least one vision model (OpenRouter recommended)

### Install

```bash
pip install -r requirements.txt
```

### Configure

Copy `.env.example` to `.env` and add your API keys:

```bash
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY_1 (and optionally _2, _3 for fallback)
```

### Run the Web UI

```bash
python main.py
# Opens http://localhost:8501
```

### Run Batch Pipeline

```bash
# Process claims.csv → output.csv
python main.py --input dataset/claims.csv --output output.csv

# Use sample set for evaluation
python main.py --input dataset/sample_claims.csv --output outputs/sample_predictions.csv
```

### Run Evaluation

```bash
# First generate predictions on sample set
python main.py --input dataset/sample_claims.csv --output outputs/sample_predictions.csv

# Then evaluate against ground truth
python evaluation/main.py \
  --sample dataset/sample_claims.csv \
  --predictions outputs/sample_predictions.csv \
  --report evaluation/evaluation_report.md
```

### Run Tests

```bash
cd code
pytest tests/ -v
```

---

## Project Structure

```
code/
├── main.py                      # Unified entry point (UI or batch)
├── config.py                    # Settings + env var loading
├── agents/
│   ├── claim_agent.py           # ClaimExtractionAgent (LLM)
│   └── vision_agent.py          # VisionReviewAgent (VLM)
├── services/
│   ├── decision_service.py      # Rule-based verdict engine
│   ├── evidence_standards_engine.py  # Evidence requirement checker
│   ├── model_service.py         # VLM/LLM provider abstraction
│   ├── history_service.py       # User risk history loader
│   ├── cache_service.py         # Content-addressed response cache
│   └── providers/
│       ├── openrouter_provider.py   # OpenRouter (Llama, Claude, Qwen)
│       └── groq_provider.py         # Groq fallback
├── pipelines/
│   └── claim_review_pipeline.py # End-to-end orchestration
├── prompts/
│   └── templates.py             # Versioned system + user prompts (v6)
├── models/                      # Pydantic schemas
├── evaluation/
│   ├── main.py                  # Evaluation CLI
│   ├── metrics.py               # Accuracy / F1 computation
│   └── evaluation_report.md     # Operational analysis
├── demo/
│   └── app.py                   # Streamlit web UI
└── tests/                       # Unit + regression + validation tests
```

---

## Model Chain (Tier Fallback)

| Tier | Model | Provider | Trigger |
|------|-------|----------|---------|
| T1 | `meta-llama/llama-3.2-11b-vision-instruct` | OpenRouter | Primary |
| T2 | `anthropic/claude-3-haiku` | OpenRouter | T1 fails |
| T3 | `qwen/qwen2.5-vl-72b-instruct` | OpenRouter | T2 fails |
| T4 | Free-tier models | OpenRouter | T3 fails |

On credit exhaustion (`402`): instant key rotation across pool.  
On rate limit (`429`): exponential backoff (0.5 → 1 → 2 → 4s).  
On all tiers failing: claim marked `not_enough_information` + `MANUAL_REVIEW_REQUIRED`.

---

## Output Schema

`output.csv` columns (in order):

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | str | Claimant ID |
| `image_paths` | str | Semicolon-separated image paths |
| `user_claim` | str | Original conversation |
| `claim_object` | str | `car`, `laptop`, or `package` |
| `evidence_standard_met` | bool | Image set sufficient to evaluate |
| `evidence_standard_met_reason` | str | Reason for evidence decision |
| `risk_flags` | str | Semicolon-separated flags or `none` |
| `issue_type` | str | Visible damage type |
| `object_part` | str | Relevant object part |
| `claim_status` | str | `supported` / `contradicted` / `not_enough_information` |
| `claim_status_justification` | str | Image-grounded explanation |
| `supporting_image_ids` | str | Image IDs supporting the decision |
| `valid_image` | bool | Image set usable for automated review |
| `severity` | str | `none` / `low` / `medium` / `high` / `unknown` |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY_1` | Primary OpenRouter key |
| `OPENROUTER_API_KEY_2` | Secondary key (rotation) |
| `OPENROUTER_API_KEY_3` | Tertiary key (rotation) |
| `MODEL_PROVIDER` | `openrouter` (default) or `none` (preflight) |
| `VISION_MODEL` | Override default vision model slug |

---

## Key Design Decisions

- **Claim-image mismatch detection**: The VLM reports what damage is actually visible.
  The pipeline compares it against what was *claimed*. If types differ and the object is
  visible, the verdict is `contradicted` — not `supported`.
- **Prompt versioning**: Every cache key includes `PROMPT_VERSION`. Bumping it (currently
  `v6`) automatically invalidates stale cached responses.
- **Lazy model probing**: Model availability is only checked on user demand (via UI button),
  never on startup — prevents blocking the main thread for 60–90 seconds.
- **Sequential processing**: Claims are processed one at a time for determinism and to
  stay within rate limits on free/low-tier API keys.
