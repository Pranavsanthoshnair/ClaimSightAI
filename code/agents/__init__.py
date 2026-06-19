"""Agent abstractions for claim extraction and visual evidence extraction."""

from agents.claim_agent import ClaimExtractionAgent
from agents.vision_agent import VisionEvidenceAgent, VisionReviewAgent

# Backward-compatible alias so any code still referencing the old name keeps working
ClaimParsingAgent = ClaimExtractionAgent

__all__ = [
    "ClaimExtractionAgent",
    "ClaimParsingAgent",
    "VisionEvidenceAgent",
    "VisionReviewAgent",
]
