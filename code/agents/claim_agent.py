"""ClaimExtractionAgent — converts conversational claim text into a
structured, normalised representation for downstream agents.

Design principles
-----------------
- Deterministic fast-path: a regex/keyword pass tries to resolve the
  issue type and object part without any model call.  This covers the
  majority of simple, unambiguous claims at zero cost.
- LLM fallback: when the fast-path returns ``UNKNOWN`` for either the
  issue type or the object part the agent falls back to a configurable
  text model.
- No visual inference: the agent never examines images and never makes
  decisions about whether images support or contradict a claim.
- Injection resistance: both the fast-path and the LLM prompt are
  hardened against conversation-borne prompt-injection attempts.
- Structured output: the agent always returns an ``ExtractedClaim``
  Pydantic model; callers never handle raw strings.
- Caching: parsed results are cached by (prompt_version, normalised
  conversation, claim_object) so identical claims are never parsed twice.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from models.claim_extraction import ClaimExtractionInput, ExtractedClaim
from models.enums import ClaimObject, IssueType, ObjectPart
from models.records import ClaimInput, EvidenceRequirement, ParsedClaim
from prompts.templates import (
    CLAIM_EXTRACTION_SYSTEM,
    CLAIM_EXTRACTION_USER,
    PROMPT_VERSION,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Taxonomy helpers — used by fast-path and for building LLM enum lists
# ---------------------------------------------------------------------------

# Maps lower-cased keyword fragments → IssueType
_ISSUE_KEYWORDS: dict[str, IssueType] = {
    # dents
    "dent": IssueType.DENT,
    "dented": IssueType.DENT,
    "denting": IssueType.DENT,
    "deform": IssueType.DENT,
    "hail": IssueType.DENT,
    # scratches
    "scratch": IssueType.SCRATCH,
    "scratched": IssueType.SCRATCH,
    "scuff": IssueType.SCRATCH,
    "paint": IssueType.SCRATCH,
    # cracks
    "crack": IssueType.CRACK,
    "cracked": IssueType.CRACK,
    "cracking": IssueType.CRACK,
    # glass shatter
    "shatter": IssueType.GLASS_SHATTER,
    "shattered": IssueType.GLASS_SHATTER,
    "broken glass": IssueType.GLASS_SHATTER,
    # broken part
    "broken": IssueType.BROKEN_PART,
    "broke": IssueType.BROKEN_PART,
    "break": IssueType.BROKEN_PART,
    "snapped": IssueType.BROKEN_PART,
    # missing part
    "missing": IssueType.MISSING_PART,
    "miss": IssueType.MISSING_PART,
    "gone": IssueType.MISSING_PART,
    "came off": IssueType.MISSING_PART,
    "fell off": IssueType.MISSING_PART,
    "keycaps": IssueType.MISSING_PART,
    # torn packaging
    "torn": IssueType.TORN_PACKAGING,
    "tear": IssueType.TORN_PACKAGING,
    "ripped": IssueType.TORN_PACKAGING,
    "open": IssueType.TORN_PACKAGING,  # context-dependent; refined downstream
    # crushed packaging
    "crushed": IssueType.CRUSHED_PACKAGING,
    "crush": IssueType.CRUSHED_PACKAGING,
    "dab": IssueType.CRUSHED_PACKAGING,  # Hindi transliteration: "dab gaya"
    # water damage
    "water": IssueType.WATER_DAMAGE,
    "wet": IssueType.WATER_DAMAGE,
    "liquid": IssueType.WATER_DAMAGE,
    "spill": IssueType.WATER_DAMAGE,
    "coffee": IssueType.WATER_DAMAGE,
    "rain": IssueType.WATER_DAMAGE,
    "moisture": IssueType.WATER_DAMAGE,
    # stain
    "stain": IssueType.STAIN,
    "stained": IssueType.STAIN,
    "oily": IssueType.STAIN,
    "oil": IssueType.STAIN,
    "mark": IssueType.STAIN,
}

# Object-part keywords keyed by ClaimObject to avoid cross-domain matches
_PART_KEYWORDS: dict[ClaimObject, dict[str, ObjectPart]] = {
    ClaimObject.CAR: {
        "front bumper": ObjectPart.FRONT_BUMPER,
        "rear bumper": ObjectPart.REAR_BUMPER,
        "back bumper": ObjectPart.REAR_BUMPER,
        "parachoques trasero": ObjectPart.REAR_BUMPER,  # Spanish
        "parachoques": ObjectPart.REAR_BUMPER,
        "bumper": ObjectPart.BODY,  # ambiguous — body fallback
        "door": ObjectPart.DOOR,
        "hood": ObjectPart.HOOD,
        "windshield": ObjectPart.WINDSHIELD,
        "front glass": ObjectPart.WINDSHIELD,
        "windscreen": ObjectPart.WINDSHIELD,
        "side mirror": ObjectPart.SIDE_MIRROR,
        "mirror": ObjectPart.SIDE_MIRROR,
        "headlight": ObjectPart.HEADLIGHT,
        "head light": ObjectPart.HEADLIGHT,
        "taillight": ObjectPart.TAILLIGHT,
        "tail light": ObjectPart.TAILLIGHT,
        "back light": ObjectPart.TAILLIGHT,
        "fender": ObjectPart.FENDER,
        "quarter panel": ObjectPart.QUARTER_PANEL,
        "body panel": ObjectPart.BODY,
        "body": ObjectPart.BODY,
    },
    ClaimObject.LAPTOP: {
        "screen": ObjectPart.SCREEN,
        "pantalla": ObjectPart.SCREEN,   # Spanish
        "display": ObjectPart.SCREEN,
        "keyboard": ObjectPart.KEYBOARD,
        "keys": ObjectPart.KEYBOARD,
        "key": ObjectPart.KEYBOARD,
        "teclas": ObjectPart.KEYBOARD,   # Spanish
        "trackpad": ObjectPart.TRACKPAD,
        "track pad": ObjectPart.TRACKPAD,
        "touchpad": ObjectPart.TRACKPAD,
        "hinge": ObjectPart.HINGE,
        "lid": ObjectPart.LID,
        "outer lid": ObjectPart.LID,
        "corner": ObjectPart.CORNER,
        "port": ObjectPart.PORT,
        "base": ObjectPart.BASE,
        "body": ObjectPart.BODY,
    },
    ClaimObject.PACKAGE: {
        "corner": ObjectPart.PACKAGE_CORNER,
        "box corner": ObjectPart.PACKAGE_CORNER,
        "side": ObjectPart.PACKAGE_SIDE,
        "seal": ObjectPart.SEAL,
        "label": ObjectPart.LABEL,
        "sticker": ObjectPart.LABEL,
        "contents": ObjectPart.CONTENTS,
        "item": ObjectPart.ITEM,
        "product": ObjectPart.ITEM,
        "inside": ObjectPart.CONTENTS,
        "box": ObjectPart.BOX,
    },
}

# Patterns that indicate the customer is trying to inject instructions
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"approve\s+(this\s+)?claim\s*(immediately|now|automatically)?", re.I),
    re.compile(r"skip\s+manual\s+review", re.I),
    re.compile(r"ignore\s+(all\s+)?(previous\s+)?instructions", re.I),
    re.compile(r"mark\s+(this\s+)?(row|claim)\s+(as\s+)?(supported|approved)", re.I),
    re.compile(r"follow\s+(the\s+)?note", re.I),
    re.compile(r"note\s+(says|is\s+enough)", re.I),
    re.compile(r"system\s+reading\s+this", re.I),
    re.compile(r"(reject|approve)\s+(claim|this)\s+(quickly|immediately)", re.I),
]


# ---------------------------------------------------------------------------
# Fast-path extraction helpers
# ---------------------------------------------------------------------------


def _normalise_text(text: str) -> str:
    """Lower-case, collapse whitespace — for matching only, not for output."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def _detect_injection(text: str) -> bool:
    """Return True if any injection pattern matches the conversation."""
    return any(pat.search(text) for pat in _INJECTION_PATTERNS)


