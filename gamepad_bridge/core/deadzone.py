"""Stick deadzone filtering and direction quantization."""
from __future__ import annotations


def apply_deadzone(value: float, deadzone: float) -> float:
    """Return 0.0 if abs(value) < deadzone, else rescale to fill 0..1."""
    if abs(value) < deadzone:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    rescaled = (abs(value) - deadzone) / (1.0 - deadzone)
    return sign * rescaled


class StickToDpad:
    """
    Converts analog stick axis events to discrete DPAD events with debouncing.
    Tracks the last direction so it doesn't re-fire while still pushed.
    """

    # axis suffix → (negative_button, positive_button)
    _AXIS_DIRS = {
        "LSTICK_X": ("DPAD_LEFT",  "DPAD_RIGHT"),
        "LSTICK_Y": ("DPAD_UP",    "DPAD_DOWN"),
        "RSTICK_X": ("DPAD_LEFT",  "DPAD_RIGHT"),
        "RSTICK_Y": ("DPAD_UP",    "DPAD_DOWN"),
    }

    def __init__(self, threshold: float = 0.6) -> None:
        self._threshold = threshold
        # axis → currently active dpad button (or None)
        self._active: dict[str, str | None] = {}

    def process(self, axis: str, value: float) -> list[tuple[str, float]]:
        """
        Returns a list of (button_name, value) tuples to emit.
        value 1.0 = press, 0.0 = release.
        """
        dirs = self._AXIS_DIRS.get(axis)
        if dirs is None:
            return []

        neg_btn, pos_btn = dirs
        prev = self._active.get(axis)
        events: list[tuple[str, float]] = []

        if value < -self._threshold:
            new = neg_btn
        elif value > self._threshold:
            new = pos_btn
        else:
            new = None

        if new != prev:
            if prev is not None:
                events.append((prev, 0.0))
            if new is not None:
                events.append((new, 1.0))
            self._active[axis] = new

        return events
