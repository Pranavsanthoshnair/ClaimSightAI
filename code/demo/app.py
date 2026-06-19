"""
ClaimSight AI — Production-Grade Evidence Review Platform
Run locally:        streamlit run code/demo/app.py
Deploy on Cloud:    Set Main file path = code/demo/app.py
                    Add OPENROUTER_API_KEY in Streamlit Cloud → Settings → Secrets
                    Optionally add GROQ_API_KEY for text reasoning fallback
"""
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

# ── Path bootstrap — works locally AND on Streamlit Cloud ───────────────────
# On Cloud: repo root is /mount/src/<repo-name> or similar; __file__ resolves
# correctly so we navigate up from code/demo/app.py → code/ → repo root.
_THIS_FILE  = Path(__file__).resolve()
_CODE_DIR   = _THIS_FILE.parent.parent          # …/code/
_REPO_DIR   = _CODE_DIR.parent                  # …/repo-root/

if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

# ── Secrets: st.secrets (Cloud) with .env fallback (local) ──────────────────
def _inject_secrets() -> None:
    """Push Streamlit secrets into os.environ so Settings() picks them up."""
    try:
        import streamlit as _st
        for key in (
            "OPENROUTER_API_KEY",
            "OPENROUTER_API_KEY_2",
            "OPENROUTER_API_KEY_3",
            "OPENROUTER_API_KEY_4",
            "OPENROUTER_API_KEY_5",
            "OPENROUTER_MODEL_PRIMARY",
            "OPENROUTER_MODEL_SECONDARY",
            "OPENROUTER_MODEL_TERTIARY",
            "GROQ_API_KEY",
            "GROQ_MODEL",
        ):
            try:
                val = _st.secrets.get(key)
                if val and not os.environ.get(key):
                    os.environ[key] = str(val)
            except Exception:
                pass
    except Exception:
        pass

    # Also try .env for local dev
    try:
        from dotenv import load_dotenv
        load_dotenv(_REPO_DIR / ".env")
    except ImportError:
        pass

_inject_secrets()

# ── Startup diagnostics ──────────────────────────────────────────────────────
_RUN_DIAGNOSTICS = True
_DEPLOYMENT_ERROR: str | None = None
try:
    from utils.dependencies import (
        check_dependencies,
        format_dependency_error_html,
        startup_diagnostics,
        write_deployment_log,
    )
    _DIAG = startup_diagnostics(repo_root=_REPO_DIR, config_path=_CODE_DIR / "config.py")
    # Update the diagnostics flag
    _DEP_REPORT = check_dependencies()
    if not _DEP_REPORT.all_required_met:
        missing_all = _DEP_REPORT.missing_required + _DEP_REPORT.version_mismatches
        if _DEP_REPORT.missing_required:
            _DEPLOYMENT_ERROR = format_dependency_error_html(missing_all)
        _RUN_DIAGNOSTICS = False
    # Write deployment log (best-effort)
    try:
        write_deployment_log(_REPO_DIR / "logs", _DIAG)
    except Exception:
        pass
except ImportError:
    _RUN_DIAGNOSTICS = False

import streamlit as st

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ClaimSight AI",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

*, *::before, *::after { box-sizing: border-box; }

html, body, [data-testid="stAppViewContainer"] {
  background: #0B0F19 !important;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  color: #E2E8F0;
}

[data-testid="stAppViewContainer"] > .main { background: #0B0F19 !important; }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] { background: #111827 !important; border-right: 1px solid #1F2937; }

/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1.5rem 2rem 4rem; max-width: 1280px; margin: 0 auto; }

