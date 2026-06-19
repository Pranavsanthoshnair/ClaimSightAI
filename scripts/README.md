# scripts/

Utility and diagnostic scripts. These are **not** part of the main pipeline — they are developer tools for setup, debugging, and probing.

| Script | Purpose |
|--------|---------|
| `check_keys.py` | Verify OPENROUTER_API_KEY values are set |
| `check_credits.py` | Check remaining OpenRouter credit balance |
| `probe_keys.py` | Test each key in the pool against the API |
| `quick_probe.py` | Quick single-model connectivity check |
| `find_free_models.py` | List all free-tier models on OpenRouter |
| `audit_script.py` | Full pipeline audit across sample_claims.csv |
| `diagnose_pipeline.py` | Step-by-step pipeline diagnostics |
| `diagnose_vision.py` | Vision model response diagnostics |
| `inspect_pipeline.py` | Inspect intermediate pipeline outputs |
| `generate_output.py` | Standalone output.csv generator |
| `run_no_model.py` | Run pipeline in preflight-only mode (no VLM) |
| `show_metrics.py` | Print evaluation metrics from metrics.json |
| `test_*.py` | End-to-end connectivity and regression tests |

## Usage

```bash
# From repo root
python scripts/check_keys.py
python scripts/audit_script.py
python scripts/show_metrics.py
```

> **Note:** These scripts require `OPENROUTER_API_KEY` to be set in `.env` or environment.