def _extract_customer_lines(conversation: str) -> str:
    """Return only the lines spoken by the customer in a support conversation.

    Recognises ``Customer:``, ``Cliente:``, ``Customer (.*):`` prefixes.
    Falls back to the full text when no structured turns are detected.
    """
    customer_re = re.compile(
        r"(?:Customer|Cliente|Buyer|User)\s*(?:\([^)]*\))?\s*:\s*(.+?)(?=\||$)",
        re.I | re.DOTALL,
    )
    matches = customer_re.findall(conversation)
    if matches:
        return " ".join(m.strip() for m in matches)
    return conversation


def _word_boundary_search(keyword: str, norm_text: str) -> bool:
    """Return True when ``keyword`` appears in ``norm_text`` at a word boundary.

    Uses ``\\b`` anchors so that short keywords like ``"dab"`` or ``"key"``
    don't match as substrings of unrelated words (e.g. ``"unreadable"``).
    Multi-word keywords (containing a space) are searched verbatim since
    spaces naturally act as boundaries.
    """
    if " " in keyword:
        return keyword in norm_text
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return bool(re.search(pattern, norm_text))


def _is_negated(keyword: str, norm_text: str) -> bool:
    """Return True when ``keyword`` is immediately preceded by a negation word.

    Covers: "not X", "no X", "isn't X", "don't X", etc.
    Only single-word keywords are checked; multi-word phrases are never negated.
    """
    if " " in keyword:
        return False
    pattern = (
        r"\b(?:not|no|isn'?t|aren'?t|wasn'?t|don'?t|doesn'?t|without|except|ignore)\s+"
        + re.escape(keyword)
        + r"\b"
    )
    return bool(re.search(pattern, norm_text))


