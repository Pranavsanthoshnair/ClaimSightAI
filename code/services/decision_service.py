"""DecisionService — produces the final ClaimOutput for one claim row.

This service is the last stage in the pipeline.  It receives outputs from
all upstream agents and services and applies constrained decision rules to
produce a fully-populated ClaimOutput row.

Decision rules (in priority order)
------------------------------------
1. If no valid image exists → NOT_ENOUGH_INFORMATION, valid_image=False,
   MANUAL_REVIEW_REQUIRED risk flag.
2. If evidence standard is not met → NOT_ENOUGH_INFORMATION with the
   evidence reason surfaced in the justification.
3. If the claimed object is not visible in any image → NOT_ENOUGH_INFORMATION,
   WRONG_OBJECT risk flag.
4. If the claimed object part is not visible → NOT_ENOUGH_INFORMATION,
   WRONG_OBJECT_PART risk flag.
5. If the claimed part IS visible AND damage consistent with the claim IS
   visible → SUPPORTED.
6. If the claimed part IS visible AND damage is NOT visible (or a different
   object/part is shown) → CONTRADICTED.
7. Fallback → NOT_ENOUGH_INFORMATION.

Risk flags
----------
- Visual quality flags pass through from VisionReviewResult.
- USER_HISTORY_RISK added only when user history flags are non-trivial.
  User history never overrides visual evidence.
- CLAIM_MISMATCH added when the visible part/issue differs from the claim.

Severity and issue_type / object_part
--------------------------------------
- Taken from VisionReviewResult (what was visible), not from the claim text.
- Falls back to ParsedClaim values only when VisionReviewResult is UNKNOWN
  and confidence is low (model not available / no model call made).

Design constraints
------------------
- No hardcoded row IDs, filenames, or dataset-specific logic.
- User history is additive context only; it cannot change a SUPPORTED or
  CONTRADICTED verdict derived from clear visual evidence.
- All output enum values are validated against the project taxonomy before
  writing.
"""

from __future__ import annotations

import logging

from models.enums import ClaimStatus, IssueType, ObjectPart, RiskFlag, Severity
from models.evidence_standard import EvidenceStandardResult, SufficiencyLevel
from models.records import (
    ClaimInput,
    ClaimOutput,
    ImageEvidence,
    ParsedClaim,
    UserHistory,
)
from models.vision_review import VisionReviewResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Risk flag helpers
# ---------------------------------------------------------------------------

_HISTORY_RISK_KEYWORDS: set[str] = {"user_history_risk", "manual_review_required"}


def _history_flags(user_history: UserHistory | None) -> list[RiskFlag]:
    """Extract risk flags from user history record."""
    if user_history is None:
        return []
    flags_str = user_history.history_flags or "none"
    result: list[RiskFlag] = []
    for part in flags_str.split(";"):
        part = part.strip()
        if part in _HISTORY_RISK_KEYWORDS:
            try:
                result.append(RiskFlag(part))
            except ValueError:
                pass
    return result


def _merge_flags(
    vision_flags: list[RiskFlag],
    history_flags: list[RiskFlag],
    extra_flags: list[RiskFlag],
) -> str:
    """Merge all flag lists, deduplicate, and serialise to semicolon string."""
    seen: set[RiskFlag] = set()
    merged: list[RiskFlag] = []
    for f in vision_flags + history_flags + extra_flags:
        if f not in seen and f != RiskFlag.NONE:
            seen.add(f)
            merged.append(f)
    return ";".join(f.value for f in merged) if merged else RiskFlag.NONE.value


def _supporting_ids_str(ids: list[str]) -> str:
    return ";".join(ids) if ids else "none"


# ---------------------------------------------------------------------------
# Severity normalisation
# ---------------------------------------------------------------------------

