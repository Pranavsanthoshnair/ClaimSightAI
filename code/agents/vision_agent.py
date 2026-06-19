"""VisionReviewAgent — analyses local images and produces structured visual
evidence findings for downstream claim decision-making.

Architecture (four phases)
--------------------------
Phase A  Per-image analysis
    1. Local preflight  : file existence, decode check, dimensions, blur score.
    2. VLM inspection   : structured JSON call with claim context injected for
                          focus only — the model must never use it to decide outcomes.
    3. Response parsing : field-by-field coercion with taxonomy validation and
                          one JSON-repair retry for malformed responses.

Phase B  Cross-image aggregation
    Merge per-image findings into a single evidence picture:
    - Object/part/issue visibility across the set.
    - Union of quality flags.
    - Contradiction detection (one image shows damage, another shows no damage
      on the same part) → recorded in reasoning, confidence reduced.

Phase C  Evidence confidence calculation
    Weighted combination of:
    - Per-image VLM confidence scores.
    - Image quality penalty (blurry, wrong angle, etc.).
    - Coverage bonus (how many images independently support the claim).
    - Contradiction penalty.

Phase D  Supporting image selection
    Select image IDs whose per-image analysis positively supports the claim target.

Design constraints
------------------
- No claim decision logic. This agent answers "what is visible?", not
  "should the claim be accepted?".
- No user-history input. History is never passed here.
- Conservative fallback: if all model calls fail, return a safe
  VisionReviewResult with valid_image=False and MANUAL_REVIEW_REQUIRED flag.
- Caching: per-image VLM results are keyed on (prompt_version, image_hash,
  claim_object, claimed_part, claimed_issue). Identical images in different
  claims reuse the cached analysis.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from pathlib import Path
from typing import Any

from models.enums import ClaimObject, IssueType, ObjectPart, RiskFlag, Severity
from models.records import ImageEvidence, ParsedClaim
from models.vision_review import PerImageAnalysis, VisionReviewInput, VisionReviewResult
from prompts.templates import (
    PROMPT_VERSION,
    VISION_EVIDENCE_SYSTEM,
    VISION_EVIDENCE_USER,
)
from utils.paths import image_id_from_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Taxonomy string helpers (injected into prompts)
# ---------------------------------------------------------------------------

_ISSUE_TYPES_STR: str = ", ".join(f'"{v}"' for v in IssueType)
_RISK_FLAGS_STR: str = ", ".join(f'"{v}"' for v in RiskFlag)

# Object-part lists scoped per ClaimObject to keep prompts focused
_PART_VALUES: dict[ClaimObject, str] = {
    ClaimObject.CAR: ", ".join(
        f'"{v}"' for v in [
            ObjectPart.FRONT_BUMPER, ObjectPart.REAR_BUMPER, ObjectPart.DOOR,
            ObjectPart.HOOD, ObjectPart.WINDSHIELD, ObjectPart.SIDE_MIRROR,
            ObjectPart.HEADLIGHT, ObjectPart.TAILLIGHT, ObjectPart.FENDER,
            ObjectPart.QUARTER_PANEL, ObjectPart.BODY, ObjectPart.UNKNOWN,
        ]
    ),
    ClaimObject.LAPTOP: ", ".join(
        f'"{v}"' for v in [
            ObjectPart.SCREEN, ObjectPart.KEYBOARD, ObjectPart.TRACKPAD,
            ObjectPart.HINGE, ObjectPart.LID, ObjectPart.CORNER,
            ObjectPart.PORT, ObjectPart.BASE, ObjectPart.BODY, ObjectPart.UNKNOWN,
        ]
    ),
    ClaimObject.PACKAGE: ", ".join(
        f'"{v}"' for v in [
            ObjectPart.BOX, ObjectPart.PACKAGE_CORNER, ObjectPart.PACKAGE_SIDE,
            ObjectPart.SEAL, ObjectPart.LABEL, ObjectPart.CONTENTS,
            ObjectPart.ITEM, ObjectPart.UNKNOWN,
        ]
    ),
}

# ---------------------------------------------------------------------------
# Image quality heuristics (local, no model required)
# ---------------------------------------------------------------------------

# Laplacian variance threshold below which we flag blurriness
_BLUR_THRESHOLD: float = 80.0
# Minimum image dimension below which we flag wrong_angle / unusable
_MIN_DIMENSION: int = 64


def _try_import_pil() -> Any:
    """Return the PIL.Image module if Pillow is installed, else None."""
    try:
        from PIL import Image  # type: ignore[import]
        return Image
    except ImportError:
        return None


def _try_import_numpy() -> Any:
    try:
        import numpy as np  # type: ignore[import]
        return np
    except ImportError:
        return None


def _compute_blur_score(image_bytes: bytes) -> float | None:
    """Return Laplacian variance as a blur proxy. None if libs unavailable."""
    Image = _try_import_pil()
    np = _try_import_numpy()
    if Image is None or np is None:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
        arr = np.array(img, dtype=float)
        # Simple Laplacian approximation: centre - mean of 4 neighbours
        lap = (
            arr[1:-1, 1:-1] * 4
            - arr[:-2, 1:-1] - arr[2:, 1:-1]
            - arr[1:-1, :-2] - arr[1:-1, 2:]
        )
        return float(np.var(lap))
    except Exception:  # noqa: BLE001
        return None


def _image_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    """Return (width, height). None if libs unavailable or decode fails."""
    Image = _try_import_pil()
    if Image is None:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return img.width, img.height
    except Exception:  # noqa: BLE001
        return None


def _local_preflight(path: Path) -> tuple[bool, bytes, list[RiskFlag], int | None, int | None, float | None]:
    """Read the file and run cheap local quality checks.

    Returns
    -------
    (readable, image_bytes, quality_flags, width, height, blur_score)
    """
    flags: list[RiskFlag] = []

    if not path.exists():
        return False, b"", [RiskFlag.MANUAL_REVIEW_REQUIRED], None, None, None

    try:
        image_bytes = path.read_bytes()
    except OSError:
        return False, b"", [RiskFlag.MANUAL_REVIEW_REQUIRED], None, None, None

    dims = _image_dimensions(image_bytes)
    width, height = (dims if dims else (None, None))

    # Too small to be useful
    if width is not None and height is not None:
        if width < _MIN_DIMENSION or height < _MIN_DIMENSION:
            flags.append(RiskFlag.CROPPED_OR_OBSTRUCTED)

    blur = _compute_blur_score(image_bytes)
    if blur is not None and blur < _BLUR_THRESHOLD:
        flags.append(RiskFlag.BLURRY_IMAGE)

    return True, image_bytes, flags, width, height, blur


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


def _image_cache_key(
    image_bytes: bytes,
    claim_object: ClaimObject,
    claimed_part: ObjectPart,
    claimed_issue: IssueType,
) -> str:
    """Content-addressed cache key for a single image VLM call."""
    payload = (
        f"{PROMPT_VERSION}|{claim_object}|{claimed_part}|{claimed_issue}|"
        + hashlib.sha256(image_bytes).hexdigest()
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# VLM response parsing helpers
# ---------------------------------------------------------------------------


def _normalise_enum_str(val: str) -> str:
    """Normalise model output to match enum values.

    OpenRouter models may return "rear bumper", "rear-bumper" or "REAR_BUMPER".
    All normalise to "rear_bumper".
    """
    return str(val).strip().lower().replace(" ", "_").replace("-", "_")


def _safe_enum(enum_cls: type, val: Any, default: Any) -> Any:
    try:
        return enum_cls(_normalise_enum_str(str(val)))
    except (ValueError, TypeError):
        return default


def _safe_enum_list(enum_cls: type, vals: Any) -> list:
    if not isinstance(vals, list):
        return []
    result = []
    for v in vals:
        normalised = _normalise_enum_str(str(v))
        try:
            result.append(enum_cls(normalised))
        except (ValueError, TypeError):
            logger.debug("Enum coercion failed: %s(%r) -> skipped", enum_cls.__name__, v)
    return result


def _parse_vlm_json(raw: Any) -> dict[str, Any]:
    """Parse VLM response to a dict, with one markdown-fence repair attempt."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            cleaned = re.sub(r"^```(?:json)?\s*|```\s*$", "", raw.strip(), flags=re.M)
            return json.loads(cleaned)
    raise ValueError(f"Unexpected VLM response type: {type(raw)}")


