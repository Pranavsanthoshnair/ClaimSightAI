"""Base protocols for pipeline agents."""

from __future__ import annotations

from typing import Protocol, TypeVar


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class Agent(Protocol[InputT, OutputT]):
    """Minimal callable agent protocol."""

    def run(self, payload: InputT) -> OutputT:
        """Process a payload and return a structured result."""
        ...
