"""Application configuration — OpenRouter-first provider architecture.

Provider hierarchy
------------------
Tier 1 (Primary):   OpenRouter → Qwen2.5-VL-72B         (OPENROUTER_MODEL_PRIMARY)
Tier 2 (Secondary): OpenRouter → Llama-3.2-90B-Vision    (OPENROUTER_MODEL_SECONDARY)
Tier 3 (Tertiary):  OpenRouter → Mistral Pixtral-12B     (OPENROUTER_MODEL_TERTIARY)
Tier 4 (Fallback):  Groq       → text reasoning only     (GROQ_API_KEY)

Gemini is no longer part of the production path.
All vision analysis runs through OpenRouter.
Groq is used only when all OpenRouter providers fail (text-only fallback).

Environment variables
---------------------
OPENROUTER_API_KEY          Required for all vision analysis
OPENROUTER_MODEL_PRIMARY    Default: qwen/qwen2.5-vl-72b-instruct
OPENROUTER_MODEL_SECONDARY  Default: meta-llama/llama-3.2-90b-vision-instruct
OPENROUTER_MODEL_TERTIARY   Default: mistralai/pixtral-12b-2409
GROQ_API_KEY                Optional — Groq text fallback
GROQ_MODEL                  Default: llama-3.1-8b-instant
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


class Settings(BaseModel):
    """Runtime settings — all provider config from environment variables."""

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

    # ── OpenRouter (primary vision stack) ────────────────────────────────────
    openrouter_api_key: str = Field(
        default_factory=lambda: _env("OPENROUTER_API_KEY", "")
    )
    openrouter_model_primary: str = Field(
        default_factory=lambda: _env("OPENROUTER_MODEL_PRIMARY",
                                     "qwen/qwen2.5-vl-72b-instruct")
    )
    openrouter_model_secondary: str = Field(
        default_factory=lambda: _env("OPENROUTER_MODEL_SECONDARY",
                                     "meta-llama/llama-3.2-11b-vision-instruct")
    )
    openrouter_model_tertiary: str = Field(
        default_factory=lambda: _env("OPENROUTER_MODEL_TERTIARY",
                                     "anthropic/claude-3-haiku")
    )

    # ── Groq (text-only reasoning fallback) ──────────────────────────────────
    groq_api_key: str = Field(
        default_factory=lambda: _env("GROQ_API_KEY", "")
    )
    groq_model: str = Field(
        default_factory=lambda: _env("GROQ_MODEL", "llama-3.1-8b-instant")
    )

    # ── Shared model settings ─────────────────────────────────────────────────
    request_timeout_seconds: int = 120
    max_retries: int = 1          # fail fast → next tier
    temperature: float = 0.0
    max_image_dimension: int = 1536
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    def resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return self.repo_root / path

    @property
    def has_vision_model(self) -> bool:
        """True when at least one vision provider is configured."""
        return bool(self.openrouter_api_key)

    @property
    def provider_summary(self) -> str:
        """Human-readable provider chain summary."""
        if not self.openrouter_api_key:
            return "No providers configured (preflight-only mode)"
        parts = [
            f"T1:{self.openrouter_model_primary.split('/')[-1]}",
            f"T2:{self.openrouter_model_secondary.split('/')[-1]}",
            f"T3:{self.openrouter_model_tertiary.split('/')[-1]}",
        ]
        if self.groq_api_key:
            parts.append(f"T4:groq/{self.groq_model.split('-')[0]}")
        return " → ".join(parts)