/* ── Topbar ── */
.cs-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.75rem 0 1.5rem; border-bottom: 1px solid #1F2937; margin-bottom: 2rem;
}
.cs-logo { display: flex; align-items: center; gap: 10px; }
.cs-logo-icon {
  width: 36px; height: 36px; background: linear-gradient(135deg,#6366F1,#8B5CF6);
  border-radius: 10px; display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 800; color: white; letter-spacing: -1px;
}
.cs-logo-text { font-size: 1.2rem; font-weight: 700; color: #F1F5F9; }
.cs-logo-text span { color: #6366F1; }
.cs-badge {
  background: rgba(99,102,241,0.15); color: #818CF8; border: 1px solid rgba(99,102,241,0.3);
  border-radius: 20px; padding: 3px 12px; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.5px;
}

/* ── Hero ── */
.cs-hero { text-align: center; padding: 2rem 0 2.5rem; }
.cs-hero h1 {
  font-size: 3rem; font-weight: 800; letter-spacing: -1.5px;
  background: linear-gradient(135deg, #F1F5F9 0%, #6366F1 60%, #8B5CF6 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text; margin: 0 0 0.75rem;
}
.cs-hero p { color: #94A3B8; font-size: 1.05rem; max-width: 520px; margin: 0 auto; line-height: 1.6; }

/* ── Cards ── */
.cs-card {
  background: #111827; border: 1px solid #1F2937; border-radius: 16px;
  padding: 1.5rem; margin-bottom: 1.25rem;
  box-shadow: 0 4px 24px rgba(0,0,0,0.4);
  transition: border-color 0.2s;
}
.cs-card:hover { border-color: #374151; }
.cs-card-title {
  font-size: 0.7rem; font-weight: 600; color: #6366F1;
  text-transform: uppercase; letter-spacing: 1px; margin-bottom: 1rem;
}

/* ── KPI Cards ── */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin: 1rem 0; }
.kpi-card {
  background: #111827; border: 1px solid #1F2937; border-radius: 14px;
  padding: 1.1rem 1.25rem; position: relative; overflow: hidden;
}
.kpi-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
}
.kpi-card.indigo::before { background: linear-gradient(90deg, #6366F1, #8B5CF6); }
.kpi-card.green::before  { background: linear-gradient(90deg, #10B981, #059669); }
.kpi-card.amber::before  { background: linear-gradient(90deg, #F59E0B, #D97706); }
.kpi-card.red::before    { background: linear-gradient(90deg, #EF4444, #DC2626); }
.kpi-card.slate::before  { background: linear-gradient(90deg, #64748B, #475569); }
.kpi-label { font-size: 0.65rem; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: 0.8px; }
.kpi-value { font-size: 1.4rem; font-weight: 700; color: #F1F5F9; margin: 0.3rem 0 0; line-height: 1.2; }
.kpi-sub   { font-size: 0.7rem; color: #6B7280; margin-top: 0.2rem; }

/* ── Status badges ── */
.status-pill {
  display: inline-flex; align-items: center; gap: 6px;
  border-radius: 999px; padding: 5px 14px; font-size: 0.8rem; font-weight: 600;
}
.status-supported   { background: rgba(16,185,129,0.15); color: #10B981; border: 1px solid rgba(16,185,129,0.3); }
.status-contradicted{ background: rgba(239,68,68,0.15);  color: #EF4444; border: 1px solid rgba(239,68,68,0.3); }
.status-nei         { background: rgba(245,158,11,0.15); color: #F59E0B; border: 1px solid rgba(245,158,11,0.3); }

/* ── Verdict banner ── */
.verdict-banner {
  border-radius: 20px; padding: 2rem; text-align: center; margin: 1.5rem 0;
}
.verdict-supported   { background: rgba(16,185,129,0.08);  border: 2px solid rgba(16,185,129,0.4); }
.verdict-contradicted{ background: rgba(239,68,68,0.08);   border: 2px solid rgba(239,68,68,0.4); }
.verdict-nei         { background: rgba(245,158,11,0.08);  border: 2px solid rgba(245,158,11,0.4); }
.verdict-banner .v-icon  { font-size: 2.5rem; margin-bottom: 0.5rem; }
.verdict-banner .v-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1.5px; color: #64748B; }
.verdict-banner .v-title { font-size: 2rem; font-weight: 800; letter-spacing: -0.5px; margin: 0.25rem 0; }
.verdict-banner .v-reason{ font-size: 0.9rem; color: #94A3B8; max-width: 640px; margin: 0 auto; line-height: 1.6; }
.verdict-supported   .v-title { color: #10B981; }
.verdict-contradicted .v-title{ color: #EF4444; }
.verdict-nei          .v-title{ color: #F59E0B; }

/* ── Pipeline steps ── */
.pipeline { display: flex; flex-direction: column; gap: 0; }
.pipe-step {
  display: flex; gap: 1rem; align-items: flex-start; position: relative; padding-bottom: 1.5rem;
}
.pipe-step:last-child { padding-bottom: 0; }
.pipe-step:not(:last-child) .pipe-connector {
  position: absolute; left: 17px; top: 38px; width: 2px;
  background: linear-gradient(180deg, #6366F1 0%, #1F2937 100%);
  height: calc(100% - 20px);
}
.pipe-icon {
  width: 36px; height: 36px; border-radius: 10px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 15px;
  position: relative; z-index: 1;
}
.pipe-icon.done    { background: rgba(16,185,129,0.2);  border: 1.5px solid rgba(16,185,129,0.5); }
.pipe-icon.active  { background: rgba(99,102,241,0.2);  border: 1.5px solid #6366F1; }
.pipe-icon.pending { background: rgba(100,116,139,0.1); border: 1.5px solid #1F2937; }
.pipe-body { flex: 1; }
.pipe-name   { font-size: 0.85rem; font-weight: 600; color: #E2E8F0; }
.pipe-detail { font-size: 0.75rem; color: #64748B; margin-top: 2px; }

/* ── Chips ── */
.chip {
  display: inline-flex; align-items: center; gap: 4px;
  border-radius: 6px; padding: 3px 10px; font-size: 0.72rem; font-weight: 500; margin: 2px;
}
.chip-red    { background: rgba(239,68,68,0.12);  color: #EF4444;  border: 1px solid rgba(239,68,68,0.25); }
.chip-amber  { background: rgba(245,158,11,0.12); color: #F59E0B;  border: 1px solid rgba(245,158,11,0.25); }
.chip-green  { background: rgba(16,185,129,0.12); color: #10B981;  border: 1px solid rgba(16,185,129,0.25); }
.chip-indigo { background: rgba(99,102,241,0.12); color: #818CF8;  border: 1px solid rgba(99,102,241,0.25); }
.chip-slate  { background: rgba(100,116,139,0.12);color: #94A3B8;  border: 1px solid rgba(100,116,139,0.25); }

/* ── Image evidence cards ── */
.img-card {
  background: #1F2937; border-radius: 12px; overflow: hidden;
  border: 1px solid #374151; transition: border-color 0.2s;
}
.img-card.supporting { border-color: rgba(16,185,129,0.5); }
.img-card.not-support{ border-color: rgba(239,68,68,0.25); }
.img-card-body { padding: 0.8rem; }
.img-card-id  { font-size: 0.65rem; font-weight: 700; color: #6366F1; text-transform: uppercase; letter-spacing: 0.5px; }
.img-card-desc{ font-size: 0.75rem; color: #94A3B8; margin-top: 4px; line-height: 1.4; }

/* ── Success card ── */
.cs-success-card {
  background: linear-gradient(135deg, rgba(16,185,129,0.08) 0%, rgba(5,150,105,0.04) 100%);
  border: 2px solid rgba(16,185,129,0.4); border-radius: 20px; padding: 2rem; text-align: center; margin: 1.5rem 0;
}
.cs-success-card .cs-big-icon { font-size: 2.5rem; margin-bottom: 0.5rem; }
.cs-success-card .cs-success-title { font-size: 1.4rem; font-weight: 700; color: #10B981; margin-bottom: 0.5rem; }
.cs-success-card .cs-success-sub { font-size: 0.85rem; color: #94A3B8; margin-bottom: 1.25rem; }
.cs-success-metrics {
  display: flex; justify-content: center; gap: 2rem; flex-wrap: wrap; margin: 1rem 0 1.5rem;
}
.cs-success-metric { text-align: center; }
.cs-success-metric .sm-label { font-size: 0.65rem; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: 0.8px; }
.cs-success-metric .sm-value { font-size: 1.1rem; font-weight: 700; color: #F1F5F9; margin-top: 2px; }

/* ── Error card ── */
.cs-error-card {
  background: rgba(239,68,68,0.06); border: 1px solid rgba(239,68,68,0.3);
  border-radius: 16px; padding: 1.5rem; margin: 1rem 0;
}
.cs-error-card .cs-error-icon { font-size: 1.5rem; margin-bottom: 0.25rem; }
.cs-error-card .cs-error-title { font-size: 0.9rem; font-weight: 700; color: #EF4444; margin-bottom: 0.25rem; }
.cs-error-card .cs-error-detail { font-size: 0.8rem; color: #94A3B8; line-height: 1.5; }

/* ── Demo preset cards ── */
.cs-demo-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin: 0.75rem 0; }
.cs-demo-card {
  background: #111827; border: 1px solid #1F2937; border-radius: 12px;
  padding: 1rem; text-align: center; cursor: pointer; transition: border-color 0.2s;
}
.cs-demo-card:hover { border-color: #6366F1; }
.cs-demo-card .cs-demo-icon { font-size: 1.5rem; margin-bottom: 0.25rem; }
.cs-demo-card .cs-demo-label { font-size: 0.75rem; font-weight: 600; color: #E2E8F0; }
.cs-demo-card .cs-demo-sub { font-size: 0.65rem; color: #64748B; margin-top: 2px; }

/* ── CTA button row ── */
.cs-cta-row {
  display: flex; justify-content: center; gap: 1rem; flex-wrap: wrap; margin-top: 1rem;
}

/* ── Progress bar override ── */
[data-testid="stProgress"] > div > div {
  background: linear-gradient(90deg, #6366F1, #8B5CF6) !important; border-radius: 999px !important;
}

/* ── Dividers ── */
.cs-divider { height: 1px; background: #1F2937; margin: 1.5rem 0; }

/* ── Section heading ── */
.cs-section-title {
  font-size: 1rem; font-weight: 700; color: #F1F5F9;
  margin: 1.5rem 0 0.75rem; display: flex; align-items: center; gap: 8px;
}
.cs-section-title::after { content:''; flex:1; height:1px; background:#1F2937; }

/* ── Expander overrides ── */
details { background: #111827 !important; border: 1px solid #1F2937 !important; border-radius: 12px !important; margin-bottom: 8px !important; }
summary { color: #E2E8F0 !important; font-weight: 600 !important; padding: 0.8rem 1rem !important; }

/* ── Tab overrides ── */
[data-testid="stTabs"] [role="tab"] { color: #64748B !important; font-weight: 600 !important; border-bottom: 2px solid transparent !important; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: #818CF8 !important; border-bottom-color: #6366F1 !important; }
[data-testid="stTabsContent"] { border: none !important; padding-top: 1.5rem !important; }

/* ── Upload area ── */
[data-testid="stFileUploader"] {
  background: #111827 !important; border: 2px dashed #374151 !important; border-radius: 14px !important;
}
[data-testid="stFileUploader"]:hover { border-color: #6366F1 !important; }

/* ── Textarea / input ── */
textarea, [data-testid="stTextArea"] textarea {
  background: #111827 !important; color: #E2E8F0 !important;
  border: 1px solid #374151 !important; border-radius: 10px !important; font-size: 0.88rem !important;
}
textarea:focus { border-color: #6366F1 !important; box-shadow: 0 0 0 3px rgba(99,102,241,0.2) !important; }

/* ── Select ── */
[data-testid="stSelectbox"] > div > div {
  background: #111827 !important; border: 1px solid #374151 !important; border-radius: 10px !important; color: #E2E8F0 !important;
}

/* ── Primary button ── */
[data-testid="stButton"] > button[kind="primary"] {
  background: linear-gradient(135deg, #6366F1, #8B5CF6) !important;
  border: none !important; border-radius: 10px !important;
  font-weight: 700 !important; font-size: 0.95rem !important;
  padding: 0.7rem 2rem !important; letter-spacing: 0.3px !important;
  box-shadow: 0 4px 20px rgba(99,102,241,0.35) !important;
  transition: all 0.2s !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover {
  transform: translateY(-1px) !important; box-shadow: 0 6px 28px rgba(99,102,241,0.5) !important;
}
</style>
""", unsafe_allow_html=True)

# ── Component helpers ────────────────────────────────────────────────────────

def topbar():
    st.markdown("""
    <div class="cs-topbar">
      <div class="cs-logo">
        <div class="cs-logo-icon">CS</div>
        <span class="cs-logo-text">Claim<span>Sight</span> AI</span>
      </div>
      <span class="cs-badge">BETA · v1.0</span>
    </div>""", unsafe_allow_html=True)


def hero():
    st.markdown("""
    <div class="cs-hero">
      <h1>Intelligent Claim Verification</h1>
      <p>Multi-modal AI pipeline that analyses damage claims using submitted images,
         conversation context, and evidence standards — in seconds.</p>
    </div>""", unsafe_allow_html=True)


def card(title: str, body: str):
    st.markdown(f"""
    <div class="cs-card">
      <div class="cs-card-title">{title}</div>
      {body}
    </div>""", unsafe_allow_html=True)


def kpi(label: str, value: str, sub: str = "", color: str = "indigo") -> str:
    inner = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (f'<div class="kpi-card {color}">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'{inner}</div>')



def chip(text: str, color: str = "slate") -> str:
    return f'<span class="chip chip-{color}">{text}</span>'


# ── Human-friendly label maps ────────────────────────────────────────────────
_VERDICT_LABELS = {
    "supported":             "Claim Verified",
    "contradicted":          "Claim Does Not Match Evidence",
    "not_enough_information": "More Evidence Needed",
}
_VERDICT_EXPLANATIONS = {
    "supported": (
        "The uploaded images clearly show damage that matches the reported claim. "
        "The affected area was identified and the damage type confirmed."
    ),
    "contradicted": (
        "The images do not show the damage described in the claim. "
        "The affected area was visible, but the reported damage was not found."
    ),
    "not_enough_information": (
        "The submitted evidence is insufficient to confirm or deny the reported damage. "
        "Additional photos or clearer images may be required."
    ),
}
_STAGE_LABELS = {
    "Claim Extraction":  "Understanding the Claim",
    "Vision Review":     "Image Analysis",
    "Evidence Standards": "Evidence Verification",
    "Decision Engine":   "Final Decision",
}
_SUFFICIENCY_LABELS = {
    "fully_met":     "Evidence Verified",
    "partially_met": "Evidence Incomplete",
    "not_met":       "Evidence Missing",
    "unverifiable":  "Unable to Verify",
}

def _humanise_image_id(raw_id: str, index: int) -> str:
    """Convert temp filenames like tmp2m1_e9g_ to 'Image #1'."""
    if raw_id.startswith("tmp") or raw_id.startswith("tmp"):
        return f"Image #{index + 1}"
    # If it looks like a real meaningful name, keep it short
    return raw_id if len(raw_id) <= 20 else f"Image #{index + 1}"

def verdict_banner(status: str, justification: str):
    cfg = {
        "supported":             ("✓", "Claim Verified",                   "verdict-supported",    "VERIFIED"),
        "contradicted":          ("✗", "Claim Does Not Match Evidence",    "verdict-contradicted", "CONTRADICTED"),
        "not_enough_information": ("~", "More Evidence Needed",             "verdict-nei",          "MORE INFO NEEDED"),
    }
    icon, title, css, label = cfg.get(status, ("?", status.replace("_"," ").title(), "verdict-nei", status.upper()))
    explanation = _VERDICT_EXPLANATIONS.get(status, justification)
    st.markdown(f"""
    <div class="verdict-banner {css}">
      <div class="v-icon">{icon}</div>
      <div class="v-label">CLAIM DECISION</div>
      <div class="v-title">{title}</div>
      <p class="v-reason">{explanation}</p>
    </div>""", unsafe_allow_html=True)


def pipeline_step(icon: str, name: str, detail: str, state: str = "done"):
    """state: done | active | pending"""
    return f"""
    <div class="pipe-step">
      <div class="pipe-connector"></div>
      <div class="pipe-icon {state}">{icon}</div>
      <div class="pipe-body">
        <div class="pipe-name">{name}</div>
        <div class="pipe-detail">{detail}</div>
      </div>
    </div>"""


def section_title(icon: str, text: str):
    st.markdown(f'<div class="cs-section-title"><span>{icon}</span>{text}</div>', unsafe_allow_html=True)


def success_card_html(verdict: str, confidence: str, provider: str, latency_ms: int) -> str:
    icon = {"supported": "✓", "contradicted": "✗", "not_enough_information": "~"}.get(verdict, "?")
    status_label = _VERDICT_LABELS.get(verdict, verdict.replace("_", " ").title())
    color = "green" if verdict == "supported" else "red" if verdict == "contradicted" else "amber"
    return f"""
    <div class="cs-success-card" style="border-color:rgba({','.join({'green':'16,185,129','red':'239,68,68','amber':'245,158,11'}.get(color,'100,116,139'))},0.4)">
      <div style="font-size:2.5rem;margin-bottom:0.5rem">{icon}</div>
      <div style="font-size:0.7rem;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:#64748B">CLAIM DECISION</div>
      <div style="font-size:1.8rem;font-weight:800;letter-spacing:-0.5px;margin:0.25rem 0;color:#{({'green':'10B981','red':'EF4444','amber':'F59E0B'}.get(color,'94A3B8'))}">{status_label}</div>
      <div class="cs-success-metrics">
        <div class="cs-success-metric"><div class="sm-label">Latency</div><div class="sm-value">{latency_ms}ms</div></div>
        <div class="cs-success-metric"><div class="sm-label">AI Model</div><div class="sm-value">Active ✓</div></div>
      </div>
    </div>"""


def error_card_html(title: str, detail: str, icon: str = "⚠️") -> str:
    return f"""
    <div class="cs-error-card">
      <div class="cs-error-icon">{icon}</div>
      <div class="cs-error-title">{title}</div>
      <div class="cs-error-detail">{detail}</div>
    </div>"""


# ── Pipeline runner ───────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=3600)
def _cached_claim_extraction(user_claim: str, claim_object: str) -> dict:
    from agents.claim_agent import ClaimExtractionAgent
    from models.claim_extraction import ClaimExtractionInput
    from models.enums import ClaimObject
    agent = ClaimExtractionAgent()
    try:
        obj = ClaimObject(claim_object)
    except ValueError:
        obj = ClaimObject.CAR
    result = agent.extract(ClaimExtractionInput(user_claim=user_claim, claim_object=obj))
    return result.model_dump(mode="json")


def run_pipeline(image_files: list, user_claim: str, claim_object: str) -> dict:
    _t0 = time.time()
    from agents.vision_agent import VisionReviewAgent
    from models.claim_extraction import ClaimExtractionInput
    from models.enums import ClaimObject, IssueType, ObjectPart
    from models.records import ClaimInput, ParsedClaim
    from models.vision_review import VisionReviewInput
    from services.decision_service import DecisionService
    from services.evidence_standards_engine import EvidenceStandardsEngine
    from services.model_service import ModelService

    # Use cached settings if available, otherwise construct
    _sess_settings = st.session_state.get("_settings")
    if _sess_settings is not None:
        settings = _sess_settings
    else:
        from config import Settings
        settings = Settings(repo_root=_REPO_DIR)

    # Save uploaded images
    tmp_paths, img_names = [], []
    img_bytes_map = {}
    for f in image_files:
        try:
            raw = f.read()
        except Exception:
            raise RuntimeError("Failed to read uploaded file.")
        suffix = Path(f.name).suffix or ".jpg"
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(raw)
            tmp.close()
            tmp_paths.append(Path(tmp.name))
            img_names.append(f.name)
            img_bytes_map[f.name] = raw
        except OSError as exc:
            raise RuntimeError(f"Failed to save uploaded file: {exc}") from exc

    try:
        # Stage A
        try:
            obj = ClaimObject(claim_object)
        except ValueError:
            obj = ClaimObject.CAR

        from agents.claim_agent import ClaimExtractionAgent
        extr_data = _cached_claim_extraction(user_claim, claim_object)
        from models.claim_extraction import ExtractedClaim
        extraction = ExtractedClaim.model_validate(extr_data)

        # Stage B
        model_svc = ModelService(settings=settings) if settings.has_vision_model else None
        vision_agent = VisionReviewAgent(model_service=model_svc)

        if tmp_paths:
            vision_result = vision_agent.review(VisionReviewInput(
                image_paths=tmp_paths,
                claim_object=obj,
                claimed_part=extraction.claimed_object_part,
                claimed_issue=extraction.claimed_issue_type,
                is_multi_part=extraction.is_multi_part,
            ))
        else:
            from models.vision_review import VisionReviewResult
            from models.enums import RiskFlag
            vision_result = VisionReviewResult(
                valid_image=False, quality_flags=[RiskFlag.MANUAL_REVIEW_REQUIRED],
                reasoning="No images uploaded.",
            )

        # Stage C
        evidence_engine = EvidenceStandardsEngine()
        evidence_engine.load(_REPO_DIR / "dataset" / "evidence_requirements.csv")
        evidence_result = evidence_engine.evaluate_from_vision(
            vision_result=vision_result,
            claim_object=str(obj),
            claimed_part=str(extraction.claimed_object_part),
            claimed_issue=str(extraction.claimed_issue_type),
            is_multi_part=extraction.is_multi_part,
        )

        # Stage D
        decision_svc = DecisionService()
        claim_input = ClaimInput(
            user_id="demo_user",
            image_paths=";".join(img_names) if img_names else "none",
            user_claim=user_claim, claim_object=obj,
        )
        parsed = ParsedClaim(
            claim_object=obj,
            claimed_issue=extraction.claimed_issue_type,
            claimed_part=extraction.claimed_object_part,
            is_multi_part=extraction.is_multi_part,
        )
        output = decision_svc.decide(
            claim=claim_input, parsed_claim=parsed,
            vision=vision_result, evidence=evidence_result,
        )

        provider = "No model"
        if settings.has_vision_model:
            provider = f"openrouter/{settings.openrouter_model_primary.split('/')[-1]}"

        _latency = round((time.time() - _t0) * 1000)

        return dict(
            extraction=extraction,
            vision=vision_result,
            evidence=evidence_result,
            output=output,
            has_model=settings.has_vision_model,
            provider=provider,
            img_bytes_map=img_bytes_map,
            latency_ms=_latency,
            _timestamp=datetime.now(tz=UTC).isoformat(),
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Dataset file not found: {exc}") from exc
    except ImportError as exc:
        raise RuntimeError(f"Missing dependency: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc
    finally:
        for p in tmp_paths:
            try: p.unlink()
            except OSError: pass

# ── AI Progress simulation ────────────────────────────────────────────────────

def show_progress(placeholder, provider: str = ""):
    steps = [
        ("🔍", "Understanding the Claim",  "Reading the conversation and identifying the reported damage…", 0.20),
        ("👁",  "Analysing Images",          "AI is reviewing the submitted evidence photos…",               0.45),
        ("📋", "Verifying Evidence",        "Checking if the evidence meets the required standards…",       0.68),
        ("⚖️",  "Assessing Risk",            "Reviewing image quality and claim history…",                   0.87),
        ("✓",  "Finalising Decision",       "Generating the claim decision…",                              1.00),
    ]
    for icon, name, detail, pct in steps:
        with placeholder.container():
            st.markdown(f"""
            <div class="cs-card" style="text-align:center;padding:1.8rem;">
              <div style="font-size:1.8rem;margin-bottom:0.3rem">{icon}</div>
              <div style="font-size:1rem;font-weight:700;color:#E2E8F0;margin-bottom:0.15rem">{name}</div>
              <div style="font-size:0.75rem;color:#64748B;margin-bottom:0.75rem">{detail}</div>
            </div>""", unsafe_allow_html=True)
            st.progress(pct)
        time.sleep(0.5)


# ── Main layout ───────────────────────────────────────────────────────────────

topbar()

# ── Pre-init session state (must happen before sidebar renders) ──────────────
if "debug_mode" not in st.session_state:
    st.session_state["debug_mode"] = False
if "_initialized" not in st.session_state:
    st.session_state["_initialized"] = True
    st.session_state["_focus_results"] = False
    st.session_state["_focus_trace"] = False
    st.session_state["_last_analysis_ts"] = 0
    st.session_state["_claims_reviewed"] = 0


# ── Graceful dependency failure gate ─────────────────────────────────────────
if _DEPLOYMENT_ERROR:
    st.markdown(_DEPLOYMENT_ERROR, unsafe_allow_html=True)
    st.stop()

_Cfg = None
try:
    from config import Settings as _Cfg
except Exception:
    _Cfg = None

# All models the system can use — confirmed working first
_ALL_MODELS = [
    ("meta-llama/llama-3.2-11b-vision-instruct",  "Llama 3.2 11B Vision", "T1 · active"),
    ("anthropic/claude-3-haiku",                   "Claude 3 Haiku",        "T2 · active"),
    ("qwen/qwen2.5-vl-72b-instruct",               "Qwen 2.5 VL 72B",       "T3 · active"),
    ("openai/gpt-4o-mini",                         "GPT-4o Mini",           "optional"),
    ("openai/gpt-4o",                              "GPT-4o",                "optional"),
    ("google/gemma-4-26b-a4b-it:free",             "Gemma 4 26B",           "free tier"),
    ("nvidia/nemotron-nano-12b-v2-vl:free",        "Nemotron VL 12B",       "free tier"),
]

@st.cache_data(show_spinner=False, ttl=300)   # cache 5 min
def _probe_models(api_key: str, backup_key: str) -> dict:
    """Live-probe each model with a tiny image. Returns {slug: 'ok'|'error:...'|'no_key'}."""
    import base64, io, requests as _req
    from PIL import Image as _Img

    if not api_key:
        return {m[0]: "no_key" for m in _ALL_MODELS}

    buf = io.BytesIO()
    _Img.new("RGB", (8, 8), (120, 80, 40)).save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    data_url = f"data:image/jpeg;base64,{b64}"

    URL = "https://openrouter.ai/api/v1/chat/completions"
    results = {}
    for slug, _label, _tier in _ALL_MODELS:
        ok = False
        for key in ([api_key] + ([backup_key] if backup_key else [])):
            if ok:
                break
            hdrs = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "X-Title": "ClaimSight AI - Status Check",
            }
            payload = {
                "model": slug,
                "max_tokens": 16,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": "Reply with the word ok only."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]}],
            }
            try:
                r = _req.post(URL, json=payload, headers=hdrs, timeout=12)
                if r.status_code == 200:
                    ok = True
                    results[slug] = "ok"
                elif r.status_code == 404:
                    results[slug] = "error:not_found"
                    break   # 404 = model doesn't exist, no point trying backup
                else:
                    err = r.json().get("error", {}).get("message", str(r.status_code))[:60]
                    results[slug] = f"error:{err}"
            except Exception as exc:
                results[slug] = f"error:{str(exc)[:50]}"
        if slug not in results:
            results[slug] = "error:unknown"
    return results

# ── Build sidebar ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <style>
    [data-testid="stSidebar"] { background: #0D1117 !important; border-right: 1px solid #1F2937; }
    .ms-header { font-size: 0.65rem; font-weight: 700; color: #6366F1;
                 text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 0.75rem; }
    .ms-row {
      display: flex; align-items: center; justify-content: space-between;
      padding: 0.55rem 0.75rem; border-radius: 10px; margin-bottom: 6px;
      background: #111827; border: 1px solid #1F2937;
      transition: border-color 0.2s;
    }
    .ms-row:hover { border-color: #374151; }
    .ms-row.active { border-color: rgba(99,102,241,0.4); background: rgba(99,102,241,0.06); }
    .ms-left { display: flex; flex-direction: column; gap: 1px; }
    .ms-name { font-size: 0.78rem; font-weight: 600; color: #E2E8F0; }
    .ms-tier { font-size: 0.62rem; color: #475569; }
    .ms-dot-ok  { width: 10px; height: 10px; border-radius: 50%;
                  background: #10B981; box-shadow: 0 0 6px rgba(16,185,129,0.6);
                  flex-shrink: 0; }
    .ms-dot-err { width: 10px; height: 10px; border-radius: 50%;
                  background: #EF4444; box-shadow: 0 0 6px rgba(239,68,68,0.5);
                  flex-shrink: 0; }
    .ms-dot-pending { width: 10px; height: 10px; border-radius: 50%;
                      background: #F59E0B; flex-shrink: 0; }
    .ms-dot-nokey { width: 10px; height: 10px; border-radius: 50%;
                    background: #374151; flex-shrink: 0; }
    .ms-err-text { font-size: 0.6rem; color: #6B7280; margin-top: 2px;
                   max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .ms-divider { height: 1px; background: #1F2937; margin: 0.75rem 0; }
    .ms-legend { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 0.5rem; }
    .ms-legend-item { display: flex; align-items: center; gap: 5px;
                      font-size: 0.62rem; color: #64748B; }
    </style>
    """, unsafe_allow_html=True)

    # ── Developer Mode toggle — TOP of sidebar, always visible ─────────
    _dev_mode_on = st.toggle(
        "⚙️ Developer Mode",
        key="debug_mode",
        help="Show technical details: internal field names, raw values, model names, confidence scores, requirement IDs.",
    )
    if _dev_mode_on:
        st.markdown(
            '<div style="font-size:0.62rem;color:#6366F1;margin-bottom:0.25rem;padding:4px 8px;'
            'background:rgba(99,102,241,0.08);border-radius:6px;border:1px solid rgba(99,102,241,0.2)">'
            '⚙️ Developer details visible</div>',
            unsafe_allow_html=True
        )
    st.markdown('<div class="ms-divider"></div>', unsafe_allow_html=True)

    # Claims reviewed this session counter
    _n_reviewed = st.session_state.get("_claims_reviewed", 0)
    if _n_reviewed > 0:
        st.markdown(
            f'<div style="font-size:0.65rem;color:#475569;margin-bottom:0.5rem">'
            f'📋 {_n_reviewed} claim{"s" if _n_reviewed > 1 else ""} reviewed this session</div>',
            unsafe_allow_html=True
        )

    st.markdown('<div class="ms-header">🤖 Model Availability</div>', unsafe_allow_html=True)

    _s_side = None
    _key_pool_side: list[str] = []
    if _Cfg is not None:
        try:
            _s_side = _Cfg(repo_root=_REPO_DIR)
            _key_pool_side = _s_side.openrouter_key_pool
            st.session_state["_settings"] = _s_side
        except Exception:
            pass

    # Configured tiers from settings
    _configured_primary   = (_s_side.openrouter_model_primary   if _s_side else "")
    _configured_secondary = (_s_side.openrouter_model_secondary if _s_side else "")
    _configured_tertiary  = (_s_side.openrouter_model_tertiary  if _s_side else "")

    # Show pool size
    _pool_count = len(_key_pool_side)
    if _pool_count > 0:
        st.markdown(
            f'<div style="font-size:0.65rem;color:#475569;margin-bottom:0.5rem">'
            f'🔑 {_pool_count} key{"s" if _pool_count>1 else ""} in pool · instant rotation on 402/429'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Probe button + cached results
    do_probe = st.button("⟳  Check Status", use_container_width=True)
    if do_probe:
        _probe_models.clear()   # bust cache on manual refresh

    probe_results: dict = {}
    _primary_key = _key_pool_side[0] if _key_pool_side else ""
    _backup_keys = ",".join(_key_pool_side[1:]) if len(_key_pool_side) > 1 else ""
    if _primary_key:
        with st.spinner(f"Probing models across {_pool_count} key(s)…"):
            probe_results = _probe_models(_primary_key, _backup_keys)
    else:
        probe_results = {m[0]: "no_key" for m in _ALL_MODELS}

    # Render rows
    any_ok = False
    rows_html = ""
    for slug, label, tier in _ALL_MODELS:
        status = probe_results.get(slug, "pending")

        # Determine which tier this is currently configured as
        if slug == _configured_primary:
            tier_label = "Active · T1"
            active_cls = " active"
        elif slug == _configured_secondary:
            tier_label = "Active · T2"
            active_cls = " active"
        elif slug == _configured_tertiary:
            tier_label = "Active · T3"
            active_cls = " active"
        else:
            tier_label = tier
            active_cls = ""

        if status == "ok":
            dot_cls = "ms-dot-ok"
            status_txt = ""
            any_ok = True
        elif status == "no_key":
            dot_cls = "ms-dot-nokey"
            status_txt = '<div class="ms-err-text">no API key</div>'
        elif status.startswith("error:"):
            dot_cls = "ms-dot-err"
            err_msg = status[6:][:38]
            status_txt = f'<div class="ms-err-text">{err_msg}</div>'
        else:
            dot_cls = "ms-dot-pending"
            status_txt = ""

        rows_html += f"""
        <div class="ms-row{active_cls}">
          <div class="ms-left">
            <div class="ms-name">{label}</div>
            <div class="ms-tier">{tier_label}</div>
            {status_txt}
          </div>
          <div class="{dot_cls}"></div>
        </div>"""

    st.markdown(rows_html, unsafe_allow_html=True)

    # Legend
    st.markdown("""
    <div class="ms-divider"></div>
    <div class="ms-legend">
      <div class="ms-legend-item"><div class="ms-dot-ok"></div> Available</div>
      <div class="ms-legend-item"><div class="ms-dot-err"></div> Error / credits</div>
      <div class="ms-legend-item"><div class="ms-dot-nokey"></div> No key set</div>
    </div>
    <div style="font-size:0.6rem;color:#374151;margin-top:0.5rem">
      Highlighted rows = currently active tiers<br>
      Probed live · cached 5 min
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="ms-divider"></div>', unsafe_allow_html=True)

    # Overall system status pill
    if not _key_pool_side:
        st.markdown(
            '<span class="chip chip-amber" style="width:100%;justify-content:center">● PREFLIGHT MODE</span>',
            unsafe_allow_html=True,
        )
        st.caption("Set OPENROUTER_API_KEY to enable vision")
    elif any_ok:
        st.markdown(
            '<span class="chip chip-green" style="width:100%;justify-content:center">● VISION READY</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="chip chip-red" style="width:100%;justify-content:center">● ALL MODELS DOWN</span>',
            unsafe_allow_html=True,
        )

    # Model selector dropdown — lets user pick which model to use for this session
    st.markdown('<div class="ms-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="ms-header">Select Active Model</div>', unsafe_allow_html=True)
    available_models = [s for s, *_ in _ALL_MODELS if probe_results.get(s) == "ok"]
    all_model_labels = [
        f"{'✅' if probe_results.get(s)=='ok' else '🔴'} {lbl} ({tier})"
        for s, lbl, tier in _ALL_MODELS
    ]
    all_model_slugs = [s for s, *_ in _ALL_MODELS]

    try:
        _default_idx = all_model_slugs.index(_configured_primary)
    except ValueError:
        _default_idx = 0

    _selected_label = st.selectbox(
        "Vision model",
        options=all_model_labels,
        index=_default_idx,
        label_visibility="collapsed",
        key="model_selector",
    )
    _selected_slug = all_model_slugs[all_model_labels.index(_selected_label)]

    if _s_side is not None and _selected_slug != _configured_primary:
        try:
            import os as _os2
            _os2.environ["OPENROUTER_MODEL_PRIMARY"] = _selected_slug
            from config import Settings as _CfgNew
            st.session_state["_settings"] = _CfgNew(repo_root=_REPO_DIR)
        except Exception:
            pass

    # ── Developer Mode toggle moved to TOP (see above) ──────────────
    # Remove old toggle position — it's now at the top of the sidebar

# ── Session state hardening (remaining fields only) ─────────────────────────
# Note: debug_mode and _initialized are pre-inited above the sidebar

# ── Tabs ─────────────────────────────────────────────────────────────────────
import os as _os
_DEMO_MODE = _os.environ.get("DEMO_MODE", "false").lower() == "true"

if _DEMO_MODE:
    tab_review, tab_results, tab_trace, tab_debug = st.tabs(
        ["⬡  Claim Review", "◈  Results", "◉  Decision Trace", "🔬  Debug Pipeline"]
    )
else:
    tab_review, tab_results, tab_trace = st.tabs(
        ["⬡  Claim Review", "◈  Results", "◉  Decision Trace"]
    )
    tab_debug = None

# ═══════════════════════════════════════════════════════════════
# TAB 1 — CLAIM REVIEW
# ═══════════════════════════════════════════════════════════════
with tab_review:
    hero()

    col_left, col_right = st.columns([3, 2], gap="large")

    with col_left:
        st.markdown('<div class="cs-card-title" style="font-size:0.7rem;color:#6366F1;font-weight:700;letter-spacing:1px;text-transform:uppercase">SUBMIT CLAIM FOR REVIEW</div>', unsafe_allow_html=True)

        uploaded_files = st.file_uploader(
            "Upload damage images",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            help="Upload one or more images showing the claimed damage.",
        )

        if uploaded_files:
            cols = st.columns(min(len(uploaded_files), 4))
            for i, f in enumerate(uploaded_files):
                f.seek(0)
                cols[i % 4].image(f.read(), caption=Path(f.name).stem, use_container_width=True)
                f.seek(0)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        user_claim = st.text_area(
            "Claim Conversation",
            height=160,
            placeholder="Customer: The rear bumper has a deep dent after a collision.\nSupport: Which part was affected?\nCustomer: Rear bumper. Photos attached.",
            label_visibility="visible",
        )

        col_obj, col_btn = st.columns([2, 1])
        with col_obj:
            claim_object = st.selectbox(
                "Object Type",
                options=["car", "laptop", "package"],
                label_visibility="visible",
            )
        with col_btn:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            analyze = st.button("Analyse →", type="primary", use_container_width=True)

    with col_right:
        st.markdown("""
        <div class="cs-card">
          <div class="cs-card-title">HOW IT WORKS</div>
          <div class="pipeline">
            <div class="pipe-step">
              <div class="pipe-connector"></div>
              <div class="pipe-icon done">1</div>
              <div class="pipe-body">
                <div class="pipe-name">Understanding the Claim</div>
                <div class="pipe-detail">Reads the conversation and identifies the reported damage</div>
              </div>
            </div>
            <div class="pipe-step">
              <div class="pipe-connector"></div>
              <div class="pipe-icon done">2</div>
              <div class="pipe-body">
                <div class="pipe-name">Image Analysis</div>
                <div class="pipe-detail">AI reviews every submitted photo for damage evidence</div>
              </div>
            </div>
            <div class="pipe-step">
              <div class="pipe-connector"></div>
              <div class="pipe-icon done">3</div>
              <div class="pipe-body">
                <div class="pipe-name">Evidence Verification</div>
                <div class="pipe-detail">Checks if the photos meet the required evidence standards</div>
              </div>
            </div>
            <div class="pipe-step">
              <div class="pipe-icon done">4</div>
              <div class="pipe-body">
                <div class="pipe-name">Final Decision</div>
                <div class="pipe-detail">Verified · Does Not Match · More Evidence Needed</div>
              </div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="cs-card">
          <div class="cs-card-title">CAPABILITIES</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;">
        """ +
        chip("Car damage", "indigo") + chip("Laptop damage", "indigo") +
        chip("Package damage", "indigo") + chip("Multi-image", "slate") +
        chip("Injection detection", "amber") + chip("3-tier fallback", "green") +
        chip("Content-addressed cache", "slate") + chip("12 issue types", "slate") +
        """
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Demo mode presets ──────────────────────────────────────
    if _DEMO_MODE:
        st.markdown("""
        <div class="cs-card" style="margin-top:0.5rem">
          <div class="cs-card-title">⚡ QUICK DEMO</div>
          <div style="font-size:0.8rem;color:#94A3B8;margin-bottom:0.75rem">
            Load a pre-configured claim scenario with a single click.
          </div>
        </div>""", unsafe_allow_html=True)
        col_d1, col_d2, col_d3 = st.columns(3)
        try:
            from models.enums import ClaimObject, IssueType, ObjectPart
        except Exception:
            pass
        for col, scenario in [
            (col_d1, ("supported", "car", "rear_bumper", "Customer: The rear bumper has a visible dent after a minor collision.\nSupport: Can you describe the damage?\nCustomer: Yes, there's a clear dent on the right side of the rear bumper about 10cm wide.")),
            (col_d2, ("contradicted", "car", "front_bumper", "Customer: The front bumper has a large crack after a parking incident.\nSupport: Where exactly is the damage?\nCustomer: Middle of the front bumper. I can see the crack clearly.")),
            (col_d3, ("not_enough_information", "laptop", "screen", "Customer: I think my laptop screen might be damaged but I'm not sure.\nSupport: Can you describe what you see?\nCustomer: It looks a bit strange but I can't tell if it's cracked or just dirty.")),
        ]:
            with col:
                if st.button(f"🔄 {scenario[0].replace('_', ' ').title()}", key=f"demo_{scenario[0]}", use_container_width=True):
                    st.session_state["_demo_claim"] = scenario[3]
                    st.session_state["_demo_object"] = scenario[1]
                    st.rerun()

    # ── Load demo scenario if set ──
    if st.session_state.get("_demo_claim"):
        user_claim = st.session_state["_demo_claim"]
        claim_object = st.session_state.get("_demo_object", "car")
        st.session_state["_demo_claim"] = ""
        # Trigger analysis automatically
        analyze_demo = True
    else:
        analyze_demo = False

    # Process claim
    if analyze or analyze_demo:
        if not user_claim.strip():
            st.error("Please enter a claim conversation before analysing.")
        else:
            provider_name = "No model"
            try:
                _s = st.session_state.get("_settings")
                if _s and _s.has_vision_model:
                    provider_name = f"openrouter/{_s.openrouter_model_primary.split('/')[-1]}"
            except Exception:
                pass
            progress_placeholder = st.empty()
            show_progress(progress_placeholder, provider=provider_name)
            progress_placeholder.empty()

            with st.spinner(""):
                try:
                    result = run_pipeline(uploaded_files or [], user_claim, claim_object)
                    st.session_state["result"] = result
                    st.session_state["_last_analysis_ts"] = time.time()
                    st.session_state["_claims_reviewed"] = st.session_state.get("_claims_reviewed", 0) + 1

                    # Show inline success card
                    r = result
                    out = r["output"]
                    vision = r["vision"]
                    status = str(out.claim_status)
                    conf_pct = f"{vision.confidence * 100:.0f}%"
                    prov = r.get("provider", "unknown")
                    lat = r.get("latency_ms", 0)

                    st.markdown(success_card_html(status, conf_pct, prov, lat), unsafe_allow_html=True)
                    st.toast("✓ Analysis complete!", icon="✅")

                    # CTA buttons
                    c1, c2, _ = st.columns([1, 1, 2])
                    with c1:
                        if st.button("◈  View Results →", key="goto_results", type="primary", use_container_width=True):
                            st.session_state["_focus_results"] = True
                            st.rerun()
                    with c2:
                        if st.button("◉  View Decision Trace →", key="goto_trace", use_container_width=True):
                            st.session_state["_focus_trace"] = True
                            st.rerun()

                except RuntimeError as exc:
                    err_msg = str(exc)
                    if "FileNotFoundError" in err_msg or "not found" in err_msg.lower():
                        st.markdown(error_card_html("Dataset Error", "A required data file could not be found. Please check that the dataset files are in place."), unsafe_allow_html=True)
                    elif "Missing dependency" in err_msg or "ImportError" in err_msg:
                        st.markdown(error_card_html("Missing Dependency", f"The required package could not be imported: {err_msg}. Run: pip install -r requirements.txt"), unsafe_allow_html=True)
                    elif "API key" in err_msg.lower() or "not authorized" in err_msg.lower() or "permission" in err_msg.lower():
                        st.markdown(error_card_html("Provider Authentication Error", "The AI provider could not authenticate. Please check your API key configuration."), unsafe_allow_html=True)
                    elif "Failed to read" in err_msg or "Failed to save" in err_msg:
                        st.markdown(error_card_html("Image Processing Error", err_msg), unsafe_allow_html=True)
                    else:
                        st.markdown(error_card_html("Pipeline Error", f"An error occurred during analysis: {err_msg[:200]}"), unsafe_allow_html=True)
                except Exception as exc:
                    st.markdown(error_card_html("Unexpected Error", f"An unexpected issue occurred. Please try again. ({type(exc).__name__})"), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# TAB 2 — RESULTS
# ═══════════════════════════════════════════════════════════════
with tab_results:
    if st.session_state.get("_focus_results"):
        st.session_state["_focus_results"] = False
        st.toast("✓ Results ready", icon="◈")

    if "result" not in st.session_state:
        st.markdown("""
        <div class="cs-card" style="text-align:center;padding:3rem;">
          <div style="font-size:3rem;margin-bottom:1rem">◈</div>
          <div style="font-size:1rem;font-weight:600;color:#94A3B8;">
            Submit a claim in the <strong style="color:#818CF8">Claim Review</strong> tab to see results here.
          </div>
        </div>""", unsafe_allow_html=True)
    else:
        r = st.session_state["result"]
        out = r["output"]
        vision = r["vision"]
        evidence = r["evidence"]
        extraction = r["extraction"]
        provider = r.get("provider", "unknown")
        img_bytes_map = r.get("img_bytes_map", {})

        status = str(out.claim_status)

        # ── Verdict banner ────────────────────────────────────────
        verdict_banner(status, str(out.claim_status_justification))

        # ── KPI row ───────────────────────────────────────────────
        section_title("◆", "Decision Metrics")
        severity_color = {"high": "red", "medium": "amber", "low": "green", "none": "slate"}.get(
            str(out.severity).lower(), "slate"
        )
        esm = str(out.evidence_standard_met).lower() == "true"
        conf_pct = f"{vision.confidence * 100:.0f}%"

        _debug = st.session_state.get("debug_mode", False)
        # Human-friendly sufficiency label
        _suf_label = _SUFFICIENCY_LABELS.get(str(evidence.sufficiency_level).lower(), str(evidence.sufficiency_level).replace("_"," ").title())

        # ── KPI grid: normal users see 3 clean cards; devs see all ────────────
        kpis_html = '<div class="kpi-grid">'
        # Always visible
        kpis_html += kpi("Decision",     _VERDICT_LABELS.get(status, status.replace("_"," ").title()), "", "green" if status == "supported" else "red" if status == "contradicted" else "amber")
        kpis_html += kpi("Damage Found", str(out.issue_type).replace("_", " ").title(), str(out.issue_type) if _debug else "", "indigo")
        kpis_html += kpi("Location",     str(out.object_part).replace("_", " ").title(), str(out.object_part) if _debug else "", "indigo")
        # Developer mode only
        if _debug:
            kpis_html += kpi("Severity",       str(out.severity).title(), "", severity_color)
            kpis_html += kpi("Evidence Status", _suf_label, str(evidence.sufficiency_level), "green" if esm else "red")
            lat_ms = r.get("latency_ms", 0)
            kpis_html += kpi("Latency",        f"{lat_ms}ms" if lat_ms else "—", "", "indigo")
            kpis_html += kpi("Confidence",     conf_pct, provider, "indigo")
            kpis_html += kpi("Risk Flags",     str(out.risk_flags), "", "amber")
        kpis_html += '</div>'
        st.markdown(kpis_html, unsafe_allow_html=True)

        # ── Debug raw data expander ────────────────────────────────
        if _debug:
            with st.expander("⚙️ Raw Output Fields (Developer Mode)", expanded=False):
                st.code(f"""claim_status          = {out.claim_status!r}
claim_status_justification = {str(out.claim_status_justification)[:300]!r}
issue_type             = {out.issue_type!r}
object_part            = {out.object_part!r}
severity               = {out.severity!r}
evidence_standard_met  = {out.evidence_standard_met!r}
evidence_standard_met_reason = {str(out.evidence_standard_met_reason)[:200]!r}
risk_flags             = {out.risk_flags!r}
supporting_image_ids   = {out.supporting_image_ids!r}
valid_image            = {out.valid_image!r}
confidence             = {vision.confidence!r}
object_visible         = {vision.object_visible!r}
object_part_visible    = {vision.object_part_visible!r}
issue_visible          = {vision.issue_visible!r}
sufficiency_level      = {evidence.sufficiency_level!r}
provider               = {provider!r}
""", language="python")

        # ── Evidence assessment ────────────────────────────────────
        section_title("◈", "Evidence Assessment")
        col_e1, col_e2 = st.columns([1, 1])
        _suf_display = _SUFFICIENCY_LABELS.get(str(evidence.sufficiency_level).lower(), str(evidence.sufficiency_level).replace("_"," ").title())
        with col_e1:
            _ev_detail = str(out.evidence_standard_met_reason)[:300] if _debug else ""
            st.markdown(f"""
            <div class="cs-card">
              <div class="cs-card-title">EVIDENCE STATUS</div>
              <div style="margin-bottom:0.5rem">
                {'<span class="chip chip-green">● Verified</span>' if esm else '<span class="chip chip-red">● Not Verified</span>'}
                <span style="font-size:0.75rem;color:#64748B;margin-left:8px">{_suf_display}</span>
              </div>
              <div style="font-size:0.8rem;color:#94A3B8;line-height:1.6">{_ev_detail}</div>
            </div>""", unsafe_allow_html=True)
        with col_e2:
            flags_raw = str(out.risk_flags)
            flags = [f.strip() for f in flags_raw.split(";") if f.strip() and f.strip() != "none"]
            flag_danger = {"possible_manipulation", "wrong_object", "text_instruction_present", "non_original_image"}
            flag_warn   = {"blurry_image", "cropped_or_obstructed", "low_light_or_glare", "wrong_angle", "user_history_risk", "manual_review_required", "damage_not_visible"}
            # User-friendly flag labels
            _flag_friendly = {
                "damage_not_visible": "Damage not visible",
                "wrong_object": "Wrong item in image",
                "wrong_object_part": "Different area shown",
                "blurry_image": "Image quality: blurry",
                "low_light_or_glare": "Image quality: lighting",
                "wrong_angle": "Image quality: angle",
                "cropped_or_obstructed": "Image quality: obstructed",
                "manual_review_required": "Manual review needed",
                "claim_mismatch": "Damage type mismatch",
                "text_instruction_present": "⚠️ Suspicious text in image",
                "non_original_image": "⚠️ Possible non-original image",
                "possible_manipulation": "⚠️ Possible manipulation",
                "user_history_risk": "Elevated claim history",
            }
            chips_html = ""
            for f in (flags or ["none"]):
                c = "red" if f in flag_danger else "amber" if f in flag_warn else "slate"
                display_f = _flag_friendly.get(f, f.replace("_", " ").title()) if not _debug else f.replace("_", " ")
                chips_html += chip(display_f, c)
            st.markdown(f"""
            <div class="cs-card">
              <div class="cs-card-title">QUALITY SIGNALS</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">{chips_html}</div>
              {'<div style="margin-top:1rem;font-size:0.75rem;color:#64748B">No issues detected</div>' if not flags else ''}
            </div>""", unsafe_allow_html=True)

        # ── Image evidence cards ───────────────────────────────────
        if img_bytes_map:
            section_title("🖼", "Image Evidence")
            supporting_ids = set(vision.supporting_image_ids or [])
            img_cols = st.columns(min(len(img_bytes_map), 3))
            for idx, (fname, raw_bytes) in enumerate(img_bytes_map.items()):
                img_id = Path(fname).stem
                display_id = _humanise_image_id(img_id, idx)
                is_supporting = img_id in supporting_ids
                col = img_cols[idx % 3]

                per_img = next((a for a in vision.per_image if a.image_id == img_id), None)
                desc = per_img.description if per_img and per_img.description else "—"
                conf_img = f"{per_img.confidence*100:.0f}%" if per_img else "—"

                with col:
                    st.image(raw_bytes, use_container_width=True)
                    css_cls = "supporting" if is_supporting else "not-support"
                    badge = '<span class="chip chip-green">✓ Supports Claim</span>' if is_supporting else '<span class="chip chip-slate">Does Not Support</span>'
                    _debug_id = f'<div style="font-size:0.6rem;color:#374151;margin-top:4px">{img_id}</div>' if _debug else ""
                    _conf_row = f'<div style="margin-top:6px;font-size:0.68rem;color:#64748B">Confidence: {conf_img}</div>' if _debug else ""
                    st.markdown(f"""
                    <div class="img-card {css_cls}">
                      <div class="img-card-body">
                        <div class="img-card-id">{display_id}</div>
                        {badge}
                        <div class="img-card-desc">{desc[:120]}</div>
                        {_conf_row}
                        {_debug_id}
                      </div>
                    </div>""", unsafe_allow_html=True)

        # ── Explainability section ─────────────────────────────────
        section_title("💡", "What We Found")
        expl_text = _VERDICT_EXPLANATIONS.get(status, str(out.claim_status_justification))
        obs_parts = []
        for _pi_idx, img_analysis in enumerate(vision.per_image):
            if hasattr(img_analysis, "description") and img_analysis.description:
                _pi_label = _humanise_image_id(img_analysis.image_id, _pi_idx)
                obs_parts.append(f"{_pi_label}: {img_analysis.description}")
        obs_str = " • ".join(obs_parts) if obs_parts else "No image observations available."

        _rationale_detail = ""
        if _debug:
            _raw_just = str(out.claim_status_justification)
            _rationale_detail = f'<div class="cs-divider"></div><div class="cs-card-title" style="margin-top:1rem">INTERNAL JUSTIFICATION</div><div style="font-size:0.78rem;color:#64748B;line-height:1.6">{_raw_just}</div>'

        st.markdown(f"""
        <div class="cs-card">
          <div class="cs-card-title">SUMMARY</div>
          <div style="font-size:0.88rem;color:#E2E8F0;line-height:1.7;margin-bottom:1rem">{expl_text}</div>
          <div class="cs-divider"></div>
          <div class="cs-card-title" style="margin-top:1rem">IMAGE OBSERVATIONS</div>
          <div style="font-size:0.82rem;color:#94A3B8;line-height:1.7">{obs_str}</div>
          {_rationale_detail}
        </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# TAB 3 — DECISION TRACE
# ═══════════════════════════════════════════════════════════════
with tab_trace:
    if st.session_state.get("_focus_trace"):
        st.session_state["_focus_trace"] = False
        st.toast("✓ Decision trace ready", icon="◉")

    if "result" not in st.session_state:
        st.markdown("""
        <div class="cs-card" style="text-align:center;padding:3rem;">
          <div style="font-size:3rem;margin-bottom:1rem">◉</div>
          <div style="font-size:1rem;font-weight:600;color:#94A3B8;">
            Submit a claim to see the full decision trace.
          </div>
        </div>""", unsafe_allow_html=True)
    else:
        r = st.session_state["result"]
        out = r["output"]
        vision = r["vision"]
        evidence = r["evidence"]
        extraction = r["extraction"]

        st.markdown("""
        <div style="margin-bottom:1.5rem">
          <div style="font-size:1.5rem;font-weight:800;color:#F1F5F9;letter-spacing:-0.5px">AI Observability</div>
          <div style="font-size:0.85rem;color:#64748B;margin-top:4px">
            Full pipeline execution trace — every stage, every output, fully auditable.
          </div>
        </div>""", unsafe_allow_html=True)

        col_pipe, col_detail = st.columns([1, 2], gap="large")

        with col_pipe:
            _trace_debug = st.session_state.get("debug_mode", False)
            steps_done = [
                ("1", "Understanding the Claim",  str(extraction.claimed_object_part).replace("_"," ").title()),
                ("2", "Image Analysis",            f"{len(vision.per_image)} image(s) analysed"),
                ("3", "Evidence Verification",     _SUFFICIENCY_LABELS.get(str(evidence.sufficiency_level).lower(), evidence.sufficiency_level.replace("_"," ").title())),
                ("4", "Final Decision",            _VERDICT_LABELS.get(str(out.claim_status), str(out.claim_status).replace("_"," ").title())),
            ]
            pipeline_html = '<div class="cs-card"><div class="cs-card-title">PIPELINE EXECUTION</div><div class="pipeline">'
            for s, name, detail in steps_done:
                pipeline_html += pipeline_step(s, name, detail, "done")
            pipeline_html += "</div></div>"
            st.markdown(pipeline_html, unsafe_allow_html=True)

        with col_detail:
            _dbg = st.session_state.get("debug_mode", False)

            # Stage 1 — Understanding the Claim
            with st.expander("Stage 1 — Understanding the Claim", expanded=True):
                c1, c2 = st.columns(2)
                c1.markdown(f"**Summary:**  \n{extraction.claim_summary}")
                c1.markdown(f"**Damage type:** {str(extraction.claimed_issue_type).replace('_',' ').title()}")
                c1.markdown(f"**Location:** {str(extraction.claimed_object_part).replace('_',' ').title()}")
                if extraction.injection_detected:
                    st.warning("⚠️ Suspicious instruction detected in the conversation text and ignored.")
                if _dbg:
                    c2.markdown(f"**Confidence:** `{extraction.claim_confidence:.0%}`")
                    c2.markdown(f"**Multi-part:** `{extraction.is_multi_part}`")
                    c2.markdown(f"**Injection detected:** `{extraction.injection_detected}`")

            # Stage 2 — Image Analysis
            with st.expander("Stage 2 — Image Analysis", expanded=True):
                v1, v2 = st.columns(2)
                v1.markdown(f"**{'✅' if vision.object_visible else '❌'} Vehicle / item detected:** {'Yes' if vision.object_visible else 'No'}")
                v1.markdown(f"**{'✅' if vision.object_part_visible else '❌'} Affected area identified:** {'Yes' if vision.object_part_visible else 'No'}")
                v1.markdown(f"**{'✅' if vision.issue_visible else '❌'} Damage detected:** {'Yes' if vision.issue_visible else 'No'}")
                v2.markdown(f"**Damage type found:** {str(vision.issue_type).replace('_',' ').title()}")
                v2.markdown(f"**Area found:** {str(vision.object_part).replace('_',' ').title()}")
                v2.markdown(f"**Severity:** {str(vision.severity).title()}")
                if vision.reasoning:
                    st.caption(vision.reasoning)
                if vision.per_image:
                    st.markdown("**Per-image breakdown:**")
                    for _im_idx, img in enumerate(vision.per_image):
                        _disp_id = _humanise_image_id(img.image_id, _im_idx)
                        parts = ", ".join(p.value.replace("_"," ").title() for p in img.visible_parts) or "none"
                        issues = ", ".join(i.value.replace("_"," ").title() for i in img.visible_issues) or "none"
                        support_icon = "✓" if img.supports_claim else "✗"
                        _line = f"- **{_disp_id}** {support_icon} · parts: *{parts}* · damage: *{issues}*"
                        if _dbg:
                            flags = ", ".join(f.value for f in img.quality_flags) or "none"
                            _line += f" · flags: *{flags}* · conf: {img.confidence:.0%} · id: `{img.image_id}`"
                        st.markdown(_line)
                if _dbg:
                    st.markdown(f"**AI Vision:** `AI Vision Analysis Active`")
                    if vision.supporting_image_ids:
                        st.markdown(f"**Supporting IDs (raw):** `{', '.join(vision.supporting_image_ids)}`")
                    st.markdown(f"**Confidence:** `{vision.confidence:.0%}`")

            # Stage 3 — Evidence Verification
            with st.expander("Stage 3 — Evidence Verification", expanded=True):
                esm_ok = str(evidence.evidence_standard_met).lower() == "true"
                _suf_lbl = _SUFFICIENCY_LABELS.get(str(evidence.sufficiency_level).lower(), str(evidence.sufficiency_level).replace("_"," ").title())
                st.markdown(
                    f"**Result:** {'✅' if esm_ok else '❌'} **{_suf_lbl}**"
                )
                st.caption(evidence.evidence_standard_met_reason)
                if evidence.per_requirement:
                    for req in evidence.per_requirement:
                        icon = "✅" if req.satisfied else "❌"
                        # Show REQ IDs only in Developer Mode
                        if _dbg:
                            st.markdown(f"{icon} `{req.requirement_id}` — *{req.applies_to}*")
                        else:
                            st.markdown(f"{icon} {req.applies_to}")
                        if not req.satisfied and req.gap_description:
                            st.caption(f"    ↳ {req.gap_description}")

            # Stage 4 — Final Decision
            with st.expander("Stage 4 — Final Decision", expanded=True):
                status = str(out.claim_status)
                status_icon = {"supported": "✅", "contradicted": "❌"}.get(status, "⚠️")
                _friendly_status = _VERDICT_LABELS.get(status, status.replace("_"," ").title())
                st.markdown(f"### {status_icon} {_friendly_status}")
                st.info(_VERDICT_EXPLANATIONS.get(status, str(out.claim_status_justification)))
                d1, d2 = st.columns(2)
                d1.markdown(f"**Damage Found:** {str(out.issue_type).replace('_',' ').title()}")
                d1.markdown(f"**Location:** {str(out.object_part).replace('_',' ').title()}")
                d2.markdown(f"**Severity:** {str(out.severity).title()}")
                if _dbg:
                    d2.markdown(f"**Risk flags:** `{out.risk_flags}`")
                    d2.markdown(f"**Supporting IDs:** `{out.supporting_image_ids}`")
                    st.markdown(f"**Internal status:** `{status}`")

        # ── Footer ─────────────────────────────────────────────────
        st.markdown("""
        <div style="margin-top:3rem;padding-top:1.5rem;border-top:1px solid #1F2937;
                    display:flex;justify-content:space-between;align-items:center;">
          <div style="font-size:0.75rem;color:#475569">
            <strong style="color:#6366F1">ClaimSight AI</strong> · Multi-Modal Evidence Review
          </div>
          <div style="font-size:0.7rem;color:#374151">
            AI Vision Analysis · Multi-Modal Evidence Review
          </div>
        </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# TAB DEBUG (DEMO_MODE only)
# ═══════════════════════════════════════════════════════════════
if tab_debug is not None:
    with tab_debug:
        st.markdown("""
        <div style="margin-bottom:1rem">
          <div style="font-size:1.3rem;font-weight:800;color:#F1F5F9">🔬 Pipeline Debugger</div>
          <div style="font-size:0.85rem;color:#64748B;margin-top:4px">
            Full stage-by-stage inspection. Identifies exactly where logic failures occur.
            Only visible when DEMO_MODE=true.
          </div>
        </div>
        """, unsafe_allow_html=True)

        if "result" not in st.session_state:
            st.info("Submit a claim in **Claim Review** first to see the debug trace.")
        else:
            r = st.session_state["result"]
            out = r["output"]
            vision = r["vision"]
            evidence = r["evidence"]
            extraction = r["extraction"]
            img_bytes_map = r.get("img_bytes_map", {})

            # ── Stage A: Claim Extraction ────────────────────────────────
            with st.expander("🔍 Stage A — Claim Extraction", expanded=True):
                st.markdown("**Root check: is_multi_part correct?**")
                mp_color = "red" if extraction.is_multi_part and not extraction.additional_claimed_parts else "green"
                st.markdown(
                    f'<span class="chip chip-{mp_color}">is_multi_part = {extraction.is_multi_part}</span> '
                    f'<span class="chip chip-slate">secondary_parts = {[str(p) for p in extraction.additional_claimed_parts]}</span>',
                    unsafe_allow_html=True
                )
                if extraction.is_multi_part and not extraction.additional_claimed_parts:
                    st.warning(
                        "⚠️ **Potential false positive:** is_multi_part=True but no secondary parts identified. "
                        "This will incorrectly include REQ_GENERAL_MULTI_IMAGE in the evidence evaluation."
                    )

                c1, c2 = st.columns(2)
                c1.code(f"""primary_issue:  {extraction.claimed_issue_type}
primary_part:   {extraction.claimed_object_part}
confidence:     {extraction.claim_confidence:.2f}
injection:      {extraction.injection_detected}
is_multi_part:  {extraction.is_multi_part}""")
                c2.code(f"""secondary_issues: {[str(i) for i in extraction.additional_claimed_issues]}
secondary_parts:  {[str(p) for p in extraction.additional_claimed_parts]}

reasoning: {extraction.reasoning[:200]}""")

            # ── Stage B: Vision Review ───────────────────────────────────
            with st.expander("👁 Stage B — Vision Review", expanded=True):
                st.markdown("**Root check: what did each image return?**")

                flags_debug = {
                    "object_visible":      vision.object_visible,
                    "object_part_visible": vision.object_part_visible,
                    "issue_visible":       vision.issue_visible,
                    "valid_image":         vision.valid_image,
                    "confidence":          f"{vision.confidence:.2f}",
                    "provider":            r.get("provider", "none"),
                }
                for k, v in flags_debug.items():
                    color = "green" if v is True else "red" if v is False else "slate"
                    st.markdown(f'<span class="chip chip-{color}">{k} = {v}</span>', unsafe_allow_html=True)

                if vision.per_image:
                    st.markdown("**Per-image breakdown:**")
                    for img in vision.per_image:
                        ok = "green" if img.supports_claim else "red"
                        st.markdown(
                            f'<span class="chip chip-{ok}">{img.image_id}</span> '
                            f'obj_present={img.object_present} | '
                            f'parts={[p.value for p in img.visible_parts]} | '
                            f'issues={[i.value for i in img.visible_issues]} | '
                            f'conf={img.confidence:.2f}',
                            unsafe_allow_html=True
                        )
                        if img.description:
                            st.caption(f"→ {img.description[:150]}")

                if not r.get("has_model"):
                    st.error(
                        "❌ **No VLM configured.** All vision fields are preflight-only. "
                        "object_visible=False because no vision provider was called. "
                        "Set OPENROUTER_API_KEY in secrets to enable real vision analysis."
                    )

            # ── Stage C: Evidence Standards ──────────────────────────────
            with st.expander("📋 Stage C — Evidence Standards Input", expanded=True):
                from services.evidence_standards_engine import EvidenceStandardsEngine
                inp = EvidenceStandardsEngine.build_input(
                    vision_result=vision,
                    claim_object=str(out.claim_object),
                    claimed_part=str(out.object_part),
                    claimed_issue=str(out.issue_type),
                    is_multi_part=extraction.is_multi_part,
                )
                st.code(f"""[INPUT TO EVIDENCE ENGINE]
claim_object:         {inp.claim_object}
claimed_part:         {inp.claimed_part}
claimed_issue:        {inp.claimed_issue}
is_multi_part:        {inp.is_multi_part}   ← from ClaimExtractionAgent
object_visible:       {inp.object_visible}
object_part_visible:  {inp.object_part_visible}
issue_visible:        {inp.issue_visible}
valid_image_count:    {inp.valid_image_count}
all_visible_parts:    {inp.all_visible_parts}
all_visible_issues:   {inp.all_visible_issues}
quality_flags:        {inp.quality_flags}""")

                if inp.is_multi_part:
                    st.warning(
                        "⚠️ is_multi_part=True → REQ_GENERAL_MULTI_IMAGE is being evaluated. "
                        "If this is a simple single-part claim, this requirement will fail with "
                        "'For multi-part claims, at least one image must...' message."
                    )

                st.markdown("**Per-requirement evaluation:**")
                for req in evidence.per_requirement:
                    icon = "✅" if req.satisfied else "❌"
                    color = "green" if req.satisfied else "red"
                    st.markdown(
                        f'{icon} <span class="chip chip-{color}">{req.requirement_id}</span> '
                        f'*{req.applies_to}*',
                        unsafe_allow_html=True
                    )
                    if not req.satisfied and req.gap_description:
                        st.caption(f"  Gap: {req.gap_description}")

            # ── Stage D: Decision ────────────────────────────────────────
            with st.expander("⚖️ Stage D — Decision Service Input", expanded=True):
                status = str(out.claim_status)
                rule = (
                    "Rule 1: no valid images" if not vision.valid_image else
                    "Rule 2: evidence not met" if not evidence.evidence_standard_met else
                    "Rule 3: object not visible" if not vision.object_visible and not vision.object_part_visible else
                    "Rule 4: part not visible" if not vision.object_part_visible else
                    "Rule 5: SUPPORTED" if vision.issue_visible and vision.supporting_image_ids else
                    "Rule 6: CONTRADICTED" if vision.object_part_visible and not vision.issue_visible else
                    "Rule 7: fallback NEI"
                )
                st.code(f"""[DECISION INPUTS]
valid_image:           {vision.valid_image}
evidence_standard_met: {evidence.evidence_standard_met}
object_visible:        {vision.object_visible}
object_part_visible:   {vision.object_part_visible}
issue_visible:         {vision.issue_visible}
supporting_image_ids:  {vision.supporting_image_ids}

[RULE FIRED]
{rule}

[FINAL OUTPUT]
claim_status:     {out.claim_status}
issue_type:       {out.issue_type}
object_part:      {out.object_part}
severity:         {out.severity}
risk_flags:       {out.risk_flags}
evidence_met:     {out.evidence_standard_met}""")

            # ── Root cause summary ───────────────────────────────────────
            section_title("🎯", "Root Cause Analysis")

            issues_found = []
            if not r.get("has_model"):
                issues_found.append("NO_MODEL_CONFIGURED: All vision outputs are preflight defaults. Set OPENROUTER_API_KEY to enable vision analysis.")
            if extraction.is_multi_part and not extraction.additional_claimed_parts:
                issues_found.append(
                    "FALSE_MULTI_PART: is_multi_part=True with no secondary parts. "
                    "ClaimExtractionAgent found multi-part keywords but no actual secondary damage. "
                    "This incorrectly triggers REQ_GENERAL_MULTI_IMAGE."
                )
            if not vision.object_visible and vision.valid_image:
                issues_found.append(
                    "OBJECT_INVISIBLE_DESPITE_VALID_IMAGE: VLM returned object_present=None or False. "
                    "Check per-image analysis above for the raw VLM response."
                )
            if evidence.sufficiency_level == "not_met" and not issues_found:
                issues_found.append(
                    f"EVIDENCE_NOT_MET: {evidence.evidence_standard_met_reason}"
                )

            if issues_found:
                for issue in issues_found:
                    cat = issue.split(":")[0]
                    detail = issue[len(cat)+1:].strip()
                    st.markdown(f"""
                    <div class="cs-card" style="border-color:#EF4444">
                      <div style="color:#EF4444;font-weight:700;font-size:0.8rem">{cat}</div>
                      <div style="color:#94A3B8;font-size:0.82rem;margin-top:4px">{detail}</div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.success("No root cause issues detected. Pipeline logic appears correct.")
