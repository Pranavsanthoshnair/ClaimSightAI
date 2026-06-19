"""Pydantic schemas for the EvidenceStandardsEngine.

This module defines the input and output contracts for evidence sufficiency
evaluation.  It sits between the VisionReviewAgent and the DecisionService
in the pipeline.

Sufficiency levels
------------------
- FULLY_MET      : all matched requirements are satisfied by at least one
                   valid, on-target image.
- PARTIALLY_MET  : some requirements are satisfied but at least one is not;
                   downstream decision should be made with reduced confidence.
- NOT_MET        : no requirement that applies to this claim is satisfied.
- UNVERIFIABLE   : the image set is entirely unreadable or unavailable;
                   evaluation is impossible without new images.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SufficiencyLevel(StrEnum):
    """Granular evidence sufficiency levels used internally."""

    FULLY_MET = "fully_met"
    PARTIALLY_MET = "partially_met"
    NOT_MET = "not_met"
    UNVERIFIABLE = "unverifiable"


class RequirementEvaluation(BaseModel):
    """Result of evaluating one EvidenceRequirement against the image set."""

    requirement_id: str
    applies_to: str
    minimum_image_evidence: str
    satisfied: bool = False
    satisfying_image_ids: list[str] = Field(default_factory=list)
    gap_description: str = ""


class EvidenceStandardInput(BaseModel):
    """Everything the EvidenceStandardsEngine needs to evaluate sufficiency."""

    claim_object: str = Field(
        ...,
        description="Object family string: car, laptop, or package.",
    )
    claimed_part: str = Field(
        default="unknown",
        description="Normalised object part from ClaimExtractionAgent.",
    )
    claimed_issue: str = Field(
        default="unknown",
        description="Normalised issue type from ClaimExtractionAgent.",
    )
    is_multi_part: bool = Field(
        default=False,
        description="True when the claim covers more than one part or issue.",
    )
    # Vision findings summary (populated from VisionReviewResult)
    object_visible: bool = False
    object_part_visible: bool = False
    issue_visible: bool = False
    valid_image_count: int = Field(default=0, ge=0)
    total_image_count: int = Field(default=0, ge=0)
    supporting_image_ids: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    # Per-image visible parts and issues (for detailed gap analysis)
    all_visible_parts: list[str] = Field(default_factory=list)
    all_visible_issues: list[str] = Field(default_factory=list)


class EvidenceStandardResult(BaseModel):
    """Output of the EvidenceStandardsEngine for one claim.

    ``evidence_standard_met`` and ``evidence_standard_met_reason`` map
    directly to the required output CSV columns.
    """

    # ---- Primary output fields (map to CSV columns) ---------------------
    evidence_standard_met: bool = Field(
        default=False,
        description="True when the image set satisfies minimum evidence requirements.",
    )
    evidence_standard_met_reason: str = Field(
        default="",
        description="Human-readable explanation of the sufficiency decision.",
    )

    # ---- Detailed evaluation ---------------------------------------------
    sufficiency_level: SufficiencyLevel = Field(
        default=SufficiencyLevel.NOT_MET,
        description="Granular sufficiency level for downstream decision logic.",
    )
    matched_requirement_ids: list[str] = Field(
        default_factory=list,
        description="IDs of all requirements that were evaluated for this claim.",
    )
    satisfied_requirement_ids: list[str] = Field(
        default_factory=list,
        description="IDs of requirements that were successfully satisfied.",
    )
    missing_evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Plain-language descriptions of what visual evidence is still needed. "
            "Populated when evidence_standard_met is False."
        ),
    )
    per_requirement: list[RequirementEvaluation] = Field(
        default_factory=list,
        description="Per-requirement evaluation breakdown for audit use.",
    )

    # ---- Confidence -----------------------------------------------------
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Engine confidence in the sufficiency determination. "
            "Reduced when image quality is poor or evidence is ambiguous."
        ),
    )
