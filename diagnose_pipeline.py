"""Check exactly what Settings sees when imported AFTER secrets injection."""
import sys, os
sys.path.insert(0, "code")

# Simulate what Streamlit Cloud does: secrets arrive as env vars
os.environ["MODEL_PROVIDER"] = "gemini"
os.environ["GEMINI_API_KEY"] = "test_key"

from config import Settings
s = Settings()
print("model_provider:", s.model_provider)
print("has_vision_model:", s.has_vision_model)
print("gemini_api_key set:", bool(s.gemini_api_key))

# Now check what ClaimReviewPipeline does with it
from pipelines.claim_review_pipeline import ClaimReviewPipeline
p = ClaimReviewPipeline(settings=s)
print("vision_agent model_service:", p.vision_agent._model_service)
print("model_service is None:", p.vision_agent._model_service is None)
