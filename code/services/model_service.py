"""ModelService — provider-neutral facade with automatic 3-tier fallback.

Provider dispatch
-----------------
Tier 1 (Primary) : GeminiProvider  (if GEMINI_API_KEY is set)
Tier 2 (Fallback): OpenRouterProvider with qwen/qwen2.5-vl-72b-instruct
Tier 3 (Fallback): OpenRouterProvider with meta-llama/llama-3.2-90b-vision-instruct

Fallback triggers:
    429, 503, timeout, ConnectionError, RuntimeError (exhausted retries),
    JSON parse failure from the provider layer.

Legacy providers (openai, anthropic) are still supported unchanged for
backward compatibility.

All providers share the same call signature:
    inspect_image(system, prompt, image_bytes) -> str | None

The caller (VisionReviewAgent) is responsible for JSON parsing.
Returns None when ALL providers fail — pipeline continues
with a preflight-only result in that case.
"""

from __future__ import annotations

import base64
import io
import logging
import time
from typing import Any

from config import Settings

logger = logging.getLogger(__name__)

# Max dimension to resize images to before sending (cost + latency control)
_MAX_DIM = 1536


def _resize_image(image_bytes: bytes, max_dim: int = _MAX_DIM) -> bytes:
    """Resize image to max_dim on the longest side. Returns original on failure."""
    try:
        from PIL import Image  # type: ignore[import]
        try:
            _LANCZOS = Image.Resampling.LANCZOS
        except AttributeError:
            _LANCZOS = Image.LANCZOS  # type: ignore[attr-defined]
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if max(w, h) <= max_dim:
            return image_bytes
        scale = max_dim / max(w, h)
        new_size = (int(w * scale), int(h * scale))
        img = img.resize(new_size, _LANCZOS)
        buf = io.BytesIO()
        fmt = img.format or "JPEG"
        img.save(buf, format=fmt)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return image_bytes


def _to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _guess_mime(image_bytes: bytes) -> str:
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:4] == b"RIFF":
        return "image/webp"
    return "image/jpeg"  # safe fallback


