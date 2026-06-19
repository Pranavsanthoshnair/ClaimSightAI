"""Complete production audit script."""
import sys
sys.path.insert(0, 'code')
from dotenv import load_dotenv
load_dotenv('.env')

from pathlib import Path
from models.enums import ClaimObject, IssueType, ObjectPart, Severity, RiskFlag
from models.vision_review import VisionReviewResult, PerImageAnalysis
from services.evidence_standards_engine import EvidenceStandardsEngine
from agents.claim_agent import ClaimExtractionAgent
from models.claim_extraction import ClaimExtractionInput

ISSUES = []
FIXES = []

def check(name, condition, detail="", fix=None):
    if condition:
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name}: {detail}")
        ISSUES.append(f"{name}: {detail}")
        if fix:
            FIXES.append(fix)

def _make_vr(obj_visible=True, part_visible=True, issue_visible=True, is_multi=False, confidence=0.9):
    per = PerImageAnalysis(
        image_id='img_1', image_path=Path('x.jpg'),
        readable=True, valid_image=True,
        object_present=obj_visible,
        visible_parts=[ObjectPart.FRONT_BUMPER] if part_visible else [],
        visible_issues=[IssueType.DENT] if issue_visible else [],
        confidence=confidence, severity=Severity.MEDIUM,
        supports_claim=obj_visible and part_visible and issue_visible,
    )
    return VisionReviewResult(
        object_visible=obj_visible, object_part_visible=part_visible,
        issue_visible=issue_visible, issue_type=IssueType.DENT,
        object_part=ObjectPart.FRONT_BUMPER, severity=Severity.MEDIUM,
        supporting_image_ids=['img_1'] if (obj_visible and part_visible and issue_visible) else [],
        valid_image=True, confidence=confidence, per_image=[per],
    )

engine = EvidenceStandardsEngine()
engine.load(Path('dataset/evidence_requirements.csv'))

print("=" * 60)
print("AUDIT 1: Evidence Standards - is_multi_part flag propagation")
print("=" * 60)

# BUG: When is_multi_part=True but only 1 image submitted,
# REQ_GENERAL_MULTI_IMAGE should NOT fire (it's about image count not part count)
vr = _make_vr()
r = engine.evaluate_from_vision(vr, 'car', 'front_bumper', 'dent', is_multi_part=True)
multi_selected = 'REQ_GENERAL_MULTI_IMAGE' in r.matched_requirement_ids
print(f"\n  is_multi_part=True, single image: REQ_GENERAL_MULTI_IMAGE selected={multi_selected}")
if multi_selected:
    multi_req = next((x for x in r.per_requirement if x.requirement_id == 'REQ_GENERAL_MULTI_IMAGE'), None)
    if multi_req:
        print(f"  Multi req satisfied={multi_req.satisfied}, gap={multi_req.gap_description[:80]}")
    check("multi_image_req_not_blocking_single_image",
          r.evidence_standard_met,
          "is_multi_part=True causes REQ_GENERAL_MULTI_IMAGE to fire and may block evidence",
          "Fix: REQ_GENERAL_MULTI_IMAGE should only fire when multiple images submitted, not based on is_multi_part")
else:
    check("multi_image_req_not_firing_needlessly", True)

# AUDIT 2: False multi-part from 'body' keyword
print("\n" + "=" * 60)
print("AUDIT 2: Claim extraction - 'body' false secondary part")
print("=" * 60)
agent = ClaimExtractionAgent()
r = agent.extract(ClaimExtractionInput(
    user_claim='Customer: Front bumper damaged and headlight also affected. Both need review.',
    claim_object=ClaimObject.CAR
))
print(f"  is_multi_part={r.is_multi_part}")
print(f"  additional_claimed_parts={[str(p) for p in r.additional_claimed_parts]}")
has_body_false_positive = ObjectPart.BODY in r.additional_claimed_parts
check("no_body_false_positive_in_multi_part",
      not has_body_false_positive,
      "'body' keyword added as secondary part even though customer only mentioned bumper+headlight",
      "Fix: Remove 'bumper' -> 'body' fallback from _PART_KEYWORDS or exclude 'body' from multi-part detection")

