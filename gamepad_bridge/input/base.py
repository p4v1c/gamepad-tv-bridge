from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


@dataclass
class GamepadDevice:
    path: str
    name: str
    vendor_id: int
    product_id: int

    def __str__(self) -> str:
        return f"{self.name} [{self.path}] (vid={self.vendor_id:04x} pid={self.product_id:04x})"


@dataclass
class GamepadEvent:
    """Normalized gamepad event."""
    button: str        # e.g. BUTTON_A, DPAD_UP, LSTICK_X
    value: float       # 1.0=pressed, 0.0=released, or -1.0..1.0 for axes
    raw_type: int = 0
    raw_code: int = 0


class GamepadReader(ABC):
    def __init__(self, device: GamepadDevice) -> None:
        self.device = device

    @abstractmethod
    def read_events(self) -> Iterator[GamepadEvent]:
        """Yield normalized events; blocks until one is available."""

    @abstractmethod
    def close(self) -> None:
        pass