def _coerce_per_image(
    data: dict[str, Any],
    image_id: str,
    image_path: Path,
    preflight_flags: list[RiskFlag],
    width: int | None,
    height: int | None,
    blur_score: float | None,
) -> PerImageAnalysis:
    """Coerce a parsed VLM dict into a validated PerImageAnalysis.

    Normalises all enum strings (spaces/dashes → underscores, lowercase)
    before coercion to tolerate minor model output variations.
    Logs raw response fields at DEBUG level for diagnostics.
    """
    logger.debug(
        "VLM raw fields for %s: object_present=%r visible_parts=%r "
        "visible_issues=%r quality_flags=%r supports_claim=%r confidence=%r severity=%r",
        image_id,
        data.get("object_present"),
        data.get("visible_parts"),
        data.get("visible_issues"),
        data.get("quality_flags"),
        data.get("supports_claim"),
        data.get("confidence"),
        data.get("severity"),
    )

    quality_flags = list(preflight_flags)

    # Coerce VLM quality flags — skip bare "none" (not a real flag)
    raw_flags = data.get("quality_flags", []) or []
    vlm_flags = _safe_enum_list(RiskFlag, [
        f for f in raw_flags
        if _normalise_enum_str(str(f)) not in ("none", "")
    ])
    for f in vlm_flags:
        if f not in quality_flags:
            quality_flags.append(f)

    readable = bool(data.get("readable", True))
    object_present = data.get("object_present")  # may be True/False/None

    visible_parts  = _safe_enum_list(ObjectPart, data.get("visible_parts",  []))
    visible_issues = _safe_enum_list(IssueType,  data.get("visible_issues", []))

    confidence = float(data.get("confidence", 0.0))
    severity   = _safe_enum(Severity, data.get("severity", "unknown"), Severity.UNKNOWN)
    supports   = bool(data.get("supports_claim", False))
    description = str(data.get("description", data.get("step1_observations", "")))

    logger.debug(
        "Coerced %s: readable=%s object_present=%s parts=%s issues=%s "
        "supports=%s confidence=%.2f severity=%s flags=%s",
        image_id, readable, object_present,
        [p.value for p in visible_parts],
        [i.value for i in visible_issues],
        supports, confidence, severity,
        [f.value for f in quality_flags],
    )

    return PerImageAnalysis(
        image_id=image_id,
        image_path=image_path,
        file_exists=True,
        readable=readable,
        width=width,
        height=height,
        blur_score=blur_score,
        object_present=object_present,
        visible_parts=visible_parts,
        visible_issues=visible_issues,
        quality_flags=quality_flags,
        description=description,
        confidence=confidence,
        severity=severity,
        supports_claim=supports,
    )