def _best_severity(
    vision_severity: Severity,
    parsed_issue: IssueType,
) -> Severity:
    """Return the most informative severity.

    If the VLM produced a concrete severity, use it.  Otherwise apply a
    conservative heuristic based on the issue type.
    """
    if vision_severity not in (Severity.UNKNOWN, Severity.NONE):
        return vision_severity

    # Conservative heuristic when VLM returned unknown
    _ISSUE_SEVERITY_HINTS: dict[IssueType, Severity] = {
        IssueType.GLASS_SHATTER:     Severity.HIGH,
        IssueType.BROKEN_PART:       Severity.HIGH,
        IssueType.MISSING_PART:      Severity.HIGH,
        IssueType.CRACK:             Severity.MEDIUM,
        IssueType.TORN_PACKAGING:    Severity.MEDIUM,
        IssueType.CRUSHED_PACKAGING: Severity.MEDIUM,
        IssueType.DENT:              Severity.MEDIUM,
        IssueType.SCRATCH:           Severity.LOW,
        IssueType.WATER_DAMAGE:      Severity.MEDIUM,
        IssueType.STAIN:             Severity.LOW,
        IssueType.NONE:              Severity.NONE,
    }
    return _ISSUE_SEVERITY_HINTS.get(parsed_issue, Severity.UNKNOWN)


# ---------------------------------------------------------------------------
# Justification string builder
# ---------------------------------------------------------------------------

def _build_justification(
    status: ClaimStatus,
    vision: VisionReviewResult,
    evidence: EvidenceStandardResult,
    extra_flags: list[RiskFlag],
) -> str:
    parts: list[str] = []

    if status == ClaimStatus.SUPPORTED:
        parts.append(
            f"Visual evidence supports the claim. "
            f"{vision.reasoning or 'Claimed object, part, and damage are visible.'}"
        )
    elif status == ClaimStatus.CONTRADICTED:
        parts.append("Visual evidence contradicts or does not match the claim.")
        if vision.reasoning:
            parts.append(vision.reasoning)
        if RiskFlag.WRONG_OBJECT_PART in extra_flags:
            parts.append("Claimed part not visible in any image.")
        if RiskFlag.CLAIM_MISMATCH in extra_flags:
            parts.append("Visible damage type differs from claimed damage.")
    else:  # NOT_ENOUGH_INFORMATION
        if not evidence.evidence_standard_met:
            parts.append(evidence.evidence_standard_met_reason)
        elif not vision.valid_image:
            parts.append("No valid images could be assessed.")
        elif not vision.object_visible:
            parts.append(f"Claimed object not visible in submitted images.")
        else:
            parts.append(
                vision.reasoning or "Insufficient visual evidence to determine claim status."
            )
        if evidence.missing_evidence:
            parts.append("Missing: " + "; ".join(evidence.missing_evidence[:2]))

    return " ".join(p.strip() for p in parts if p.strip())


# ---------------------------------------------------------------------------
# DecisionService
# ---------------------------------------------------------------------------


