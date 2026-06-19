"""OpenRouterProvider — vision via OpenRouter API.

Uses the standard OpenAI-compatible chat/completions endpoint at
https://openrouter.ai/api/v1/chat/completions.

Image is sent as a base64 data URL in the message content.
Supports any vision-capable model accessible on OpenRouter.

Provider chain (managed by ModelService):
    Tier 1 (Primary):   qwen/qwen2.5-vl-72b-instruct
    Tier 2 (Secondary): meta-llama/llama-3.2-11b-vision-instruct
    Tier 3 (Tertiary):  anthropic/claude-3-haiku

Robustness features:
    - max_tokens cap to avoid 402 credit errors on large models.
    - No response_format enforcement (not all models support json_object mode).
      JSON is extracted from the response text using a flexible extractor that
      handles raw JSON, markdown code fences, and partial wrapping.
    - 429 rate-limit handling: sleep + 1 retry before raising to trigger
      ModelService fallback to the next tier.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import time

import requests  # standard library available

from .base import BaseVisionProvider

logger = logging.getLogger(__name__)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "qwen/qwen2.5-vl-72b-instruct"
_MAX_DIM = 1536

# Models that support response_format: json_object natively via OpenRouter
_JSON_MODE_MODELS: frozenset[str] = frozenset({
    "qwen/qwen2.5-vl-72b-instruct",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/gpt-4-turbo",
})


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


def _extract_json(text: str) -> str:
    """Extract a JSON object from model output that may contain markdown fences.

    Handles:
    - Plain JSON: ``{"key": "value"}``
    - Markdown fenced: ` ```json\\n{...}\\n``` `
    - Mixed prose with JSON embedded: "Here is the result: {...}"

    Returns the raw JSON string (unparsed) so the caller can parse it.
    Raises ValueError if no JSON object is found.
    """
    text = text.strip()

    # 1. Try parsing as-is (fastest path for clean models)
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences: ```json ... ``` or ``` ... ```
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # 3. Find first { ... } block in the text
    start = text.find("{")
    if start != -1:
        # Walk to find matching closing brace
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"No valid JSON object found in model response: {text[:200]!r}")


class OpenRouterProvider(BaseVisionProvider):
    """Vision provider backed by the OpenRouter API.

    Parameters
    ----------
    key_pool : list[str]
        Up to 5 OpenRouter API keys tried in order on any 402/429.
        No sleep between attempts — instant rotation to the next key.
    model : str
        Model slug, e.g. ``"meta-llama/llama-3.2-11b-vision-instruct"``.
    temperature : float
        Sampling temperature; 0 for deterministic output.
    timeout : int
        Request timeout in seconds.
    max_image_dimension : int
        Longest side in pixels before resizing.
    max_tokens : int
        Output token cap — keeps cost low on large models (default 1024).
    """

    def __init__(
        self,
        key_pool: list[str],
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.0,
        timeout: int = 120,
        max_image_dimension: int = _MAX_DIM,
        max_tokens: int = 1024,
        # legacy compat — ignored, kept so old call sites don't crash
        api_key: str = "",
        backup_api_key: str = "",
        rate_limit_sleep: float = 0.0,
    ) -> None:
        # Accept both new key_pool and old api_key + backup_api_key call sites
        if key_pool:
            self._key_pool: list[str] = [k for k in key_pool if k]
        else:
            self._key_pool = [k for k in [api_key, backup_api_key] if k]
        if not self._key_pool:
            raise ValueError("OpenRouterProvider requires at least one API key")
        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._max_image_dimension = max_image_dimension
        self._max_tokens = max_tokens

    @property
    def provider_name(self) -> str:
        return "openrouter"

    def _call(self, payload: dict, base_headers: dict) -> str:
        """Try each key in the pool in order.

        On 402 (credit exhausted) or 429 (rate limited): move to the next key
        immediately — zero sleep. First key that returns HTTP 200 wins.
        If all keys fail, raises RuntimeError with the last error seen.
        """
        last_error = "no keys in pool"
        tried = 0

        for key in self._key_pool:
            tried += 1
            headers = {**base_headers, "Authorization": f"Bearer {key}"}
            try:
                resp = requests.post(
                    _OPENROUTER_BASE_URL,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                logger.warning("OpenRouter network error on key #%d: %s", tried, exc)
                continue

            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    last_error = f"no choices in response: {data}"
                    logger.warning("OpenRouter key #%d returned no choices", tried)
                    continue
                content = choices[0].get("message", {}).get("content", "")
                if not content:
                    last_error = f"empty content in response: {data}"
                    logger.warning("OpenRouter key #%d returned empty content", tried)
                    continue
                if tried > 1:
                    logger.info(
                        "OpenRouter key #%d succeeded for %s after %d failures",
                        tried, self._model, tried - 1,
                    )
                return content

            elif resp.status_code in (402, 429):
                reason = "credits exhausted" if resp.status_code == 402 else "rate limited"
                last_error = f"HTTP {resp.status_code} ({reason}): {resp.text[:120]}"
                logger.warning(
                    "OpenRouter key #%d %s on %s — trying next key instantly",
                    tried, reason, self._model,
                )
                continue  # no sleep — next key immediately

            else:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(
                    "OpenRouter key #%d returned %d on %s: %s",
                    tried, resp.status_code, self._model, resp.text[:100],
                )
                # Non-transient error (400, 404, 500 etc.) — skip remaining keys
                break

        raise RuntimeError(
            f"OpenRouter [{self._model}] — all {tried} key(s) failed. "
            f"Last error: {last_error}"
        )

    def analyze_image(self, system: str, prompt: str, image_bytes: bytes) -> str:
        """Send one image to OpenRouter and return a JSON string.

        Authorization is injected per-key inside _call().
        response_format is only added for models that support json_object mode.
        For all others, JSON extraction is performed on the raw text response.
        """
        resized  = _resize_image(image_bytes, self._max_image_dimension)
        mime     = _guess_mime(resized)
        b64      = _to_base64(resized)
        data_url = f"data:{mime};base64,{b64}"

        # Base headers — Authorization is set per-key inside _call()
        base_headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/multi-modal-evidence-review",
            "X-Title": "ClaimSight AI - Multi-Modal Evidence Review",
        }

        payload: dict = {
            "model": self._model,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        }

        # Only add response_format for models that support json_object natively
        if self._model in _JSON_MODE_MODELS:
            payload["response_format"] = {"type": "json_object"}

        logger.debug("OpenRouter: calling model=%s (pool size=%d)", self._model, len(self._key_pool))
        raw_content = self._call(payload, base_headers)

        # Extract JSON from the response (handles markdown fences, prose wrapping)
        try:
            json_str = _extract_json(raw_content)
        except ValueError as exc:
            raise RuntimeError(
                f"OpenRouter ({self._model}) returned non-JSON content: {exc}"
            ) from exc

        return json_str
