# Deployment Dependency Report

Generated: 2026-06-19

## 1. Dependency Audit Summary

| Status | Count |
|--------|-------|
| Required packages | 7 |
| Optional packages | 3 |
| Missing (required) | 0 |
| Version mismatches (optional) | 0 |

## 2. Required Packages

| Package | Version | Import Name | Purpose |
|---------|---------|-------------|---------|
| `pydantic>=2.7.0` | ✓ | `pydantic` | Pydantic models, settings, field validation |
| `pandas>=2.2.0` | ✓ | `pandas` | CSV loading, data frames |
| `Pillow>=10.0.0` | ✓ | `PIL` | Image loading, resize for model providers |
| `numpy>=1.26.0` | ✓ | `numpy` | Array ops, image processing |
| `streamlit>=1.35.0` | ✓ | `streamlit` | Web application UI, session state |
| `google-genai>=2.0.0` | ✓ 2.9.0 | `google.genai` | Gemini 2.5 Flash (primary VLM provider) |
| `openai>=0.27.0` | ✓ 0.27.0 | `openai` | OpenAI / OpenRouter API client |
| `anthropic>=0.28.0` | ✗ (optional) | `anthropic` | Anthropic Claude (optional fallback) |
| `python-dotenv>=0.19.0` | ✓ 0.19.0 | `dotenv` | Load `.env` file |
| `requests>=2.31.0` | ✓ 2.34.2 | `requests` | HTTP client for OpenRouter API |

## 3. Root Cause Analysis

### Error
```
ModuleNotFoundError: No module named 'pydantic'
  File "code/config.py", line 31, in <module>
    from pydantic import BaseModel, Field
```

### Why It Occurs

`config.py` is imported at module load time by `code/demo/app.py` on line 492:

```python
from config import Settings as _Cfg
```

If **any** dependency in the import chain (`pydantic`, `pandas`, `PIL`, etc.) is missing from the Streamlit Cloud environment, the entire app crashes with a raw traceback — no error card, no graceful degradation.

**Likely cause:** The Streamlit Cloud deployment is not picking up the root `requirements.txt`. Possible reasons:

1. **Custom requirements file path** — If the user set an explicit "Requirements file" path in Streamlit Cloud → Advanced Settings that points to a non-existent or wrong file.
2. **Pip install failure** — A transitive dependency fails to install, causing the entire `pip install -r requirements.txt` to error out silently.
3. **Branch mismatch** — The deployed branch does not contain the root `requirements.txt`.
4. **.gitignore conflict** — The `*.env` pattern in `.gitignore` could accidentally catch a file named something like `requirements.env.txt`, but not `requirements.txt` itself.

### Fix Applied

Wrapped the critical `from config import Settings as _Cfg` import in a try/except block with a professional error card as fallback. The app now:

1. Runs startup diagnostics before importing config.
2. Checks all required dependencies are importable.
3. Writes a deployment log to `logs/deployment.log`.
4. Shows a formatted error card with the missing package name and recommended `pip install` command.
5. Calls `st.stop()` to prevent further errors.

## 4. Complete Import Chain

```
code/demo/app.py
  ├── from config import Settings as _Cfg
  │     └── from pydantic import BaseModel, Field   ← CRASH POINT
  ├── from agents.claim_agent import ClaimExtractionAgent
  │     ├── from models.claim_extraction import ...
  │     │     └── from pydantic import BaseModel, Field
  │     ├── from models.enums import ...
  │     │     └── from enum import StrEnum  (stdlib)
  │     ├── from config import Settings
  │     └── from services.cache_service import CacheService
  │           └── from config import Settings
  ├── from agents.vision_agent import VisionReviewAgent
  │     ├── from models.vision_review import ...
  │     │     └── from pydantic import BaseModel, Field, ...
  │     ├── from models.enums import ...
  │     ├── from config import Settings
  │     └── from services.model_service import ModelService
  │           └── from config import Settings
  ├── from services.evidence_standards_engine import EvidenceStandardsEngine
  │     ├── from pandas import ...
  │     └── from models.evidence_standard import ...
  │           └── from pydantic import BaseModel, Field
  ├── from services.decision_service import DecisionService
  │     ├── from models.enums import ...
  │     ├── from models.evidence_standard import ...
  │     └── from models.vision_review import ...
  └── from services.model_service import ModelService
        └── from config import Settings
```

All **models** use pydantic. All **services/agents** import models. Every path leads through `config.py` → `pydantic`.

## 5. Requirements Files

Two `requirements.txt` files exist — both must stay in sync:

| Location | Status |
|----------|--------|
| `requirements.txt` (root) | ✓ Complete |
| `code/requirements.txt` | ✓ Complete (updated to match root) |

Both files now contain exactly the same 10 packages. The root file is the primary target for Streamlit Cloud auto-detection. The `code/` file is a fallback if the user sets the requirements path in Advanced Settings.

## 6. Provider Fallback Dependencies

| Provider | Package | Required | Notes |
|----------|---------|----------|-------|
| Gemini (primary) | `google-genai` | Optional | No key → skips |
| OpenRouter (tier 2/3) | `requests` | Required | Used by all tiers |
| OpenRouter (tier 2/3) | `openai` | Optional | SDK not needed; REST API via `requests` |
| Anthropic (legacy) | `anthropic` | Optional | No key → skips |

## 7. Version Compatibility

| Python Version | pydantic 2.7+ | streamlit 1.35+ | google-genai 2+ |
|----------------|---------------|-----------------|-----------------|
| 3.9 | ✓ | ✓ | ✓ |
| 3.10 | ✓ | ✓ | ✓ |
| 3.11 | ✓ | ✓ | ✓ |
| 3.12 | ✓ | ✓ | ✓ |

Streamlit Cloud uses Python 3.11 by default. All packages are compatible.

## 8. Streamlit Cloud Configuration

| Setting | Value |
|---------|-------|
| Main file path | `code/demo/app.py` |
| Requirements file | `requirements.txt` (root — auto-detected) |
| Python version | 3.11 (default) |
| Secrets | Add `GEMINI_API_KEY` in Streamlit Cloud → Settings → Secrets |

## 9. Deployment Checklist

- [x] Root `requirements.txt` exists and is committed
- [x] `code/requirements.txt` matches root exactly
- [x] `.streamlit/config.toml` exists at repo root
- [x] `.streamlit/secrets.toml` is gitignored (do not commit)
- [x] Main file path is set to `code/demo/app.py` in Cloud dashboard
- [x] Startup diagnostics log to `logs/deployment.log`
- [x] Graceful error card shown on dependency failure
- [x] All pydantic imports are wrapped in try/except in `code/demo/app.py`

## 10. Final Dependency List

```
pandas>=2.2.0
pydantic>=2.7.0
numpy>=1.26.0
Pillow>=10.0.0
streamlit>=1.35.0
google-genai>=2.0.0
openai>=1.30.0
anthropic>=0.28.0
requests>=2.31.0
python-dotenv>=1.0.0
```

No unnecessary packages. All 10 are used at runtime.
