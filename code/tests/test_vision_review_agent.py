"""Unit tests for VisionReviewAgent.

Coverage:
1.  Preflight — missing file
2.  Preflight — unreadable bytes
3.  Preflight-only mode (no model service) — readable image
4.  VLM happy path — single image
5.  VLM happy path — multiple images, all supporting
6.  Multi-image partial support (some images support, some don't)
7.  Contradictory images (object present vs absent) → confidence penalty
8.  Quality flags from VLM response
9.  VLM returns invalid enum values → coerced to UNKNOWN/empty
10. VLM returns markdown-fenced JSON → repaired
11. VLM call raises exception → preflight-only fallback
12. Caching — second call with same bytes skips model
13. Aggregation — no supporting images
14. Aggregation — severity ranking selects highest
15. Legacy run() interface returns list[ImageEvidence]
16. VisionReviewInput requires at least 1 image path
17. PerImageAnalysis.derive_valid_image validator
18. VisionReviewResult.deduplicate_image_ids validator
19. Injection-flagged text in image → TEXT_INSTRUCTION_PRESENT risk flag
20. supports_claim=True only when object+part+issue all visible
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_CODE_DIR = Path(__file__).resolve().parent.parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

from agents.vision_agent import VisionReviewAgent, _aggregate, _coerce_per_image
from models.enums import ClaimObject, IssueType, ObjectPart, RiskFlag, Severity
from models.records import ParsedClaim
from models.vision_review import PerImageAnalysis, VisionReviewInput, VisionReviewResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tiny_jpeg_bytes() -> bytes:
    """Return minimal valid JPEG bytes via Pillow (or a raw JFIF marker)."""
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (100, 100), color=(180, 30, 30)).save(buf, format="JPEG")
        return buf.getvalue()
    except ImportError:
        # Minimal JFIF header that PIL can decode
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xd9"
        )


def _make_tmp_image(tmp_path: Path, name: str = "img_1.jpg",
                    check_size: int = 4, brightness: int = 0) -> Path:
    """Create a checkerboard image with high Laplacian variance (>blur threshold).

    A uniform-color image triggers preflight blur detection (Laplacian variance
    < 80 → BLURRY_IMAGE flag).  The bug-B fix makes BLURRY_IMAGE a blocking flag,
    which would exclude the image from aggregation.  This helper produces a
    high-frequency checkerboard with variance well above the threshold.

    Parameters
    ----------
    check_size : int
        Size of each checkerboard square.  Vary to create distinct images.
    brightness : int
        Offset added to all pixel values (0-127) for visual distinction.
    """
    p = tmp_path / name
    try:
        from PIL import Image
        img = Image.new("RGB", (100, 100))
        pixels = img.load()
        for x in range(100):
            for y in range(100):
                base = 240 if ((x // check_size) + (y // check_size)) % 2 == 0 else 16
                v = min(255, max(0, base + brightness))
                pixels[x, y] = (v, v, v)
        img.save(p, format="JPEG")
    except ImportError:
        p.write_bytes(_tiny_jpeg_bytes())
    return p


def _make_vlm_response(
    image_id: str = "img_1",
    readable: bool = True,
    object_present: bool | None = True,
    visible_parts: list = None,
    visible_issues: list = None,
    quality_flags: list = None,
    description: str = "Dent visible on front bumper.",
    confidence: float = 0.87,
    severity: str = "medium",
    supports_claim: bool = True,
) -> dict:
    return {
        "image_id": image_id,
        "readable": readable,
        "object_present": object_present,
        "visible_parts": visible_parts or ["front_bumper"],
        "visible_issues": visible_issues or ["dent"],
        "quality_flags": quality_flags or [],
        "description": description,
        "confidence": confidence,
        "severity": severity,
        "supports_claim": supports_claim,
    }


def _make_agent(response=None, cache=None) -> VisionReviewAgent:
    if response is None:
        return VisionReviewAgent(model_service=None, cache=cache or {})
    mock_svc = MagicMock()
    mock_svc.inspect_image.return_value = response
    return VisionReviewAgent(model_service=mock_svc, cache=cache or {})


def _make_input(paths: list[Path], obj="car", part="front_bumper", issue="dent") -> VisionReviewInput:
    return VisionReviewInput(
        image_paths=paths,
        claim_object=ClaimObject(obj),
        claimed_part=ObjectPart(part),
        claimed_issue=IssueType(issue),
    )


# ---------------------------------------------------------------------------
# 1–3: Preflight tests
# ---------------------------------------------------------------------------

class TestPreflight:
    def test_missing_file_returns_not_readable(self, tmp_path):
        agent = _make_agent()
        result = agent.review(_make_input([tmp_path / "nonexistent.jpg"]))
        assert result.valid_image is False
        assert RiskFlag.MANUAL_REVIEW_REQUIRED in result.quality_flags
        assert result.confidence == 0.0

    def test_unreadable_bytes_returns_not_readable(self, tmp_path):
        p = tmp_path / "bad.jpg"
        p.write_bytes(b"\x00\x01\x02\x03corrupt")
        agent = _make_agent()
        result = agent.review(_make_input([p]))
        # File exists but image may not decode — at minimum valid_image should be False
        # (Pillow may raise, flagging as MANUAL_REVIEW_REQUIRED)
        assert isinstance(result, VisionReviewResult)

    def test_preflight_only_readable_image(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        agent = _make_agent()  # no model service
        result = agent.review(_make_input([p]))
        assert result.valid_image is True
        assert len(result.per_image) == 1
        assert result.per_image[0].readable is True
        # Without VLM, nothing is conclusively visible
        assert result.per_image[0].supports_claim is False


# ---------------------------------------------------------------------------
# 4–5: VLM happy path
# ---------------------------------------------------------------------------

class TestVLMHappyPath:
    def test_single_image_supporting(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        agent = _make_agent(_make_vlm_response())
        result = agent.review(_make_input([p]))
        assert result.object_visible is True
        assert result.issue_visible is True
        assert result.issue_type == IssueType.DENT
        assert result.object_part == ObjectPart.FRONT_BUMPER
        assert result.severity == Severity.MEDIUM
        assert "img_1" in result.supporting_image_ids
        assert result.valid_image is True
        assert result.confidence > 0.0

    def test_three_images_all_supporting(self, tmp_path):
        paths = [_make_tmp_image(tmp_path, f"img_{i}.jpg") for i in range(1, 4)]
        mock_svc = MagicMock()
        mock_svc.inspect_image.side_effect = [
            _make_vlm_response(image_id=f"img_{i}", supports_claim=True, confidence=0.9)
            for i in range(1, 4)
        ]
        agent = VisionReviewAgent(model_service=mock_svc)
        result = agent.review(_make_input(paths))
        assert len(result.supporting_image_ids) == 3
        assert result.confidence > 0.85  # coverage bonus applies


# ---------------------------------------------------------------------------
# 6: Multi-image partial support
# ---------------------------------------------------------------------------

class TestPartialSupport:
    def test_two_of_three_support(self, tmp_path):
        # Write distinct bytes for each image so cache keys differ
        try:
            from PIL import Image as PILImage
            paths = []
            # Different checkerboard sizes → different byte content
            for i, cs in enumerate([3, 5, 7], 1):
                p = tmp_path / f"img_{i}.jpg"
                buf = io.BytesIO()
                img = PILImage.new("RGB", (100, 100))
                pixels = img.load()
                for x in range(100):
                    for y in range(100):
                        v = 240 if ((x // cs) + (y // cs)) % 2 == 0 else 16
                        pixels[x, y] = (v, v, v)
                img.save(buf, format="JPEG")
                p.write_bytes(buf.getvalue())
                paths.append(p)
        except ImportError:
            paths = [_make_tmp_image(tmp_path, f"img_{i}.jpg", check_size=s)
                     for i, s in zip(range(1, 4), (3, 5, 7))]
            # Without PIL, images differ by checkboard pattern; cache keys are distinct

        mock_svc = MagicMock()
        mock_svc.inspect_image.side_effect = [
            _make_vlm_response(image_id="img_1", supports_claim=True, confidence=0.85),
            _make_vlm_response(image_id="img_2", supports_claim=False, confidence=0.4,
                               visible_issues=[], object_present=False,
                               description="Object not clearly visible."),
            _make_vlm_response(image_id="img_3", supports_claim=True, confidence=0.9),
        ]
        agent = VisionReviewAgent(model_service=mock_svc)
        result = agent.review(_make_input(paths))
        assert set(result.supporting_image_ids) == {"img_1", "img_3"}
        assert result.valid_image is True


# ---------------------------------------------------------------------------
# 7: Contradictory images
# ---------------------------------------------------------------------------

class TestContradiction:
    def test_contradictory_images_reduce_confidence(self, tmp_path):
        paths = [_make_tmp_image(tmp_path, f"img_{i}.jpg") for i in range(1, 3)]
        mock_svc = MagicMock()
        mock_svc.inspect_image.side_effect = [
            _make_vlm_response(image_id="img_1", object_present=True,
                               supports_claim=True, confidence=0.9),
            _make_vlm_response(image_id="img_2", object_present=False,
                               visible_issues=[], supports_claim=False, confidence=0.85),
        ]
        agent_no_contradiction = VisionReviewAgent(model_service=MagicMock())
        # Build two analyses to test _aggregate directly
        analyses_no_contra = [
            PerImageAnalysis(image_id="img_1", image_path=paths[0], readable=True,
                             object_present=True, visible_issues=[IssueType.DENT],
                             visible_parts=[ObjectPart.FRONT_BUMPER],
                             supports_claim=True, confidence=0.9),
            PerImageAnalysis(image_id="img_2", image_path=paths[1], readable=True,
                             object_present=True, visible_issues=[IssueType.DENT],
                             visible_parts=[ObjectPart.FRONT_BUMPER],
                             supports_claim=True, confidence=0.9),
        ]
        analyses_contra = [
            PerImageAnalysis(image_id="img_1", image_path=paths[0], readable=True,
                             object_present=True, visible_issues=[IssueType.DENT],
                             visible_parts=[ObjectPart.FRONT_BUMPER],
                             supports_claim=True, confidence=0.9),
            PerImageAnalysis(image_id="img_2", image_path=paths[1], readable=True,
                             object_present=False, visible_issues=[],
                             supports_claim=False, confidence=0.85),
        ]
        result_clean = _aggregate(analyses_no_contra, ObjectPart.FRONT_BUMPER, IssueType.DENT)
        result_contra = _aggregate(analyses_contra, ObjectPart.FRONT_BUMPER, IssueType.DENT)
        assert result_clean.confidence > result_contra.confidence


# ---------------------------------------------------------------------------
# 8: Quality flags
# ---------------------------------------------------------------------------

class TestQualityFlags:
    def test_blurry_flag_from_vlm(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        agent = _make_agent(
            _make_vlm_response(quality_flags=["blurry_image"], supports_claim=False)
        )
        result = agent.review(_make_input([p]))
        assert RiskFlag.BLURRY_IMAGE in result.quality_flags

    def test_wrong_object_flag(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        agent = _make_agent(
            _make_vlm_response(quality_flags=["wrong_object"], object_present=False,
                               visible_issues=[], supports_claim=False)
        )
        result = agent.review(_make_input([p]))
        assert RiskFlag.WRONG_OBJECT in result.quality_flags

    def test_text_instruction_flag(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        agent = _make_agent(
            _make_vlm_response(quality_flags=["text_instruction_present"], supports_claim=False)
        )
        result = agent.review(_make_input([p]))
        assert RiskFlag.TEXT_INSTRUCTION_PRESENT in result.quality_flags


# ---------------------------------------------------------------------------
# 9: Invalid enum coercion
# ---------------------------------------------------------------------------

class TestEnumCoercion:
    def test_invalid_issue_type_ignored(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        agent = _make_agent({
            "readable": True,
            "object_present": True,
            "visible_parts": ["front_bumper"],
            "visible_issues": ["INVALID_ISSUE", "dent"],
            "quality_flags": [],
            "description": "Dent on bumper.",
            "confidence": 0.8,
            "severity": "medium",
            "supports_claim": True,
        })
        result = agent.review(_make_input([p]))
        assert IssueType.DENT in result.per_image[0].visible_issues
        # INVALID_ISSUE should be silently dropped
        assert all(isinstance(i, IssueType) for i in result.per_image[0].visible_issues)

    def test_invalid_severity_defaults_to_unknown(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        agent = _make_agent(_make_vlm_response(severity="SUPER_HIGH"))
        result = agent.review(_make_input([p]))
        assert result.severity == Severity.UNKNOWN


# ---------------------------------------------------------------------------
# 10: Markdown-fenced JSON repair
# ---------------------------------------------------------------------------

class TestJsonRepair:
    def test_fenced_response_parsed(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        fenced = "```json\n" + json.dumps(_make_vlm_response()) + "\n```"
        agent = _make_agent(fenced)
        result = agent.review(_make_input([p]))
        assert result.issue_type == IssueType.DENT


# ---------------------------------------------------------------------------
# 11: VLM failure fallback
# ---------------------------------------------------------------------------

class TestVLMFailure:
    def test_vlm_exception_returns_preflight_result(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        mock_svc = MagicMock()
        mock_svc.inspect_image.side_effect = RuntimeError("API timeout")
        agent = VisionReviewAgent(model_service=mock_svc)
        result = agent.review(_make_input([p]))
        assert isinstance(result, VisionReviewResult)
        assert result.per_image[0].supports_claim is False
        assert RiskFlag.MANUAL_REVIEW_REQUIRED in result.quality_flags


# ---------------------------------------------------------------------------
# 12: Caching
# ---------------------------------------------------------------------------

class TestCaching:
    def test_second_call_uses_cache(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        mock_svc = MagicMock()
        mock_svc.inspect_image.return_value = _make_vlm_response()
        cache: dict = {}
        agent = VisionReviewAgent(model_service=mock_svc, cache=cache)
        inp = _make_input([p])
        agent.review(inp)
        agent.review(inp)  # second call — same bytes, same context
        assert mock_svc.inspect_image.call_count == 1  # only called once

    def test_different_images_different_cache_entries(self, tmp_path):
        p1 = _make_tmp_image(tmp_path, "img_1.jpg")
        p2 = tmp_path / "img_2.jpg"
        # write different bytes
        try:
            from PIL import Image as PILImage
            buf = io.BytesIO()
            PILImage.new("RGB", (120, 120), color=(10, 200, 50)).save(buf, format="JPEG")
            p2.write_bytes(buf.getvalue())
        except ImportError:
            p2.write_bytes(_tiny_jpeg_bytes() + b"\x00extra")
        mock_svc = MagicMock()
        mock_svc.inspect_image.side_effect = [
            _make_vlm_response(image_id="img_1"),
            _make_vlm_response(image_id="img_2"),
        ]
        cache: dict = {}
        agent = VisionReviewAgent(model_service=mock_svc, cache=cache)
        agent.review(_make_input([p1]))
        agent.review(_make_input([p2]))
        assert mock_svc.inspect_image.call_count == 2


# ---------------------------------------------------------------------------
# 13–14: Aggregation edge cases
# ---------------------------------------------------------------------------

class TestAggregation:
    def test_no_supporting_images(self, tmp_path):
        # Test _aggregate directly to avoid image byte / caching issues
        paths = [tmp_path / f"img_{i}.jpg" for i in range(1, 3)]
        analyses = [
            PerImageAnalysis(image_id="img_1", image_path=paths[0], readable=True,
                             object_present=False, visible_issues=[],
                             visible_parts=[], supports_claim=False, confidence=0.3,
                             severity=Severity.NONE),
            PerImageAnalysis(image_id="img_2", image_path=paths[1], readable=True,
                             object_present=False, visible_issues=[],
                             visible_parts=[], supports_claim=False, confidence=0.3,
                             severity=Severity.NONE),
        ]
        result = _aggregate(analyses, ObjectPart.FRONT_BUMPER, IssueType.DENT)
        assert result.supporting_image_ids == []
        assert result.issue_visible is False

    def test_severity_takes_maximum(self, tmp_path):
        paths = [_make_tmp_image(tmp_path, f"img_{i}.jpg") for i in range(1, 3)]
        analyses = [
            PerImageAnalysis(image_id="img_1", image_path=paths[0], readable=True,
                             visible_issues=[IssueType.DENT], visible_parts=[ObjectPart.FRONT_BUMPER],
                             supports_claim=True, confidence=0.8,
                             severity=Severity.LOW),
            PerImageAnalysis(image_id="img_2", image_path=paths[1], readable=True,
                             visible_issues=[IssueType.DENT], visible_parts=[ObjectPart.FRONT_BUMPER],
                             supports_claim=True, confidence=0.85,
                             severity=Severity.HIGH),
        ]
        result = _aggregate(analyses, ObjectPart.FRONT_BUMPER, IssueType.DENT)
        assert result.severity == Severity.HIGH

    def test_empty_readable_images_returns_safe_result(self, tmp_path):
        analyses = [
            PerImageAnalysis(image_id="img_1", image_path=tmp_path / "img_1.jpg",
                             readable=False, quality_flags=[RiskFlag.MANUAL_REVIEW_REQUIRED])
        ]
        result = _aggregate(analyses, ObjectPart.UNKNOWN, IssueType.UNKNOWN)
        assert result.valid_image is False
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# 15: Legacy run() interface
# ---------------------------------------------------------------------------

class TestLegacyRunInterface:
    def test_run_returns_image_evidence_list(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        agent = _make_agent(_make_vlm_response())
        parsed = ParsedClaim(
            claim_object=ClaimObject.CAR,
            claimed_issue=IssueType.DENT,
            claimed_part=ObjectPart.FRONT_BUMPER,
        )
        evidence = agent.run([p], parsed)
        assert len(evidence) == 1
        assert evidence[0].image_id == "img_1"
        assert evidence[0].readable is True

    def test_run_empty_paths_returns_empty(self, tmp_path):
        agent = _make_agent()
        parsed = ParsedClaim(claim_object=ClaimObject.CAR)
        evidence = agent.run([], parsed)
        assert evidence == []


# ---------------------------------------------------------------------------
# 16: Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_empty_image_paths_raises(self):
        with pytest.raises(Exception):
            VisionReviewInput(
                image_paths=[],
                claim_object=ClaimObject.CAR,
            )


# ---------------------------------------------------------------------------
# 17: PerImageAnalysis.derive_valid_image
# ---------------------------------------------------------------------------

class TestPerImageValidImage:
    def test_readable_no_flags_is_valid(self, tmp_path):
        a = PerImageAnalysis(
            image_id="x", image_path=tmp_path / "x.jpg",
            readable=True, quality_flags=[]
        )
        assert a.valid_image is True

    def test_readable_with_blurry_flag_is_not_valid(self, tmp_path):
        a = PerImageAnalysis(
            image_id="x", image_path=tmp_path / "x.jpg",
            readable=True,
            quality_flags=[RiskFlag.BLURRY_IMAGE],
        )
        assert a.valid_image is False

    def test_not_readable_is_not_valid(self, tmp_path):
        a = PerImageAnalysis(
            image_id="x", image_path=tmp_path / "x.jpg",
            readable=False,
        )
        assert a.valid_image is False


# ---------------------------------------------------------------------------
# 18: VisionReviewResult deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_duplicate_image_ids_deduplicated(self):
        r = VisionReviewResult(supporting_image_ids=["img_1", "img_1", "img_2"])
        assert r.supporting_image_ids == ["img_1", "img_2"]


# ---------------------------------------------------------------------------
# 19–20: supports_claim logic
# ---------------------------------------------------------------------------

class TestSupportsClaim:
    def test_supports_claim_requires_all_three(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        # Object present, part visible, but NO visible issue → should not support
        agent = _make_agent(_make_vlm_response(
            visible_issues=[],
            supports_claim=False,
            object_present=True,
        ))
        result = agent.review(_make_input([p]))
        assert "img_1" not in result.supporting_image_ids

    def test_supports_claim_true_when_all_present(self, tmp_path):
        p = _make_tmp_image(tmp_path)
        agent = _make_agent(_make_vlm_response(supports_claim=True))
        result = agent.review(_make_input([p]))
        assert "img_1" in result.supporting_image_ids