class ModelService:
    """Provider-neutral model client facade with automatic 3-tier Gemini → OpenRouter fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._gemini_client: Any = None

        # Lazily-initialised provider instances
        self._primary_provider: Any | None = None
        self._fallback_providers: list[Any] = []   # ordered list: tier2, tier3
        self._providers_initialised = False

        # Stats tracking
        self.call_count: int = 0
        self.fallback_count: int = 0
        self.cache_hit_count: int = 0

    # ------------------------------------------------------------------
    # Provider initialisation
    # ------------------------------------------------------------------

    def _init_providers(self) -> None:
        """Lazily initialise primary and fallback providers (3-tier)."""
        if self._providers_initialised:
            return

        from services.providers.gemini_provider import GeminiProvider
        from services.providers.openrouter_provider import OpenRouterProvider

        if self.settings.gemini_api_key:
            self._primary_provider = GeminiProvider(
                api_key=self.settings.gemini_api_key,
                model_name=self.settings.vision_model or "gemini-2.5-flash",
                temperature=self.settings.temperature,
                max_retries=self.settings.max_retries,
                max_image_dimension=self.settings.max_image_dimension,
            )
            logger.debug("Tier 1 provider: GeminiProvider")

        if self.settings.openrouter_api_key:
            # Tier 2: qwen2.5-vl-72b (or env override)
            tier2_model = self.settings.openrouter_model_tier2
            tier2 = OpenRouterProvider(
                api_key=self.settings.openrouter_api_key,
                model=tier2_model,
                temperature=self.settings.temperature,
                timeout=self.settings.request_timeout_seconds,
                max_image_dimension=self.settings.max_image_dimension,
            )
            self._fallback_providers.append(tier2)
            logger.debug("Tier 2 provider: OpenRouterProvider (model=%s)", tier2_model)

            # Tier 3: llama-3.2-90b (or env override)
            tier3_model = self.settings.openrouter_model_tier3
            tier3 = OpenRouterProvider(
                api_key=self.settings.openrouter_api_key,
                model=tier3_model,
                temperature=self.settings.temperature,
                timeout=self.settings.request_timeout_seconds,
                max_image_dimension=self.settings.max_image_dimension,
            )
            self._fallback_providers.append(tier3)
            logger.debug("Tier 3 provider: OpenRouterProvider (model=%s)", tier3_model)

        self._providers_initialised = True

    @property
    def provider_name(self) -> str:
        """Return the name of the primary configured provider."""
        self._init_providers()
        if self._primary_provider is not None:
            return self._primary_provider.provider_name
        if self._fallback_providers:
            return self._fallback_providers[0].provider_name
        return self.settings.model_provider

    # ------------------------------------------------------------------
    # Main vision interface used by VisionReviewAgent
    # ------------------------------------------------------------------

    def inspect_image(
        self,
        system: str,
        prompt: str,
        image_bytes: bytes,
    ) -> str | None:
        """Analyse one image and return a raw string response (JSON expected).

        Tries the primary provider first; falls back to the secondary on
        transient errors.  Returns None when both fail.

        Parameters
        ----------
        system : str
            System-level instruction for the model.
        prompt : str
            User-level prompt (includes schema and claim context).
        image_bytes : bytes
            Raw image file bytes.

        Returns
        -------
        str | None
            Model response text, or None if all providers failed.
        """
        provider = self.settings.model_provider
        self.call_count += 1

        # Use new provider abstraction for gemini / none (with API keys set)
        if provider in ("gemini", "none"):
            self._init_providers()
            if self._primary_provider is not None or self._fallback_providers:
                return self._inspect_with_fallback(system, prompt, image_bytes)

        # Legacy paths
        if provider == "gemini":
            return self._gemini_inspect(system, prompt, image_bytes)
        if provider == "openai":
            return self._openai_inspect(system, prompt, image_bytes)
        if provider == "anthropic":
            return self._anthropic_inspect(system, prompt, image_bytes)

        raise NotImplementedError(
            f"No VLM configured (provider='{provider}'). "
            "Set MODEL_PROVIDER and the corresponding API key."
        )

    def _inspect_with_fallback(
        self,
        system: str,
        prompt: str,
        image_bytes: bytes,
    ) -> str | None:
        """Try primary (Tier 1 Gemini), then each fallback in order (Tier 2, Tier 3)."""
        t0 = time.time()

        # Tier 1: primary provider
        if self._primary_provider is not None:
            try:
                result = self._primary_provider.analyze_image(system, prompt, image_bytes)
                latency_ms = round((time.time() - t0) * 1000)
                logger.debug(
                    "provider_used=%s tier=1 latency_ms=%d",
                    self._primary_provider.provider_name, latency_ms,
                )
                return result
            except Exception as exc:  # noqa: BLE001
                fallback_reason = str(exc)[:120]
                latency_ms = round((time.time() - t0) * 1000)
                logger.warning(
                    "Tier 1 (%s) failed (latency_ms=%d): %s",
                    self._primary_provider.provider_name, latency_ms, fallback_reason,
                )
                logger.info(
                    "provider_used=%s fallback_reason=%s latency_ms=%d",
                    self._primary_provider.provider_name, fallback_reason, latency_ms,
                )

        # Tier 2+: iterate fallback providers in order
        for tier_idx, provider in enumerate(self._fallback_providers, start=2):
            t_tier = time.time()
            try:
                result = provider.analyze_image(system, prompt, image_bytes)
                self.fallback_count += 1
                latency_ms = round((time.time() - t_tier) * 1000)
                logger.info(
                    "Tier %d (%s) succeeded: provider_used=%s latency_ms=%d",
                    tier_idx, provider.provider_name, provider.provider_name, latency_ms,
                )
                return result
            except Exception as exc:  # noqa: BLE001
                latency_ms = round((time.time() - t_tier) * 1000)
                logger.error(
                    "Tier %d (%s) failed (latency_ms=%d): %s",
                    tier_idx, provider.provider_name, latency_ms, str(exc)[:120],
                )

        # All providers failed
        logger.error("All %d provider tier(s) failed. Returning None.", 1 + len(self._fallback_providers))
        return None

    # kept for legacy compatibility
    def inspect_images(self, prompt: str, image_paths: list[str]) -> dict[str, Any]:
        raise NotImplementedError("Use inspect_image() instead.")

    def complete_text(self, system: str, prompt: str) -> str:
        provider = self.settings.model_provider
        if provider == "gemini":
            return self._gemini_text(system, prompt)
        raise NotImplementedError(f"Text model not implemented for provider '{provider}'.")

    # ------------------------------------------------------------------
    # Gemini implementation — uses google-genai SDK (v2.x)
    # ------------------------------------------------------------------

    def _get_gemini_client(self) -> Any:
        if self._gemini_client is not None:
            return self._gemini_client
        try:
            from google import genai  # type: ignore[import]
            from google.genai import types  # type: ignore[import]  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "google-genai is required for Gemini. "
                "Run: pip install google-genai"
            ) from e
        client = genai.Client(api_key=self.settings.gemini_api_key)
        self._gemini_client = client
        return client

    def _gemini_inspect(self, system: str, prompt: str, image_bytes: bytes) -> str:
        from google import genai  # type: ignore[import]  # noqa: F401
        from google.genai import types  # type: ignore[import]

        client = self._get_gemini_client()
        model_name = self.settings.vision_model or "gemini-2.5-flash"
        resized = _resize_image(image_bytes, self.settings.max_image_dimension)
        mime = _guess_mime(resized)

        image_part = types.Part.from_bytes(data=resized, mime_type=mime)
        text_part = types.Part.from_text(text=prompt)

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.settings.temperature,
            response_mime_type="application/json",
        )

        import re as _re
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[image_part, text_part],
                    config=config,
                )
                return response.text
            except Exception as exc:  # noqa: BLE001
                exc_str = str(exc)
                logger.warning("Gemini attempt %d failed: %s", attempt + 1, exc_str[:120])
                if attempt < self.settings.max_retries:
                    retry_after = 12
                    m = _re.search(r"retry in (\d+)", exc_str)
                    if m:
                        retry_after = int(m.group(1)) + 2
                    elif "503" in exc_str:
                        retry_after = 5
                    logger.info("Waiting %ds before retry...", retry_after)
                    time.sleep(retry_after)
        raise RuntimeError("All Gemini retries exhausted.")

    def _gemini_text(self, system: str, prompt: str) -> str:
        from google import genai  # type: ignore[import]  # noqa: F401
        from google.genai import types  # type: ignore[import]

        client = self._get_gemini_client()
        model_name = self.settings.text_model or "gemini-2.5-flash"
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.settings.temperature,
            response_mime_type="application/json",
        )
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )
        return response.text

    # ------------------------------------------------------------------
    # OpenAI implementation
    # ------------------------------------------------------------------

    def _openai_inspect(self, system: str, prompt: str, image_bytes: bytes) -> str:
        try:
            from openai import OpenAI  # type: ignore[import]
        except ImportError as e:
            raise ImportError("openai package required. Run: pip install openai") from e

        client = OpenAI(api_key=self.settings.openai_api_key)
        resized = _resize_image(image_bytes, self.settings.max_image_dimension)
        mime = _guess_mime(resized)
        b64 = _to_base64(resized)
        model_name = self.settings.vision_model or "gpt-4o"

        response = client.chat.completions.create(
            model=model_name,
            temperature=self.settings.temperature,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Anthropic implementation
    # ------------------------------------------------------------------

    def _anthropic_inspect(self, system: str, prompt: str, image_bytes: bytes) -> str:
        try:
            import anthropic  # type: ignore[import]
        except ImportError as e:
            raise ImportError("anthropic package required. Run: pip install anthropic") from e

        client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        resized = _resize_image(image_bytes, self.settings.max_image_dimension)
        mime = _guess_mime(resized)
        b64 = _to_base64(resized)
        model_name = self.settings.vision_model or "claude-3-5-sonnet-20241022"

        response = client.messages.create(
            model=model_name,
            max_tokens=1024,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return response.content[0].text
