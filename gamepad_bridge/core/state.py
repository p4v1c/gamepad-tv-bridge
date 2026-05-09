"""Per-button state machine: IDLE → PRESSED → HELD/RELEASED."""
from __future__ import annotations

import threading
import time
from enum import Enum, auto
from typing import Callable

from gamepad_bridge.profiles.schema import Binding, KeyAction


class _State(Enum):
    IDLE = auto()
    PRESSED = auto()
    HELD = auto()


class ButtonStateMachine:
    """
    Manages press/release/hold lifecycle for a single button.
    Calls fire_action(action, is_repeat) at the right moment.
    """

    def __init__(
        self,
        button: str,
        long_press_ms: int,
        fire_action: Callable[[KeyAction, bool], None],
    ) -> None:
        self.button = button
        self._long_press_s = long_press_ms / 1000.0
        self._fire_action = fire_action
        self._state = _State.IDLE
        self._press_time: float = 0.0
        self._long_press_timer: threading.Timer | None = None
        self._binding: Binding | None = None
        self._lock = threading.Lock()

    def on_press(self, binding: Binding | None) -> None:
        with self._lock:
            if self._state != _State.IDLE:
                return
            self._binding = binding
            self._state = _State.PRESSED
            self._press_time = time.monotonic()
            self._long_press_timer = threading.Timer(
                self._long_press_s, self._on_long_press
            )
            self._long_press_timer.daemon = True
            self._long_press_timer.start()

    def on_release(self) -> None:
        with self._lock:
            if self._state == _State.IDLE:
                return
            if self._long_press_timer is not None:
                self._long_press_timer.cancel()
                self._long_press_timer = None

            was_held = self._state == _State.HELD
            self._state = _State.IDLE
            binding = self._binding
            self._binding = None

        if binding is None:
            return

        if was_held:
            action = binding.long_press or binding.short_press
        else:
            action = binding.short_press

        if action is not None:
            self._fire_action(action, False)

    def _on_long_press(self) -> None:
        with self._lock:
            if self._state != _State.PRESSED:
                return
            self._state = _State.HELD

    @property
    def is_held(self) -> bool:
        return self._state == _State.HELD

    @property
    def binding(self) -> Binding | None:
        return self._binding
