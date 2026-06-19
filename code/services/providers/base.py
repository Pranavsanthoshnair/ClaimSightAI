"""BaseVisionProvider — abstract base class for all vision model providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseVisionProvider(ABC):
    """Abstract base class for vision model providers.

    All providers must implement ``analyze_image`` and expose a
    ``provider_name`` property so the facade can log which backend
    was used on each call.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the provider (e.g. 'gemini', 'openrouter')."""
        ...

    @abstractmethod
    def analyze_image(self, system: str, prompt: str, image_bytes: bytes) -> str:
        """Send one image to the model and return the raw response text.

        Parameters
        ----------
        system : str
            System-level instruction.
        prompt : str
            User-level prompt (includes schema and claim context).
        image_bytes : bytes
            Raw image file bytes.

        Returns
        -------
        str
            Raw model response (JSON expected by the caller).
        """
        ...
