"""ModelService — OpenRouter-first multi-tier vision provider.

Provider chain (in order):
  Tier 1: OpenRouter Qwen2.5-VL-72B        (primary)
  Tier 2: OpenRouter Llama-3.2-90B-Vision  (secondary)
  Tier 3: OpenRouter Pixtral-12B           (tertiary)
  Tier 4: Groq reasoning fallback          (text-only, conservative response)

Gemini has been removed from the production path.
All vision analysis runs through OpenRouter.

Fallback triggers (any tier → next tier):
  - HTTP 429 (rate limit)
  - HTTP 503 (unavailable)
  - ConnectionError / TimeoutError
  - RuntimeError from exhausted retries
  - Malformed JSON response
  - Empty response

Telemetry tracked per call:
  call_count, fallback_count, provider_used_last
"""

from __future__ import annotations

import logging
import time
from typing import Any

from config import Settings

logger = logging.getLogger(__name__)

# Substrings in exception messages that trigger fallback to next tier
_FALLBACK_TRIGGERS = (
    "429", "503", "timeout", "timed out", "exhausted",
    "quota", "rate", "unavailable", "connection",
)


def _should_fallback(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    return any(t in str(exc).lower() for t in _FALLBACK_TRIGGERS)


class ModelService:
    """OpenRouter-first vision provider with automatic tier fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._providers: list[Any] = []
        self._providers_init = False

        # Stats
        self.call_count: int = 0
        self.fallback_count: int = 0
        self.cache_hit_count: int = 0
        self.provider_used_last: str = "none"

    # ── Lazy provider initialisation ─────────────────────────────────────────

    def _init_providers(self) -> None:
        if self._providers_init:
            return

        from services.providers.openrouter_provider import OpenRouterProvider
        from services.providers.groq_provider import GroqProvider

        s = self.settings

        if s.openrouter_api_key:
            # Tier 1 — Qwen2.5-VL
            self._providers.append(OpenRouterProvider(
                api_key=s.openrouter_api_key,
                model=s.openrouter_model_primary,
                temperature=s.temperature,
                timeout=s.request_timeout_seconds,
                max_image_dimension=s.max_image_dimension,
            ))
            # Tier 2 — Llama Vision
            self._providers.append(OpenRouterProvider(
                api_key=s.openrouter_api_key,
                model=s.openrouter_model_secondary,
                temperature=s.temperature,
                timeout=s.request_timeout_seconds,
                max_image_dimension=s.max_image_dimension,
            ))
            # Tier 3 — Pixtral
            self._providers.append(OpenRouterProvider(
                api_key=s.openrouter_api_key,
                model=s.openrouter_model_tertiary,
                temperature=s.temperature,
                timeout=s.request_timeout_seconds,
                max_image_dimension=s.max_image_dimension,
            ))
            logger.info(
                "Vision provider chain: %s",
                " → ".join(p._model for p in self._providers),
            )

        if s.groq_api_key:
            # Tier 4 — Groq text fallback (conservative JSON)
            self._providers.append(GroqProvider(
                api_key=s.groq_api_key,
                model=s.groq_model,
                temperature=s.temperature,
                vision_capable=False,  # text-only conservative fallback
            ))
            logger.info("Groq text fallback registered (tier %d)", len(self._providers))

        self._providers_init = True

    @property
    def provider_name(self) -> str:
        self._init_providers()
        return self._providers[0].provider_name if self._providers else "none"

    @property
    def provider_chain_summary(self) -> str:
        self._init_providers()
        if not self._providers:
            return "No providers configured"
        return " → ".join(
            getattr(p, "_model", p.provider_name) for p in self._providers
        )

    # ── Main interface ────────────────────────────────────────────────────────

    def inspect_image(
        self,
        system: str,
        prompt: str,
        image_bytes: bytes,
    ) -> str | None:
        """Analyse one image through the provider chain.

        Returns the raw response string (JSON expected) or None if all tiers fail.
        """
        self._init_providers()
        self.call_count += 1

        if not self._providers:
            logger.error("No providers configured. Set OPENROUTER_API_KEY.")
            return None

        for tier_idx, provider in enumerate(self._providers, start=1):
            t0 = time.time()
            try:
                result = provider.analyze_image(system, prompt, image_bytes)
                latency_ms = round((time.time() - t0) * 1000)
                pname = getattr(provider, "_model", provider.provider_name)
                self.provider_used_last = pname
                logger.info(
                    "provider_used=%s tier=%d latency_ms=%d",
                    pname, tier_idx, latency_ms,
                )
                return result
            except Exception as exc:  # noqa: BLE001
                latency_ms = round((time.time() - t0) * 1000)
                pname = getattr(provider, "_model", provider.provider_name)
                logger.warning(
                    "Tier %d (%s) failed (latency_ms=%d): %s",
                    tier_idx, pname, latency_ms, str(exc)[:120],
                )
                if tier_idx < len(self._providers):
                    self.fallback_count += 1
                    logger.info(
                        "fallback_reason=%s → trying tier %d",
                        str(exc)[:80], tier_idx + 1,
                    )

        logger.error("All %d provider tier(s) exhausted. Returning None.", len(self._providers))
        return None

    def complete_text(self, system: str, prompt: str) -> str:
        """Text completion via Groq (if configured), else raises."""
        self._init_providers()
        from services.providers.groq_provider import GroqProvider
        for provider in self._providers:
            if isinstance(provider, GroqProvider):
                return provider.complete_text(system, prompt)
        raise NotImplementedError(
            "No text provider configured. Set GROQ_API_KEY for text completion."
        )

    # Legacy compatibility
    def inspect_images(self, prompt: str, image_paths: list[str]) -> dict[str, Any]:
        raise NotImplementedError("Use inspect_image() instead.")
