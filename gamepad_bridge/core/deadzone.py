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
    Uses dominant-axis filtering: the first axis to cross the threshold locks
    out the perpendicular axis until it is released.
    """

    # axis → (negative_button, positive_button)
    _AXIS_DIRS = {
        "LSTICK_X": ("DPAD_LEFT",  "DPAD_RIGHT"),
        "LSTICK_Y": ("DPAD_UP",    "DPAD_DOWN"),
        "RSTICK_X": ("DPAD_LEFT",  "DPAD_RIGHT"),
        "RSTICK_Y": ("DPAD_UP",    "DPAD_DOWN"),
    }

    # axis → sibling axis on the same stick
    _SIBLING = {
        "LSTICK_X": "LSTICK_Y",
        "LSTICK_Y": "LSTICK_X",
        "RSTICK_X": "RSTICK_Y",
        "RSTICK_Y": "RSTICK_X",
    }

    def __init__(self, threshold: float = 0.6) -> None:
        self._threshold = threshold
        self._release_threshold = threshold * 0.65  # hysteresis: release at 65% of press threshold
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

        # Hysteresis: use a lower threshold to release than to press
        if prev == neg_btn:
            new = neg_btn if value < -self._release_threshold else None
        elif prev == pos_btn:
            new = pos_btn if value > self._release_threshold else None
        elif value < -self._threshold:
            new = neg_btn
        elif value > self._threshold:
            new = pos_btn
        else:
            new = None

        # Dominant-axis lock: if the sibling axis is already active and this
        # axis isn't, suppress new presses on this axis.
        sibling = self._SIBLING.get(axis)
        sibling_active = sibling is not None and self._active.get(sibling) is not None
        if sibling_active and prev is None and new is not None:
            return []

        if new != prev:
            if prev is not None:
                events.append((prev, 0.0))
            if new is not None:
                events.append((new, 1.0))
            self._active[axis] = new

        return events