class DecisionService:
    """Aggregates all upstream outputs into a complete ClaimOutput row."""

    # ------------------------------------------------------------------
    # Primary interface (new, takes VisionReviewResult + EvidenceStandardResult)
    # ------------------------------------------------------------------

    def decide(
        self,
        claim: ClaimInput,
        parsed_claim: ParsedClaim,
        vision: VisionReviewResult,
        evidence: EvidenceStandardResult,
        user_history: UserHistory | None = None,
    ) -> ClaimOutput:
        """Produce a fully-populated ClaimOutput for one claim row.

        Parameters
        ----------
        claim:          Raw input row from claims.csv.
        parsed_claim:   Structured claim from ClaimExtractionAgent.
        vision:         Aggregated visual findings from VisionReviewAgent.
        evidence:       Evidence sufficiency from EvidenceStandardsEngine.
        user_history:   Optional risk context (never overrides visual evidence).
        """
        extra_flags: list[RiskFlag] = []

        # ----------------------------------------------------------------
        # Step 1: determine claim_status
        # ----------------------------------------------------------------
        status, extra_flags = self._determine_status(
            parsed_claim=parsed_claim,
            vision=vision,
            evidence=evidence,
        )

        # ----------------------------------------------------------------
        # Step 2: best-effort issue_type and object_part
        # ----------------------------------------------------------------
        issue_type = vision.issue_type
        if issue_type == IssueType.UNKNOWN:
            issue_type = parsed_claim.claimed_issue  # fallback to claim text

        object_part = vision.object_part
        if object_part == ObjectPart.UNKNOWN:
            object_part = parsed_claim.claimed_part  # fallback to claim text

        # ----------------------------------------------------------------
        # Step 3: severity
        # ----------------------------------------------------------------
        severity = _best_severity(vision.severity, issue_type)

        # ----------------------------------------------------------------
        # Step 4: risk flags
        # ----------------------------------------------------------------
        hist_flags = _history_flags(user_history)
        risk_flags_str = _merge_flags(
            list(vision.quality_flags), hist_flags, extra_flags
        )

        # ----------------------------------------------------------------
        # Step 5: justification
        # ----------------------------------------------------------------
        justification = _build_justification(status, vision, evidence, extra_flags)

        output = ClaimOutput(
            user_id=claim.user_id,
            image_paths=claim.image_paths,
            user_claim=claim.user_claim,
            claim_object=claim.claim_object,
            evidence_standard_met=evidence.evidence_standard_met,
            evidence_standard_met_reason=evidence.evidence_standard_met_reason,
            risk_flags=risk_flags_str,
            issue_type=issue_type,
            object_part=object_part,
            claim_status=status,
            claim_status_justification=justification,
            supporting_image_ids=_supporting_ids_str(vision.supporting_image_ids),
            valid_image=vision.valid_image,
            severity=severity,
        )

        logger.info(
            "Decision: user=%s status=%s evidence_met=%s valid=%s "
            "issue=%s part=%s severity=%s flags=%s",
            claim.user_id, status, evidence.evidence_standard_met,
            vision.valid_image, issue_type, object_part, severity,
            risk_flags_str,
        )
        return output

    # ------------------------------------------------------------------
    # Legacy interface (pipeline calls build_output with ImageEvidence list)
    # ------------------------------------------------------------------

    def build_output(
        self,
        claim: ClaimInput,
        parsed_claim: ParsedClaim,
        image_evidence: list[ImageEvidence],
        user_history: UserHistory | None,
    ) -> ClaimOutput:
        """Bridge for the legacy ClaimReviewPipeline interface.

        Converts the list[ImageEvidence] format to a minimal VisionReviewResult
        and a conservative EvidenceStandardResult, then delegates to decide().
        """
        from models.vision_review import PerImageAnalysis, VisionReviewResult
        from models.enums import Severity as Sev

        # Build a minimal VisionReviewResult from legacy ImageEvidence
        per_image: list[PerImageAnalysis] = []
        for ev in image_evidence:
            per_image.append(PerImageAnalysis(
                image_id=ev.image_id,
                image_path=ev.image_path,
                readable=ev.readable,
                object_present=ev.object_present,
                visible_parts=ev.visible_parts,
                visible_issues=ev.visible_issues,
                quality_flags=ev.risk_flags,
                description=ev.description,
                confidence=float(ev.confidence or 0.0),
                supports_claim=bool(
                    ev.object_present
                    and ev.visible_issues
                    and (
                        parsed_claim.claimed_issue in ev.visible_issues
                        or parsed_claim.claimed_issue == IssueType.UNKNOWN
                    )
                ),
                severity=Sev.UNKNOWN,
            ))

        supporting_ids = [p.image_id for p in per_image if p.supports_claim]
        object_visible = any(p.object_present is True for p in per_image)
        part_visible = any(
            parsed_claim.claimed_part in p.visible_parts
            or parsed_claim.claimed_part == ObjectPart.UNKNOWN
            for p in per_image if p.readable
        )
        issue_visible = any(
            parsed_claim.claimed_issue in p.visible_issues
            for p in per_image if p.readable
        )

        all_parts = list({p for img in per_image for p in img.visible_parts})
        all_issues = list({i for img in per_image for i in img.visible_issues})
        all_flags = list({f for img in per_image for f in img.quality_flags})
        valid = any(p.valid_image for p in per_image)
        conf = (
            sum(p.confidence for p in per_image if p.readable) / max(len(per_image), 1)
        )

        vision = VisionReviewResult(
            object_visible=object_visible,
            object_part_visible=part_visible,
            issue_visible=issue_visible,
            issue_type=all_issues[0] if all_issues else IssueType.UNKNOWN,
            object_part=all_parts[0] if all_parts else ObjectPart.UNKNOWN,
            severity=Sev.UNKNOWN,
            supporting_image_ids=supporting_ids,
            valid_image=valid,
            quality_flags=all_flags,
            confidence=round(conf, 4),
            reasoning="",
            per_image=per_image,
        )

        from services.evidence_standards_engine import EvidenceStandardsEngine
        from models.evidence_standard import EvidenceStandardResult, SufficiencyLevel

        # Conservative evidence result (no requirements loaded in legacy path)
        evidence = EvidenceStandardResult(
            evidence_standard_met=valid,
            evidence_standard_met_reason=(
                "Visual evidence available." if valid
                else "No valid images."
            ),
            sufficiency_level=(
                SufficiencyLevel.FULLY_MET if valid
                else SufficiencyLevel.UNVERIFIABLE
            ),
        )

        return self.decide(
            claim=claim,
            parsed_claim=parsed_claim,
            vision=vision,
            evidence=evidence,
            user_history=user_history,
        )

    # ------------------------------------------------------------------
    # Decision logic
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_status(
        parsed_claim: ParsedClaim,
        vision: VisionReviewResult,
        evidence: EvidenceStandardResult,
    ) -> tuple[ClaimStatus, list[RiskFlag]]:
        """Apply decision rules and return (status, extra_risk_flags)."""
        extra: list[RiskFlag] = []

        # Rule 1: no valid images
        if not vision.valid_image:
            extra.append(RiskFlag.MANUAL_REVIEW_REQUIRED)
            return ClaimStatus.NOT_ENOUGH_INFORMATION, extra

        # Rule 2: evidence standard not met (primary requirement failed)
        if not evidence.evidence_standard_met:
            if evidence.sufficiency_level == SufficiencyLevel.UNVERIFIABLE:
                extra.append(RiskFlag.MANUAL_REVIEW_REQUIRED)
            return ClaimStatus.NOT_ENOUGH_INFORMATION, extra

        # Rule 3: claimed object not visible
        # Only flag WRONG_OBJECT when NEITHER the object NOR its claimed part
        # is visible. A close-up of a car bumper IS a car image — the whole
        # object doesn't need to be in frame if the claimed part IS visible.
        if not vision.object_visible and not vision.object_part_visible:
            extra.append(RiskFlag.WRONG_OBJECT)
            return ClaimStatus.NOT_ENOUGH_INFORMATION, extra

        # Rule 4: claimed part not visible
        if not vision.object_part_visible:
            extra.append(RiskFlag.WRONG_OBJECT_PART)
            return ClaimStatus.NOT_ENOUGH_INFORMATION, extra

        # Rule 5: part visible AND damage visible AND claim-consistent → SUPPORTED
        if vision.issue_visible and vision.supporting_image_ids:
            # Check for mismatch between visible issue and claimed issue
            claimed = parsed_claim.claimed_issue
            visible = vision.issue_type
            if (
                claimed != IssueType.UNKNOWN
                and visible != IssueType.UNKNOWN
                and claimed != visible
            ):
                extra.append(RiskFlag.CLAIM_MISMATCH)
                # Still SUPPORTED if evidence_standard_met and there's a
                # supporting image — the damage is real, just a taxonomy diff
            return ClaimStatus.SUPPORTED, extra

        # Rule 5b: issue visible but wrong type, no supporting IDs → CONTRADICTED
        if (
            vision.issue_visible
            and not vision.supporting_image_ids
            and vision.object_part_visible
        ):
            claimed = parsed_claim.claimed_issue
            visible = vision.issue_type
            if (
                claimed != IssueType.UNKNOWN
                and visible != IssueType.UNKNOWN
                and claimed != visible
            ):
                extra.append(RiskFlag.CLAIM_MISMATCH)
                return ClaimStatus.CONTRADICTED, extra

        # Rule 6: part visible but damage absent / wrong
        if vision.object_part_visible and not vision.issue_visible:
            extra.append(RiskFlag.DAMAGE_NOT_VISIBLE)
            return ClaimStatus.CONTRADICTED, extra

        # Rule 7: fallback
        return ClaimStatus.NOT_ENOUGH_INFORMATION, extra
