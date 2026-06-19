"""End-to-end claim review pipeline."""

from __future__ import annotations

import logging
from pathlib import Path

from agents.claim_agent import ClaimExtractionAgent
from agents.vision_agent import VisionReviewAgent
from config import Settings
from models.claim_extraction import ClaimExtractionInput
from models.vision_review import VisionReviewInput
from services.cache_service import CacheService
from services.csv_service import CsvService
from services.decision_service import DecisionService
from services.evidence_standards_engine import EvidenceStandardsEngine
from services.history_service import UserHistoryService
from services.logging_service import LoggingService
from services.model_service import ModelService

logger = logging.getLogger(__name__)


class ClaimReviewPipeline:
    """Coordinates the batch claim review workflow."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.csv_service = CsvService()
        self.cache_service = CacheService(settings=settings)
        self.logging_service = LoggingService(settings=settings)
        self.history_service = UserHistoryService()
        self.evidence_engine = EvidenceStandardsEngine()
        self.claim_agent = ClaimExtractionAgent()
        # Wire the real vision model if configured
        model_svc = ModelService(settings=settings) if settings.has_vision_model else None
        if model_svc is not None:
            logger.info("VisionReviewAgent: using provider=%s model=%s",
                        settings.model_provider, settings.vision_model)
        else:
            logger.info("VisionReviewAgent: no model configured, running in preflight-only mode")
        self.vision_agent = VisionReviewAgent(model_service=model_svc)
        self.decision_service = DecisionService()

    def run(self, input_path: Path, output_path: Path) -> None:
        """Run the full pipeline and write output.csv."""
        resolved_input = self.settings.resolve_path(input_path)
        resolved_output = self.settings.resolve_path(output_path)
        self._load_reference_data()

        claims = self.csv_service.read_claims(resolved_input)
        logger.info("Processing %d claims from %s", len(claims), resolved_input)

        outputs = []
        for i, claim in enumerate(claims):
            logger.info("Claim %d/%d user=%s", i + 1, len(claims), claim.user_id)

            # Stage A: claim extraction
            extracted = self.claim_agent.extract(
                ClaimExtractionInput(
                    user_claim=claim.user_claim,
                    claim_object=claim.claim_object,
                )
            )

            # Stage B: vision review
            image_paths = [
                self._resolve_image_path(p)
                for p in claim.image_path_list
            ]
            vision_result = self.vision_agent.review(
                VisionReviewInput(
                    image_paths=image_paths,
                    claim_object=claim.claim_object,
                    claimed_part=extracted.claimed_object_part,
                    claimed_issue=extracted.claimed_issue_type,
                    is_multi_part=extracted.is_multi_part,
                )
            ) if image_paths else self._empty_vision_result(image_paths)

            # Stage C: evidence standards
            evidence_result = self.evidence_engine.evaluate_from_vision(
                vision_result=vision_result,
                claim_object=str(claim.claim_object),
                claimed_part=str(extracted.claimed_object_part),
                claimed_issue=str(extracted.claimed_issue_type),
                is_multi_part=extracted.is_multi_part,
            )

            # Stage D: decision
            from models.records import ParsedClaim
            parsed_claim = ParsedClaim(
                claim_object=claim.claim_object,
                claimed_issue=extracted.claimed_issue_type,
                claimed_part=extracted.claimed_object_part,
                is_multi_part=extracted.is_multi_part,
            )
            output = self.decision_service.decide(
                claim=claim,
                parsed_claim=parsed_claim,
                vision=vision_result,
                evidence=evidence_result,
                user_history=self.history_service.get(claim.user_id),
            )
            outputs.append(output)

            # Log per-claim event for observability
            self.logging_service.write_event("pipeline_events.jsonl", {
                "event": "claim_processed",
                "user_id": claim.user_id,
                "claim_index": i,
                "status": output.claim_status.value,
                "evidence_met": output.evidence_standard_met,
                "issue_type": output.issue_type.value,
                "object_part": output.object_part.value,
                "severity": output.severity.value,
                "risk_flags": output.risk_flags,
                "valid_image": output.valid_image,
                "supporting_count": len(vision_result.supporting_image_ids),
                "confidence": vision_result.confidence,
            })

        self.csv_service.write_outputs(resolved_output, outputs)
        logger.info("Wrote %d rows to %s", len(outputs), resolved_output)

    def _resolve_image_path(self, raw: str) -> Path:
        """Resolve an image path from the CSV, trying dataset/ prefix if needed."""
        direct = self.settings.resolve_path(Path(raw))
        if direct.exists():
            return direct
        # Try prepending dataset/ (CSV stores paths without the dataset prefix)
        with_dataset = self.settings.resolve_path(Path("dataset") / raw)
        if with_dataset.exists():
            return with_dataset
        return direct  # return original even if missing, preflight will flag it

    def _load_reference_data(self) -> None:
        self.history_service.load(
            self.settings.resolve_path(self.settings.user_history_csv)
        )
        self.evidence_engine.load(
            self.settings.resolve_path(self.settings.evidence_requirements_csv)
        )

    @staticmethod
    def _empty_vision_result(image_paths: list[Path]):  # type: ignore[return]
        from models.vision_review import VisionReviewResult
        from models.enums import RiskFlag
        return VisionReviewResult(
            valid_image=False,
            quality_flags=[RiskFlag.MANUAL_REVIEW_REQUIRED],
            reasoning="No image paths provided.",
        )
