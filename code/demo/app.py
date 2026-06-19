"""
ClaimSight AI — Production-Grade Evidence Review Platform
Run: streamlit run code/demo/app.py
"""
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import sys
import tempfile
import time
from pathlib import Path

_CODE_DIR = Path(__file__).resolve().parent.parent
_REPO_DIR = _CODE_DIR.parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_DIR / ".env")
except ImportError:
    pass

import streamlit as st

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ClaimSight AI",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="collapsed",
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


def kpi(label: str, value: str, sub: str = "", color: str = "indigo"):
    return f"""
    <div class="kpi-card {color}">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      {'<div class="kpi-sub">' + sub + '</div>' if sub else ''}
    </div>"""


def chip(text: str, color: str = "slate") -> str:
    return f'<span class="chip chip-{color}">{text}</span>'


def verdict_banner(status: str, justification: str):
    cfg = {
        "supported":            ("✓", "Claim Verified", "verdict-supported",    "SUPPORTED"),
        "contradicted":         ("✗", "Claim Contradicted","verdict-contradicted","CONTRADICTED"),
        "not_enough_information":("~", "Insufficient Evidence","verdict-nei",   "NOT ENOUGH INFORMATION"),
    }
    icon, title, css, label = cfg.get(status, ("?", status.upper(), "verdict-nei", status.upper()))
    st.markdown(f"""
    <div class="verdict-banner {css}">
      <div class="v-icon">{icon}</div>
      <div class="v-label">CLAIM DECISION</div>
      <div class="v-title">{title}</div>
      <p class="v-reason">{justification[:280]}</p>
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
    from agents.vision_agent import VisionReviewAgent
    from config import Settings
    from models.claim_extraction import ClaimExtractionInput
    from models.enums import ClaimObject, IssueType, ObjectPart
    from models.records import ClaimInput, ParsedClaim
    from models.vision_review import VisionReviewInput
    from services.decision_service import DecisionService
    from services.evidence_standards_engine import EvidenceStandardsEngine
    from services.model_service import ModelService

    settings = Settings(repo_root=_REPO_DIR)

    # Save uploaded images
    tmp_paths, img_names = [], []
    img_bytes_map = {}
    for f in image_files:
        raw = f.read()
        suffix = Path(f.name).suffix or ".jpg"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(raw)
        tmp.close()
        tmp_paths.append(Path(tmp.name))
        img_names.append(f.name)
        img_bytes_map[f.name] = raw

    # Stage A
    try:
        obj = ClaimObject(claim_object)
    except ValueError:
        obj = ClaimObject.CAR

    from agents.claim_agent import ClaimExtractionAgent
    extr_data = _cached_claim_extraction(user_claim, claim_object)
    # Reconstruct typed object from cached dict
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

    # Cleanup
    for p in tmp_paths:
        try: p.unlink()
        except OSError: pass

    provider = "No model"
    if settings.has_vision_model:
        provider = f"{settings.model_provider}/{settings.vision_model}"

    return dict(
        extraction=extraction,
        vision=vision_result,
        evidence=evidence_result,
        output=output,
        has_model=settings.has_vision_model,
        provider=provider,
        img_bytes_map=img_bytes_map,
    )

# ── AI Progress simulation ────────────────────────────────────────────────────

def show_progress(placeholder):
    steps = [
        ("🔍", "Parsing claim conversation…",      0.20),
        ("👁", "Analysing visual evidence…",        0.50),
        ("📋", "Evaluating evidence standards…",    0.72),
        ("⚖️",  "Running risk assessment…",          0.88),
        ("✓",  "Computing final decision…",         1.00),
    ]
    for icon, label, pct in steps:
        with placeholder.container():
            st.markdown(f"""
            <div class="cs-card" style="text-align:center;padding:2rem;">
              <div style="font-size:2rem;margin-bottom:0.5rem">{icon}</div>
              <div style="font-size:1rem;font-weight:600;color:#E2E8F0;margin-bottom:1rem">{label}</div>
            </div>""", unsafe_allow_html=True)
            st.progress(pct)
        time.sleep(0.6)


# ── Main layout ───────────────────────────────────────────────────────────────

topbar()

# ── Model status indicator (sidebar-free, top-right) ─────────────────────────
from config import Settings as _Cfg
_s = _Cfg(repo_root=_REPO_DIR)
if _s.has_vision_model:
    st.markdown(
        f'<div style="text-align:right;margin-top:-3rem;margin-bottom:1.5rem">'
        f'<span class="chip chip-green">● {_s.model_provider.upper()} CONNECTED</span></div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div style="text-align:right;margin-top:-3rem;margin-bottom:1.5rem">'
        '<span class="chip chip-amber">● PREFLIGHT MODE</span></div>',
        unsafe_allow_html=True,
    )

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_review, tab_results, tab_trace = st.tabs(
    ["⬡  Claim Review", "◈  Results", "◉  Decision Trace"]
)

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
                <div class="pipe-name">Claim Extraction</div>
                <div class="pipe-detail">Parses conversation · extracts object, part, issue type</div>
              </div>
            </div>
            <div class="pipe-step">
              <div class="pipe-connector"></div>
              <div class="pipe-icon done">2</div>
              <div class="pipe-body">
                <div class="pipe-name">Vision Review</div>
                <div class="pipe-detail">Gemini 2.5 Flash · per-image VLM analysis</div>
              </div>
            </div>
            <div class="pipe-step">
              <div class="pipe-connector"></div>
              <div class="pipe-icon done">3</div>
              <div class="pipe-body">
                <div class="pipe-name">Evidence Standards</div>
                <div class="pipe-detail">Rule-based sufficiency engine · CSV-driven requirements</div>
              </div>
            </div>
            <div class="pipe-step">
              <div class="pipe-icon done">4</div>
              <div class="pipe-body">
                <div class="pipe-name">Decision Engine</div>
                <div class="pipe-detail">Deterministic rules · Supported / Contradicted / NEI</div>
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

    # Process claim
    if analyze:
        if not user_claim.strip():
            st.error("Please enter a claim conversation before analysing.")
        else:
            progress_placeholder = st.empty()
            show_progress(progress_placeholder)
            progress_placeholder.empty()

            with st.spinner(""):
                try:
                    result = run_pipeline(uploaded_files or [], user_claim, claim_object)
                    st.session_state["result"] = result
                    st.success("Analysis complete — switch to the **Results** tab to view findings.")
                except Exception as exc:
                    st.error(f"Pipeline error: {exc}")


# ═══════════════════════════════════════════════════════════════
# TAB 2 — RESULTS
# ═══════════════════════════════════════════════════════════════
with tab_results:
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

        kpis_html = '<div class="kpi-grid">'
        kpis_html += kpi("Claim Status",    status.replace("_", " ").title(),          "", "green" if status == "supported" else "red" if status == "contradicted" else "amber")
        kpis_html += kpi("Issue Type",      str(out.issue_type).replace("_", " ").title(), "", "indigo")
        kpis_html += kpi("Object Part",     str(out.object_part).replace("_", " ").title(), "", "indigo")
        kpis_html += kpi("Severity",        str(out.severity).title(),                 "", severity_color)
        kpis_html += kpi("Evidence Std.",   "Met" if esm else "Not Met",               "", "green" if esm else "red")
        kpis_html += kpi("Confidence",      conf_pct,                                  provider, "indigo")
        kpis_html += '</div>'
        st.markdown(kpis_html, unsafe_allow_html=True)

        # ── Evidence standard reason ───────────────────────────────
        section_title("◈", "Evidence Assessment")
        col_e1, col_e2 = st.columns([1, 1])
        with col_e1:
            st.markdown(f"""
            <div class="cs-card">
              <div class="cs-card-title">EVIDENCE STANDARD</div>
              <div style="margin-bottom:0.5rem">
                {'<span class="chip chip-green">● MET</span>' if esm else '<span class="chip chip-red">● NOT MET</span>'}
                <span style="font-size:0.75rem;color:#64748B;margin-left:8px">{evidence.sufficiency_level}</span>
              </div>
              <div style="font-size:0.8rem;color:#94A3B8;line-height:1.6">{str(out.evidence_standard_met_reason)[:300]}</div>
            </div>""", unsafe_allow_html=True)
        with col_e2:
            flags_raw = str(out.risk_flags)
            flags = [f.strip() for f in flags_raw.split(";") if f.strip() and f.strip() != "none"]
            flag_danger = {"possible_manipulation", "wrong_object", "text_instruction_present", "non_original_image"}
            flag_warn   = {"blurry_image", "cropped_or_obstructed", "low_light_or_glare", "wrong_angle", "user_history_risk", "manual_review_required", "damage_not_visible"}
            chips_html = ""
            for f in (flags or ["none"]):
                c = "red" if f in flag_danger else "amber" if f in flag_warn else "slate"
                chips_html += chip(f.replace("_", " "), c)
            st.markdown(f"""
            <div class="cs-card">
              <div class="cs-card-title">RISK FLAGS</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">{chips_html}</div>
              {'<div style="margin-top:1rem;font-size:0.75rem;color:#64748B">No risk flags detected</div>' if not flags else ''}
            </div>""", unsafe_allow_html=True)

        # ── Image evidence cards ───────────────────────────────────
        if img_bytes_map:
            section_title("🖼", "Image Evidence")
            supporting_ids = set(vision.supporting_image_ids or [])
            img_cols = st.columns(min(len(img_bytes_map), 3))
            for idx, (fname, raw_bytes) in enumerate(img_bytes_map.items()):
                img_id = Path(fname).stem
                is_supporting = img_id in supporting_ids
                col = img_cols[idx % 3]

                # Find per-image analysis
                per_img = next((a for a in vision.per_image if a.image_id == img_id), None)
                desc = per_img.description if per_img and per_img.description else "—"
                conf_img = f"{per_img.confidence*100:.0f}%" if per_img else "—"

                with col:
                    st.image(raw_bytes, use_container_width=True)
                    css_cls = "supporting" if is_supporting else "not-support"
                    badge = '<span class="chip chip-green">✓ Supporting</span>' if is_supporting else '<span class="chip chip-slate">Not primary</span>'
                    st.markdown(f"""
                    <div class="img-card {css_cls}">
                      <div class="img-card-body">
                        <div class="img-card-id">{img_id}</div>
                        {badge}
                        <div class="img-card-desc">{desc[:120]}</div>
                        <div style="margin-top:6px;font-size:0.68rem;color:#64748B">Confidence: {conf_img}</div>
                      </div>
                    </div>""", unsafe_allow_html=True)

        # ── Explainability section ─────────────────────────────────
        section_title("💡", "AI Reasoning")
        expl_text = str(out.claim_status_justification)
        obs_parts = []
        for img_analysis in vision.per_image:
            if hasattr(img_analysis, "description") and img_analysis.description:
                obs_parts.append(f"[{img_analysis.image_id}] {img_analysis.description}")
        obs_str = " • ".join(obs_parts) if obs_parts else "Visual content requires model inspection."

        st.markdown(f"""
        <div class="cs-card">
          <div class="cs-card-title">DECISION RATIONALE</div>
          <div style="font-size:0.88rem;color:#E2E8F0;line-height:1.7;margin-bottom:1rem">{expl_text}</div>
          <div class="cs-divider"></div>
          <div class="cs-card-title" style="margin-top:1rem">IMAGE-GROUNDED OBSERVATIONS</div>
          <div style="font-size:0.82rem;color:#94A3B8;line-height:1.7">{obs_str}</div>
        </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# TAB 3 — DECISION TRACE
# ═══════════════════════════════════════════════════════════════
with tab_trace:
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
            # Animated pipeline diagram
            steps_done = [
                ("1", "Claim Extraction",   str(extraction.claimed_object_part).replace("_"," ").title()),
                ("2", "Vision Review",      f"{len(vision.per_image)} image(s) · conf {vision.confidence*100:.0f}%"),
                ("3", "Evidence Standards", evidence.sufficiency_level.replace("_"," ").title()),
                ("4", "Decision Engine",    str(out.claim_status).replace("_"," ").title()),
            ]
            pipeline_html = '<div class="cs-card"><div class="cs-card-title">PIPELINE EXECUTION</div><div class="pipeline">'
            for s, name, detail in steps_done:
                pipeline_html += pipeline_step(s, name, detail, "done")
            pipeline_html += "</div></div>"
            st.markdown(pipeline_html, unsafe_allow_html=True)

        with col_detail:
            # Stage 1 detail
            with st.expander("Stage 1 — Claim Extraction", expanded=True):
                c1, c2 = st.columns(2)
                c1.markdown(f"**Summary:**  \n{extraction.claim_summary}")
                c1.markdown(f"**Claimed issue:** `{extraction.claimed_issue_type}`")
                c1.markdown(f"**Claimed part:** `{extraction.claimed_object_part}`")
                c2.markdown(f"**Confidence:** `{extraction.claim_confidence:.0%}`")
                c2.markdown(f"**Multi-part:** `{extraction.is_multi_part}`")
                c2.markdown(f"**Injection detected:** `{extraction.injection_detected}`")
                if extraction.injection_detected:
                    st.warning("⚠️ Prompt injection attempt detected in conversation and neutralised.")

            # Stage 2 detail
            with st.expander("Stage 2 — Vision Review", expanded=True):
                v1, v2 = st.columns(2)
                v1.markdown(f"**Object visible:** `{vision.object_visible}`")
                v1.markdown(f"**Part visible:** `{vision.object_part_visible}`")
                v1.markdown(f"**Issue visible:** `{vision.issue_visible}`")
                v1.markdown(f"**Valid image:** `{vision.valid_image}`")
                v2.markdown(f"**Best issue:** `{vision.issue_type}`")
                v2.markdown(f"**Best part:** `{vision.object_part}`")
                v2.markdown(f"**Severity:** `{vision.severity}`")
                v2.markdown(f"**Confidence:** `{vision.confidence:.0%}`")
                if vision.supporting_image_ids:
                    st.markdown(f"**Supporting images:** `{', '.join(vision.supporting_image_ids)}`")
                if vision.reasoning:
                    st.caption(vision.reasoning)
                if vision.per_image:
                    st.markdown("**Per-image breakdown:**")
                    for img in vision.per_image:
                        parts = ", ".join(p.value for p in img.visible_parts) or "none"
                        issues = ", ".join(i.value for i in img.visible_issues) or "none"
                        flags  = ", ".join(f.value for f in img.quality_flags) or "none"
                        support_icon = "✓" if img.supports_claim else "✗"
                        st.markdown(
                            f"- `{img.image_id}` {support_icon} · "
                            f"parts: *{parts}* · issues: *{issues}* · "
                            f"flags: *{flags}* · conf: {img.confidence:.0%}"
                        )

            # Stage 3 detail
            with st.expander("Stage 3 — Evidence Standards", expanded=True):
                esm_ok = str(evidence.evidence_standard_met).lower() == "true"
                st.markdown(
                    f"**Result:** {'✅ Met' if esm_ok else '❌ Not Met'} "
                    f"(`{evidence.sufficiency_level}`)"
                )
                st.caption(evidence.evidence_standard_met_reason)
                if evidence.per_requirement:
                    for req in evidence.per_requirement:
                        icon = "✅" if req.satisfied else "❌"
                        st.markdown(f"{icon} `{req.requirement_id}` — *{req.applies_to}*")
                        if not req.satisfied and req.gap_description:
                            st.caption(f"    Gap: {req.gap_description}")

            # Stage 4 detail
            with st.expander("Stage 4 — Decision Engine", expanded=True):
                status = str(out.claim_status)
                status_icon = {"supported": "✅", "contradicted": "❌"}.get(status, "⚠️")
                st.markdown(f"### {status_icon} `{status}`")
                st.info(str(out.claim_status_justification))
                d1, d2 = st.columns(2)
                d1.markdown(f"**Issue type:** `{out.issue_type}`")
                d1.markdown(f"**Object part:** `{out.object_part}`")
                d2.markdown(f"**Severity:** `{out.severity}`")
                d2.markdown(f"**Risk flags:** `{out.risk_flags}`")
                d2.markdown(f"**Supporting IDs:** `{out.supporting_image_ids}`")

        # ── Footer ─────────────────────────────────────────────────
        st.markdown("""
        <div style="margin-top:3rem;padding-top:1.5rem;border-top:1px solid #1F2937;
                    display:flex;justify-content:space-between;align-items:center;">
          <div style="font-size:0.75rem;color:#475569">
            <strong style="color:#6366F1">ClaimSight AI</strong> · Multi-Modal Evidence Review
          </div>
          <div style="font-size:0.7rem;color:#374151">
            Powered by Gemini 2.5 Flash · OpenRouter fallback · Pydantic schemas
          </div>
        </div>""", unsafe_allow_html=True)
