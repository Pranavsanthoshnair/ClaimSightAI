"""EvidenceStandardsEngine — determines whether the submitted image set
satisfies the minimum evidence requirements for evaluating a claim.

This engine answers: "Can this image set be used to evaluate the claim?"
It does NOT answer: "Should the claim be accepted or rejected?"

Architecture
------------
Step 1  Requirement selection
    Filter the loaded requirement catalogue to those applicable to the
    current claim (by claim_object and applies_to keywords).  Always include
    REQ_GENERAL_OBJECT_PART and REQ_REVIEW_TRUST.

Step 2  Per-requirement evaluation
    For each selected requirement, check whether the VisionReviewResult
    satisfies it.  Each check is self-contained and explained.

Step 3  Sufficiency aggregation
    Combine per-requirement results into an overall SufficiencyLevel:
    - FULLY_MET       → all requirements satisfied
    - PARTIALLY_MET   → at least one satisfied, at least one not
    - NOT_MET         → none satisfied
    - UNVERIFIABLE    → no valid images at all

Step 4  Gap analysis
    Collect plain-language descriptions of missing evidence for each
    unsatisfied requirement.

Step 5  Confidence calculation
    Weighted by: fraction of requirements satisfied × image quality ×
    vision agent confidence.

Design constraints
------------------
- No hardcoded dataset-specific logic.  All matching is keyword-based
  against the ``applies_to`` field of each requirement record.
- No user history.  This engine only reasons about image evidence.
- No claim status decisions.  Output is evidence sufficiency only.
- The engine is stateless per call; requirements are loaded once at startup
  and injected.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from models.enums import ClaimObject, IssueType, ObjectPart, RiskFlag
from models.evidence_standard import (
    EvidenceStandardInput,
    EvidenceStandardResult,
    RequirementEvaluation,
    SufficiencyLevel,
)
from models.records import EvidenceRequirement
from models.vision_review import VisionReviewResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword maps used for dynamic requirement matching
# ---------------------------------------------------------------------------

# Maps IssueType values → keyword groups that appear in applies_to fields
_ISSUE_APPLIES_KEYWORDS: dict[str, list[str]] = {
    "dent":              ["dent", "deform", "hail", "surface"],
    "scratch":           ["scratch", "scuff", "paint", "surface"],
    "crack":             ["crack", "broken", "glass", "component"],
    "glass_shatter":     ["glass", "crack", "shatter", "broken"],
    "broken_part":       ["broken", "crack", "missing", "component"],
    "missing_part":      ["missing", "broken", "component"],
    "torn_packaging":    ["torn", "seal", "open", "exterior"],
    "crushed_packaging": ["crushed", "exterior", "corner", "seal"],
    "water_damage":      ["water", "stain", "label", "wet"],
    "stain":             ["stain", "water", "label", "surface"],
}

# Maps ObjectPart values → keyword groups that appear in applies_to fields
_PART_APPLIES_KEYWORDS: dict[str, list[str]] = {
    "front_bumper":   ["panel", "bumper", "body", "dent", "scratch"],
    "rear_bumper":    ["panel", "bumper", "body", "dent", "scratch"],
    "door":           ["panel", "body", "dent", "scratch"],
    "hood":           ["panel", "body", "dent", "scratch"],
    "windshield":     ["glass", "crack", "broken"],
    "side_mirror":    ["glass", "mirror", "broken", "missing"],
    "headlight":      ["light", "glass", "broken", "crack"],
    "taillight":      ["light", "glass", "broken", "crack"],
    "fender":         ["panel", "body", "dent", "scratch"],
    "quarter_panel":  ["panel", "body", "dent", "scratch"],
    "screen":         ["screen", "crack", "stain", "keyboard"],
    "keyboard":       ["screen", "keyboard", "trackpad", "missing"],
    "trackpad":       ["screen", "keyboard", "trackpad"],
    "hinge":          ["hinge", "lid", "corner", "body", "port"],
    "lid":            ["hinge", "lid", "corner", "body"],
    "corner":         ["hinge", "lid", "corner", "body"],
    "port":           ["hinge", "lid", "corner", "body", "port"],
    "base":           ["hinge", "lid", "corner", "body", "base"],
    "body":           ["hinge", "lid", "corner", "body"],
    "box":            ["exterior", "crushed", "torn", "seal"],
    "package_corner": ["exterior", "crushed", "corner", "seal"],
    "package_side":   ["exterior", "crushed", "torn", "seal"],
    "seal":           ["exterior", "torn", "seal"],
    "label":          ["label", "water", "stain"],
    "contents":       ["contents", "item", "inner"],
    "item":           ["contents", "item", "inner"],
}

# Quality flags that reduce the evidence bar (image may not be fully assessable)
_QUALITY_DEGRADING_FLAGS: set[str] = {
    RiskFlag.BLURRY_IMAGE,
    RiskFlag.CROPPED_OR_OBSTRUCTED,
    RiskFlag.LOW_LIGHT_OR_GLARE,
    RiskFlag.WRONG_ANGLE,
}

# Quality flags that invalidate trust entirely
_TRUST_BREAKING_FLAGS: set[str] = {
    RiskFlag.WRONG_OBJECT,
    RiskFlag.POSSIBLE_MANIPULATION,
    RiskFlag.TEXT_INSTRUCTION_PRESENT,
}


# ---------------------------------------------------------------------------
# Requirement matching helpers
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _applies_to_matches(applies_to: str, issue: str, part: str) -> bool:
    """Return True when the requirement's applies_to field is relevant to
    the claim's issue and part.

    Matching strategy (any of the following suffices):
    1. A keyword from the issue's keyword group appears in applies_to.
    2. A keyword from the part's keyword group appears in applies_to.
    3. applies_to contains "general" (universal requirement).
    4. applies_to contains "reviewability" (trust requirement).
    """
    norm = _normalise(applies_to)

    if any(kw in norm for kw in ("general", "reviewability", "multi-image")):
        return True

    issue_kws = _ISSUE_APPLIES_KEYWORDS.get(issue, [])
    if any(kw in norm for kw in issue_kws):
        return True

    part_kws = _PART_APPLIES_KEYWORDS.get(part, [])
    if any(kw in norm for kw in part_kws):
        return True

    return False


def _select_requirements(
    requirements: list[EvidenceRequirement],
    claim_object: str,
    claimed_issue: str,
    claimed_part: str,
    is_multi_part: bool,
) -> list[EvidenceRequirement]:
    """Filter requirements to those applicable to this claim."""
    selected: list[EvidenceRequirement] = []

    for req in requirements:
        # Object filter: keep "all" requirements and those matching claim_object
        if req.claim_object not in ("all", claim_object):
            continue

        # REQ_GENERAL_MULTI_IMAGE: only applies to multi-part / multi-image claims
        if req.requirement_id == "REQ_GENERAL_MULTI_IMAGE" and not is_multi_part:
            continue

        # applies_to filter: match against claim issue + part
        if _applies_to_matches(req.applies_to, claimed_issue, claimed_part):
            selected.append(req)

    # Deduplicate while preserving order
    seen: set[str] = set()
    return [r for r in selected if not (r.requirement_id in seen or seen.add(r.requirement_id))]  # type: ignore[func-returns-value]


# ---------------------------------------------------------------------------
# Per-requirement evaluators
# ---------------------------------------------------------------------------

def _eval_general_object_part(inp: EvidenceStandardInput, req: EvidenceRequirement) -> RequirementEvaluation:
    """REQ_GENERAL_OBJECT_PART: claimed object, part, and condition must be visible."""
    issue_ok = (
        inp.claimed_issue in ("unknown", "none", "")
        or inp.issue_visible
        or inp.claimed_issue in inp.all_visible_issues
    )

    # Primary check: strict visibility
    satisfied = (
        inp.object_visible
        and inp.object_part_visible
        and inp.valid_image_count > 0
        and issue_ok
    )

    # Partial evidence: if object is not directly confirmed but claimed part IS
    # visible, infer object presence (close-up photos don't show the full object)
    if not satisfied and inp.valid_image_count > 0 and inp.object_part_visible and issue_ok:
        # The claimed part IS visible — object must be present
        satisfied = True

    gap = ""
    if not inp.valid_image_count:
        gap = "No valid images could be assessed."
    elif not inp.object_visible and not inp.object_part_visible:
        gap = f"The claimed {inp.claim_object} is not visible in any image."
    elif not inp.object_part_visible:
        claimed_part_str = inp.claimed_part.replace("_", " ")
        gap = (
            f"The claimed part '{claimed_part_str}' is not visible; "
            f"visible parts: {_fmt_list(inp.all_visible_parts) or 'none'}."
        )
    elif not issue_ok:
        claimed_issue_str = inp.claimed_issue.replace("_", " ")
        gap = (
            f"The claimed damage '{claimed_issue_str}' is not visible; "
            f"visible issues: {_fmt_list(inp.all_visible_issues) or 'none'}."
        )
    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        applies_to=req.applies_to,
        minimum_image_evidence=req.minimum_image_evidence,
        satisfied=satisfied,
        satisfying_image_ids=inp.supporting_image_ids if satisfied else [],
        gap_description=gap,
    )


def _eval_review_trust(inp: EvidenceStandardInput, req: EvidenceRequirement) -> RequirementEvaluation:
    """REQ_REVIEW_TRUST: images must be usable and not manipulated."""
    trust_broken = bool(set(inp.quality_flags) & _TRUST_BREAKING_FLAGS)
    no_valid = inp.valid_image_count == 0
    satisfied = not trust_broken and not no_valid

    gap = ""
    if no_valid:
        gap = "No readable or usable images were submitted."
    elif trust_broken:
        bad_flags = set(inp.quality_flags) & _TRUST_BREAKING_FLAGS
        gap = f"Image trust flags detected: {', '.join(f.replace('_', ' ') for f in bad_flags)}."
    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        applies_to=req.applies_to,
        minimum_image_evidence=req.minimum_image_evidence,
        satisfied=satisfied,
        satisfying_image_ids=inp.supporting_image_ids if satisfied else [],
        gap_description=gap,
    )


def _eval_multi_image(inp: EvidenceStandardInput, req: EvidenceRequirement) -> RequirementEvaluation:
    """REQ_GENERAL_MULTI_IMAGE: at least one image must show the claimed part."""
    satisfied = inp.object_part_visible and inp.valid_image_count > 0
    gap = "" if satisfied else (
        "For multi-part claims, at least one image must clearly show the claimed object part."
    )
    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        applies_to=req.applies_to,
        minimum_image_evidence=req.minimum_image_evidence,
        satisfied=satisfied,
        satisfying_image_ids=inp.supporting_image_ids if satisfied else [],
        gap_description=gap,
    )


def _eval_generic(inp: EvidenceStandardInput, req: EvidenceRequirement) -> RequirementEvaluation:
    """Generic evaluator for all other requirements.

    Checks:
    1. At least one valid image exists.
    2. The claimed object is visible.
    3. The claimed part is visible (or part is unknown/general).
    4. Damage is visible (issue_visible).
    """
    part_ok = (
        inp.claimed_part in ("unknown", "")
        or inp.object_part_visible
        or inp.claimed_part in inp.all_visible_parts
    )
    issue_ok = (
        inp.claimed_issue in ("unknown", "")
        or inp.issue_visible
        or inp.claimed_issue in inp.all_visible_issues
    )
    satisfied = (
        inp.valid_image_count > 0
        and inp.object_visible
        and part_ok
        and issue_ok
    )

    gap_parts: list[str] = []
    if inp.valid_image_count == 0:
        gap_parts.append("No usable images.")
    else:
        if not inp.object_visible:
            gap_parts.append(f"{inp.claim_object.capitalize()} not visible in images.")
        if not part_ok:
            gap_parts.append(
                f"Claimed part '{inp.claimed_part.replace('_', ' ')}' not visible "
                f"(visible: {_fmt_list(inp.all_visible_parts) or 'none'})."
            )
        if not issue_ok:
            gap_parts.append(
                f"Claimed damage '{inp.claimed_issue.replace('_', ' ')}' not visible "
                f"(visible: {_fmt_list(inp.all_visible_issues) or 'none'})."
            )

    return RequirementEvaluation(
        requirement_id=req.requirement_id,
        applies_to=req.applies_to,
        minimum_image_evidence=req.minimum_image_evidence,
        satisfied=satisfied,
        satisfying_image_ids=inp.supporting_image_ids if satisfied else [],
        gap_description=" ".join(gap_parts),
    )


def _eval_requirement(
    inp: EvidenceStandardInput,
    req: EvidenceRequirement,
) -> RequirementEvaluation:
    """Dispatch to the appropriate per-requirement evaluator."""
    rid = req.requirement_id
    if rid == "REQ_GENERAL_OBJECT_PART":
        return _eval_general_object_part(inp, req)
    if rid == "REQ_REVIEW_TRUST":
        return _eval_review_trust(inp, req)
    if rid == "REQ_GENERAL_MULTI_IMAGE":
        return _eval_multi_image(inp, req)
    return _eval_generic(inp, req)


# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------

def _compute_confidence(
    inp: EvidenceStandardInput,
    satisfied_count: int,
    total_count: int,
    vision_confidence: float,
) -> float:
    if total_count == 0:
        return 0.0

    satisfaction_ratio = satisfied_count / total_count

    # Quality penalty: each degrading flag reduces confidence slightly
    degrading = set(inp.quality_flags) & _QUALITY_DEGRADING_FLAGS
    quality_penalty = min(0.25, len(degrading) * 0.07)

    # No valid images → very low confidence
    if inp.valid_image_count == 0:
        return 0.0

    # Blend satisfaction ratio with vision agent's own confidence
    base = (satisfaction_ratio * 0.6) + (vision_confidence * 0.4)
    return round(max(0.0, min(1.0, base - quality_penalty)), 4)


# ---------------------------------------------------------------------------
# Reason string generation
# ---------------------------------------------------------------------------

def _fmt_list(items: list[str], limit: int = 3) -> str:
    shown = items[:limit]
    suffix = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return ", ".join(s.replace("_", " ") for s in shown) + suffix


def _build_reason(
    inp: EvidenceStandardInput,
    level: SufficiencyLevel,
    per_req: list[RequirementEvaluation],
    satisfied_ids: list[str],
    vision_confidence: float,
) -> str:
    """Build a human-readable evidence_standard_met_reason string."""
    if level == SufficiencyLevel.UNVERIFIABLE:
        return "No readable images were available; evidence standard cannot be evaluated."

    sat_count = sum(1 for r in per_req if r.satisfied)
    total = len(per_req)

    if level == SufficiencyLevel.FULLY_MET:
        img_str = (
            f" Supporting images: {', '.join(inp.supporting_image_ids)}."
            if inp.supporting_image_ids else ""
        )
        return (
            f"All {total} applicable evidence requirement(s) satisfied."
            f"{img_str}"
        )

    if level == SufficiencyLevel.PARTIALLY_MET:
        gaps = [r.gap_description for r in per_req if not r.satisfied and r.gap_description]
        gap_str = " ".join(gaps[:2])
        return (
            f"{sat_count}/{total} evidence requirement(s) satisfied. "
            f"Gaps: {gap_str}"
        ).strip()

    # NOT_MET
    gaps = [r.gap_description for r in per_req if r.gap_description]
    gap_str = " ".join(gaps[:2])
    if not gap_str:
        gap_str = (
            f"Claimed {inp.claim_object} {inp.claimed_part.replace('_', ' ')} "
            f"with {inp.claimed_issue.replace('_', ' ')} not evidenced."
        )
    return f"Evidence standard not met. {gap_str}".strip()


# ---------------------------------------------------------------------------
# EvidenceStandardsEngine
# ---------------------------------------------------------------------------


class EvidenceStandardsEngine:
    """Evaluates whether the image set satisfies minimum evidence requirements.

    Usage::

        engine = EvidenceStandardsEngine()
        engine.load(Path("dataset/evidence_requirements.csv"))

        result: EvidenceStandardResult = engine.evaluate(
            inp=EvidenceStandardInput.from_vision_result(
                vision_result, extracted_claim
            ),
            vision_confidence=vision_result.confidence,
        )

    The engine is also callable via the legacy ``EvidenceRequirementService``
    interface so the pipeline needs no changes.
    """

    def __init__(self) -> None:
        self._requirements: list[EvidenceRequirement] = []

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, path: Path) -> None:
        """Load evidence requirements from a CSV file.

        Accepts the same file format as the existing EvidenceRequirementService.
        """
        frame = pd.read_csv(path)
        required_cols = {"requirement_id", "claim_object", "applies_to", "minimum_image_evidence"}
        missing = required_cols - set(frame.columns)
        if missing:
            raise ValueError(f"evidence_requirements.csv missing columns: {missing}")

        self._requirements = [
            EvidenceRequirement.model_validate(row)
            for row in frame.to_dict(orient="records")
        ]
        logger.info("Loaded %d evidence requirements from %s", len(self._requirements), path)

    def load_from_list(self, requirements: list[EvidenceRequirement]) -> None:
        """Load requirements from an already-parsed list (useful in tests)."""
        self._requirements = list(requirements)

    # ------------------------------------------------------------------
    # Factory helper: build input from VisionReviewResult + claim context
    # ------------------------------------------------------------------

    @staticmethod
    def build_input(
        vision_result: VisionReviewResult,
        claim_object: str,
        claimed_part: str = "unknown",
        claimed_issue: str = "unknown",
        is_multi_part: bool = False,
    ) -> EvidenceStandardInput:
        """Convenience constructor — builds EvidenceStandardInput from the
        VisionReviewResult produced by VisionReviewAgent.
        """
        all_visible_parts = list(dict.fromkeys(
            p.value for img in vision_result.per_image for p in img.visible_parts
        ))
        all_visible_issues = list(dict.fromkeys(
            i.value for img in vision_result.per_image for i in img.visible_issues
        ))

        # Infer object_visible from part visibility when VLM is uncertain
        # (close-up photos of a car bumper ARE car photos — full object need not be in frame)
        object_visible = vision_result.object_visible
        if not object_visible and claimed_part not in ("unknown", "") and claimed_part in all_visible_parts:
            # Claimed part is visible → claimed object must be present
            object_visible = True

        # Infer object_part_visible from all_visible_parts (covers null object_present case)
        object_part_visible = vision_result.object_part_visible
        if not object_part_visible and claimed_part not in ("unknown", "") and claimed_part in all_visible_parts:
            object_part_visible = True

        return EvidenceStandardInput(
            claim_object=claim_object,
            claimed_part=claimed_part,
            claimed_issue=claimed_issue,
            is_multi_part=is_multi_part,
            object_visible=object_visible,
            object_part_visible=object_part_visible,
            issue_visible=vision_result.issue_visible,
            valid_image_count=sum(1 for img in vision_result.per_image if img.valid_image),
            total_image_count=len(vision_result.per_image),
            supporting_image_ids=list(vision_result.supporting_image_ids),
            quality_flags=[f.value for f in vision_result.quality_flags],
            all_visible_parts=all_visible_parts,
            all_visible_issues=all_visible_issues,
        )

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        inp: EvidenceStandardInput,
        vision_confidence: float = 0.0,
    ) -> EvidenceStandardResult:
        """Evaluate evidence sufficiency for one claim.

        Parameters
        ----------
        inp:
            EvidenceStandardInput built from VisionReviewResult and claim data.
        vision_confidence:
            The confidence score from VisionReviewResult, used in the
            confidence calculation.

        Returns
        -------
        EvidenceStandardResult
            Full sufficiency determination with per-requirement breakdown.
        """
        if not self._requirements:
            logger.warning("No requirements loaded; returning conservative NOT_MET result.")
            return EvidenceStandardResult(
                evidence_standard_met=False,
                evidence_standard_met_reason="No evidence requirements are configured.",
                sufficiency_level=SufficiencyLevel.NOT_MET,
                confidence=0.0,
            )

        # Step 1: select applicable requirements
        selected = _select_requirements(
            self._requirements,
            inp.claim_object,
            inp.claimed_issue,
            inp.claimed_part,
            inp.is_multi_part,
        )
        logger.debug(
            "Selected %d requirement(s) for %s / %s / %s",
            len(selected), inp.claim_object, inp.claimed_issue, inp.claimed_part,
        )

        # Step 2: unverifiable guard (no valid images at all)
        if inp.valid_image_count == 0:
            missing = [
                f"Readable image showing {inp.claim_object} {inp.claimed_part.replace('_', ' ')} "
                f"with visible {inp.claimed_issue.replace('_', ' ')} damage."
            ]
            return EvidenceStandardResult(
                evidence_standard_met=False,
                evidence_standard_met_reason=(
                    "No valid images were available for assessment."
                ),
                sufficiency_level=SufficiencyLevel.UNVERIFIABLE,
                matched_requirement_ids=[r.requirement_id for r in selected],
                missing_evidence=missing,
                confidence=0.0,
            )

        # Step 3: evaluate each requirement
        per_req: list[RequirementEvaluation] = [
            _eval_requirement(inp, req) for req in selected
        ]

        satisfied_ids = [r.requirement_id for r in per_req if r.satisfied]
        unsatisfied = [r for r in per_req if not r.satisfied]

        # Step 4: sufficiency level
        if not per_req:
            level = SufficiencyLevel.NOT_MET
        elif len(satisfied_ids) == len(per_req):
            level = SufficiencyLevel.FULLY_MET
        elif satisfied_ids:
            level = SufficiencyLevel.PARTIALLY_MET
        else:
            level = SufficiencyLevel.NOT_MET

        # Step 5: gap analysis
        missing_evidence = [
            r.gap_description for r in unsatisfied if r.gap_description
        ]

        # Step 6: confidence
        confidence = _compute_confidence(
            inp,
            len(satisfied_ids),
            len(per_req),
            vision_confidence,
        )

        # Step 7: build reason
        reason = _build_reason(inp, level, per_req, satisfied_ids, vision_confidence)

        evidence_met = level in (SufficiencyLevel.FULLY_MET, SufficiencyLevel.PARTIALLY_MET)

        # Stricter gate: even PARTIALLY_MET is insufficient when the primary
        # visibility requirement fails.  The evidence standard is only met when
        # at minimum the claimed object AND its part are visible in at least one
        # valid image — without that, downstream decision-making is impossible.
        if evidence_met and level == SufficiencyLevel.PARTIALLY_MET:
            obj_part_req = next(
                (r for r in per_req if r.requirement_id == "REQ_GENERAL_OBJECT_PART"),
                None,
            )
            if obj_part_req is not None and not obj_part_req.satisfied:
                evidence_met = False

        result = EvidenceStandardResult(
            evidence_standard_met=evidence_met,
            evidence_standard_met_reason=reason,
            sufficiency_level=level,
            matched_requirement_ids=[r.requirement_id for r in per_req],
            satisfied_requirement_ids=satisfied_ids,
            missing_evidence=missing_evidence,
            per_requirement=per_req,
            confidence=confidence,
        )

        logger.info(
            "Evidence standard: %s (level=%s, satisfied=%d/%d, confidence=%.2f) — %s",
            evidence_met,
            level,
            len(satisfied_ids),
            len(per_req),
            confidence,
            reason[:80],
        )
        return result

    # ------------------------------------------------------------------
    # Convenience: evaluate directly from VisionReviewResult
    # ------------------------------------------------------------------

    def evaluate_from_vision(
        self,
        vision_result: VisionReviewResult,
        claim_object: str,
        claimed_part: str = "unknown",
        claimed_issue: str = "unknown",
        is_multi_part: bool = False,
    ) -> EvidenceStandardResult:
        """One-call convenience that builds the input and evaluates.

        Equivalent to calling ``build_input()`` then ``evaluate()``.
        """
        inp = self.build_input(
            vision_result=vision_result,
            claim_object=claim_object,
            claimed_part=claimed_part,
            claimed_issue=claimed_issue,
            is_multi_part=is_multi_part,
        )
        return self.evaluate(inp, vision_confidence=vision_result.confidence)

    # ------------------------------------------------------------------
    # Legacy EvidenceRequirementService interface
    # ------------------------------------------------------------------

    def for_claim_object(self, claim_object: ClaimObject) -> list[EvidenceRequirement]:
        """Return requirements that apply to a claim object (legacy interface)."""
        return [
            r for r in self._requirements
            if r.claim_object in ("all", claim_object.value)
        ]
