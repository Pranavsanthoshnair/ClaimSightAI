"""Evidence requirement lookup service skeleton."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from models.enums import ClaimObject
from models.records import EvidenceRequirement


class EvidenceRequirementService:
    """Loads and filters minimum evidence requirements."""

    def __init__(self) -> None:
        self.requirements: list[EvidenceRequirement] = []

    def load(self, path: Path) -> None:
        """Load evidence requirements from CSV."""
        frame = pd.read_csv(path)
        self.requirements = [
            EvidenceRequirement.model_validate(record)
            for record in frame.to_dict(orient="records")
        ]

    def for_claim_object(self, claim_object: ClaimObject) -> list[EvidenceRequirement]:
        """Return requirements that apply to a claim object."""
        return [
            requirement
            for requirement in self.requirements
            if requirement.claim_object in {"all", claim_object.value}
        ]