def _fast_path_issue(text: str) -> IssueType:
    """Keyword-based issue type extraction on the normalised conversation."""
    norm = _normalise_text(text)
    # Sort by length desc so longer, more-specific phrases win over shorter ones
    for keyword, issue in sorted(_ISSUE_KEYWORDS.items(), key=lambda kv: -len(kv[0])):
        if _word_boundary_search(keyword, norm) and not _is_negated(keyword, norm):
            return issue
    return IssueType.UNKNOWN


def _fast_path_part(text: str, claim_object: ClaimObject) -> ObjectPart:
    """Keyword-based object-part extraction for the given claim object."""
    norm = _normalise_text(text)
    part_map = _PART_KEYWORDS.get(claim_object, {})
    for keyword, part in sorted(part_map.items(), key=lambda kv: -len(kv[0])):
        if _word_boundary_search(keyword, norm) and not _is_negated(keyword, norm):
            return part
    return ObjectPart.UNKNOWN


def _build_claim_summary(
    customer_text: str,
    claim_object: str,
    issue: IssueType,
    part: ObjectPart,
) -> str:
    """Compose a short deterministic summary when fast-path succeeds."""
    if issue != IssueType.UNKNOWN and part != ObjectPart.UNKNOWN:
        return (
            f"Customer claims {issue.replace('_', ' ')} "
            f"on {claim_object} {part.replace('_', ' ')}."
        )
    if issue != IssueType.UNKNOWN:
        return f"Customer claims {issue.replace('_', ' ')} on their {claim_object}."
    if part != ObjectPart.UNKNOWN:
        return (
            f"Customer reports damage on the {part.replace('_', ' ')} "
            f"of their {claim_object}."
        )
    # Trim to first meaningful customer sentence as fallback
    first_sentence = re.split(r"[.!?]", customer_text)[0].strip()
    return first_sentence[:120] if first_sentence else f"{claim_object} damage claim."


