"""GroqProvider — Groq API for text reasoning / structured validation fallback.

Groq is used ONLY when all OpenRouter vision providers fail.
Groq is NOT used for image understanding — it is used for:
  - claim extraction reasoning
  - structured validation
  - audit review text generation

If a vision-capable Groq model becomes available, it can be enabled
by setting GROQ_MODEL to a vision-capable slug.
"""

from __future__ import annotations

import base64
import io
import logging

import requests

from .base import BaseVisionProvider

logger = logging.getLogger(__name__)

_GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL  = "llama-3.1-8b-instant"
_MAX_DIM = 1536


def _resize_image(image_bytes: bytes, max_dim: int = _MAX_DIM) -> bytes:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if max(w, h) <= max_dim:
            return image_bytes
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format=img.format or "JPEG")
        return buf.getvalue()
    except Exception:
        return image_bytes


def _guess_mime(image_bytes: bytes) -> str:
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"


def _to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


class GroqProvider(BaseVisionProvider):
    """Text-only reasoning provider via Groq API.

    When used as a vision fallback, it returns a conservative preflight-only
    JSON response rather than attempting image understanding.

    Parameters
    ----------
    api_key : str
        Groq API key.
    model : str
        Model slug, e.g. 'llama-3.1-8b-instant'.
    temperature : float
        Sampling temperature.
    timeout : int
        Request timeout in seconds.
    vision_capable : bool
        Set True only if the configured model supports image input.
        Default False — Groq is text-only by default.
    """

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.0,
        timeout: int = 30,
        vision_capable: bool = False,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._vision_capable = vision_capable

    @property
    def provider_name(self) -> str:
        return "groq"

    def analyze_image(self, system: str, prompt: str, image_bytes: bytes) -> str:
        """Groq vision fallback.

        If vision_capable=True, sends image as base64 (for future vision models).
        If vision_capable=False (default), returns a conservative structured
        response indicating image analysis requires a vision provider.
        """
        if not self._vision_capable:
            # Text-only mode: return a safe conservative JSON that signals
            # the VisionReviewAgent to treat this as preflight-only.
            logger.warning(
                "Groq provider called for image analysis but is not vision-capable. "
                "Returning conservative preflight response. "
                "All OpenRouter vision providers must have failed."
            )
            return (
                '{"readable":true,"object_present":null,'
                '"visible_parts":[],"visible_issues":[],'
                '"quality_flags":["manual_review_required"],'
                '"description":"Image analysis unavailable - all vision providers failed. Manual review required.",'
                '"confidence":0.0,"severity":"unknown","supports_claim":false,'
                '"step1_observations":"All vision providers exhausted. This response is a safe fallback."}'
            )

        # Vision-capable path (e.g. future Groq vision model)
        resized = _resize_image(image_bytes)
        mime = _guess_mime(resized)
        b64 = _to_base64(resized)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
        }

        logger.debug("Groq vision call: model=%s", self._model)
        resp = requests.post(_GROQ_BASE_URL, json=payload, headers=headers,
                             timeout=self._timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Groq returned HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"Groq returned no choices: {data}")
        return choices[0].get("message", {}).get("content", "")

    def complete_text(self, system: str, prompt: str) -> str:
        """Call Groq for text completion (claim extraction, reasoning)."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        resp = requests.post(_GROQ_BASE_URL, json=payload, headers=headers,
                             timeout=self._timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Groq text completion failed: {resp.status_code} {resp.text[:200]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]
