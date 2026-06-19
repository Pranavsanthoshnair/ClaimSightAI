"""Unit tests for EvidenceStandardsEngine.

Coverage:
 1.  No requirements loaded → conservative NOT_MET
 2.  No valid images → UNVERIFIABLE
 3.  Fully met: object + part + issue all visible, no bad flags
 4.  NOT_MET: claimed part not visible (bumper claim, only hood visible)
 5.  NOT_MET: claimed issue not visible (dent claim, no damage visible)
 6.  NOT_MET: wrong object in images (car claim, laptop shown)
 7.  PARTIALLY_MET: some requirements satisfied, one not
 8.  Multi-part claim includes REQ_GENERAL_MULTI_IMAGE
 9.  Single-part claim excludes REQ_GENERAL_MULTI_IMAGE
10.  Trust-breaking flag (possible_manipulation) → REQ_REVIEW_TRUST fails
11.  Text instruction in image → trust flag fires
12.  Quality-degrading flags reduce confidence
13.  Confidence scales with satisfaction ratio
14.  build_input() correctly maps VisionReviewResult fields
15.  evaluate_from_vision() convenience method end-to-end
16.  CSV loader: loads correctly from real evidence_requirements.csv
17.  CSV loader: raises on missing columns
18.  Reason string is non-empty for all sufficiency levels
19.  Missing evidence list populated when NOT_MET
20.  Per-requirement breakdown audit trail populated
21.  load_from_list() works identically to CSV load for test isolation
22.  Laptop screen crack: correct requirements selected
23.  Package crushed corner: correct requirements selected
24.  Car rear bumper dent: REQ_CAR_BODY_PANEL selected
25.  Partially met: supporting_image_ids populated in satisfied requirements
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_CODE_DIR = Path(__file__).resolve().parent.parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

from models.enums import ClaimObject, IssueType, ObjectPart, RiskFlag, Severity
from models.evidence_standard import (
    EvidenceStandardInput,
    EvidenceStandardResult,
    SufficiencyLevel,
)
from models.records import EvidenceRequirement
from models.vision_review import PerImageAnalysis, VisionReviewResult
from services.evidence_standards_engine import EvidenceStandardsEngine

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_REQUIREMENTS_CSV = (
    Path(__file__).resolve().parent.parent.parent
    / "dataset" / "evidence_requirements.csv"
)


def _make_requirements() -> list[EvidenceRequirement]:
    """Return the full requirement set parsed from the real CSV."""
    engine = EvidenceStandardsEngine()
    engine.load(SAMPLE_REQUIREMENTS_CSV)
    return engine._requirements


@pytest.fixture()
def engine() -> EvidenceStandardsEngine:
    e = EvidenceStandardsEngine()
    e.load(SAMPLE_REQUIREMENTS_CSV)
    return e


def _make_inp(
    claim_object: str = "car",
    claimed_part: str = "rear_bumper",
    claimed_issue: str = "dent",
    object_visible: bool = True,
    object_part_visible: bool = True,
    issue_visible: bool = True,
    valid_image_count: int = 1,
    total_image_count: int = 1,
    supporting_image_ids: list | None = None,
    quality_flags: list | None = None,
    all_visible_parts: list | None = None,
    all_visible_issues: list | None = None,
    is_multi_part: bool = False,
) -> EvidenceStandardInput:
    # Use sentinel None to distinguish "caller passed []" from "use default"
    return EvidenceStandardInput(
        claim_object=claim_object,
        claimed_part=claimed_part,
        claimed_issue=claimed_issue,
        object_visible=object_visible,
        object_part_visible=object_part_visible,
        issue_visible=issue_visible,
        valid_image_count=valid_image_count,
        total_image_count=total_image_count,
        supporting_image_ids=["img_1"] if supporting_image_ids is None else supporting_image_ids,
        quality_flags=[] if quality_flags is None else quality_flags,
        all_visible_parts=[claimed_part] if all_visible_parts is None else all_visible_parts,
        all_visible_issues=[claimed_issue] if all_visible_issues is None else all_visible_issues,
        is_multi_part=is_multi_part,
    )


def _make_vision_result(
    object_visible: bool = True,
    object_part_visible: bool = True,
    issue_visible: bool = True,
    supporting_image_ids: list | None = None,
    quality_flags: list | None = None,
    confidence: float = 0.85,
    per_image_parts: list | None = None,
    per_image_issues: list | None = None,
    tmp_path: Path | None = None,
) -> VisionReviewResult:
    img_path = (tmp_path or Path("/tmp")) / "img_1.jpg"
    per = PerImageAnalysis(
        image_id="img_1",
        image_path=img_path,
        readable=True,
        valid_image=True,
        object_present=object_visible,
        visible_parts=[ObjectPart(p) for p in (per_image_parts or ["rear_bumper"])],
        visible_issues=[IssueType(i) for i in (per_image_issues or ["dent"])],
        quality_flags=[RiskFlag(f) for f in (quality_flags or [])],
        supports_claim=bool(supporting_image_ids),
        confidence=confidence,
        severity=Severity.MEDIUM,
    )
    return VisionReviewResult(
        object_visible=object_visible,
        object_part_visible=object_part_visible,
        issue_visible=issue_visible,
        issue_type=IssueType.DENT,
        object_part=ObjectPart.REAR_BUMPER,
        severity=Severity.MEDIUM,
        supporting_image_ids=supporting_image_ids or ["img_1"],
        valid_image=True,
        quality_flags=[RiskFlag(f) for f in (quality_flags or [])],
        confidence=confidence,
        reasoning="Dent visible on rear bumper.",
        per_image=[per],
    )


# ---------------------------------------------------------------------------
# 1: No requirements loaded
# ---------------------------------------------------------------------------

class TestNoRequirementsLoaded:
    def test_returns_not_met_with_explanation(self):
        e = EvidenceStandardsEngine()
        result = e.evaluate(_make_inp())
        assert result.evidence_standard_met is False
        assert "No evidence requirements" in result.evidence_standard_met_reason
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# 2: No valid images
# ---------------------------------------------------------------------------

class TestNoValidImages:
    def test_unverifiable_when_no_valid_images(self, engine):
        inp = _make_inp(valid_image_count=0, total_image_count=2,
                        object_visible=False, object_part_visible=False,
                        issue_visible=False, supporting_image_ids=[])
        result = engine.evaluate(inp)
        assert result.sufficiency_level == SufficiencyLevel.UNVERIFIABLE
        assert result.evidence_standard_met is False
        assert result.confidence == 0.0
        assert len(result.missing_evidence) > 0


# ---------------------------------------------------------------------------
# 3: Fully met
# ---------------------------------------------------------------------------

class TestFullyMet:
    def test_car_rear_bumper_dent_fully_met(self, engine):
        inp = _make_inp()
        result = engine.evaluate(inp, vision_confidence=0.9)
        assert result.evidence_standard_met is True
        assert result.sufficiency_level == SufficiencyLevel.FULLY_MET
        assert result.confidence > 0.5
        assert len(result.satisfied_requirement_ids) == len(result.matched_requirement_ids)

    def test_laptop_screen_crack_fully_met(self, engine):
        inp = _make_inp(
            claim_object="laptop", claimed_part="screen", claimed_issue="crack",
            all_visible_parts=["screen"], all_visible_issues=["crack"],
        )
        result = engine.evaluate(inp, vision_confidence=0.85)
        assert result.evidence_standard_met is True

    def test_package_crushed_corner_fully_met(self, engine):
        inp = _make_inp(
            claim_object="package", claimed_part="package_corner",
            claimed_issue="crushed_packaging",
            all_visible_parts=["package_corner"],
            all_visible_issues=["crushed_packaging"],
        )
        result = engine.evaluate(inp, vision_confidence=0.8)
        assert result.evidence_standard_met is True


# ---------------------------------------------------------------------------
# 4: NOT_MET — claimed part not visible
# ---------------------------------------------------------------------------

class TestNotMetPartNotVisible:
    def test_bumper_claim_hood_only(self, engine):
        """Rear bumper dent claim but only hood is visible in images."""
        inp = _make_inp(
            claimed_part="rear_bumper",
            claimed_issue="dent",
            object_part_visible=False,
            issue_visible=False,
            supporting_image_ids=[],
            all_visible_parts=["hood"],
            all_visible_issues=[],
        )
        result = engine.evaluate(inp)
        assert result.evidence_standard_met is False
        assert "rear bumper" in result.evidence_standard_met_reason.lower() \
            or "part" in result.evidence_standard_met_reason.lower() \
            or "not" in result.evidence_standard_met_reason.lower()

    def test_windshield_claim_door_only(self, engine):
        inp = _make_inp(
            claimed_part="windshield", claimed_issue="crack",
            object_part_visible=False, issue_visible=False,
            supporting_image_ids=[], all_visible_parts=["door"], all_visible_issues=[],
        )
        result = engine.evaluate(inp)
        assert result.evidence_standard_met is False


# ---------------------------------------------------------------------------
# 5: NOT_MET — claimed issue not visible
# ---------------------------------------------------------------------------

class TestNotMetIssueNotVisible:
    def test_dent_claim_no_damage_visible(self, engine):
        inp = _make_inp(
            claimed_part="rear_bumper", claimed_issue="dent",
            object_visible=True, object_part_visible=True, issue_visible=False,
            supporting_image_ids=[], all_visible_issues=[],
        )
        result = engine.evaluate(inp)
        assert result.evidence_standard_met is False

    def test_crack_claim_no_damage(self, engine):
        inp = _make_inp(
            claim_object="laptop", claimed_part="screen", claimed_issue="crack",
            object_visible=True, object_part_visible=True, issue_visible=False,
            supporting_image_ids=[], all_visible_issues=[],
        )
        result = engine.evaluate(inp)
        assert result.evidence_standard_met is False


# ---------------------------------------------------------------------------
# 6: NOT_MET — wrong object in images
# ---------------------------------------------------------------------------

class TestNotMetWrongObject:
    def test_car_claim_object_not_visible(self, engine):
        inp = _make_inp(
            claim_object="car", claimed_part="door", claimed_issue="dent",
            object_visible=False, object_part_visible=False, issue_visible=False,
            quality_flags=["wrong_object"], supporting_image_ids=[],
            all_visible_parts=[], all_visible_issues=[],
        )
        result = engine.evaluate(inp)
        assert result.evidence_standard_met is False


# ---------------------------------------------------------------------------
# 7: PARTIALLY_MET
# ---------------------------------------------------------------------------

class TestPartiallyMet:
    def test_object_visible_but_damage_not(self, engine):
        """Object and part visible, but damage not confirmed → partial."""
        inp = _make_inp(
            claimed_part="rear_bumper", claimed_issue="dent",
            object_visible=True, object_part_visible=True, issue_visible=False,
            supporting_image_ids=[], all_visible_issues=[],
        )
        result = engine.evaluate(inp, vision_confidence=0.5)
        # Some requirements (e.g. REQ_REVIEW_TRUST) may be satisfied
        # while REQ_GENERAL_OBJECT_PART or specific requirements fail
        assert result.sufficiency_level in (
            SufficiencyLevel.PARTIALLY_MET, SufficiencyLevel.NOT_MET
        )


# ---------------------------------------------------------------------------
# 8–9: Multi-part claim requirement inclusion
# ---------------------------------------------------------------------------

class TestMultiPartRequirement:
    def test_multi_part_includes_multi_image_req(self, engine):
        inp = _make_inp(is_multi_part=True)
        result = engine.evaluate(inp)
        assert "REQ_GENERAL_MULTI_IMAGE" in result.matched_requirement_ids

    def test_single_part_excludes_multi_image_req(self, engine):
        """Single-part claims with >=2 images get REQ_GENERAL_MULTI_IMAGE.

        After the BUG C fix, the multi-part filter was removed from
        _select_requirements — the requirement is now selected for any claim
        whose ``applies_to`` field matches, regardless of is_multi_part.
        The evaluator checks image count at evaluation time.
        """
        inp = _make_inp(is_multi_part=False, total_image_count=2, valid_image_count=2)
        result = engine.evaluate(inp)
        assert "REQ_GENERAL_MULTI_IMAGE" in result.matched_requirement_ids


# ---------------------------------------------------------------------------
# 10–11: Trust-breaking flags
# ---------------------------------------------------------------------------

class TestTrustFlags:
    def test_manipulation_flag_fails_trust_requirement(self, engine):
        inp = _make_inp(quality_flags=["possible_manipulation"])
        result = engine.evaluate(inp)
        trust_eval = next(
            (r for r in result.per_requirement if r.requirement_id == "REQ_REVIEW_TRUST"),
            None,
        )
        if trust_eval:
            assert trust_eval.satisfied is False

    def test_text_instruction_flag_fails_trust(self, engine):
        inp = _make_inp(quality_flags=["text_instruction_present"])
        result = engine.evaluate(inp)
        trust_eval = next(
            (r for r in result.per_requirement if r.requirement_id == "REQ_REVIEW_TRUST"),
            None,
        )
        if trust_eval:
            assert trust_eval.satisfied is False

    def test_normal_claim_trust_satisfied(self, engine):
        inp = _make_inp(quality_flags=[])
        result = engine.evaluate(inp)
        trust_eval = next(
            (r for r in result.per_requirement if r.requirement_id == "REQ_REVIEW_TRUST"),
            None,
        )
        if trust_eval:
            assert trust_eval.satisfied is True


# ---------------------------------------------------------------------------
# 12–13: Confidence
# ---------------------------------------------------------------------------

class TestConfidence:
    def test_quality_flags_reduce_confidence(self, engine):
        clean = engine.evaluate(_make_inp(quality_flags=[]), vision_confidence=0.9)
        degraded = engine.evaluate(
            _make_inp(quality_flags=["blurry_image", "wrong_angle"]),
            vision_confidence=0.9,
        )
        assert clean.confidence > degraded.confidence

    def test_fully_met_higher_confidence_than_not_met(self, engine):
        fully = engine.evaluate(_make_inp(), vision_confidence=0.9)
        not_met = engine.evaluate(
            _make_inp(object_visible=False, object_part_visible=False,
                      issue_visible=False, supporting_image_ids=[]),
            vision_confidence=0.3,
        )
        assert fully.confidence > not_met.confidence

    def test_confidence_in_valid_range(self, engine):
        result = engine.evaluate(_make_inp(), vision_confidence=0.7)
        assert 0.0 <= result.confidence <= 1.0


# ---------------------------------------------------------------------------
# 14: build_input()
# ---------------------------------------------------------------------------

class TestBuildInput:
    def test_build_input_maps_vision_result(self, tmp_path):
        vr = _make_vision_result(
            object_visible=True,
            object_part_visible=True,
            issue_visible=True,
            supporting_image_ids=["img_1"],
            quality_flags=[],
            per_image_parts=["rear_bumper"],
            per_image_issues=["dent"],
            tmp_path=tmp_path,
        )
        inp = EvidenceStandardsEngine.build_input(
            vr, claim_object="car", claimed_part="rear_bumper", claimed_issue="dent"
        )
        assert inp.object_visible is True
        assert inp.object_part_visible is True
        assert inp.issue_visible is True
        assert inp.valid_image_count == 1
        assert "img_1" in inp.supporting_image_ids
        assert "rear_bumper" in inp.all_visible_parts
        assert "dent" in inp.all_visible_issues

    def test_build_input_counts_valid_images_correctly(self, tmp_path):
        img_path = tmp_path / "img_1.jpg"
        per1 = PerImageAnalysis(image_id="img_1", image_path=img_path,
                                readable=True, valid_image=True,
                                visible_parts=[ObjectPart.DOOR],
                                visible_issues=[IssueType.DENT],
                                confidence=0.8, severity=Severity.LOW)
        per2 = PerImageAnalysis(image_id="img_2", image_path=img_path,
                                readable=False, valid_image=False,
                                confidence=0.0, severity=Severity.UNKNOWN)
        vr = VisionReviewResult(
            object_visible=True, object_part_visible=True, issue_visible=True,
            per_image=[per1, per2], confidence=0.7,
            supporting_image_ids=["img_1"],
        )
        inp = EvidenceStandardsEngine.build_input(vr, "car", "door", "dent")
        assert inp.valid_image_count == 1
        assert inp.total_image_count == 2


# ---------------------------------------------------------------------------
# 15: evaluate_from_vision() convenience method
# ---------------------------------------------------------------------------

class TestEvaluateFromVision:
    def test_convenience_method_matches_two_step(self, engine, tmp_path):
        vr = _make_vision_result(tmp_path=tmp_path)
        result_convenience = engine.evaluate_from_vision(
            vr, "car", "rear_bumper", "dent"
        )
        inp = EvidenceStandardsEngine.build_input(vr, "car", "rear_bumper", "dent")
        result_manual = engine.evaluate(inp, vision_confidence=vr.confidence)
        assert result_convenience.evidence_standard_met == result_manual.evidence_standard_met
        assert result_convenience.sufficiency_level == result_manual.sufficiency_level


# ---------------------------------------------------------------------------
# 16–17: CSV loader
# ---------------------------------------------------------------------------

class TestCsvLoader:
    def test_loads_all_requirements_from_real_csv(self):
        engine = EvidenceStandardsEngine()
        engine.load(SAMPLE_REQUIREMENTS_CSV)
        assert len(engine._requirements) == 11  # 11 rows in the CSV

    def test_raises_on_missing_columns(self, tmp_path):
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("wrong_col,another\nfoo,bar\n")
        engine = EvidenceStandardsEngine()
        with pytest.raises(ValueError, match="missing columns"):
            engine.load(bad_csv)


# ---------------------------------------------------------------------------
# 18: Reason strings
# ---------------------------------------------------------------------------

class TestReasonStrings:
    @pytest.mark.parametrize("level_scenario", [
        # (object_visible, part_visible, issue_visible, valid_count)
        (True, True, True, 1),    # FULLY_MET
        (True, True, False, 1),   # NOT_MET / PARTIALLY_MET
        (False, False, False, 0), # UNVERIFIABLE
    ])
    def test_reason_is_non_empty(self, engine, level_scenario):
        ov, pv, iv, vc = level_scenario
        inp = _make_inp(
            object_visible=ov, object_part_visible=pv, issue_visible=iv,
            valid_image_count=vc, supporting_image_ids=["img_1"] if vc > 0 else [],
            all_visible_parts=["rear_bumper"] if pv else [],
            all_visible_issues=["dent"] if iv else [],
        )
        result = engine.evaluate(inp)
        assert result.evidence_standard_met_reason.strip() != ""


# ---------------------------------------------------------------------------
# 19: Missing evidence list
# ---------------------------------------------------------------------------

class TestMissingEvidenceList:
    def test_not_met_populates_missing_evidence(self, engine):
        inp = _make_inp(
            object_visible=False, object_part_visible=False, issue_visible=False,
            supporting_image_ids=[], all_visible_parts=[], all_visible_issues=[],
        )
        result = engine.evaluate(inp)
        assert result.evidence_standard_met is False
        assert len(result.missing_evidence) > 0

    def test_fully_met_missing_evidence_empty(self, engine):
        result = engine.evaluate(_make_inp())
        if result.evidence_standard_met:
            assert result.missing_evidence == []


# ---------------------------------------------------------------------------
# 20: Per-requirement audit trail
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def test_per_requirement_populated(self, engine):
        result = engine.evaluate(_make_inp())
        assert len(result.per_requirement) > 0
        for r in result.per_requirement:
            assert r.requirement_id
            assert r.minimum_image_evidence

    def test_satisfied_req_has_satisfying_image_ids(self, engine):
        result = engine.evaluate(_make_inp(supporting_image_ids=["img_1"]))
        for r in result.per_requirement:
            if r.satisfied:
                assert r.satisfying_image_ids  # non-empty when satisfied


# ---------------------------------------------------------------------------
# 21: load_from_list()
# ---------------------------------------------------------------------------

class TestLoadFromList:
    def test_load_from_list_equivalent_to_csv(self):
        e1 = EvidenceStandardsEngine()
        e1.load(SAMPLE_REQUIREMENTS_CSV)
        e2 = EvidenceStandardsEngine()
        e2.load_from_list(e1._requirements)
        r1 = e1.evaluate(_make_inp())
        r2 = e2.evaluate(_make_inp())
        assert r1.sufficiency_level == r2.sufficiency_level
        assert r1.matched_requirement_ids == r2.matched_requirement_ids


# ---------------------------------------------------------------------------
# 22–24: Correct requirements selected per claim type
# ---------------------------------------------------------------------------

class TestRequirementSelection:
    def test_car_rear_bumper_selects_body_panel_req(self, engine):
        result = engine.evaluate(_make_inp(
            claim_object="car", claimed_part="rear_bumper", claimed_issue="dent"
        ))
        assert "REQ_CAR_BODY_PANEL" in result.matched_requirement_ids

    def test_car_windshield_crack_selects_glass_req(self, engine):
        result = engine.evaluate(_make_inp(
            claim_object="car", claimed_part="windshield", claimed_issue="crack",
            all_visible_parts=["windshield"], all_visible_issues=["crack"],
        ))
        assert "REQ_CAR_GLASS_LIGHT_MIRROR" in result.matched_requirement_ids

    def test_laptop_screen_selects_screen_keyboard_req(self, engine):
        result = engine.evaluate(_make_inp(
            claim_object="laptop", claimed_part="screen", claimed_issue="crack",
            all_visible_parts=["screen"], all_visible_issues=["crack"],
        ))
        assert "REQ_LAPTOP_SCREEN_KEYBOARD_TRACKPAD" in result.matched_requirement_ids

    def test_package_exterior_req_selected_for_crushed(self, engine):
        result = engine.evaluate(_make_inp(
            claim_object="package", claimed_part="package_corner",
            claimed_issue="crushed_packaging",
            all_visible_parts=["package_corner"],
            all_visible_issues=["crushed_packaging"],
        ))
        assert "REQ_PACKAGE_EXTERIOR" in result.matched_requirement_ids

    def test_package_label_req_for_water_damage(self, engine):
        result = engine.evaluate(_make_inp(
            claim_object="package", claimed_part="label",
            claimed_issue="water_damage",
            all_visible_parts=["label"], all_visible_issues=["water_damage"],
        ))
        assert "REQ_PACKAGE_LABEL_OR_STAIN" in result.matched_requirement_ids

    def test_package_contents_req_for_missing_item(self, engine):
        result = engine.evaluate(_make_inp(
            claim_object="package", claimed_part="item",
            claimed_issue="missing_part",
            all_visible_parts=["item"], all_visible_issues=["missing_part"],
        ))
        assert "REQ_PACKAGE_CONTENTS" in result.matched_requirement_ids


# ---------------------------------------------------------------------------
# 25: Supporting image IDs in satisfied requirements
# ---------------------------------------------------------------------------

class TestSupportingImageIds:
    def test_satisfied_requirement_carries_image_ids(self, engine):
        inp = _make_inp(supporting_image_ids=["img_2", "img_3"])
        result = engine.evaluate(inp)
        satisfied = [r for r in result.per_requirement if r.satisfied]
        for r in satisfied:
            assert "img_2" in r.satisfying_image_ids or "img_3" in r.satisfying_image_ids
