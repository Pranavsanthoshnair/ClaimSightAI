"""GeminiProvider — Google Gemini 2.5 Flash via google-genai SDK.

Free-tier constraints handled here:
- 12-second minimum inter-call delay (≤ 5 req/min).
- Respects "retry in Xs" hint from 429 responses.
- Exponential-backoff style retry on 429 / 503.
"""

from __future__ import annotations

import base64
import io
import logging
import re
import time
from typing import Any

from .base import BaseVisionProvider

logger = logging.getLogger(__name__)

_MAX_DIM = 1536
_FREE_TIER_DELAY = 12  # seconds between calls


def _resize_image(image_bytes: bytes, max_dim: int = _MAX_DIM) -> bytes:
    """Resize image so the longest side ≤ max_dim. Returns original on failure."""
    try:
        from PIL import Image  # type: ignore[import]
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if max(w, h) <= max_dim:
            return image_bytes
        scale = max_dim / max(w, h)
        new_size = (int(w * scale), int(h * scale))
        img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        fmt = img.format or "JPEG"
        img.save(buf, format=fmt)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return image_bytes


def _guess_mime(image_bytes: bytes) -> str:
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:4] == b"RIFF":
        return "image/webp"
    return "image/jpeg"


class GeminiProvider(BaseVisionProvider):
    """Vision provider backed by Google Gemini 2.5 Flash (google-genai SDK).

    Parameters
    ----------
    api_key : str
        Gemini API key.
    model_name : str
        Model name, default ``"gemini-2.5-flash"``.
    temperature : float
        Sampling temperature; 0 for deterministic output.
    max_retries : int
        Number of retry attempts on transient errors.
    max_image_dimension : int
        Longest side in pixels before resizing.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.5-flash",
        temperature: float = 0.0,
        max_retries: int = 2,
        max_image_dimension: int = _MAX_DIM,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._temperature = temperature
        self._max_retries = max_retries
        self._max_image_dimension = max_image_dimension
        self._client: Any = None
        self._last_call_time: float = 0.0

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google import genai  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-genai is required. Run: pip install google-genai"
            ) from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _throttle(self) -> None:
        """Enforce minimum delay between API calls for free-tier compliance."""
        elapsed = time.time() - self._last_call_time
        wait = _FREE_TIER_DELAY - elapsed
        if wait > 0:
            logger.debug("Gemini throttle: sleeping %.1fs for free-tier limit", wait)
            time.sleep(wait)

    def analyze_image(self, system: str, prompt: str, image_bytes: bytes) -> str:
        """Send one image to Gemini and return raw response text."""
        from google import genai  # type: ignore[import]  # noqa: F401
        from google.genai import types  # type: ignore[import]

        client = self._get_client()
        resized = _resize_image(image_bytes, self._max_image_dimension)
        mime = _guess_mime(resized)

        image_part = types.Part.from_bytes(data=resized, mime_type=mime)
        text_part = types.Part.from_text(text=prompt)

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._temperature,
            response_mime_type="application/json",
        )

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self._throttle()
            try:
                self._last_call_time = time.time()
                response = client.models.generate_content(
                    model=self._model_name,
                    contents=[image_part, text_part],
                    config=config,
                )
                return response.text
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                exc_str = str(exc)
                logger.warning(
                    "Gemini attempt %d/%d failed: %s",
                    attempt + 1, self._max_retries + 1, exc_str[:120],
                )
                # On 429 quota exhaustion, raise immediately so ModelService
                # can fall back to OpenRouter without wasting time retrying.
                if "429" in exc_str and "quota" in exc_str.lower():
                    raise RuntimeError(f"429 quota exhausted: {exc_str[:200]}") from exc

                if attempt < self._max_retries:
                    retry_after = _FREE_TIER_DELAY
                    m = re.search(r"retry in (\d+)", exc_str, re.IGNORECASE)
                    if m:
                        retry_after = int(m.group(1)) + 2
                    elif "503" in exc_str:
                        retry_after = 5
                    logger.info("Waiting %ds before retry...", retry_after)
                    time.sleep(retry_after)

        raise RuntimeError(
            f"Gemini: all {self._max_retries + 1} attempts exhausted. "
            f"Last error: {last_exc}"
        )
