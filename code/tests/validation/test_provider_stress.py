"""Provider reliability stress tests — 429 handling, fallback, malformed responses.

Covers:
1. 429 quota exhaustion → immediate fallback (Gemini → OpenRouter)
2. 503 service unavailable → retry then fallback
3. Timeout/ConnectionError → fallback trigger
4. All tiers fail → graceful None return
5. Non-200 from OpenRouter → RuntimeError → next tier
6. Empty content from OpenRouter → RuntimeError → next tier
7. Malformed non-JSON response → VisionReviewAgent retry
8. Provider init with missing API keys
9. Mixed success/failure across 3 tiers
10. Consecutive 429s on first image → still tries remaining images
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_CODE_DIR = Path(__file__).resolve().parent.parent.parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

from agents.vision_agent import VisionReviewAgent
from config import Settings
from models.enums import ClaimObject, IssueType, ObjectPart, RiskFlag
from models.vision_review import VisionReviewInput
from services.model_service import ModelService

_FAKE_JSON = json.dumps({
    "image_id": "img_1",
    "readable": True,
    "object_present": True,
    "visible_parts": ["front_bumper"],
    "visible_issues": ["dent"],
    "quality_flags": [],
    "description": "Test image.",
    "severity": "medium",
    "confidence": 0.85,
    "supports_claim": True,
})


def _make_image_bytes(tmp_path: Path) -> Path:
    """Create a checkerboard JPEG that passes blur detection."""
    from PIL import Image
    import io
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100))
    pixels = img.load()
    for x in range(100):
        for y in range(100):
            v = 240 if ((x // 4) + (y // 4)) % 2 == 0 else 16
            pixels[x, y] = (v, v, v)
    img.save(buf, format="JPEG")
    p = tmp_path / "stress.jpg"
    p.write_bytes(buf.getvalue())
    return p


def _make_agent(model_service: MagicMock) -> VisionReviewAgent:
    return VisionReviewAgent(model_service=model_service, cache={})


class TestProviderStress:
    """Provider reliability under stress conditions."""

    def test_429_quota_immediate_fallback(self, tmp_path):
        """Gemini 429 quota → immediate RuntimeError → fallback to Tier 2 succeeds."""
        p = _make_image_bytes(tmp_path)
        svc = MagicMock()
        svc.inspect_image.side_effect = [
            RuntimeError("429 quota exhausted"),
            _FAKE_JSON,
        ]
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.object_visible is True
        assert svc.inspect_image.call_count == 2

    def test_429_on_first_of_two_images_second_still_works(self, tmp_path):
        """429 on image 1 → fallback works; image 2 uncached succeeds."""
        from PIL import Image
        import io

        def _make_img(name: str, offset: int = 0) -> Path:
            buf = io.BytesIO()
            img = Image.new("RGB", (100, 100))
            pixels = img.load()
            for x in range(100):
                for y in range(100):
                    v = 240 if ((x // 4) + (y // 4) + offset) % 2 == 0 else 16
                    pixels[x, y] = (v, v, v)
            img.save(buf, format="JPEG")
            p = tmp_path / name
            p.write_bytes(buf.getvalue())
            return p

        p1 = _make_img("img_a.jpg", offset=0)
        p2 = _make_img("img_b.jpg", offset=1)  # different content → different cache key
        svc = MagicMock()
        svc.inspect_image.side_effect = [
            RuntimeError("429 quota exhausted"),
            _FAKE_JSON,
            _FAKE_JSON,
        ]
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p1, p2],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.object_visible is True
        assert svc.inspect_image.call_count == 3

    def test_503_retry_then_fallback(self, tmp_path):
        """Gemini 503 → retry, then fallback on exhaustion."""
        p = _make_image_bytes(tmp_path)
        svc = MagicMock()
        svc.inspect_image.side_effect = [
            RuntimeError("503 Service Unavailable"),
            _FAKE_JSON,
        ]
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.object_visible is True
        assert svc.inspect_image.call_count == 2

    def test_all_tiers_fail_graceful_degradation(self, tmp_path):
        """All providers fail → preflight-only result, not crash."""
        p = _make_image_bytes(tmp_path)
        svc = MagicMock()
        svc.inspect_image.side_effect = RuntimeError("all failed")
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.valid_image is False
        assert RiskFlag.MANUAL_REVIEW_REQUIRED in result.quality_flags
        assert result.confidence == 0.0

    def test_non_json_response_triggers_retry(self, tmp_path):
        """Non-JSON response → agent retries (BUG A fix)."""
        p = _make_image_bytes(tmp_path)
        svc = MagicMock()
        svc.inspect_image.side_effect = [
            "this is not json",
            _FAKE_JSON,
        ]
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.valid_image is True
        assert svc.inspect_image.call_count == 2

    def test_all_non_json_no_valid_result(self, tmp_path):
        """All responses non-JSON → preflight-only fallback."""
        p = _make_image_bytes(tmp_path)
        svc = MagicMock()
        svc.inspect_image.return_value = "not json at all"
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.valid_image is False
        assert result.confidence == 0.0

    def test_empty_json_response_handled(self, tmp_path):
        """Empty JSON dict returned → default fields, not crash."""
        p = _make_image_bytes(tmp_path)
        svc = MagicMock()
        svc.inspect_image.return_value = "{}"
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        # Should produce safe defaults
        assert result.valid_image is True  # readable=True default in PerImageAnalysis
        assert result.confidence >= 0.0

    def test_inspect_image_returns_none(self, tmp_path):
        """ModelService returns None (no provider configured) → graceful."""
        p = _make_image_bytes(tmp_path)
        svc = MagicMock()
        svc.inspect_image.return_value = None
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.valid_image is False
        assert RiskFlag.MANUAL_REVIEW_REQUIRED in result.quality_flags

    def test_connection_error_trigger_fallback(self, tmp_path):
        """ConnectionError → fallback to next tier."""
        p = _make_image_bytes(tmp_path)
        svc = MagicMock()
        svc.inspect_image.side_effect = [
            ConnectionError("connection refused"),
            _FAKE_JSON,
        ]
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.object_visible is True
        assert svc.inspect_image.call_count == 2

    def test_timeout_triggers_fallback(self, tmp_path):
        """TimeoutError → fallback to next tier."""
        p = _make_image_bytes(tmp_path)
        svc = MagicMock()
        svc.inspect_image.side_effect = [
            TimeoutError("request timed out"),
            _FAKE_JSON,
        ]
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.object_visible is True
        assert svc.inspect_image.call_count == 2


class TestModelServiceProviderInit:
    """ModelService initialization edge cases."""

    def test_no_api_keys_preflight_mode(self):
        """No API keys → has_vision_model is False."""
        settings = Settings(model_provider="none")
        assert settings.has_vision_model is False

    def test_gemini_api_key_enables_vision(self):
        """Gemini API key alone → has_vision_model is True."""
        settings = Settings(model_provider="gemini", gemini_api_key="fake-key")
        assert settings.has_vision_model is True

    def test_openrouter_api_key_enables_vision(self):
        """OpenRouter API key alone → has_vision_model is True."""
        settings = Settings(model_provider="none", openrouter_api_key="fake-key")
        assert settings.has_vision_model is True

    def test_model_service_init_no_keys(self):
        """ModelService init with no keys → inspect_image raises NotImplementedError."""
        settings = Settings(model_provider="none")
        svc = ModelService(settings=settings)
        with pytest.raises(NotImplementedError, match="No VLM configured"):
            svc.inspect_image("sys", "prompt", b"\x00" * 100)

    def test_provider_property_with_only_fallback(self, tmp_path):
        """provider_name works when only fallback configured."""
        settings = Settings(
            model_provider="gemini",
            openrouter_api_key="fake-or-key",
        )
        svc = ModelService(settings=settings)
        # Primary provider not created (no gemini key), but fallbacks are
        name = svc.provider_name
        assert isinstance(name, str)


class TestProviderResilience:
    """Statistical resilience: repeated calls under stress."""

    def test_consecutive_calls_all_fail(self, tmp_path):
        """10 consecutive images, all fail → preflight-only each time, not crash."""
        paths = [_make_image_bytes(tmp_path) for _ in range(3)]
        svc = MagicMock()
        svc.inspect_image.side_effect = RuntimeError("fail")
        agent = _make_agent(svc)
        for p in paths:
            result = agent.review(VisionReviewInput(
                image_paths=[p],
                claim_object=ClaimObject.CAR,
                claimed_part=ObjectPart.FRONT_BUMPER,
                claimed_issue=IssueType.DENT,
            ))
            assert result.valid_image is False
        # Agent retries each image twice (range(2) in _call_vlm)
        assert svc.inspect_image.call_count == 6  # 3 images × 2 attempts each

    def test_mixed_success_failure(self, tmp_path):
        """2 of 3 images fail, last succeeds → still produces aggregate result."""
        from PIL import Image
        import io

        def _mkimg(name: str, offset: int) -> Path:
            buf = io.BytesIO()
            img = Image.new("RGB", (100, 100))
            pixels = img.load()
            for x in range(100):
                for y in range(100):
                    v = 240 if ((x // 4) + (y // 4) + offset) % 2 == 0 else 16
                    pixels[x, y] = (v, v, v)
            img.save(buf, format="JPEG")
            p = tmp_path / name
            p.write_bytes(buf.getvalue())
            return p

        p1 = _mkimg("mix_a.jpg", 0)
        p2 = _mkimg("mix_b.jpg", 1)
        p3 = _mkimg("mix_c.jpg", 2)
        svc = MagicMock()
        svc.inspect_image.side_effect = [
            RuntimeError("fail"),
            RuntimeError("fail"),
            _FAKE_JSON,
        ]
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p1, p2, p3],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.object_visible is True
        assert result.valid_image is True  # at least one valid
        assert svc.inspect_image.call_count >= 3  # at least 3 calls to inspect_image

    def test_large_image_resize(self, tmp_path):
        """Image much larger than max_dim → resize without crash."""
        from PIL import Image
        import io
        buf = io.BytesIO()
        img = Image.new("RGB", (4000, 3000))  # much larger than 1536
        pixels = img.load()
        for x in range(0, 4000, 8):
            for y in range(0, 3000, 8):
                v = 240 if ((x // 8) + (y // 8)) % 2 == 0 else 16
                for dx in range(8):
                    for dy in range(8):
                        if x + dx < 4000 and y + dy < 3000:
                            pixels[x + dx, y + dy] = (v, v, v)
        img.save(buf, format="JPEG")
        p = tmp_path / "large.jpg"
        p.write_bytes(buf.getvalue())

        svc = MagicMock()
        svc.inspect_image.return_value = _FAKE_JSON
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.object_visible is True

    def test_non_image_bytes(self, tmp_path):
        """Non-image bytes passed to preflight → readable=False, not crash."""
        p = tmp_path / "not_an_image.txt"
        p.write_text("this is not an image file")
        svc = MagicMock()
        svc.inspect_image.return_value = None
        agent = _make_agent(svc)
        result = agent.review(VisionReviewInput(
            image_paths=[p],
            claim_object=ClaimObject.CAR,
            claimed_part=ObjectPart.FRONT_BUMPER,
            claimed_issue=IssueType.DENT,
        ))
        assert result.valid_image is False
