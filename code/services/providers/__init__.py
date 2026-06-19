"""Vision provider package.

Exports:
    BaseVisionProvider  — abstract base class
    OpenRouterProvider  — OpenRouter API (multi-model, 3-tier vision chain)
    GroqProvider        — Groq API (text reasoning fallback)

Provider hierarchy (managed by ModelService):
    Tier 1 (Primary):   OpenRouter → Qwen2.5-VL-72B
    Tier 2 (Secondary): OpenRouter → Llama-3.2-90B-Vision
    Tier 3 (Tertiary):  OpenRouter → Pixtral Large
    Tier 4 (Fallback):  Groq → text reasoning only (no image understanding)

Gemini has been fully removed from the production path.
All vision analysis runs through OpenRouter.
"""

from .base import BaseVisionProvider
from .openrouter_provider import OpenRouterProvider
from .groq_provider import GroqProvider

__all__ = ["BaseVisionProvider", "OpenRouterProvider", "GroqProvider"]