# ---------------------------------------------------------------------------
# Phase B–D: aggregation helpers
# ---------------------------------------------------------------------------


def _severity_rank(s: Severity) -> int:
    return {Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1,
            Severity.NONE: 0, Severity.UNKNOWN: -1}[s]


def _quality_weight(a: PerImageAnalysis) -> float:
    """Return a quality weight [0.0, 1.0] for an image to use in confidence weighting.

    Penalises images with blurry/wrong-angle quality flags but does not
    fully discard them — they still contribute at reduced weight.
    """
    penalised_flags = {
        RiskFlag.BLURRY_IMAGE: 0.4,
        RiskFlag.CROPPED_OR_OBSTRUCTED: 0.3,
        RiskFlag.LOW_LIGHT_OR_GLARE: 0.3,
        RiskFlag.WRONG_ANGLE: 0.25,
    }
    weight = 1.0
    for flag, penalty in penalised_flags.items():
        if flag in a.quality_flags:
            weight -= penalty
    return max(0.05, weight)


def _aggregate(
    analyses: list[PerImageAnalysis],
    claimed_part: ObjectPart,
    claimed_issue: IssueType,
) -> VisionReviewResult:
    """Phase B + C + D: merge per-image findings into a VisionReviewResult.

    Improvements over original:
    - Per-image quality weights in confidence calculation.
    - Wrong-object images do not pollute the aggregate (parts/issues excluded).
    - Supporting image selection: only clean images with supports_claim=True.
    - Partial-support fallback: right part + damage but not full supports_claim.
    - Contradiction detection: object present vs absent (excluding wrong-object images).
    - Calibrated penalties: WRONG_OBJECT and POSSIBLE_MANIPULATION → 0.12 each.
    - WRONG_ANGLE not penalised if at least one other clean image exists.
    """
    supporting_ids: list[str] = []
    partial_support_ids: list[str] = []
    all_quality_flags: list[RiskFlag] = []
    all_visible_parts: list[ObjectPart] = []
    all_visible_issues: list[IssueType] = []
    valid_analyses: list[PerImageAnalysis] = []

    blocking_flags = frozenset({
        RiskFlag.BLURRY_IMAGE, RiskFlag.CROPPED_OR_OBSTRUCTED,
        RiskFlag.LOW_LIGHT_OR_GLARE, RiskFlag.WRONG_ANGLE,
        RiskFlag.WRONG_OBJECT, RiskFlag.POSSIBLE_MANIPULATION,
    })

    # Phase B — collect and union
    for a in analyses:
        # Union quality flags
        for f in a.quality_flags:
            if f not in all_quality_flags:
                all_quality_flags.append(f)

        if not a.valid_image:
            continue

        valid_analyses.append(a)

        # Only add parts/issues from images that are NOT flagged as wrong-object
        # Wrong-object images show a completely different scene and would pollute
        # the aggregate's visible parts/issues list.
        if RiskFlag.WRONG_OBJECT not in a.quality_flags:
            for p in a.visible_parts:
                if p not in all_visible_parts:
                    all_visible_parts.append(p)
            for i in a.visible_issues:
                if i not in all_visible_issues:
                    all_visible_issues.append(i)

        # Phase D — supporting image selection
        # Primary: fully supports claim AND no disqualifying flags
        disqualifying = {RiskFlag.WRONG_OBJECT, RiskFlag.POSSIBLE_MANIPULATION}
        if a.supports_claim and not (disqualifying & set(a.quality_flags)):
            supporting_ids.append(a.image_id)
        elif (
            not a.supports_claim
            and RiskFlag.WRONG_OBJECT not in a.quality_flags
            and RiskFlag.POSSIBLE_MANIPULATION not in a.quality_flags
            and claimed_part in a.visible_parts
            and bool(a.visible_issues)
        ):
            # Partial support: right part with some damage visible
            partial_support_ids.append(a.image_id)

    if not valid_analyses:
        return VisionReviewResult(
            object_visible=False,
            object_part_visible=False,
            issue_visible=False,
            issue_type=IssueType.UNKNOWN,
            object_part=ObjectPart.UNKNOWN,
            severity=Severity.UNKNOWN,
            supporting_image_ids=[],
            valid_image=False,
            quality_flags=all_quality_flags or [RiskFlag.MANUAL_REVIEW_REQUIRED],
            confidence=0.0,
            reasoning="No readable images could be analysed.",
            per_image=analyses,
        )

    # Object / part / issue visibility
    # Only count object_present=True from images that are NOT flagged wrong_object
    object_visible = any(
        a.object_present is True
        for a in valid_analyses
        if RiskFlag.WRONG_OBJECT not in a.quality_flags
    )
    if not object_visible:
        # Infer: if claimed part is visible, the claimed object must be present
        # (a close-up of a car bumper IS a car image — whole object need not be in frame)
        object_visible = any(
            claimed_part in a.visible_parts
            for a in valid_analyses
            if RiskFlag.WRONG_OBJECT not in a.quality_flags
        )
    part_visible = (
        claimed_part == ObjectPart.UNKNOWN
        or claimed_part in all_visible_parts
        or any(  # Allow if model was uncertain (null) but part list matches
            claimed_part in a.visible_parts
            for a in valid_analyses
        )
    )
    issue_visible = (
        claimed_issue == IssueType.UNKNOWN
        or claimed_issue in all_visible_issues
        or bool(all_visible_issues)
    )

    # Best-match issue and part from supporting images (prefer claimed values)
    best_issue = IssueType.UNKNOWN
    best_part = ObjectPart.UNKNOWN
    if claimed_issue != IssueType.UNKNOWN and claimed_issue in all_visible_issues:
        best_issue = claimed_issue
    elif all_visible_issues:
        best_issue = all_visible_issues[0]

    if claimed_part != ObjectPart.UNKNOWN and claimed_part in all_visible_parts:
        best_part = claimed_part
    elif all_visible_parts:
        best_part = all_visible_parts[0]

    # Best severity — take the maximum visible across supporting images
    best_severity = Severity.UNKNOWN
    for a in valid_analyses:
        if a.supports_claim and _severity_rank(a.severity) > _severity_rank(best_severity):
            best_severity = a.severity
    if best_severity == Severity.UNKNOWN and valid_analyses:
        for a in valid_analyses:
            if _severity_rank(a.severity) > _severity_rank(best_severity):
                best_severity = a.severity

    # Phase C — confidence calculation (quality-weighted)
    readable_count = len(valid_analyses)
    support_count = len(supporting_ids)

    # Check whether at least one clean image exists (no WRONG_ANGLE or worse)
    clean_images_exist = any(
        RiskFlag.WRONG_ANGLE not in a.quality_flags
        and RiskFlag.WRONG_OBJECT not in a.quality_flags
        for a in valid_analyses
    )

    if readable_count == 0:
        confidence = 0.0
    else:
        # Base: quality-weighted mean VLM confidence
        weights = [_quality_weight(a) for a in valid_analyses]
        total_weight = sum(weights)
        if total_weight > 0:
            base = sum(a.confidence * w for a, w in zip(valid_analyses, weights)) / total_weight
        else:
            base = 0.0

        # Coverage bonus: more supporting images → higher confidence (capped at 0.21)
        coverage_bonus = min(0.21, support_count * 0.07)

        # Quality penalty per blocking flag (calibrated)
        heavy_penalty_flags = {
            RiskFlag.WRONG_OBJECT: 0.12,
            RiskFlag.POSSIBLE_MANIPULATION: 0.12,
        }
        light_penalty_flags = {
            RiskFlag.BLURRY_IMAGE: 0.08,
            RiskFlag.CROPPED_OR_OBSTRUCTED: 0.08,
            RiskFlag.LOW_LIGHT_OR_GLARE: 0.08,
            RiskFlag.WRONG_ANGLE: 0.08,  # only applied when no clean image exists
        }

        penalty = 0.0
        present_flags = set(all_quality_flags)
        for flag, pen in heavy_penalty_flags.items():
            if flag in present_flags:
                penalty += pen
        for flag, pen in light_penalty_flags.items():
            if flag in present_flags:
                # Don't penalise WRONG_ANGLE if any other clean image exists
                if flag == RiskFlag.WRONG_ANGLE and clean_images_exist:
                    continue
                penalty += pen
        penalty = min(0.4, penalty)

        # Contradiction detection:
        # One image shows object present, another shows it absent
        # — but exclude wrong-object images from the vote (they show a different scene)
        credible_analyses = [
            a for a in valid_analyses
            if RiskFlag.WRONG_OBJECT not in a.quality_flags
        ]
        present_votes = [
            a.object_present
            for a in credible_analyses
            if a.object_present is not None
        ]
        contradicted = len(set(present_votes)) > 1
        if contradicted:
            all_quality_flags_set = set(all_quality_flags)
            if RiskFlag.CLAIM_MISMATCH not in all_quality_flags_set:
                all_quality_flags.append(RiskFlag.CLAIM_MISMATCH)
        contradiction_penalty = 0.15 if contradicted else 0.0

        confidence = max(0.0, min(1.0, base + coverage_bonus - penalty - contradiction_penalty))

    # If no full support but partial support exists, include partial support in reasoning
    effective_supporting = supporting_ids if supporting_ids else partial_support_ids

    # Build reasoning string
    parts = []
    if supporting_ids:
        parts.append(
            f"{len(supporting_ids)}/{len(analyses)} image(s) support the claim "
            f"({', '.join(supporting_ids)})."
        )
    elif partial_support_ids:
        parts.append(
            f"No image fully supports the claim. "
            f"{len(partial_support_ids)} image(s) show partial evidence "
            f"({', '.join(partial_support_ids)})."
        )
    else:
        parts.append("No image directly supports the claimed damage.")

    if all_visible_issues:
        parts.append(f"Visible issues: {', '.join(i.value for i in all_visible_issues)}.")
    if all_visible_parts:
        parts.append(f"Visible parts: {', '.join(p.value for p in all_visible_parts)}.")
    if all_quality_flags:
        blocking = set(all_quality_flags) & blocking_flags
        if blocking:
            parts.append(f"Quality concerns: {', '.join(f.value for f in blocking)}.")

    # Include per-image descriptions for the best supporting images (up to 1)
    for a in valid_analyses:
        if a.supports_claim and a.description:
            parts.append(f"[{a.image_id}] {a.description}")
            break

    reasoning = " ".join(parts)

    return VisionReviewResult(
        object_visible=object_visible,
        object_part_visible=part_visible,
        issue_visible=issue_visible and bool(all_visible_issues),
        issue_type=best_issue,
        object_part=best_part,
        severity=best_severity,
        supporting_image_ids=supporting_ids,
        valid_image=bool(valid_analyses),
        quality_flags=all_quality_flags,
        confidence=round(confidence, 4),
        reasoning=reasoning,
        per_image=analyses,
    )


