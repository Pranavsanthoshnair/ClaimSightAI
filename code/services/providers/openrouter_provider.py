"""OpenRouterProvider — vision via OpenRouter API.

Uses the standard OpenAI-compatible chat/completions endpoint at
https://openrouter.ai/api/v1/chat/completions.

Image is sent as a base64 data URL in the message content.
Supports any vision-capable model accessible on OpenRouter.

Provider chain (managed by ModelService):
    Tier 1 (Primary):   qwen/qwen2.5-vl-72b-instruct
    Tier 2 (Secondary): meta-llama/llama-3.2-90b-vision-instruct
    Tier 3 (Tertiary):  mistralai/pixtral-large-2411
"""

from __future__ import annotations

import base64
import io
import logging

import requests  # standard library available

from .base import BaseVisionProvider

logger = logging.getLogger(__name__)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "qwen/qwen2.5-vl-72b-instruct"
_MAX_DIM = 1536


def _resize_image(image_bytes: bytes, max_dim: int = _MAX_DIM) -> bytes:
    """Resize image so the longest side ≤ max_dim. Returns original on failure."""
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


def _guess_mime(image_bytes: bytes) -> str:
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:4] == b"RIFF":
        return "image/webp"
    return "image/jpeg"


def _to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


class OpenRouterProvider(BaseVisionProvider):
    """Vision provider backed by the OpenRouter API.

    Parameters
    ----------
    api_key : str
        OpenRouter API key (Bearer token).
    model : str
        Model slug, e.g. ``"qwen/qwen2.5-vl-72b-instruct"``.
    temperature : float
        Sampling temperature; 0 for deterministic output.
    timeout : int
        Request timeout in seconds.
    max_image_dimension : int
        Longest side in pixels before resizing.
    """

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.0,
        timeout: int = 120,
        max_image_dimension: int = _MAX_DIM,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._max_image_dimension = max_image_dimension

    @property
    def provider_name(self) -> str:
        return "openrouter"

    def analyze_image(self, system: str, prompt: str, image_bytes: bytes) -> str:
        """Send one image to OpenRouter and return raw response text."""
        resized = _resize_image(image_bytes, self._max_image_dimension)
        mime = _guess_mime(resized)
        b64 = _to_base64(resized)
        data_url = f"data:{mime};base64,{b64}"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/multi-modal-evidence-review",
            "X-Title": "ClaimSight AI — Multi-Modal Evidence Review",
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
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
        }

        logger.debug("OpenRouter: calling model=%s", self._model)
        resp = requests.post(
            _OPENROUTER_BASE_URL,
            json=payload,
            headers=headers,
            timeout=self._timeout,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"OpenRouter returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"OpenRouter returned no choices: {data}")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise RuntimeError(f"OpenRouter returned empty content: {data}")

        return content