# AUDIT 3: EvidenceStandardsEngine valid_image_count vs blurry images
print("\n" + "=" * 60)
print("AUDIT 3: valid_image_count counts blurry images as valid")
print("=" * 60)
blurry_per = PerImageAnalysis(
    image_id='img_1', image_path=Path('x.jpg'),
    readable=True, valid_image=False,  # blurry -> valid_image=False
    quality_flags=[RiskFlag.BLURRY_IMAGE],
    object_present=None, visible_parts=[], visible_issues=[],
    confidence=0.0, severity=Severity.UNKNOWN, supports_claim=False,
)
blurry_vr = VisionReviewResult(
    valid_image=False, per_image=[blurry_per],
    object_visible=False, object_part_visible=False, issue_visible=False,
)
inp = EvidenceStandardsEngine.build_input(blurry_vr, 'car', 'front_bumper', 'dent')
print(f"  valid_image_count={inp.valid_image_count} (blurry image)")
check("blurry_image_not_counted_as_valid",
      inp.valid_image_count == 0,
      f"blurry image counted as valid_image_count={inp.valid_image_count}",
      "Fix: EvidenceStandardsEngine.build_input uses img.valid_image — this is already correct if PerImageAnalysis.valid_image=False")

# AUDIT 4: Decision service - does it produce CONTRADICTED correctly?
print("\n" + "=" * 60)
print("AUDIT 4: Decision service - contradicted logic")
print("=" * 60)
from services.decision_service import DecisionService
from models.records import ClaimInput, ParsedClaim, ClaimOutput
from models.evidence_standard import EvidenceStandardResult, SufficiencyLevel
from models.enums import ClaimStatus

ds = DecisionService()

# Part visible, no damage -> should be CONTRADICTED
vr_contradicted = _make_vr(obj_visible=True, part_visible=True, issue_visible=False)
vr_contradicted.supporting_image_ids = []
claim_in = ClaimInput(user_id='u1', image_paths='img.jpg',
                      user_claim='test', claim_object=ClaimObject.CAR)
parsed = ParsedClaim(claim_object=ClaimObject.CAR,
                     claimed_issue=IssueType.DENT,
                     claimed_part=ObjectPart.FRONT_BUMPER)
evidence_met = EvidenceStandardResult(
    evidence_standard_met=True,
    evidence_standard_met_reason="Test",
    sufficiency_level=SufficiencyLevel.FULLY_MET,
)
out = ds.decide(claim=claim_in, parsed_claim=parsed, vision=vr_contradicted, evidence=evidence_met)
print(f"  part_visible=True, issue_visible=False -> claim_status={out.claim_status}")
check("contradicted_when_part_visible_no_damage",
      out.claim_status == ClaimStatus.CONTRADICTED,
      f"Expected CONTRADICTED, got {out.claim_status}")

# Part NOT visible -> should be NOT_ENOUGH_INFORMATION
vr_nei = _make_vr(obj_visible=True, part_visible=False, issue_visible=False)
vr_nei.supporting_image_ids = []
evidence_not_met = EvidenceStandardResult(
    evidence_standard_met=False,
    evidence_standard_met_reason="Part not visible",
    sufficiency_level=SufficiencyLevel.NOT_MET,
)
out2 = ds.decide(claim=claim_in, parsed_claim=parsed, vision=vr_nei, evidence=evidence_not_met)
print(f"  part_visible=False -> claim_status={out2.claim_status}")
check("nei_when_part_not_visible",
      out2.claim_status == ClaimStatus.NOT_ENOUGH_INFORMATION,
      f"Expected NEI, got {out2.claim_status}")

