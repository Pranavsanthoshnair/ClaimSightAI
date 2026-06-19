"""End-to-end vision pipeline test with real Gemini call."""
import sys
sys.path.insert(0, "code")
from dotenv import load_dotenv
load_dotenv(".env")

from pathlib import Path
from config import Settings
from services.model_service import ModelService
from agents.vision_agent import VisionReviewAgent
from models.vision_review import VisionReviewInput
from models.enums import ClaimObject, ObjectPart, IssueType
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

repo = Path(".").resolve()
settings = Settings(repo_root=repo)
svc = ModelService(settings=settings)
agent = VisionReviewAgent(model_service=svc)

img = repo / "dataset/images/sample/case_001/img_1.jpg"
result = agent.review(VisionReviewInput(
    image_paths=[img],
    claim_object=ClaimObject.CAR,
    claimed_part=ObjectPart.REAR_BUMPER,
    claimed_issue=IssueType.DENT,
))

print("\n=== RESULT ===")
print(f"object_visible:      {result.object_visible}")
print(f"object_part_visible: {result.object_part_visible}")
print(f"issue_visible:       {result.issue_visible}")
print(f"issue_type:          {result.issue_type}")
print(f"object_part:         {result.object_part}")
print(f"severity:            {result.severity}")
print(f"confidence:          {result.confidence}")
print(f"supporting_ids:      {result.supporting_image_ids}")
print(f"quality_flags:       {[f.value for f in result.quality_flags]}")
print(f"reasoning:           {result.reasoning[:200]}")

assert result.object_visible, "FAIL: object not visible"
assert result.object_part_visible, "FAIL: part not visible"
assert result.confidence > 0, "FAIL: confidence is 0"
assert len(result.per_image[0].visible_parts) > 0, "FAIL: no visible parts"
print("\nAll assertions PASSED")
