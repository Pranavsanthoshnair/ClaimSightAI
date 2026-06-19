"""Streamlit demo for Multi-Modal Evidence Review.

Run from repo root:
    streamlit run code/demo/app.py

Requires: pip install streamlit
"""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

# Bootstrap path so code/ modules are importable
_CODE_DIR = Path(__file__).resolve().parent.parent
_REPO_DIR = _CODE_DIR.parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_DIR / ".env")
except ImportError:
    pass

import streamlit as st

# -----------------------------------------------------------------------
# Page config
# -----------------------------------------------------------------------

st.set_page_config(
    page_title="Evidence Review · AI Claim Analyser",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------
# Custom CSS
# -----------------------------------------------------------------------

st.markdown("""
<style>
.status-supported   { background:#d4edda; color:#155724; padding:16px 24px;
                      border-radius:8px; font-size:1.6rem; font-weight:700;
                      text-align:center; border-left:6px solid #28a745; }
.status-contradicted{ background:#f8d7da; color:#721c24; padding:16px 24px;
                      border-radius:8px; font-size:1.6rem; font-weight:700;
                      text-align:center; border-left:6px solid #dc3545; }
.status-nei         { background:#fff3cd; color:#856404; padding:16px 24px;
                      border-radius:8px; font-size:1.6rem; font-weight:700;
                      text-align:center; border-left:6px solid #ffc107; }
.metric-card        { background:#f8f9fa; border-radius:8px; padding:12px 16px;
                      border:1px solid #dee2e6; margin-bottom:8px; }
.step-box           { background:#e7f3ff; border-radius:8px; padding:12px 16px;
                      border-left:4px solid #0d6efd; margin:8px 0; }
.flag-chip          { display:inline-block; background:#e9ecef; color:#495057;
                      border-radius:16px; padding:4px 12px; margin:3px;
                      font-size:0.85rem; }
.flag-chip-warn     { background:#fff3cd; color:#856404; }
.flag-chip-danger   { background:#f8d7da; color:#721c24; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------
# Helper: run pipeline on uploaded files
# -----------------------------------------------------------------------

def _run_pipeline(
    image_files: list,
    user_claim: str,
    claim_object: str,
) -> dict:
    """Run the full 4-stage pipeline and return a result dict."""
    from config import Settings
    from agents.claim_agent import ClaimExtractionAgent
    from agents.vision_agent import VisionReviewAgent
    from services.model_service import ModelService
    from services.evidence_standards_engine import EvidenceStandardsEngine
    from services.decision_service import DecisionService
    from models.claim_extraction import ClaimExtractionInput
    from models.vision_review import VisionReviewInput
    from models.records import ClaimInput, ParsedClaim
    from models.enums import ClaimObject, IssueType, ObjectPart

    settings = Settings(repo_root=_REPO_DIR)

    # Save uploaded images to temp files
    tmp_paths = []
    for f in image_files:
        suffix = Path(f.name).suffix or ".jpg"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(f.read())
        tmp.close()
        tmp_paths.append(Path(tmp.name))

    # Stage A: claim extraction
    claim_agent = ClaimExtractionAgent()
    try:
        claim_obj = ClaimObject(claim_object)
    except ValueError:
        claim_obj = ClaimObject.CAR

    extraction = claim_agent.extract(
        ClaimExtractionInput(user_claim=user_claim, claim_object=claim_obj)
    )

    # Stage B: vision review
    model_svc = ModelService(settings=settings) if settings.has_vision_model else None
    vision_agent = VisionReviewAgent(model_service=model_svc)

    if tmp_paths:
        vision_result = vision_agent.review(VisionReviewInput(
            image_paths=tmp_paths,
            claim_object=claim_obj,
            claimed_part=extraction.claimed_object_part,
            claimed_issue=extraction.claimed_issue_type,
            is_multi_part=extraction.is_multi_part,
        ))
    else:
        from models.vision_review import VisionReviewResult
        from models.enums import RiskFlag
        vision_result = VisionReviewResult(
            valid_image=False,
            quality_flags=[RiskFlag.MANUAL_REVIEW_REQUIRED],
            reasoning="No images uploaded.",
        )

    # Stage C: evidence standards
    evidence_engine = EvidenceStandardsEngine()
    evidence_engine.load(_REPO_DIR / "dataset" / "evidence_requirements.csv")
    evidence_result = evidence_engine.evaluate_from_vision(
        vision_result=vision_result,
        claim_object=str(claim_obj),
        claimed_part=str(extraction.claimed_object_part),
        claimed_issue=str(extraction.claimed_issue_type),
        is_multi_part=extraction.is_multi_part,
    )

    # Stage D: decision
    decision_svc = DecisionService()
    claim_input = ClaimInput(
        user_id="demo_user",
        image_paths=";".join(f.name for f in image_files) if image_files else "none",
        user_claim=user_claim,
        claim_object=claim_obj,
    )
    parsed_claim = ParsedClaim(
        claim_object=claim_obj,
        claimed_issue=extraction.claimed_issue_type,
        claimed_part=extraction.claimed_object_part,
        is_multi_part=extraction.is_multi_part,
    )
    output = decision_svc.decide(
        claim=claim_input,
        parsed_claim=parsed_claim,
        vision=vision_result,
        evidence=evidence_result,
    )

    # Clean up temp files
    for p in tmp_paths:
        try:
            p.unlink()
        except OSError:
            pass

    return {
        "extraction": extraction,
        "vision": vision_result,
        "evidence": evidence_result,
        "output": output,
        "has_model": settings.has_vision_model,
        "model_provider": settings.model_provider,
    }


# -----------------------------------------------------------------------
# UI — tabs
# -----------------------------------------------------------------------

st.title("🔍 Multi-Modal Evidence Review")
st.caption("Powered by Gemini 2.5 Flash · Multi-Stage AI Pipeline")

tab_input, tab_results, tab_trace = st.tabs(
    ["📋 Claim Review", "📊 Results", "🔬 Decision Trace"]
)

# -----------------------------------------------------------------------
# Tab 1: Claim Review (input)
# -----------------------------------------------------------------------

with tab_input:
    st.header("Submit a Claim for Review")

    col_form, col_info = st.columns([2, 1])

    with col_form:
        uploaded_files = st.file_uploader(
            "Upload claim images",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            help="Upload one or more images showing the claimed damage.",
        )

        if uploaded_files:
            img_cols = st.columns(min(len(uploaded_files), 4))
            for i, f in enumerate(uploaded_files):
                with img_cols[i % 4]:
                    st.image(f, caption=f.name, use_container_width=True)

        user_claim = st.text_area(
            "Claim conversation",
            height=180,
            placeholder=(
                "Customer: My rear bumper has a deep dent after someone hit my car. "
                "| Support: Which part is damaged? "
                "| Customer: Rear bumper area, I attached the photo."
            ),
            help="Paste the support conversation or describe the damage.",
        )

        claim_object = st.selectbox(
            "Object type",
            options=["car", "laptop", "package"],
            help="Select the type of object being claimed.",
        )

        submitted = st.button("🚀 Analyse Claim", type="primary", use_container_width=True)

    with col_info:
        st.info("""
**How it works:**

1. **Claim Extraction** — parses the conversation to identify the claimed damage
2. **Vision Review** — analyses each image independently with a VLM
3. **Evidence Standards** — checks if images meet minimum evidence requirements
4. **Decision Engine** — produces the final verdict

**Tip:** For best results, upload clear, well-lit images showing the claimed damage area.
        """)

        from config import Settings as _S
        _settings = _S(repo_root=_REPO_DIR)
        if _settings.has_vision_model:
            st.success(f"✅ VLM active: {_settings.model_provider}/{_settings.vision_model}")
        else:
            st.warning("⚠️ No VLM configured — running in preflight-only mode.\n\nSet `GEMINI_API_KEY` in `.env` for real analysis.")

    if submitted:
        if not user_claim.strip():
            st.error("Please enter a claim conversation.")
        else:
            with st.spinner("Analysing claim…"):
                try:
                    result = _run_pipeline(uploaded_files or [], user_claim, claim_object)
                    st.session_state["result"] = result
                    st.success("Analysis complete! Switch to the **Results** tab.")
                except Exception as exc:
                    st.error(f"Pipeline error: {exc}")

# -----------------------------------------------------------------------
# Tab 2: Results
# -----------------------------------------------------------------------

with tab_results:
    if "result" not in st.session_state:
        st.info("Submit a claim in the **Claim Review** tab to see results.")
    else:
        r = st.session_state["result"]
        out = r["output"]
        vision = r["vision"]
        evidence = r["evidence"]
        extraction = r["extraction"]

        status = str(out.claim_status)
        status_label = {
            "supported": "✅ SUPPORTED",
            "contradicted": "❌ CONTRADICTED",
            "not_enough_information": "⚠️ NOT ENOUGH INFORMATION",
        }.get(status, status.upper())
        status_css = {
            "supported": "status-supported",
            "contradicted": "status-contradicted",
            "not_enough_information": "status-nei",
        }.get(status, "status-nei")

        st.markdown(f'<div class="{status_css}">{status_label}</div>', unsafe_allow_html=True)
        st.markdown("")

        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Issue Type", str(out.issue_type).replace("_", " ").title())
        col2.metric("Object Part", str(out.object_part).replace("_", " ").title())
        col3.metric("Severity", str(out.severity).title())
        col4.metric("Confidence", f"{vision.confidence:.0%}")

        st.divider()

        col_ev, col_flags = st.columns(2)

        with col_ev:
            st.subheader("Evidence Standard")
            esm = out.evidence_standard_met
            esm_icon = "✅" if str(esm).lower() == "true" else "❌"
            st.markdown(f"**{esm_icon} {'Met' if str(esm).lower() == 'true' else 'Not Met'}**")
            st.caption(str(out.evidence_standard_met_reason))

        with col_flags:
            st.subheader("Risk Flags")
            flags_raw = str(out.risk_flags)
            flags = [f.strip() for f in flags_raw.split(";") if f.strip() and f.strip() != "none"]
            if flags:
                flag_html = ""
                for flag in flags:
                    css = "flag-chip-danger" if flag in ("possible_manipulation", "wrong_object", "text_instruction_present") \
                          else "flag-chip-warn" if flag in ("blurry_image", "cropped_or_obstructed", "low_light_or_glare", "user_history_risk") \
                          else "flag-chip"
                    flag_html += f'<span class="{css} flag-chip">{flag.replace("_", " ")}</span>'
                st.markdown(flag_html, unsafe_allow_html=True)
            else:
                st.markdown('<span class="flag-chip">none</span>', unsafe_allow_html=True)

        st.divider()

        # Justification
        st.subheader("Justification")
        st.info(str(out.claim_status_justification))

        # Claim summary
        st.subheader("Claim Summary (extracted)")
        st.write(extraction.claim_summary)

        # Supporting images
        if not r.get("has_model", False):
            st.warning("No VLM configured — visual analysis not available. Results are based on claim text only.")

# -----------------------------------------------------------------------
# Tab 3: Decision Trace
# -----------------------------------------------------------------------

with tab_trace:
    if "result" not in st.session_state:
        st.info("Submit a claim in the **Claim Review** tab to see the decision trace.")
    else:
        r = st.session_state["result"]
        extraction = r["extraction"]
        vision = r["vision"]
        evidence = r["evidence"]
        out = r["output"]

        st.header("Decision Trace")
        st.caption("Step-by-step pipeline execution")

        # Step 1: Claim Extraction
        with st.expander("**Stage 1 — Claim Extraction** 📝", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Extracted claim:**")
                st.markdown(f'<div class="step-box">{extraction.claim_summary}</div>', unsafe_allow_html=True)
                st.markdown(f"**Claimed issue:** `{extraction.claimed_issue_type}`")
                st.markdown(f"**Claimed part:** `{extraction.claimed_object_part}`")
            with c2:
                st.markdown(f"**Confidence:** `{extraction.claim_confidence:.0%}`")
                st.markdown(f"**Multi-part:** `{extraction.is_multi_part}`")
                st.markdown(f"**Injection detected:** `{extraction.injection_detected}`")
            if extraction.reasoning:
                st.caption(f"Reasoning: {extraction.reasoning}")

        # Step 2: Vision Review
        with st.expander("**Stage 2 — Vision Review** 👁️", expanded=True):
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                st.markdown(f"**Object visible:** `{vision.object_visible}`")
                st.markdown(f"**Part visible:** `{vision.object_part_visible}`")
                st.markdown(f"**Issue visible:** `{vision.issue_visible}`")
                st.markdown(f"**Valid image:** `{vision.valid_image}`")
            with col_v2:
                st.markdown(f"**Best issue:** `{vision.issue_type}`")
                st.markdown(f"**Best part:** `{vision.object_part}`")
                st.markdown(f"**Severity:** `{vision.severity}`")
                st.markdown(f"**Confidence:** `{vision.confidence:.0%}`")

            if vision.supporting_image_ids:
                st.success(f"Supporting images: {', '.join(vision.supporting_image_ids)}")

            if vision.reasoning:
                st.caption(vision.reasoning)

            # Per-image breakdown
            if vision.per_image:
                st.markdown("**Per-image analysis:**")
                for img in vision.per_image:
                    with st.container():
                        st.markdown(f"- `{img.image_id}`: readable={img.readable}, "
                                    f"object_present={img.object_present}, "
                                    f"supports_claim={img.supports_claim}, "
                                    f"confidence={img.confidence:.0%}")
                        if hasattr(img, 'description') and img.description:
                            st.caption(f"  → {img.description}")

        # Step 3: Evidence Standards
        with st.expander("**Stage 3 — Evidence Standards** 📋", expanded=True):
            esm = str(evidence.evidence_standard_met).lower() == "true"
            if esm:
                st.success(f"Evidence standard MET ({evidence.sufficiency_level})")
            else:
                st.error(f"Evidence standard NOT MET ({evidence.sufficiency_level})")
            st.caption(evidence.evidence_standard_met_reason)

            if evidence.per_requirement:
                for req in evidence.per_requirement:
                    icon = "✅" if req.satisfied else "❌"
                    st.markdown(f"{icon} `{req.requirement_id}` — {req.applies_to}")
                    if not req.satisfied and req.gap_description:
                        st.caption(f"  Gap: {req.gap_description}")

        # Step 4: Decision Engine
        with st.expander("**Stage 4 — Decision Engine** ⚖️", expanded=True):
            status = str(out.claim_status)
            status_emoji = {"supported": "✅", "contradicted": "❌", "not_enough_information": "⚠️"}.get(status, "❓")
            st.markdown(f"### {status_emoji} Final verdict: `{status}`")
            st.info(str(out.claim_status_justification))
            col_d1, col_d2 = st.columns(2)
            col_d1.markdown(f"**Risk flags:** `{out.risk_flags}`")
            col_d2.markdown(f"**Severity:** `{out.severity}`")
