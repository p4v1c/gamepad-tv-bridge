"""Linux evdev gamepad reader."""
from __future__ import annotations

import select
from typing import Iterator

import evdev

from gamepad_bridge.input.base import GamepadDevice, GamepadEvent, GamepadReader
from gamepad_bridge.input.mapping import (
    ABS_MAP,
    BTN_MAP,
    HAT_MAP,
    normalize_axis,
)


class EvdevReader(GamepadReader):
    def __init__(self, device: GamepadDevice) -> None:
        super().__init__(device)
        self._dev = evdev.InputDevice(device.path)
        # Pre-cache absinfo for all absolute axes
        caps = self._dev.capabilities(absinfo=True)
        self._abs_cache: dict[int, evdev.AbsInfo] = {}
        for item in caps.get(evdev.ecodes.EV_ABS, []):
            code, absinfo = item
            if isinstance(code, int) and absinfo is not None:
                self._abs_cache[code] = absinfo
        # Track current HAT state to synthesize press/release
        self._hat_state: dict[str, int] = {}

    def read_events(self) -> Iterator[GamepadEvent]:
        while True:
            r, _, _ = select.select([self._dev.fd], [], [], 0.05)
            if not r:
                return
            try:
                for ev in self._dev.read():
                    yield from self._process(ev)
            except OSError:
                return

    def _process(self, ev: evdev.InputEvent) -> Iterator[GamepadEvent]:
        if ev.type == evdev.ecodes.EV_KEY:
            name = BTN_MAP.get(ev.code)
            if name:
                yield GamepadEvent(
                    button=name,
                    value=float(ev.value),
                    raw_type=ev.type,
                    raw_code=ev.code,
                )

        elif ev.type == evdev.ecodes.EV_ABS:
            axis_name = ABS_MAP.get(ev.code)
            if axis_name is None:
                return

            if axis_name in HAT_MAP:
                # HAT axis: emit discrete DPAD press/release events
                hat_buttons = HAT_MAP[axis_name]
                prev = self._hat_state.get(axis_name, 0)
                curr = ev.value

                if prev != 0 and prev in hat_buttons:
                    # Release previous direction
                    yield GamepadEvent(
                        button=hat_buttons[prev],
                        value=0.0,
                        raw_type=ev.type,
                        raw_code=ev.code,
                    )

                self._hat_state[axis_name] = curr

                if curr != 0 and curr in hat_buttons:
                    # Press new direction
                    yield GamepadEvent(
                        button=hat_buttons[curr],
                        value=1.0,
                        raw_type=ev.type,
                        raw_code=ev.code,
                    )
            else:
                info = self._abs_cache.get(ev.code)
                if info is not None:
                    normalized = normalize_axis(ev.value, info)
                    yield GamepadEvent(
                        button=axis_name,
                        value=normalized,
                        raw_type=ev.type,
                        raw_code=ev.code,
                    )

    def close(self) -> None:
        try:
            self._dev.close()
        except OSError:
            pass
