"""PipelineDebugger — captures the full state at every stage of the pipeline.

Usage:
    debugger = PipelineDebugger()
    report = debugger.run(
        user_claim=..., claim_object="car",
        image_paths=[...], user_id="demo"
    )
    report.save("debug_pipeline_report.json")
    print(report.summary())

This module NEVER modifies business logic — it only observes and records.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ── Stage output containers ──────────────────────────────────────────────────

@dataclass
class ClaimExtractionDebug:
    raw_claim: str = ""
    claim_object: str = ""
    primary_issue: str = ""
    primary_part: str = ""
    secondary_issues: list[str] = field(default_factory=list)
    secondary_parts: list[str] = field(default_factory=list)
    is_multi_part: bool = False
    claim_confidence: float = 0.0
    claim_summary: str = ""
    injection_detected: bool = False
    reasoning: str = ""
    error: str | None = None


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
    supports_claim: bool = False
    confidence: float = 0.0
    severity: str = "unknown"
    description: str = ""
    raw_vlm_response: str = ""
    error: str | None = None


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
    valid_image: bool = False
    quality_flags: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    per_image: list[PerImageDebug] = field(default_factory=list)
    total_latency_s: float = 0.0
    error: str | None = None


@dataclass
class EvidenceInputDebug:
    claim_object: str = ""
    claimed_part: str = ""
    claimed_issue: str = ""
    is_multi_part: bool = False
    object_visible: bool = False
    object_part_visible: bool = False
    issue_visible: bool = False
    valid_image_count: int = 0
    total_image_count: int = 0
    supporting_image_ids: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    all_visible_parts: list[str] = field(default_factory=list)
    all_visible_issues: list[str] = field(default_factory=list)


@dataclass
class RequirementEvalDebug:
    requirement_id: str = ""
    applies_to: str = ""
    satisfied: bool = False
    satisfying_image_ids: list[str] = field(default_factory=list)
    gap_description: str = ""


@dataclass
class EvidenceStandardDebug:
    evidence_standard_met: bool = False
    evidence_standard_met_reason: str = ""
    sufficiency_level: str = ""
    matched_requirement_ids: list[str] = field(default_factory=list)
    satisfied_requirement_ids: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    per_requirement: list[RequirementEvalDebug] = field(default_factory=list)
    error: str | None = None


@dataclass
class DecisionInputDebug:
    claim_object: str = ""
    claimed_issue: str = ""
    claimed_part: str = ""
    is_multi_part: bool = False
    object_visible: bool = False
    object_part_visible: bool = False
    issue_visible: bool = False
    evidence_standard_met: bool = False
    sufficiency_level: str = ""
    supporting_image_ids: list[str] = field(default_factory=list)
    valid_image: bool = False
    quality_flags: list[str] = field(default_factory=list)
    vision_confidence: float = 0.0
    has_user_history_risk: bool = False


@dataclass
class FinalOutputDebug:
    claim_status: str = ""
    evidence_standard_met: str = ""
    evidence_standard_met_reason: str = ""
    issue_type: str = ""
    object_part: str = ""
    severity: str = ""
    risk_flags: str = ""
    supporting_image_ids: str = ""
    valid_image: str = ""
    claim_status_justification: str = ""


@dataclass
class PipelineDebugReport:
    user_id: str = ""
    timestamp: str = ""
    claim_extraction: ClaimExtractionDebug = field(default_factory=ClaimExtractionDebug)
    vision_review: VisionReviewDebug = field(default_factory=VisionReviewDebug)
    evidence_input: EvidenceInputDebug = field(default_factory=EvidenceInputDebug)
    evidence_standard: EvidenceStandardDebug = field(default_factory=EvidenceStandardDebug)
    decision_input: DecisionInputDebug = field(default_factory=DecisionInputDebug)
    final_output: FinalOutputDebug = field(default_factory=FinalOutputDebug)
    anomalies: list[str] = field(default_factory=list)
    total_latency_s: float = 0.0

    def save(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(asdict(self), indent=2, default=str),
            encoding="utf-8",
        )

    def summary(self) -> str:
        lines = [
            f"=== CLAIM EXTRACTION ===",
            f"  claim_object:   {self.claim_extraction.claim_object}",
            f"  primary_issue:  {self.claim_extraction.primary_issue}",
            f"  primary_part:   {self.claim_extraction.primary_part}",
            f"  is_multi_part:  {self.claim_extraction.is_multi_part}",
            f"  confidence:     {self.claim_extraction.claim_confidence:.2f}",
            f"",
            f"=== VISION REVIEW ===",
            f"  provider:        {self.vision_review.provider_used}",
            f"  object_visible:  {self.vision_review.object_visible}",
            f"  part_visible:    {self.vision_review.object_part_visible}",
            f"  issue_visible:   {self.vision_review.issue_visible}",
            f"  visible_parts:   {[p.image_id + ':' + str(p.visible_parts) for p in self.vision_review.per_image]}",
            f"  supporting:      {self.vision_review.supporting_image_ids}",
            f"  confidence:      {self.vision_review.confidence:.2f}",
            f"",
            f"=== EVIDENCE STANDARD INPUT ===",
            f"  is_multi_part:      {self.evidence_input.is_multi_part}",
            f"  object_visible:     {self.evidence_input.object_visible}",
            f"  object_part_vis:    {self.evidence_input.object_part_visible}",
            f"  issue_visible:      {self.evidence_input.issue_visible}",
            f"  valid_image_count:  {self.evidence_input.valid_image_count}",
            f"  all_visible_parts:  {self.evidence_input.all_visible_parts}",
            f"",
            f"=== REQUIREMENT EVALUATIONS ===",
        ]
        for req in self.evidence_standard.per_requirement:
            status = "PASS" if req.satisfied else "FAIL"
            lines.append(f"  [{status}] {req.requirement_id}: {req.gap_description or 'OK'}")

        lines += [
            f"",
            f"=== FINAL OUTPUT ===",
            f"  claim_status:     {self.final_output.claim_status}",
            f"  evidence_met:     {self.final_output.evidence_standard_met}",
            f"  severity:         {self.final_output.severity}",
            f"  risk_flags:       {self.final_output.risk_flags}",
        ]

        if self.anomalies:
            lines += ["", "=== ANOMALIES DETECTED ==="]
            for a in self.anomalies:
                lines.append(f"  ⚠ {a}")

        return "\n".join(lines)