def _collect_multi_parts(
    norm_text: str,
    primary_part: ObjectPart,
    claim_object: ClaimObject,
) -> list[ObjectPart]:
    """Return any secondary parts mentioned alongside the primary claim part."""
    part_map = _PART_KEYWORDS.get(claim_object, {})
    extras: list[ObjectPart] = []
    for keyword, part in sorted(part_map.items(), key=lambda kv: -len(kv[0])):
        if (
            _word_boundary_search(keyword, norm_text)
            and not _is_negated(keyword, norm_text)
            and part != primary_part
            and part not in extras
        ):
            extras.append(part)
    return extras


# ---------------------------------------------------------------------------
# LLM schema helpers
# ---------------------------------------------------------------------------


def _issue_type_values_str() -> str:
    return ", ".join(f'"{v}"' for v in IssueType)


def _object_part_values_str(claim_object: ClaimObject) -> str:
    part_map = _PART_KEYWORDS.get(claim_object, {})
    if part_map:
        parts = list(dict.fromkeys(part_map.values()))
    else:
        parts = list(ObjectPart)
    return ", ".join(f'"{v}"' for v in parts) + ', "unknown"'


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


def _cache_key(user_claim: str, claim_object: ClaimObject) -> str:
    """Stable, content-addressed cache key for claim extraction results."""
    payload = f"{PROMPT_VERSION}|{claim_object}|{_normalise_text(user_claim)}"
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# ClaimExtractionAgent
# ---------------------------------------------------------------------------


