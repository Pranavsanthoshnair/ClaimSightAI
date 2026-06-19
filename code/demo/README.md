# Evidence Review Demo

A Streamlit web application demonstrating the Multi-Modal Evidence Review pipeline.

## How to Run

```bash
# From repo root:
streamlit run code/demo/app.py
```

Then open http://localhost:8501 in your browser.

## Requirements

```bash
pip install -r requirements.txt
```

## Provider Configuration

Set `OPENROUTER_API_KEY` in `.env` for real VLM analysis:

```env
# Required — get your key at https://openrouter.ai/keys
OPENROUTER_API_KEY=your_key_here

# Optional — model overrides (defaults shown)
OPENROUTER_MODEL_PRIMARY=qwen/qwen2.5-vl-72b-instruct
OPENROUTER_MODEL_SECONDARY=meta-llama/llama-3.2-90b-vision-instruct
OPENROUTER_MODEL_TERTIARY=mistralai/pixtral-large-2411

# Optional — Groq text reasoning fallback
GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=llama-3.1-8b-instant
```

Without an API key the app runs in **preflight-only mode** — claim extraction works but visual image analysis is unavailable.

## Provider Chain

The app uses a 4-tier provider chain:

| Tier | Provider | Model | Role |
|------|----------|-------|------|
| T1 | OpenRouter | Qwen2.5-VL-72B | Primary vision |
| T2 | OpenRouter | Llama-3.2-90B-Vision | Secondary fallback |
| T3 | OpenRouter | Pixtral Large (124B) | Tertiary fallback |
| T4 | Groq | llama-3.1-8b-instant | Text reasoning fallback |

## Pages

**Claim Review** — upload images, enter the support conversation, select object type, submit.

**Results** — shows claim status (SUPPORTED / CONTRADICTED / NOT ENOUGH INFORMATION) with issue type, object part, severity, confidence, evidence standard, and risk flags.

**Decision Trace** — visualises all 4 pipeline stages:
1. Claim Extraction → extracted claim, issue type, object part
2. Vision Review → per-image findings, visible parts/issues, confidence
3. Evidence Standards → which requirements passed/failed
4. Decision Engine → which decision rule fired

## Architecture

The Streamlit app is a thin presentation layer on top of the existing pipeline:

```
app.py → ClaimExtractionAgent → VisionReviewAgent → EvidenceStandardsEngine → DecisionService
```

No database, no authentication, no backend redesign.
