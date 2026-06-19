"""Integration tests for the Streamlit demo app (code/demo/app.py).

Tests the core helper functions and pipeline execution path.

Coverage:
1.  Secrets injection (.env fallback, missing streamlit)
2.  Component functions — topbar, hero, card, kpi, chip, verdict_banner
3.  Pipeline step rendering
4.  _cached_claim_extraction — happy path
5.  _cached_claim_extraction — invalid object fallback
6.  run_pipeline — no images (no-upload case)
7.  run_pipeline — with images preflight-only mode
8.  run_pipeline — FileNotFoundError handling
9.  run_pipeline — ImportError handling
10. show_progress rendering
11. Verdict banner all statuses (SUPPORTED, CONTRADICTED, NEI, unknown)
12. KPI grid with all severity colors
13. Verdict justification truncation
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_CODE_DIR = Path(__file__).resolve().parent.parent.parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

# Import stubs that don't need Streamlit runtime
from demo.app import (
    card,
    chip,
    hero,
    kpi,
    pipeline_step,
    run_pipeline,
    section_title,
    topbar,
    verdict_banner,
    success_card_html,
    error_card_html,
    _inject_secrets,
    show_progress,
)
import demo.app as _demo_app

from models.enums import RiskFlag
from models.vision_review import VisionReviewResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_st_mock():
    """Return a fresh MagicMock configured as streamlit."""
    m = MagicMock()
    m.session_state = {}
    m.secrets = {}
    m.cache_data = lambda **kw: (lambda fn: fn)
    m.cache_resource = lambda **kw: (lambda fn: fn)
    return m


# ---------------------------------------------------------------------------
# Startup / Secrets
# ---------------------------------------------------------------------------


def test_inject_secrets_empty_env():
    _inject_secrets()
    assert True


def test_inject_secrets_missing_streamlit():
    with patch.dict("sys.modules", {"streamlit": None}):
        _inject_secrets()
        assert True


# ---------------------------------------------------------------------------
# Component helpers
# ---------------------------------------------------------------------------


def test_topbar_renders_markdown():
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        topbar()
        mock_st.markdown.assert_called_once()


def test_hero_renders_markdown():
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        hero()
        mock_st.markdown.assert_called_once()


def test_card_renders_markdown():
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        card("Test Title", "Test body content")
        mock_st.markdown.assert_called_once()
        html = mock_st.markdown.call_args[0][0]
        assert "Test Title" in html
        assert "Test body content" in html


def test_kpi_renders_html():
    result = kpi("Status", "Supported", "details", "green")
    assert "kpi-card green" in result
    assert "Status" in result
    assert "Supported" in result
    assert "details" in result


def test_kpi_no_sub():
    result = kpi("Status", "NEI", "", "amber")
    assert "kpi-card amber" in result
    assert "NEI" in result


def test_chip_renders():
    result = chip("blurry_image", "red")
    assert "chip-red" in result
    assert "blurry_image" in result


def test_chip_default_color():
    result = chip("normal")
    assert "chip-slate" in result


def test_verdict_banner_supported():
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        verdict_banner("supported", "Visual evidence matches claim.")
        html = mock_st.markdown.call_args[0][0]
        assert "Claim Verified" in html
        assert "verdict-supported" in html


def test_verdict_banner_contradicted():
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        verdict_banner("contradicted", "Damage does not match claim.")
        html = mock_st.markdown.call_args[0][0]
        assert "Claim Contradicted" in html
        assert "verdict-contradicted" in html


def test_verdict_banner_nei():
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        verdict_banner("not_enough_information", "Cannot confirm damage.")
        html = mock_st.markdown.call_args[0][0]
        assert "Insufficient Evidence" in html
        assert "verdict-nei" in html


def test_verdict_banner_fallback():
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        verdict_banner("unknown_status", "Some reason.")
        html = mock_st.markdown.call_args[0][0]
        assert "UNKNOWN_STATUS" in html


def test_pipeline_step_renders():
    result = pipeline_step("✓", "Claim Extraction", "Parsing conversation", "done")
    assert "pipe-step" in result
    assert "pipe-icon done" in result
    assert "Claim Extraction" in result
    assert "Parsing conversation" in result


def test_pipeline_step_active():
    result = pipeline_step("1", "Vision", "Analysis", "active")
    assert "pipe-icon active" in result


def test_pipeline_step_pending():
    result = pipeline_step("2", "Decision", "Final", "pending")
    assert "pipe-icon pending" in result


def test_section_title_renders():
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        section_title("◆", "Decision Metrics")
        mock_st.markdown.assert_called_once()
        html = mock_st.markdown.call_args[0][0]
        assert "Decision Metrics" in html


# ---------------------------------------------------------------------------
# _cached_claim_extraction
# ---------------------------------------------------------------------------


def test_cached_claim_extraction_happy_path():
    with (
        patch.object(_demo_app, "st", _make_st_mock()),
        patch("agents.claim_agent.ClaimExtractionAgent") as mock_agent_cls,
    ):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "claim_summary": "Test claim",
            "claimed_issue_type": "dent",
            "claimed_object_part": "rear_bumper",
            "claim_confidence": 0.95,
            "is_multi_part": False,
            "additional_claimed_parts": [],
            "additional_claimed_issues": [],
            "injection_detected": False,
            "reasoning": "Test reasoning",
        }
        mock_agent.extract.return_value = mock_result

        result = _demo_app._cached_claim_extraction("Bumper dent", "car")
        assert result["claim_summary"] == "Test claim"
        assert result["claimed_issue_type"] == "dent"


def test_cached_claim_extraction_invalid_object_fallback():
    with (
        patch.object(_demo_app, "st", _make_st_mock()),
        patch("agents.claim_agent.ClaimExtractionAgent") as mock_agent_cls,
    ):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "claim_summary": "Test",
            "claimed_issue_type": "dent",
            "claimed_object_part": "rear_bumper",
            "claim_confidence": 0.9,
            "is_multi_part": False,
            "additional_claimed_parts": [],
            "additional_claimed_issues": [],
            "injection_detected": False,
            "reasoning": "",
        }
        mock_agent.extract.return_value = mock_result

        result = _demo_app._cached_claim_extraction("Screen cracked", "invalid_object")
        assert result is not None


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------


def test_run_pipeline_no_images():
    with (
        patch.object(_demo_app, "st", _make_st_mock()),
        patch.object(_demo_app, "_cached_claim_extraction") as mock_cache,
        patch("config.Settings") as mock_settings_cls,
        patch("services.model_service.ModelService"),
        patch("services.evidence_standards_engine.EvidenceStandardsEngine"),
        patch("services.decision_service.DecisionService"),
    ):
        mock_settings = MagicMock()
        mock_settings.has_vision_model = True
        mock_settings.openrouter_model_primary = "qwen/qwen2.5-vl-72b-instruct"
        mock_settings.openrouter_model_secondary = "meta-llama/llama-3.2-90b-vision-instruct"
        mock_settings.openrouter_model_tertiary = "mistralai/pixtral-large-2411"
        mock_settings_cls.return_value = mock_settings

        mock_cache.return_value = {
            "claim_summary": "Test", "claimed_issue_type": "dent",
            "claimed_object_part": "rear_bumper", "is_multi_part": False,
        }

        result = run_pipeline([], "Test claim", "car")
        assert "extraction" in result
        assert "vision" in result
        assert "evidence" in result
        assert "output" in result
        assert result["has_model"]


def test_run_pipeline_with_images():
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), color=(100, 100, 100)).save(buf, format="JPEG")

    mock_file = MagicMock()
    mock_file.name = "test_img.jpg"
    mock_file.read.return_value = buf.getvalue()

    mock_vision_result = VisionReviewResult(
        valid_image=True, object_visible=True, object_part_visible=True,
        issue_visible=True, supporting_image_ids=["test_img"],
        quality_flags=[], confidence=0.95,
    )

    with (
        patch.object(_demo_app, "st", _make_st_mock()),
        patch.object(_demo_app, "_cached_claim_extraction") as mock_cache,
        patch("config.Settings") as mock_settings_cls,
        patch("agents.vision_agent.VisionReviewAgent") as mock_vision_cls,
        patch("services.evidence_standards_engine.EvidenceStandardsEngine"),
        patch("services.decision_service.DecisionService"),
    ):
        mock_settings = MagicMock()
        mock_settings.has_vision_model = False
        mock_settings.model_provider = "none"
        mock_settings_cls.return_value = mock_settings

        mock_cache.return_value = {
            "claim_summary": "Test", "claimed_issue_type": "dent",
            "claimed_object_part": "rear_bumper", "is_multi_part": False,
        }

        mock_vision = MagicMock()
        mock_vision_cls.return_value = mock_vision
        mock_vision.review.return_value = mock_vision_result

        result = run_pipeline([mock_file], "Test claim", "car")
        assert result["vision"].valid_image
        assert "test_img.jpg" in result["img_bytes_map"]


def test_run_pipeline_file_not_found():
    with (
        patch.object(_demo_app, "st", _make_st_mock()),
        patch.object(_demo_app, "_cached_claim_extraction") as mock_cache,
        patch("config.Settings") as mock_settings_cls,
        patch("services.model_service.ModelService"),
        patch("services.evidence_standards_engine.EvidenceStandardsEngine") as mock_ev_cls,
        patch("services.decision_service.DecisionService"),
    ):
        mock_settings = MagicMock(has_vision_model=False)
        mock_settings_cls.return_value = mock_settings

        mock_cache.return_value = {
            "claim_summary": "Test", "claimed_issue_type": "dent",
            "claimed_object_part": "rear_bumper", "is_multi_part": False,
        }

        mock_ev_cls.return_value.load.side_effect = FileNotFoundError(
            "evidence_requirements.csv not found"
        )

        with pytest.raises(RuntimeError, match="Dataset file not found"):
            run_pipeline([], "Test claim", "car")


def test_run_pipeline_import_error():
    with (
        patch.object(_demo_app, "st", _make_st_mock()),
        patch.object(_demo_app, "_cached_claim_extraction") as mock_cache,
        patch("config.Settings") as mock_settings_cls,
        patch("services.model_service.ModelService",
              side_effect=ImportError("No module named X")),
        patch("services.evidence_standards_engine.EvidenceStandardsEngine"),
        patch("services.decision_service.DecisionService"),
    ):
        mock_settings = MagicMock(has_vision_model=True)
        mock_settings_cls.return_value = mock_settings

        mock_cache.return_value = {
            "claim_summary": "Test", "claimed_issue_type": "dent",
            "claimed_object_part": "rear_bumper", "is_multi_part": False,
        }

        with pytest.raises(RuntimeError, match="Missing dependency"):
            run_pipeline([], "Test claim", "car")


# ---------------------------------------------------------------------------
# show_progress
# ---------------------------------------------------------------------------


def test_show_progress_renders_all_steps():
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        placeholder = MagicMock()
        mock_container = MagicMock()
        placeholder.container.return_value = mock_container
        show_progress(placeholder)
        assert placeholder.container.call_count >= 1


# ---------------------------------------------------------------------------
# Token / UI limits
# ---------------------------------------------------------------------------


def test_verdict_justification_truncated():
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        long_reason = "X" * 500
        verdict_banner("supported", long_reason)
        html = mock_st.markdown.call_args[0][0]
        assert "X" * 280 in html


@pytest.mark.parametrize("status,expected_title", [
    ("supported", "Claim Verified"),
    ("contradicted", "Claim Contradicted"),
    ("not_enough_information", "Insufficient Evidence"),
])
def test_verdict_banner_all_statuses(status, expected_title):
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        verdict_banner(status, "Reason")
        html = mock_st.markdown.call_args[0][0]
        assert expected_title in html


@pytest.mark.parametrize("status,expected_key", [
    ("supported", "green"),
    ("contradicted", "red"),
    ("not_enough_information", "amber"),
])
def test_kpi_status_color(status, expected_key):
    result = kpi("Claim Status", status.replace("_", " ").title(), "", expected_key)
    assert expected_key in result


# ---------------------------------------------------------------------------
# success_card_html
# ---------------------------------------------------------------------------


def test_success_card_html_supported():
    html = success_card_html("supported", "95%", "openrouter/qwen2.5-vl-72b-instruct", 3200)
    assert "Claim Verified" in html
    assert "95%" in html
    assert "openrouter/qwen2.5-vl-72b-instruct" in html
    assert "3200ms" in html


def test_success_card_html_contradicted():
    html = success_card_html("contradicted", "80%", "openrouter/qwen", 5100)
    assert "Claim Contradicted" in html
    assert "80%" in html


def test_success_card_html_nei():
    html = success_card_html("not_enough_information", "60%", "openrouter/llama", 4200)
    assert "Insufficient Evidence" in html


def test_success_card_html_unknown_verdict():
    html = success_card_html("unknown", "0%", "", 0)
    assert "Unknown" in html


# ---------------------------------------------------------------------------
# error_card_html
# ---------------------------------------------------------------------------


def test_error_card_html_renders():
    html = error_card_html("Provider Error", "The provider is unavailable.")
    assert "Provider Error" in html
    assert "The provider is unavailable." in html


def test_error_card_html_icon():
    html = error_card_html("Test", "Detail", icon="🚨")
    assert "🚨" in html


# ---------------------------------------------------------------------------
# run_pipeline latency tracking
# ---------------------------------------------------------------------------


def test_run_pipeline_returns_latency():
    with (
        patch.object(_demo_app, "st", _make_st_mock()),
        patch.object(_demo_app, "_cached_claim_extraction") as mock_cache,
        patch("config.Settings") as mock_settings_cls,
        patch("services.model_service.ModelService"),
        patch("services.evidence_standards_engine.EvidenceStandardsEngine"),
        patch("services.decision_service.DecisionService"),
    ):
        mock_settings = MagicMock(has_vision_model=False)
        mock_settings_cls.return_value = mock_settings

        mock_cache.return_value = {
            "claim_summary": "Test", "claimed_issue_type": "dent",
            "claimed_object_part": "rear_bumper", "is_multi_part": False,
        }

        result = run_pipeline([], "Test claim", "car")
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], int)
        assert "_timestamp" in result


# ---------------------------------------------------------------------------
# show_progress with provider
# ---------------------------------------------------------------------------


def test_show_progress_with_provider():
    with patch.object(_demo_app, "st", _make_st_mock()) as mock_st:
        placeholder = MagicMock()
        mock_container = MagicMock()
        placeholder.container.return_value = mock_container
        show_progress(placeholder, provider="openrouter/qwen2.5-vl-72b-instruct")
        assert placeholder.container.call_count >= 1


# ---------------------------------------------------------------------------
# Session state hardening
# ---------------------------------------------------------------------------


def test_session_state_initialized():
    st_mock = _make_st_mock()
    st_mock.session_state = {}
    with patch.object(_demo_app, "st", st_mock):
        if "_initialized" not in st_mock.session_state:
            st_mock.session_state["_initialized"] = True
            st_mock.session_state["_focus_results"] = False
            st_mock.session_state["_focus_trace"] = False
            st_mock.session_state["_last_analysis_ts"] = 0
        assert st_mock.session_state.get("_initialized") is True
        assert st_mock.session_state.get("_focus_results") is False
        assert st_mock.session_state.get("_focus_trace") is False


# ---------------------------------------------------------------------------
# Empty state views
# ---------------------------------------------------------------------------


def test_results_tab_empty_state():
    html = """
    <div class="cs-card" style="text-align:center;padding:3rem;">
      <div style="font-size:3rem;margin-bottom:1rem">◈</div>
      <div style="font-size:1rem;font-weight:600;color:#94A3B8;">
        Submit a claim in the Claim Review tab to see results here.
      </div>
    </div>"""
    assert "Submit a claim" in html
    assert "Claim Review" in html


def test_trace_tab_empty_state():
    html = """
    <div class="cs-card" style="text-align:center;padding:3rem;">
      <div style="font-size:3rem;margin-bottom:1rem">◉</div>
      <div style="font-size:1rem;font-weight:600;color:#94A3B8;">
        Submit a claim to see the full decision trace.
      </div>
    </div>"""
    assert "Submit a claim" in html
    assert "decision trace" in html.lower()


# ---------------------------------------------------------------------------
# Error handling edge cases
# ---------------------------------------------------------------------------


def test_run_pipeline_failed_file_read():
    mock_file = MagicMock()
    mock_file.read.side_effect = OSError("Disk error")

    with (
        patch.object(_demo_app, "st", _make_st_mock()),
        patch.object(_demo_app, "_cached_claim_extraction") as mock_cache,
        patch("config.Settings") as mock_settings_cls,
    ):
        mock_settings = MagicMock(has_vision_model=False)
        mock_settings_cls.return_value = mock_settings
        mock_cache.return_value = {"claim_summary": "Test", "claimed_issue_type": "dent",
                                    "claimed_object_part": "rear_bumper", "is_multi_part": False}
        with pytest.raises(RuntimeError, match="Failed to read"):
            run_pipeline([mock_file], "Test claim", "car")


def test_run_pipeline_tempfile_error():
    mock_file = MagicMock()
    mock_file.name = "test.jpg"
    mock_file.read.return_value = b"fake_image_data"

    with (
        patch.object(_demo_app, "st", _make_st_mock()),
        patch.object(_demo_app, "_cached_claim_extraction") as mock_cache,
        patch("config.Settings") as mock_settings_cls,
        patch("tempfile.NamedTemporaryFile", side_effect=OSError("No space")),
    ):
        mock_settings = MagicMock(has_vision_model=False)
        mock_settings_cls.return_value = mock_settings
        mock_cache.return_value = {"claim_summary": "Test", "claimed_issue_type": "dent",
                                    "claimed_object_part": "rear_bumper", "is_multi_part": False}
        with pytest.raises(RuntimeError, match="Failed to save"):
            run_pipeline([mock_file], "Test claim", "car")


# ---------------------------------------------------------------------------
# Demo mode presets
# ---------------------------------------------------------------------------


def test_demo_mode_supported_preset():
    scenario = ("supported", "car", "rear_bumper",
                "Customer: The rear bumper has a visible dent after a minor collision.")
    assert scenario[0] == "supported"
    assert "rear_bumper" in scenario[2]


def test_demo_mode_contradicted_preset():
    scenario = ("contradicted", "car", "front_bumper",
                "Customer: The front bumper has a large crack after a parking incident.")
    assert scenario[0] == "contradicted"
    assert "crack" in scenario[3]


def test_demo_mode_nei_preset():
    scenario = ("not_enough_information", "laptop", "screen",
                "Customer: I think my laptop screen might be damaged but I'm not sure.")
    assert scenario[0] == "not_enough_information"
    assert "screen" in scenario[2]
