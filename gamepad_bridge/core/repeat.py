"""Auto-repeat: fire action repeatedly while a button is held."""
from __future__ import annotations

import threading
from typing import Callable

from gamepad_bridge.profiles.schema import KeyAction


class AutoRepeat:
    def __init__(
        self,
        fire_action: Callable[[KeyAction, bool], None],
    ) -> None:
        self._fire_action = fire_action
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(
        self,
        action: KeyAction,
        delay_ms: int,
        rate_ms: int,
    ) -> None:
        with self._lock:
            self._cancel()
            self._stop_event = threading.Event()
            stop = self._stop_event

            def _run() -> None:
                if stop.wait(delay_ms / 1000.0):
                    return
                while not stop.is_set():
                    self._fire_action(action, True)
                    stop.wait(rate_ms / 1000.0)

            self._thread = threading.Thread(target=_run, daemon=True, name="auto-repeat")
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._cancel()

    def _cancel(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=0.1)
            self._thread = None
