# ClaimSight AI

**Multi-modal damage claim verification using AI vision and evidence standards.**

ClaimSight AI analyses damage claims submitted with photos and conversation context. It verifies whether the submitted visual evidence supports, contradicts, or is insufficient for the stated claim — producing a structured, auditable decision in seconds.

---

## Live Demo

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://claimsightai.streamlit.app)

---

## Features

- 🔍 **Claim understanding** — extracts damage type, object, and location from natural language
- 👁 **AI image analysis** — multi-tier vision model chain (Llama → Claude → Qwen)
- 📋 **Evidence standards** — CSV-driven requirement rules per claim type
- ⚖️ **Deterministic decisions** — rule-based engine: Verified / Does Not Match / More Evidence Needed
- 🔄 **Auto key rotation** — up to 5 OpenRouter keys with instant 402/429 failover
- 🔬 **Developer Mode** — toggle technical details on/off in the sidebar
- 📦 **Content-addressed cache** — identical images reuse cached VLM responses

---

## Project Structure

```
ClaimSightAI/
│
├── README.md                      ← You are here
├── problem_statement.md           ← Challenge task description
├── AGENTS.md                      ← Agent rules and log contract
├── requirements.txt               ← Python dependencies
├── .env.example                   ← Credential template
│
├── code/                          ← All source code
│   ├── main.py                    ← Pipeline entry point (run on claims.csv)
│   ├── config.py                  ← Settings / env var loader
│   ├── agents/                    ← Claim extraction + vision agents
│   ├── demo/                      ← Streamlit web UI (app.py)
│   ├── evaluation/                ← Evaluation pipeline (sample_claims.csv)
│   ├── models/                    ← Pydantic data models + enums
│   ├── pipelines/                 ← Orchestration pipeline
│   ├── prompts/                   ← LLM/VLM prompt templates (v6)
│   ├── services/                  ← Vision service + OpenRouter provider
│   ├── tests/                     ← Unit tests
│   └── utils/                     ← Shared utilities
│
├── dataset/
│   ├── claims.csv                 ← Test inputs (no labels)
│   ├── sample_claims.csv          ← Dev inputs + ground truth
│   ├── user_history.csv           ← Claim history risk context
│   ├── evidence_requirements.csv  ← Per-type evidence rules
│   └── images/
│       ├── sample/                ← Images for sample_claims.csv
│       └── test/                  ← Images for claims.csv
│
├── outputs/
│   └── output.csv                 ← Generated predictions
│
├── docs/                          ← Documentation
│   ├── architecture.md
│   ├── accuracy_improvement.md
│   ├── ux_simplification.md
│   └── dev/                       ← Internal engineering notes
│
├── scripts/                       ← Diagnostic + utility scripts
│   ├── check_keys.py
│   ├── audit_script.py
│   └── ...
│
└── logs/                          ← Runtime logs
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set credentials

```bash
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

### 3. Run the pipeline on test claims

```bash
python code/main.py
# Writes output.csv to repo root
```

### 4. Run evaluation on sample claims

```bash
python code/evaluation/main.py
# Writes metrics to code/evaluation/metrics.json
```

### 5. Launch the demo UI

```bash
streamlit run code/demo/app.py
```

---

## Streamlit Cloud Deployment

Set the following in **Streamlit Cloud → Settings → Secrets**:

```toml
OPENROUTER_API_KEY   = "sk-or-..."
OPENROUTER_API_KEY_2 = "sk-or-..."   # optional — pool rotation
OPENROUTER_API_KEY_3 = "sk-or-..."
OPENROUTER_API_KEY_4 = "sk-or-..."
OPENROUTER_API_KEY_5 = "sk-or-..."
GROQ_API_KEY         = "gsk_..."     # optional — text reasoning fallback
```

Main file path: `code/demo/app.py`

---

## Output Schema

`output.csv` columns:

| Column | Description |
|--------|-------------|
| `user_id` | Claim submitter ID |
| `claim_status` | `supported` / `contradicted` / `not_enough_information` |
| `claim_status_justification` | Natural language explanation |
| `issue_type` | Detected damage type (e.g. `dent`, `scratch`) |
| `object_part` | Affected part (e.g. `rear_bumper`) |
| `severity` | `low` / `medium` / `high` / `none` |
| `evidence_standard_met` | `true` / `false` |
| `evidence_standard_met_reason` | Requirement gap explanation |
| `risk_flags` | Semicolon-separated quality signals |
| `supporting_image_ids` | Images that support the claim |
| `valid_image` | Whether at least one image was processable |

---

## Model Chain

| Tier | Model | Role |
|------|-------|------|
| T1 | `meta-llama/llama-3.2-11b-vision-instruct` | Primary vision |
| T2 | `anthropic/claude-3-haiku` | Vision fallback |
| T3 | `qwen/qwen2.5-vl-72b-instruct` | High-accuracy fallback |
| T4 | `groq/llama-3.1-8b-instant` | Text reasoning only |

Auto-fallback on 402, 429, 404, or timeout. Up to 5 API keys rotated per tier.

---

## Evaluation Results (sample_claims.csv — 20 rows)

| Metric | Score |
|--------|-------|
| Claim status accuracy | 55% |
| Evidence standard accuracy | 85% |
| Supported F1 | 0.78 |
| Contradicted recall | 0.20 → improving with v6 fixes |

Baseline (no model): 10% accuracy.

---

*Built for HackerRank Orchestrate — Multi-Modal Evidence Review (June 2026)*
