"""pipeline_inspector.py — generates a full debug trace for one claim.

Usage:
    inspector = PipelineInspector(settings)
    report = inspector.inspect(claim_input, image_paths)
    report.save("logs/debug_pipeline_report.json")

The report captures every intermediate value at every pipeline stage
so the exact point of any logic failure can be pinpointed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report data structures
# ---------------------------------------------------------------------------

@dataclass
class ClaimExtractionDebug:
    raw_claim: str = ""
    claim_object: str = ""
    primary_issue: str = ""
    primary_part: str = ""
    secondary_issues: list[str] = field(default_factory=list)
    secondary_parts: list[str] = field(default_factory=list)
    is_multi_part: bool = False
    injection_detected: bool = False
    confidence: float = 0.0
    reasoning: str = ""
    fast_path_used: bool = True


@dataclass
class PerImageDebug:
    image_id: str = ""
    image_path: str = ""
    file_exists: bool = False
    readable: bool = False
    width: int | None = None
    height: int | None = None
    blur_score: float | None = None
    object_present: bool | None = None
    visible_parts: list[str] = field(default_factory=list)
    visible_issues: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    description: str = ""
    confidence: float = 0.0
    severity: str = "unknown"
    supports_claim: bool = False
    vlm_called: bool = False
    raw_vlm_response_preview: str = ""


@dataclass
class VisionReviewDebug:
    provider_used: str = "none"
    fallback_used: bool = False
    object_visible: bool = False
    object_part_visible: bool = False
    issue_visible: bool = False
    issue_type: str = "unknown"
    object_part: str = "unknown"
    severity: str = "unknown"
    supporting_image_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    quality_flags: list[str] = field(default_factory=list)
    reasoning: str = ""
    per_image: list[PerImageDebug] = field(default_factory=list)
    aggregation_notes: list[str] = field(default_factory=list)


@dataclass
class EvidenceStandardDebug:
    # Input fields
    inp_claim_object: str = ""
    inp_claimed_part: str = ""
    inp_claimed_issue: str = ""
    inp_is_multi_part: bool = False
    inp_object_visible: bool = False
    inp_object_part_visible: bool = False
    inp_issue_visible: bool = False
    inp_valid_image_count: int = 0
    inp_total_image_count: int = 0
    inp_supporting_image_ids: list[str] = field(default_factory=list)
    inp_quality_flags: list[str] = field(default_factory=list)
    inp_all_visible_parts: list[str] = field(default_factory=list)
    inp_all_visible_issues: list[str] = field(default_factory=list)
    # Selected requirements
    selected_requirements: list[str] = field(default_factory=list)
    # Per-requirement evaluation
    requirement_evaluations: list[dict[str, Any]] = field(default_factory=list)
    # Output
    sufficiency_level: str = ""
    evidence_standard_met: bool = False
    evidence_standard_met_reason: str = ""
    satisfied_requirements: list[str] = field(default_factory=list)
    unsatisfied_requirements: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    # Diagnosis
    diagnosis: str = ""


@dataclass
class DecisionDebug:
    # Inputs
    claim_status_from_evidence: bool = False
    vision_valid_image: bool = False
    vision_object_visible: bool = False
    vision_object_part_visible: bool = False
    vision_issue_visible: bool = False
    vision_supporting_ids: list[str] = field(default_factory=list)
    evidence_standard_met: bool = False
    # Rule that fired
    rule_fired: str = ""
    extra_flags_added: list[str] = field(default_factory=list)
    # Output
    claim_status: str = ""
    issue_type: str = ""
    object_part: str = ""
    severity: str = ""
    risk_flags: str = ""
    evidence_standard_met_reason: str = ""
    claim_status_justification: str = ""


@dataclass
class PipelineDebugReport:
    claim_id: str = ""
    claim_object: str = ""
    image_paths: list[str] = field(default_factory=list)
    # Stage outputs
    claim_extraction: ClaimExtractionDebug = field(default_factory=ClaimExtractionDebug)
    vision_review: VisionReviewDebug = field(default_factory=VisionReviewDebug)
    evidence_standard: EvidenceStandardDebug = field(default_factory=EvidenceStandardDebug)
    decision: DecisionDebug = field(default_factory=DecisionDebug)
    # Root cause analysis
    root_cause_flags: list[str] = field(default_factory=list)
    pipeline_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Pipeline debug report saved to %s", path)

    def print_summary(self) -> None:
        """Print a concise human-readable summary to stdout."""
        print("\n" + "=" * 60)
        print(f"PIPELINE DEBUG: {self.claim_id} ({self.claim_object})")
        print("=" * 60)
        print(f"\n[CLAIM EXTRACTION]")
        e = self.claim_extraction
        print(f"  primary_issue:    {e.primary_issue}")
        print(f"  primary_part:     {e.primary_part}")
        print(f"  is_multi_part:    {e.is_multi_part}  <- CHECK THIS")
        print(f"  confidence:       {e.confidence:.2f}")
        print(f"\n[VISION REVIEW]")
        v = self.vision_review
        print(f"  provider:         {v.provider_used}")
        print(f"  object_visible:   {v.object_visible}")
        print(f"  part_visible:     {v.object_part_visible}")
        print(f"  issue_visible:    {v.issue_visible}")
        print(f"  confidence:       {v.confidence:.2f}")
        print(f"  visible_parts:    {v.per_image[0].visible_parts if v.per_image else []}")
        print(f"  visible_issues:   {v.per_image[0].visible_issues if v.per_image else []}")
        print(f"\n[EVIDENCE STANDARDS]")
        es = self.evidence_standard
        print(f"  inp.is_multi_part:        {es.inp_is_multi_part}")
        print(f"  inp.object_visible:       {es.inp_object_visible}")
        print(f"  inp.object_part_visible:  {es.inp_object_part_visible}")
        print(f"  inp.issue_visible:        {es.inp_issue_visible}")
        print(f"  inp.valid_image_count:    {es.inp_valid_image_count}")
        print(f"  selected_requirements:    {es.selected_requirements}")
        print(f"  evidence_standard_met:    {es.evidence_standard_met}")
        print(f"  reason:                   {es.evidence_standard_met_reason[:120]}")
        for req in es.requirement_evaluations:
            icon = "[PASS]" if req.get("satisfied") else "[FAIL]"
            print(f"    {icon} {req.get('requirement_id')}: {req.get('gap_description', '')[:80]}")
        print(f"\n[DECISION]")
        d = self.decision
        print(f"  rule_fired:    {d.rule_fired}")
        print(f"  claim_status:  {d.claim_status}")
        print(f"  risk_flags:    {d.risk_flags}")
        print(f"\n[ROOT CAUSE FLAGS]")
        for flag in self.root_cause_flags:
            print(f"  [!] {flag}")
        print(f"\n[SUMMARY] {self.pipeline_summary}")
        print("=" * 60)


# ---------------------------------------------------------------------------
# Inspector
# ---------------------------------------------------------------------------

class PipelineInspector:
    """Runs the full pipeline and captures every intermediate value."""

    def __init__(self, settings=None) -> None:
        self.settings = settings

    def inspect(
        self,
        user_claim: str,
        claim_object_str: str,
        image_paths: list[Path],
        user_id: str = "debug",
    ) -> PipelineDebugReport:
        """Run all 4 stages and return a fully-populated debug report."""
        from agents.claim_agent import ClaimExtractionAgent
        from agents.vision_agent import VisionReviewAgent
        from config import Settings
        from models.claim_extraction import ClaimExtractionInput
        from models.enums import ClaimObject, IssueType, ObjectPart
        from models.records import ClaimInput, ParsedClaim
        from models.vision_review import VisionReviewInput
        from services.decision_service import DecisionService
        from services.evidence_standards_engine import EvidenceStandardsEngine
        from services.model_service import ModelService

        if self.settings is None:
            from pathlib import Path as _Path
            repo = _Path(__file__).resolve().parent.parent.parent
            self.settings = Settings(repo_root=repo)

        report = PipelineDebugReport(
            claim_id=user_id,
            claim_object=claim_object_str,
            image_paths=[str(p) for p in image_paths],
        )
        root_cause_flags: list[str] = []

        # ────────────────────────────────────────────────────────────────
        # STAGE A: Claim Extraction
        # ────────────────────────────────────────────────────────────────
        try:
            claim_obj = ClaimObject(claim_object_str)
        except ValueError:
            claim_obj = ClaimObject.CAR

        claim_agent = ClaimExtractionAgent()
        extraction = claim_agent.extract(
            ClaimExtractionInput(user_claim=user_claim, claim_object=claim_obj)
        )

        report.claim_extraction = ClaimExtractionDebug(
            raw_claim=user_claim[:500],
            claim_object=claim_object_str,
            primary_issue=str(extraction.claimed_issue_type),
            primary_part=str(extraction.claimed_object_part),
            secondary_issues=[str(i) for i in extraction.additional_claimed_issues],
            secondary_parts=[str(p) for p in extraction.additional_claimed_parts],
            is_multi_part=extraction.is_multi_part,
            injection_detected=extraction.injection_detected,
            confidence=extraction.claim_confidence,
            reasoning=extraction.reasoning,
        )

        if extraction.is_multi_part and not extraction.additional_claimed_parts:
            root_cause_flags.append(
                "SUSPICIOUS_MULTI_PART: is_multi_part=True but additional_claimed_parts is empty. "
                "This may incorrectly trigger REQ_GENERAL_MULTI_IMAGE."
            )

        # ────────────────────────────────────────────────────────────────
        # STAGE B: Vision Review
        # ────────────────────────────────────────────────────────────────
        model_svc = ModelService(self.settings) if self.settings.has_vision_model else None
        vision_agent = VisionReviewAgent(model_service=model_svc, cache={})

        valid_paths = [p for p in image_paths if p.exists()]
        if valid_paths:
            vision_result = vision_agent.review(VisionReviewInput(
                image_paths=valid_paths,
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
                reasoning="No valid image paths provided.",
            )

        per_image_debug = []
        for a in vision_result.per_image:
            per_image_debug.append(PerImageDebug(
                image_id=a.image_id,
                image_path=str(a.image_path),
                file_exists=a.file_exists,
                readable=a.readable,
                width=a.width,
                height=a.height,
                blur_score=a.blur_score,
                object_present=a.object_present,
                visible_parts=[p.value for p in a.visible_parts],
                visible_issues=[i.value for i in a.visible_issues],
                quality_flags=[f.value for f in a.quality_flags],
                description=a.description[:200],
                confidence=a.confidence,
                severity=str(a.severity),
                supports_claim=a.supports_claim,
                vlm_called=model_svc is not None,
            ))

        agg_notes = []
        if not vision_result.object_visible:
            agg_notes.append(
                f"object_visible=False. VLM object_present votes: "
                f"{[a.object_present for a in vision_result.per_image]}"
            )
        if not vision_result.object_part_visible:
            agg_notes.append(
                f"object_part_visible=False. Visible parts across all images: "
                f"{[p.value for a in vision_result.per_image for p in a.visible_parts]}"
            )
        if not vision_result.issue_visible:
            agg_notes.append(
                f"issue_visible=False. Visible issues across all images: "
                f"{[i.value for a in vision_result.per_image for i in a.visible_issues]}"
            )

        report.vision_review = VisionReviewDebug(
            provider_used=getattr(model_svc, "provider_name", "none") if model_svc else "none",
            fallback_used=getattr(model_svc, "fallback_count", 0) > 0 if model_svc else False,
            object_visible=vision_result.object_visible,
            object_part_visible=vision_result.object_part_visible,
            issue_visible=vision_result.issue_visible,
            issue_type=str(vision_result.issue_type),
            object_part=str(vision_result.object_part),
            severity=str(vision_result.severity),
            supporting_image_ids=list(vision_result.supporting_image_ids),
            confidence=vision_result.confidence,
            quality_flags=[f.value for f in vision_result.quality_flags],
            reasoning=vision_result.reasoning,
            per_image=per_image_debug,
            aggregation_notes=agg_notes,
        )

        if model_svc is None:
            root_cause_flags.append(
                "NO_MODEL: VisionReviewAgent running in preflight-only mode. "
                "object_visible/issue_visible will always be False without a VLM."
            )

        # ────────────────────────────────────────────────────────────────
        # STAGE C: Evidence Standards
        # ────────────────────────────────────────────────────────────────
        evidence_engine = EvidenceStandardsEngine()
        req_csv = self.settings.resolve_path(self.settings.evidence_requirements_csv)
        if req_csv.exists():
            evidence_engine.load(req_csv)

        from services.evidence_standards_engine import EvidenceStandardsEngine as ESE
        inp = ESE.build_input(
            vision_result=vision_result,
            claim_object=str(claim_obj),
            claimed_part=str(extraction.claimed_object_part),
            claimed_issue=str(extraction.claimed_issue_type),
            is_multi_part=extraction.is_multi_part,
        )

        evidence_result = evidence_engine.evaluate(inp, vision_confidence=vision_result.confidence)

        req_evals = []
        for req in evidence_result.per_requirement:
            req_evals.append({
                "requirement_id": req.requirement_id,
                "applies_to": req.applies_to,
                "satisfied": req.satisfied,
                "gap_description": req.gap_description,
                "satisfying_image_ids": req.satisfying_image_ids,
            })

        # Diagnosis: find which requirement caused the failure
        diagnosis = ""
        for req in evidence_result.per_requirement:
            if not req.satisfied and req.gap_description:
                if "multi-part" in req.gap_description.lower():
                    diagnosis = (
                        f"REQ_GENERAL_MULTI_IMAGE was selected because is_multi_part={inp.is_multi_part}. "
                        f"If this is a simple single-part claim, the ClaimExtractionAgent "
                        f"incorrectly set is_multi_part=True."
                    )
                    root_cause_flags.append(f"MULTI_PART_FALSE_POSITIVE: {diagnosis}")
                elif "not visible in any image" in req.gap_description.lower():
                    diagnosis = (
                        f"The EvidenceStandardsEngine received object_visible={inp.object_visible}, "
                        f"object_part_visible={inp.object_part_visible}. "
                        f"These come from VisionReviewResult which had: "
                        f"object_visible={vision_result.object_visible}, "
                        f"object_part_visible={vision_result.object_part_visible}."
                    )
                    root_cause_flags.append(f"OBJECT_NOT_VISIBLE_IN_ENGINE: {diagnosis}")
                break

        report.evidence_standard = EvidenceStandardDebug(
            inp_claim_object=inp.claim_object,
            inp_claimed_part=inp.claimed_part,
            inp_claimed_issue=inp.claimed_issue,
            inp_is_multi_part=inp.is_multi_part,
            inp_object_visible=inp.object_visible,
            inp_object_part_visible=inp.object_part_visible,
            inp_issue_visible=inp.issue_visible,
            inp_valid_image_count=inp.valid_image_count,
            inp_total_image_count=inp.total_image_count,
            inp_supporting_image_ids=inp.supporting_image_ids,
            inp_quality_flags=inp.quality_flags,
            inp_all_visible_parts=inp.all_visible_parts,
            inp_all_visible_issues=inp.all_visible_issues,
            selected_requirements=evidence_result.matched_requirement_ids,
            requirement_evaluations=req_evals,
            sufficiency_level=str(evidence_result.sufficiency_level),
            evidence_standard_met=evidence_result.evidence_standard_met,
            evidence_standard_met_reason=evidence_result.evidence_standard_met_reason,
            satisfied_requirements=evidence_result.satisfied_requirement_ids,
            unsatisfied_requirements=[
                r.requirement_id for r in evidence_result.per_requirement if not r.satisfied
            ],
            missing_evidence=evidence_result.missing_evidence,
            confidence=evidence_result.confidence,
            diagnosis=diagnosis,
        )

        # ────────────────────────────────────────────────────────────────
        # STAGE D: Decision
        # ────────────────────────────────────────────────────────────────
        decision_svc = DecisionService()
        claim_input = ClaimInput(
            user_id=user_id,
            image_paths=";".join(str(p) for p in image_paths) if image_paths else "none",
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

        # Determine which rule fired
        rule_fired = "unknown"
        if not vision_result.valid_image:
            rule_fired = "Rule 1: no valid images"
        elif not evidence_result.evidence_standard_met:
            rule_fired = "Rule 2: evidence standard not met"
        elif not vision_result.object_visible and not vision_result.object_part_visible:
            rule_fired = "Rule 3: object not visible"
        elif not vision_result.object_part_visible:
            rule_fired = "Rule 4: part not visible"
        elif vision_result.issue_visible and vision_result.supporting_image_ids:
            rule_fired = "Rule 5: supported"
        elif vision_result.object_part_visible and not vision_result.issue_visible:
            rule_fired = "Rule 6: contradicted"
        else:
            rule_fired = "Rule 7: fallback NEI"

        report.decision = DecisionDebug(
            claim_status_from_evidence=evidence_result.evidence_standard_met,
            vision_valid_image=vision_result.valid_image,
            vision_object_visible=vision_result.object_visible,
            vision_object_part_visible=vision_result.object_part_visible,
            vision_issue_visible=vision_result.issue_visible,
            vision_supporting_ids=list(vision_result.supporting_image_ids),
            evidence_standard_met=evidence_result.evidence_standard_met,
            rule_fired=rule_fired,
            extra_flags_added=[],
            claim_status=str(output.claim_status),
            issue_type=str(output.issue_type),
            object_part=str(output.object_part),
            severity=str(output.severity),
            risk_flags=str(output.risk_flags),
            evidence_standard_met_reason=str(output.evidence_standard_met_reason),
            claim_status_justification=str(output.claim_status_justification),
        )

        # ────────────────────────────────────────────────────────────────
        # Root cause summary
        # ────────────────────────────────────────────────────────────────
        report.root_cause_flags = root_cause_flags

        if not root_cause_flags:
            if str(output.claim_status) == "not_enough_information":
                report.pipeline_summary = (
                    f"Pipeline reached NOT_ENOUGH_INFORMATION via {rule_fired}. "
                    f"object_visible={vision_result.object_visible}, "
                    f"evidence_met={evidence_result.evidence_standard_met}. "
                    f"This is correct behaviour when VLM is unavailable or evidence is genuinely insufficient."
                )
            else:
                report.pipeline_summary = (
                    f"Pipeline completed normally → {output.claim_status} "
                    f"(confidence={vision_result.confidence:.2f})"
                )
        else:
            report.pipeline_summary = "ROOT CAUSE IDENTIFIED: " + " | ".join(root_cause_flags[:2])

        return report