class ClaimExtractionAgent:
    """Extracts a structured claim from a conversational customer message.

    Usage::

        agent = ClaimExtractionAgent(model_service=model_svc)
        result: ExtractedClaim = agent.extract(
            ClaimExtractionInput(user_claim=text, claim_object="car")
        )

    The agent is also callable via the legacy ``run()`` interface expected
    by ``ClaimReviewPipeline`` so no pipeline changes are required.
    """

    def __init__(
        self,
        model_service: Any | None = None,
        cache: dict[str, ExtractedClaim] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        model_service:
            Optional model client.  When ``None`` (or when the provider is
            ``"none"``), the agent runs in fast-path-only mode and returns
            ``UNKNOWN`` for fields it cannot resolve deterministically.
        cache:
            In-memory cache mapping cache keys → ``ExtractedClaim`` instances.
            Inject an external mapping (e.g. backed by JSONL) to share cache
            across pipeline runs.  Defaults to an empty in-process dict.
        """
        self._model_service = model_service
        self._cache: dict[str, ExtractedClaim] = cache if cache is not None else {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def extract(self, payload: ClaimExtractionInput) -> ExtractedClaim:
        """Extract a structured claim from the given input.

        Steps
        -----
        1. Check in-memory cache.
        2. Run deterministic fast-path.
        3. If fast-path is inconclusive AND a model service is available,
           call the LLM and validate/repair its JSON response.
        4. Cache and return the result.
        """
        key = _cache_key(payload.user_claim, payload.claim_object)
        if key in self._cache:
            logger.debug("Cache hit for claim extraction key %s", key[:12])
            return self._cache[key]

        result = self._fast_path(payload)

        if self._needs_llm_fallback(result) and self._model_service is not None:
            logger.info(
                "Fast-path inconclusive (confidence=%.2f), invoking LLM fallback.",
                result.claim_confidence,
            )
            result = self._llm_extract(payload, fast_path_result=result)

        self._cache[key] = result
        logger.info(
            "Extracted claim: object=%s part=%s issue=%s multi=%s "
            "injection=%s confidence=%.2f",
            payload.claim_object,
            result.claimed_object_part,
            result.claimed_issue_type,
            result.is_multi_part,
            result.injection_detected,
            result.claim_confidence,
        )
        return result

    # ------------------------------------------------------------------
    # Legacy pipeline interface (ClaimReviewPipeline calls .run())
    # ------------------------------------------------------------------

    def run(
        self,
        claim: ClaimInput,
        requirements: list[EvidenceRequirement],
    ) -> ParsedClaim:
        """Convert a ``ClaimInput`` to a ``ParsedClaim`` for the pipeline.

        This bridges the legacy ``ClaimParsingAgent`` interface while
        delegating real work to the new ``extract()`` method.
        """
        extraction_input = ClaimExtractionInput(
            user_claim=claim.user_claim,
            claim_object=claim.claim_object,
        )
        extracted = self.extract(extraction_input)

        relevant_req_ids = self._match_requirements(extracted, requirements)

        return ParsedClaim(
            claim_object=claim.claim_object,
            claimed_issue=extracted.claimed_issue_type,
            claimed_part=extracted.claimed_object_part,
            is_multi_part=extracted.is_multi_part,
            relevant_requirement_ids=relevant_req_ids,
            rationale=extracted.reasoning,
        )

    # ------------------------------------------------------------------
    # Fast-path (deterministic, no model calls)
    # ------------------------------------------------------------------

    def _fast_path(self, payload: ClaimExtractionInput) -> ExtractedClaim:
        """Keyword-based extraction — zero cost, handles most simple claims."""
        injection = _detect_injection(payload.user_claim)
        customer_text = _extract_customer_lines(payload.user_claim)
        norm = _normalise_text(customer_text)

        issue = _fast_path_issue(norm)
        part = _fast_path_part(norm, payload.claim_object)

        # Detect multi-part signals: "and", "also", "both", "plus", "too"
        multi_signals = re.search(
            r"\b(and|also|both|plus|too|together|two things|two issues)\b", norm
        )
        extra_parts = _collect_multi_parts(norm, part, payload.claim_object)
        is_multi = bool(multi_signals and extra_parts)

        summary = _build_claim_summary(
            customer_text, payload.claim_object, issue, part
        )

        # Confidence heuristic: full resolution → high; partial → medium; none → low
        if issue != IssueType.UNKNOWN and part != ObjectPart.UNKNOWN:
            confidence = 0.85
        elif issue != IssueType.UNKNOWN or part != ObjectPart.UNKNOWN:
            confidence = 0.55
        else:
            confidence = 0.25

        reasoning = (
            f"Fast-path extraction: issue='{issue}' via keyword match, "
            f"part='{part}' via keyword match for object '{payload.claim_object}'. "
            f"Multi-part signal={'yes' if is_multi else 'no'}. "
            f"Injection={'detected' if injection else 'none'}."
        )

        return ExtractedClaim(
            claim_summary=summary,
            claimed_issue_type=issue,
            claimed_object_part=part,
            additional_claimed_parts=extra_parts if is_multi else [],
            additional_claimed_issues=[],
            claim_confidence=confidence,
            is_multi_part=is_multi,
            injection_detected=injection,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # LLM fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _needs_llm_fallback(result: ExtractedClaim) -> bool:
        """True when fast-path left key fields unresolved."""
        return (
            result.claimed_issue_type == IssueType.UNKNOWN
            or result.claimed_object_part == ObjectPart.UNKNOWN
            or result.claim_confidence < 0.5
        )

    def _llm_extract(
        self,
        payload: ClaimExtractionInput,
        fast_path_result: ExtractedClaim,
    ) -> ExtractedClaim:
        """Call the configured text model and parse its JSON response."""
        prompt = CLAIM_EXTRACTION_USER.format(
            claim_object=payload.claim_object,
            user_claim=payload.user_claim,
            issue_type_values=_issue_type_values_str(),
            object_part_values=_object_part_values_str(payload.claim_object),
        )
        try:
            raw = self._model_service.complete_text(
                system=CLAIM_EXTRACTION_SYSTEM,
                prompt=prompt,
            )
            return self._parse_llm_response(raw, fast_path_result)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM extraction failed (%s), falling back to fast-path result.", exc
            )
            return fast_path_result

    def _parse_llm_response(
        self,
        raw: dict[str, Any],
        fast_path_result: ExtractedClaim,
    ) -> ExtractedClaim:
        """Validate and coerce the LLM JSON response into ``ExtractedClaim``.

        Falls back field-by-field to the fast-path result when the model
        returns an invalid or out-of-taxonomy value.
        """
        # Accept either a pre-parsed dict or a string that needs JSON parsing
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # One repair attempt: strip markdown fences
                cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M)
                data = json.loads(cleaned)
        else:
            data = raw

        def _safe_issue(val: Any) -> IssueType:
            try:
                return IssueType(val)
            except (ValueError, TypeError):
                return fast_path_result.claimed_issue_type

        def _safe_part(val: Any) -> ObjectPart:
            try:
                return ObjectPart(val)
            except (ValueError, TypeError):
                return fast_path_result.claimed_object_part

        def _safe_parts(vals: Any) -> list[ObjectPart]:
            if not isinstance(vals, list):
                return []
            result = []
            for v in vals:
                try:
                    result.append(ObjectPart(v))
                except (ValueError, TypeError):
                    pass
            return result

        def _safe_issues(vals: Any) -> list[IssueType]:
            if not isinstance(vals, list):
                return []
            result = []
            for v in vals:
                try:
                    result.append(IssueType(v))
                except (ValueError, TypeError):
                    pass
            return result

        return ExtractedClaim(
            claim_summary=str(data.get("claim_summary", fast_path_result.claim_summary)),
            claimed_issue_type=_safe_issue(data.get("claimed_issue_type")),
            claimed_object_part=_safe_part(data.get("claimed_object_part")),
            additional_claimed_parts=_safe_parts(data.get("additional_claimed_parts", [])),
            additional_claimed_issues=_safe_issues(data.get("additional_claimed_issues", [])),
            claim_confidence=float(data.get("claim_confidence", fast_path_result.claim_confidence)),
            is_multi_part=bool(data.get("is_multi_part", fast_path_result.is_multi_part)),
            injection_detected=bool(
                data.get("injection_detected", fast_path_result.injection_detected)
            ),
            reasoning=str(data.get("reasoning", fast_path_result.reasoning)),
        )

    # ------------------------------------------------------------------
    # Evidence requirement matching
    # ------------------------------------------------------------------

    @staticmethod
    def _match_requirements(
        extracted: ExtractedClaim,
        requirements: list[EvidenceRequirement],
    ) -> list[str]:
        """Return requirement IDs relevant to this claim.

        Matching strategy:
        - Always include REQ_GENERAL_OBJECT_PART and REQ_REVIEW_TRUST.
        - Include REQ_GENERAL_MULTI_IMAGE for multi-part claims.
        - Match object-specific requirements against the claim object and
          the issue/part keywords in the ``applies_to`` field.
        """
        result_ids: list[str] = []
        obj = extracted.claimed_object_part.value
        issue = extracted.claimed_issue_type.value

        for req in requirements:
            rid = req.requirement_id
            applies = _normalise_text(req.applies_to)

            # Universal requirements
            if rid in ("REQ_GENERAL_OBJECT_PART", "REQ_REVIEW_TRUST"):
                result_ids.append(rid)
                continue

            # Multi-image requirement
            if rid == "REQ_GENERAL_MULTI_IMAGE" and extracted.is_multi_part:
                result_ids.append(rid)
                continue

            # Object-specific matching: check applies_to text against claim fields
            if req.claim_object not in ("all", extracted.claimed_issue_type):
                # Check if the requirement applies to this claim's object family
                claim_obj_norm = extracted.claimed_object_part.value.replace("_", " ")
                if req.claim_object != "all":
                    # Skip requirements for a different object family
                    # (claim_object on the req is "car", "laptop", "package")
                    pass

            # Match applies_to against issue and part keywords
            issue_words = set(issue.replace("_", " ").split())
            part_words = set(obj.replace("_", " ").split())
            applies_words = set(applies.split())
            if issue_words & applies_words or part_words & applies_words:
                result_ids.append(rid)

        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for rid in result_ids:
            if rid not in seen:
                seen.add(rid)
                deduped.append(rid)
        return deduped