# AUDIT 5: Severity propagation
print("\n" + "=" * 60)
print("AUDIT 5: Severity propagation from vision to output")
print("=" * 60)
vr_high = _make_vr()
vr_high.severity = Severity.HIGH
evidence_full = EvidenceStandardResult(
    evidence_standard_met=True, evidence_standard_met_reason="OK",
    sufficiency_level=SufficiencyLevel.FULLY_MET,
)
out3 = ds.decide(claim=claim_in, parsed_claim=parsed, vision=vr_high, evidence=evidence_full)
print(f"  vision severity=HIGH -> output severity={out3.severity}")
check("severity_propagates_from_vision",
      out3.severity == Severity.HIGH,
      f"Expected HIGH, got {out3.severity}")

# AUDIT 6: User history cannot flip claim status
print("\n" + "=" * 60)
print("AUDIT 6: User history never overrides visual evidence")
print("=" * 60)
from models.records import UserHistory
risky_user = UserHistory(user_id='risky', history_flags='user_history_risk;manual_review_required')
out_risky = ds.decide(claim=claim_in, parsed_claim=parsed,
                      vision=_make_vr(), evidence=evidence_full,
                      user_history=risky_user)
print(f"  risky user, clear evidence -> claim_status={out_risky.claim_status}")
check("risky_user_cannot_change_supported_to_nei",
      out_risky.claim_status == ClaimStatus.SUPPORTED,
      f"Risky user history changed claim_status to {out_risky.claim_status}")
check("risky_user_adds_risk_flag",
      'user_history_risk' in out_risky.risk_flags,
      "risk flag not added for risky user")

# AUDIT 7: Enum coercion - spaces and case
print("\n" + "=" * 60)
print("AUDIT 7: Enum coercion robustness")
print("=" * 60)
from agents.vision_agent import _safe_enum_list, _normalise_enum_str

parts = _safe_enum_list(ObjectPart, ["rear bumper", "FRONT_BUMPER", "door", "invalid_xyz"])
print(f"  coerced parts: {[p.value for p in parts]}")
check("rear_bumper_with_space_coerces", ObjectPart.REAR_BUMPER in parts,
      "rear bumper (with space) not coerced to rear_bumper")
check("FRONT_BUMPER_uppercase_coerces", ObjectPart.FRONT_BUMPER in parts,
      "FRONT_BUMPER (uppercase) not coerced")
check("invalid_silently_dropped", len(parts) == 3,
      f"invalid value not silently dropped, got {len(parts)} parts")

# AUDIT 8: Cache key stability
print("\n" + "=" * 60)
print("AUDIT 8: Cache key stability")
print("=" * 60)
from agents.claim_agent import _cache_key as claim_cache_key
from models.enums import ClaimObject
k1 = claim_cache_key("Customer: rear bumper dent", ClaimObject.CAR)
k2 = claim_cache_key("Customer: rear bumper dent", ClaimObject.CAR)  # same
k3 = claim_cache_key("Customer: REAR BUMPER DENT", ClaimObject.CAR)  # uppercase - normalised
k4 = claim_cache_key("Customer: rear bumper dent", ClaimObject.LAPTOP)  # different object
print(f"  same input same key: {k1 == k2}")
print(f"  same input uppercase key: {k1 == k3} (should be True - both normalised)")
print(f"  different object different key: {k1 != k4}")
check("cache_key_deterministic", k1 == k2, "cache key not deterministic")
check("cache_key_case_insensitive", k1 == k3, "cache key not case-insensitive (both normalised)")
check("cache_key_differs_by_object", k1 != k4, "cache key doesn't differ by claim_object")

# Summary
print("\n" + "=" * 60)
print(f"AUDIT COMPLETE: {len(ISSUES)} issues found")
print("=" * 60)
if ISSUES:
    for i, issue in enumerate(ISSUES, 1):
        print(f"  {i}. {issue}")
    if FIXES:
        print("\nFixes needed:")
        for fix in FIXES:
            print(f"  - {fix}")
else:
    print("  All checks passed!")
