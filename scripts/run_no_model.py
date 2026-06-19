"""Quick no-model pipeline run to generate output.csv structure."""
import sys, os
from pathlib import Path

# Temporarily override MODEL_PROVIDER to none
os.environ["MODEL_PROVIDER"] = "none"

sys.path.insert(0, str(Path(__file__).parent / "code"))

from config import Settings
from pipelines.claim_review_pipeline import ClaimReviewPipeline

repo = Path(__file__).parent.resolve()
settings = Settings(repo_root=repo, cache_enabled=False)
print(f"Provider: {settings.model_provider}, has_vision: {settings.has_vision_model}")

pipeline = ClaimReviewPipeline(settings=settings)
pipeline.run(input_path=Path("dataset/claims.csv"), output_path=Path("output.csv"))

import pandas as pd
df = pd.read_csv(repo / "output.csv")
print(f"Written {len(df)} rows to output.csv")
print("Columns:", list(df.columns))
print("claim_status counts:", df["claim_status"].value_counts().to_dict())