# ---------------------------------------------------------------------------
# VisionReviewAgent
# ---------------------------------------------------------------------------


class VisionReviewAgent:
    """Analyses local images and returns structured visual evidence findings.

    Usage::

        agent = VisionReviewAgent(model_service=svc)
        result: VisionReviewResult = agent.review(
            VisionReviewInput(
                image_paths=[Path("dataset/images/test/case_001/img_1.jpg")],
                claim_object=ClaimObject.CAR,
                claimed_part=ObjectPart.FRONT_BUMPER,
                claimed_issue=IssueType.DENT,
            )
        )

    The agent also exposes the legacy ``run()`` interface expected by
    ``ClaimReviewPipeline`` for backward compatibility.
    """

    def __init__(
        self,
        model_service: Any | None = None,
        cache: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        model_service:
            Vision model client.  Must expose ``inspect_image(system, prompt,
            image_bytes) -> dict | str``.  When None the agent runs in
            preflight-only mode: readable/quality flags from local checks only,
            all VLM fields default to unknown/empty.
        cache:
            In-memory dict mapping cache key → raw VLM response dict.
            Inject an external mapping backed by JSONL for cross-run caching.
        """
        self._model_service = model_service
        self._cache: dict[str, dict[str, Any]] = cache if cache is not None else {}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def review(self, payload: VisionReviewInput) -> VisionReviewResult:
        """Run all four phases and return aggregated visual evidence.

        Parameters
        ----------
        payload:
            VisionReviewInput containing image paths and claim context.

        Returns
        -------
        VisionReviewResult
            Aggregated findings across all submitted images.
        """
        analyses: list[PerImageAnalysis] = []

        for path in payload.image_paths:
            analysis = self._analyse_single_image(
                path=path,
                claim_object=payload.claim_object,
                claimed_part=payload.claimed_part,
                claimed_issue=payload.claimed_issue,
            )
            analyses.append(analysis)
            logger.info(
                "Image %s: readable=%s valid=%s supports_claim=%s "
                "issues=%s parts=%s flags=%s confidence=%.2f",
                analysis.image_id,
                analysis.readable,
                analysis.valid_image,
                analysis.supports_claim,
                [i.value for i in analysis.visible_issues],
                [p.value for p in analysis.visible_parts],
                [f.value for f in analysis.quality_flags],
                analysis.confidence,
            )

        result = _aggregate(analyses, payload.claimed_part, payload.claimed_issue)
        logger.info(
            "Vision review complete: object_visible=%s part_visible=%s "
            "issue_visible=%s issue=%s part=%s severity=%s "
            "supporting=%s confidence=%.2f",
            result.object_visible,
            result.object_part_visible,
            result.issue_visible,
            result.issue_type,
            result.object_part,
            result.severity,
            result.supporting_image_ids,
            result.confidence,
        )
        return result

    # ------------------------------------------------------------------
    # Legacy pipeline interface (ClaimReviewPipeline calls .run())
    # ------------------------------------------------------------------

    def run(
        self,
        image_paths: list[Path],
        parsed_claim: ParsedClaim,
    ) -> list[ImageEvidence]:
        """Bridge to the legacy ImageEvidence list format used by the pipeline.

        Internally calls ``review()`` and maps the result back to the
        existing ``ImageEvidence`` record format so the pipeline needs no
        changes.
        """
        if not image_paths:
            return []

        review_input = VisionReviewInput(
            image_paths=image_paths,
            claim_object=parsed_claim.claim_object,
            claimed_part=parsed_claim.claimed_part,
            claimed_issue=parsed_claim.claimed_issue,
            is_multi_part=parsed_claim.is_multi_part,
        )
        result = self.review(review_input)

        # Convert per-image analyses back to the legacy ImageEvidence format
        evidence_list: list[ImageEvidence] = []
        for analysis in result.per_image:
            evidence_list.append(
                ImageEvidence(
                    image_id=analysis.image_id,
                    image_path=analysis.image_path,
                    readable=analysis.readable,
                    object_present=analysis.object_present,
                    visible_parts=analysis.visible_parts,
                    visible_issues=analysis.visible_issues,
                    risk_flags=analysis.quality_flags,
                    description=analysis.description,
                    confidence=analysis.confidence,
                )
            )
        return evidence_list

    # ------------------------------------------------------------------
    # Phase A: single image analysis
    # ------------------------------------------------------------------

    def _analyse_single_image(
        self,
        path: Path,
        claim_object: ClaimObject,
        claimed_part: ObjectPart,
        claimed_issue: IssueType,
    ) -> PerImageAnalysis:
        """Run preflight + optional VLM call for one image."""
        image_id = image_id_from_path(path)

        # --- Step 1: local preflight
        readable, image_bytes, preflight_flags, width, height, blur = _local_preflight(path)

        if not readable:
            logger.warning("Image %s not readable: %s", image_id, path)
            return PerImageAnalysis(
                image_id=image_id,
                image_path=path,
                file_exists=path.exists(),
                readable=False,
                quality_flags=[RiskFlag.MANUAL_REVIEW_REQUIRED],
                confidence=0.0,
            )

        # --- Step 2: cache lookup
        cache_key = _image_cache_key(image_bytes, claim_object, claimed_part, claimed_issue)
        if cache_key in self._cache:
            logger.debug("Cache hit for image %s key %s", image_id, cache_key[:12])
            cached = self._cache[cache_key]
            return _coerce_per_image(
                cached, image_id, path, preflight_flags, width, height, blur
            )

        # --- Step 3: VLM call (if model service available)
        if self._model_service is None:
            logger.info(
                "PREFLIGHT-ONLY: No model service configured for %s. "
                "Set MODEL_PROVIDER + API key to enable vision analysis.",
                image_id,
            )
            return self._preflight_only_result(
                image_id, path, preflight_flags, width, height, blur,
                claim_object, claimed_part, claimed_issue,
            )

        data = self._call_vlm(image_id, path, image_bytes, claim_object, claimed_part, claimed_issue)

        if data is None:
            logger.warning(
                "VLM returned None for %s — all provider tiers failed. "
                "Falling back to preflight-only result.",
                image_id,
            )
            return self._preflight_only_result(
                image_id, path,
                preflight_flags + [RiskFlag.MANUAL_REVIEW_REQUIRED],
                width, height, blur,
                claim_object, claimed_part, claimed_issue,
            )

        logger.info("VLM response received for %s: keys=%s",
                    image_id, list(data.keys()))

        self._cache[cache_key] = data
        return _coerce_per_image(data, image_id, path, preflight_flags, width, height, blur)

    def _call_vlm(
        self,
        image_id: str,
        path: Path,
        image_bytes: bytes,
        claim_object: ClaimObject,
        claimed_part: ObjectPart,
        claimed_issue: IssueType,
    ) -> dict[str, Any] | None:
        """Call the vision model, retry on API error OR JSON parse failure.

        Tries up to 2 attempts.  Each attempt calls ``inspect_image()`` which
        internally runs the 3-tier OpenRouter fallback chain (Qwen2.5-VL → Llama Vision → Pixtral Large)
        followed by Groq text fallback if all vision tiers fail.
        If the raw response is not valid JSON, the attempt is retried.
        Returns ``None`` when all attempts and all tiers have been exhausted.
        """
        prompt = VISION_EVIDENCE_USER.format(
            claim_object=claim_object,
            claimed_part=claimed_part,
            claimed_issue=claimed_issue,
            image_id=image_id,
            issue_type_values=_ISSUE_TYPES_STR,
            object_part_values=_PART_VALUES.get(claim_object, _ISSUE_TYPES_STR),
            risk_flag_values=_RISK_FLAGS_STR,
        )
        for attempt in range(2):
            try:
                raw = self._model_service.inspect_image(
                    system=VISION_EVIDENCE_SYSTEM,
                    prompt=prompt,
                    image_bytes=image_bytes,
                )
                if raw is None:
                    continue
                return _parse_vlm_json(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "VLM call attempt %d failed for %s: %s", attempt + 1, image_id, exc
                )
        return None

    @staticmethod
    def _preflight_only_result(
        image_id: str,
        path: Path,
        quality_flags: list[RiskFlag],
        width: int | None,
        height: int | None,
        blur_score: float | None,
        claim_object: ClaimObject,
        claimed_part: ObjectPart,
        claimed_issue: IssueType,
    ) -> PerImageAnalysis:
        """Conservative result when no VLM is available or VLM fails."""
        # Even without a VLM, we can note the file is readable
        return PerImageAnalysis(
            image_id=image_id,
            image_path=path,
            file_exists=True,
            readable=True,
            width=width,
            height=height,
            blur_score=blur_score,
            object_present=None,
            visible_parts=[],
            visible_issues=[],
            quality_flags=quality_flags,
            description="Image readable; visual content requires model inspection.",
            confidence=0.0,
            supports_claim=False,
        )


# ---------------------------------------------------------------------------
# Backward-compatible alias (legacy name used in ClaimReviewPipeline)
# ---------------------------------------------------------------------------

VisionEvidenceAgent = VisionReviewAgent
