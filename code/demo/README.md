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
pip install streamlit
```

Also set `GEMINI_API_KEY` in `.env` for real VLM analysis:
```
MODEL_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

Without an API key the app runs in preflight-only mode — claim extraction works but visual analysis is unavailable.

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
