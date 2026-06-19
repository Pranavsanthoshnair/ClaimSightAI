"""Structured data contracts for pipeline inputs, outputs, and intermediates."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from models.enums import (
    ClaimObject,
    ClaimStatus,
    IssueType,
    ObjectPart,
    RiskFlag,
    Severity,
)


OUTPUT_COLUMNS: tuple[str, ...] = (
    "user_id",
    "image_paths",
    "user_claim",
    "claim_object",
    "evidence_standard_met",
    "evidence_standard_met_reason",
    "risk_flags",
    "issue_type",
    "object_part",
    "claim_status",
    "claim_status_justification",
    "supporting_image_ids",
    "valid_image",
    "severity",
)


class ClaimInput(BaseModel):
    """One input row from claims.csv or sample_claims.csv."""

    user_id: str
    image_paths: str
    user_claim: str
    claim_object: ClaimObject

    @property
    def image_path_list(self) -> list[str]:
        """Return image paths split from the semicolon-delimited source field."""
        return [path.strip() for path in self.image_paths.split(";") if path.strip()]


class ClaimOutput(ClaimInput):
    """One output row matching the required submission schema."""

    evidence_standard_met: bool
    evidence_standard_met_reason: str
    risk_flags: str
    issue_type: IssueType
    object_part: ObjectPart
    claim_status: ClaimStatus
    claim_status_justification: str
    supporting_image_ids: str
    valid_image: bool
    severity: Severity

    @field_validator("risk_flags", "supporting_image_ids")
    @classmethod
    def non_empty_semicolon_field(cls, value: str) -> str:
        """Ensure compact list fields are never blank."""
        return value.strip() or "none"

    def to_output_dict(self) -> dict[str, object]:
        """Return values in the exact required output column order."""
        return {column: getattr(self, column) for column in OUTPUT_COLUMNS}


class UserHistory(BaseModel):
    """Risk-context row from user_history.csv."""

    user_id: str
    past_claim_count: int = 0
    accept_claim: int = 0
    manual_review_claim: int = 0
    rejected_claim: int = 0
    last_90_days_claim_count: int = 0
    history_flags: str = "none"
    history_summary: str = ""


class EvidenceRequirement(BaseModel):
    """Minimum image evidence requirement row."""

    requirement_id: str
    claim_object: str
    applies_to: str
    minimum_image_evidence: str


class ParsedClaim(BaseModel):
    """Normalized claim target extracted from the conversation."""

    claim_object: ClaimObject
    claimed_issue: IssueType = IssueType.UNKNOWN
    claimed_part: ObjectPart = ObjectPart.UNKNOWN
    issue_family: str = "unknown"
    is_multi_part: bool = False
    relevant_requirement_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class ImageEvidence(BaseModel):
    """Image-level evidence extracted before final claim aggregation."""

    image_id: str
    image_path: Path
    readable: bool = False
    object_present: bool | None = None
    visible_parts: list[ObjectPart] = Field(default_factory=list)
    visible_issues: list[IssueType] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    description: str = ""
    confidence: float | None = None
