"""Pydantic schemas for VisionReviewAgent inputs and outputs.

Schema hierarchy
----------------
VisionReviewInput
    -> Per-image analysis   : PerImageAnalysis
    -> Cross-image aggregate: VisionReviewResult   (agent output)

Design constraints
------------------
- Every field has a safe, conservative default so callers never hit KeyError.
- ``quality_flags`` maps 1:1 to ``RiskFlag`` enum values (subset relevant to
  images); they are kept as strings here so the schema stays serialisable
  without importing the full enum tree.
- ``supporting_image_ids`` is the authoritative list of image IDs whose
  visual evidence positively supports the claim target.
- No field encodes claim status or accept/reject decisions — that belongs to
  the DecisionService downstream.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from models.enums import ClaimObject, IssueType, ObjectPart, RiskFlag, Severity


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------


class VisionReviewInput(BaseModel):
    """Everything the VisionReviewAgent needs to analyse a set of images."""

    image_paths: list[Path] = Field(
        ...,
        description="Resolved absolute paths to local image files.",
        min_length=1,
    )
    claim_object: ClaimObject = Field(
        ...,
        description="Object family: car, laptop, or package.",
    )
    claimed_part: ObjectPart = Field(
        default=ObjectPart.UNKNOWN,
        description="Normalised object part from ClaimExtractionAgent.",
    )
    claimed_issue: IssueType = Field(
        default=IssueType.UNKNOWN,
        description="Normalised issue type from ClaimExtractionAgent.",
    )
    is_multi_part: bool = Field(
        default=False,
        description="True when the claim targets more than one part.",
    )


# ---------------------------------------------------------------------------
# Phase A output: per-image analysis
# ---------------------------------------------------------------------------


class PerImageAnalysis(BaseModel):
    """Structured findings for a single image.

    This is the raw output of Phase A (per-image VLM call or local preflight).
    It is aggregated in Phase B to produce ``VisionReviewResult``.
    """

    image_id: str = Field(..., description="Filename stem used as a stable image ID.")
    image_path: Path = Field(..., description="Resolved path to the image file.")

    # ---- Readability / validity ------------------------------------------
    file_exists: bool = Field(default=False)
    readable: bool = Field(
        default=False,
        description="True when the image could be decoded and is usable.",
    )
    valid_image: bool = Field(
        default=False,
        description=(
            "True when the image is readable AND free of severe quality blockers "
            "that would prevent visual assessment."
        ),
    )

    # ---- Image quality metrics (local preflight) -------------------------
    width: int | None = Field(default=None)
    height: int | None = Field(default=None)
    blur_score: float | None = Field(
        default=None,
        description="Laplacian variance — lower means blurrier.",
    )

    # ---- VLM-derived fields ----------------------------------------------
    object_present: bool | None = Field(
        default=None,
        description="True/False/None = yes/no/cannot determine.",
    )
    visible_parts: list[ObjectPart] = Field(default_factory=list)
    visible_issues: list[IssueType] = Field(default_factory=list)
    quality_flags: list[RiskFlag] = Field(default_factory=list)
    description: str = Field(
        default="",
        description="1-2 sentence visual description grounded in what is seen.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="VLM confidence for this image's findings.",
    )
    severity: Severity = Field(
        default=Severity.UNKNOWN,
        description="Estimated damage severity visible in this image.",
    )

    # ---- Derived support flag --------------------------------------------
    supports_claim: bool = Field(
        default=False,
        description=(
            "True when this image shows the claimed object, claimed part, and "
            "a visible issue consistent with the claimed damage type."
        ),
    )

    @model_validator(mode="after")
    def derive_valid_image(self) -> "PerImageAnalysis":
        """valid_image = readable AND no severe blocking quality flags."""
        blocking = {
            RiskFlag.BLURRY_IMAGE,
            RiskFlag.CROPPED_OR_OBSTRUCTED,
            RiskFlag.LOW_LIGHT_OR_GLARE,
            RiskFlag.WRONG_OBJECT,
            RiskFlag.POSSIBLE_MANIPULATION,
        }
        if not self.readable:
            self.valid_image = False
        elif set(self.quality_flags) & blocking:
            self.valid_image = False
        else:
            self.valid_image = True
        return self


# ---------------------------------------------------------------------------
# Phase D output: aggregated vision review result
# ---------------------------------------------------------------------------


class VisionReviewResult(BaseModel):
    """Aggregated visual evidence findings across all submitted images.

    This is the final output of the VisionReviewAgent and the primary input
    to the downstream DecisionService.
    """

    # ---- Object-level findings -------------------------------------------
    object_visible: bool = Field(
        default=False,
        description="True when at least one image shows the claimed object.",
    )
    object_part_visible: bool = Field(
        default=False,
        description="True when at least one image shows the claimed object part.",
    )
    issue_visible: bool = Field(
        default=False,
        description="True when at least one image shows damage consistent with the claim.",
    )

    # ---- Normalised taxonomy output --------------------------------------
    issue_type: IssueType = Field(
        default=IssueType.UNKNOWN,
        description="Best-match visible issue type across all supporting images.",
    )
    object_part: ObjectPart = Field(
        default=ObjectPart.UNKNOWN,
        description="Best-match visible object part across all supporting images.",
    )
    severity: Severity = Field(
        default=Severity.UNKNOWN,
        description="Estimated damage severity derived from visual evidence.",
    )

    # ---- Supporting evidence --------------------------------------------
    supporting_image_ids: list[str] = Field(
        default_factory=list,
        description="Image IDs whose evidence positively supports the claim target.",
    )
    valid_image: bool = Field(
        default=False,
        description="True when at least one submitted image is usable for review.",
    )

    # ---- Quality / risk flags -------------------------------------------
    quality_flags: list[RiskFlag] = Field(
        default_factory=list,
        description="Union of quality flags found across all images.",
    )

    # ---- Confidence & reasoning -----------------------------------------
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Aggregated evidence confidence in [0, 1]. "
            "Reflects both VLM certainty and image quality."
        ),
    )
    reasoning: str = Field(
        default="",
        description=(
            "Concise, image-grounded explanation of the aggregated findings. "
            "Suitable for claim_status_justification context."
        ),
    )

    # ---- Per-image breakdown (for audit / evaluation) -------------------
    per_image: list[PerImageAnalysis] = Field(
        default_factory=list,
        description="Per-image analysis records for audit and evaluation use.",
    )

    @field_validator("supporting_image_ids")
    @classmethod
    def deduplicate_image_ids(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        return [x for x in v if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]
