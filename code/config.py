"""Application configuration for the evidence review system.

Model provider is read from environment variables so no secrets are hardcoded.

Supported providers
-------------------
- ``none``       : preflight-only mode; no model calls made.
- ``gemini``     : Google Gemini via google-genai SDK.
                   Requires env var ``GEMINI_API_KEY``.
- ``openai``     : OpenAI GPT-4o-vision.
                   Requires env var ``OPENAI_API_KEY``.
- ``anthropic``  : Anthropic Claude vision.
                   Requires env var ``ANTHROPIC_API_KEY``.
- ``custom``     : Any provider that exposes the same inspect_image interface.

Fallback chain
--------------
When ``MODEL_PROVIDER=gemini`` (or auto-detected), GeminiProvider is tried
first.  If it raises 429/503/timeout/RuntimeError, OpenRouterProvider is used
as the fallback (if ``OPENROUTER_API_KEY`` is set).  If both fail, the
pipeline continues with a preflight-only result (None returned from
inspect_image).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


class Settings(BaseModel):
    """Runtime settings loaded from environment variables and defaults."""

    repo_root: Path = Field(default_factory=lambda: Path.cwd())
    dataset_dir: Path = Path("dataset")
    claims_csv: Path = Path("dataset/claims.csv")
    sample_claims_csv: Path = Path("dataset/sample_claims.csv")
    user_history_csv: Path = Path("dataset/user_history.csv")
    evidence_requirements_csv: Path = Path("dataset/evidence_requirements.csv")
    output_csv: Path = Path("output.csv")

    cache_dir: Path = Path("code/.cache")
    logs_dir: Path = Path("code/logs")
    outputs_dir: Path = Path("code/outputs")

    cache_enabled: bool = True
    prompt_version: str = "v4"
    decision_version: str = "v1"
    schema_version: str = "v1"

    # ----------------------------------------------------------------
    # Model configuration — read from env by default
    # ----------------------------------------------------------------
    model_provider: Literal["none", "gemini", "openai", "anthropic", "custom"] = Field(
        default_factory=lambda: _env("MODEL_PROVIDER", "none")  # type: ignore[return-value]
    )
    vision_model: str = Field(
        default_factory=lambda: _env("VISION_MODEL", "gemini-2.5-flash")
    )
    text_model: str = Field(
        default_factory=lambda: _env("TEXT_MODEL", "gemini-2.5-flash")
    )
    gemini_api_key: str = Field(
        default_factory=lambda: _env("GEMINI_API_KEY", "")
    )
    openai_api_key: str = Field(
        default_factory=lambda: _env("OPENAI_API_KEY", "")
    )
    anthropic_api_key: str = Field(
        default_factory=lambda: _env("ANTHROPIC_API_KEY", "")
    )

    # ----------------------------------------------------------------
    # OpenRouter fallback configuration (3-tier)
    # ----------------------------------------------------------------
    openrouter_api_key: str = Field(
        default_factory=lambda: _env("OPENROUTER_API_KEY", "")
    )
    openrouter_model: str = Field(
        default_factory=lambda: _env("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    )
    openrouter_model_tier2: str = Field(
        default_factory=lambda: _env("OPENROUTER_MODEL_TIER2", "qwen/qwen2.5-vl-72b-instruct")
    )
    openrouter_model_tier3: str = Field(
        default_factory=lambda: _env("OPENROUTER_MODEL_TIER3", "meta-llama/llama-3.2-90b-vision-instruct")
    )

    request_timeout_seconds: int = 120
    max_retries: int = 2
    temperature: float = 0.0

    max_image_dimension: int = 1536
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    def resolve_path(self, path: Path) -> Path:
        """Resolve a path relative to the repository root."""
        if path.is_absolute():
            return path
        return self.repo_root / path

    @property
    def has_vision_model(self) -> bool:
        """True when a real vision model is configured (primary OR fallback)."""
        if self.model_provider == "none":
            # Still true if at least one API key is present
            if self.gemini_api_key or self.openrouter_api_key:
                return True
            return False
        if self.model_provider == "gemini":
            # Primary is Gemini; fallback is OpenRouter
            return bool(self.gemini_api_key or self.openrouter_api_key)
        if self.model_provider == "openai" and not self.openai_api_key:
            return False
        if self.model_provider == "anthropic" and not self.anthropic_api_key:
            return False
        return True
