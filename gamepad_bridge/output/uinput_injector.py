"""Virtual keyboard via python-uinput; all injected keys are isTrusted=true."""
from __future__ import annotations

import time

import uinput

from gamepad_bridge.output.base import KeyInjector

# Declare every standard key so browsers see a full keyboard
_ALL_KEYS = [
    uinput.KEY_ESC, uinput.KEY_1, uinput.KEY_2, uinput.KEY_3, uinput.KEY_4,
    uinput.KEY_5, uinput.KEY_6, uinput.KEY_7, uinput.KEY_8, uinput.KEY_9,
    uinput.KEY_0, uinput.KEY_MINUS, uinput.KEY_EQUAL, uinput.KEY_BACKSPACE,
    uinput.KEY_TAB, uinput.KEY_Q, uinput.KEY_W, uinput.KEY_E, uinput.KEY_R,
    uinput.KEY_T, uinput.KEY_Y, uinput.KEY_U, uinput.KEY_I, uinput.KEY_O,
    uinput.KEY_P, uinput.KEY_LEFTBRACE, uinput.KEY_RIGHTBRACE, uinput.KEY_ENTER,
    uinput.KEY_LEFTCTRL, uinput.KEY_A, uinput.KEY_S, uinput.KEY_D, uinput.KEY_F,
    uinput.KEY_G, uinput.KEY_H, uinput.KEY_J, uinput.KEY_K, uinput.KEY_L,
    uinput.KEY_SEMICOLON, uinput.KEY_APOSTROPHE, uinput.KEY_GRAVE,
    uinput.KEY_LEFTSHIFT, uinput.KEY_BACKSLASH, uinput.KEY_Z, uinput.KEY_X,
    uinput.KEY_C, uinput.KEY_V, uinput.KEY_B, uinput.KEY_N, uinput.KEY_M,
    uinput.KEY_COMMA, uinput.KEY_DOT, uinput.KEY_SLASH, uinput.KEY_RIGHTSHIFT,
    uinput.KEY_KPASTERISK, uinput.KEY_LEFTALT, uinput.KEY_SPACE, uinput.KEY_CAPSLOCK,
    uinput.KEY_F1, uinput.KEY_F2, uinput.KEY_F3, uinput.KEY_F4, uinput.KEY_F5,
    uinput.KEY_F6, uinput.KEY_F7, uinput.KEY_F8, uinput.KEY_F9, uinput.KEY_F10,
    uinput.KEY_F11, uinput.KEY_F12,
    uinput.KEY_NUMLOCK, uinput.KEY_SCROLLLOCK,
    uinput.KEY_HOME, uinput.KEY_UP, uinput.KEY_PAGEUP,
    uinput.KEY_LEFT, uinput.KEY_RIGHT,
    uinput.KEY_END, uinput.KEY_DOWN, uinput.KEY_PAGEDOWN,
    uinput.KEY_INSERT, uinput.KEY_DELETE,
    uinput.KEY_RIGHTCTRL, uinput.KEY_RIGHTALT,
    uinput.KEY_PAUSE, uinput.KEY_SYSRQ,
    uinput.KEY_LEFTMETA, uinput.KEY_RIGHTMETA,
    uinput.KEY_MUTE, uinput.KEY_VOLUMEDOWN, uinput.KEY_VOLUMEUP,
    uinput.KEY_NEXTSONG, uinput.KEY_PLAYPAUSE, uinput.KEY_PREVIOUSSONG,
    uinput.KEY_STOPCD, uinput.KEY_RECORD, uinput.KEY_REWIND, uinput.KEY_FASTFORWARD,
]

# Minimum hold time in seconds so apps like YT TV register the keystroke
_MIN_HOLD_S = 0.025

# Map string key names to uinput constants
_KEY_NAME_MAP: dict[str, int] = {
    name: getattr(uinput, name)
    for name in dir(uinput)
    if name.startswith("KEY_")
}

# Aliases: evdev names that differ from python-uinput names
_ALIASES: dict[str, str] = {
    "KEY_RETURN":       "KEY_ENTER",
    "KEY_ESCAPE":       "KEY_ESC",
    "KEY_LEFTCONTROL":  "KEY_LEFTCTRL",
    "KEY_RIGHTCONTROL": "KEY_RIGHTCTRL",
    "KEY_MENU":         "KEY_COMPOSE",
    "KEY_PAGEUP":       "KEY_PAGEUP",
    "KEY_PAGEDOWN":     "KEY_PAGEDOWN",
}
for _alias, _target in _ALIASES.items():
    if _alias not in _KEY_NAME_MAP and _target in _KEY_NAME_MAP:
        _KEY_NAME_MAP[_alias] = _KEY_NAME_MAP[_target]


class UinputInjector(KeyInjector):
    def __init__(self) -> None:
        try:
            self._device = uinput.Device(_ALL_KEYS, name="gamepad-tv-bridge")
        except PermissionError as e:
            raise PermissionError(
                "Cannot open /dev/uinput. "
                "Add yourself to the input group: sudo usermod -aG input $USER"
            ) from e

    def _resolve(self, key_name: str) -> int | None:
        key = _KEY_NAME_MAP.get(key_name)
        if key is None:
            from rich.console import Console
            Console().print(f"[red]Unknown key: {key_name!r} — skipped[/red]")
        return key

    def press_key(self, key_name: str) -> None:
        key = self._resolve(key_name)
        if key is not None:
            self._device.emit(key, 1)

    def release_key(self, key_name: str) -> None:
        key = self._resolve(key_name)
        if key is not None:
            self._device.emit(key, 0)

    def tap_key(self, key_name: str) -> None:
        key = self._resolve(key_name)
        if key is not None:
            self._device.emit(key, 1)
            time.sleep(_MIN_HOLD_S)
            self._device.emit(key, 0)

    def tap_combo(self, key_names: list[str]) -> None:
        keys = [k for k in (self._resolve(n) for n in key_names) if k is not None]
        if not keys:
            return
        for k in keys:
            self._device.emit(k, 1)
        time.sleep(_MIN_HOLD_S)
        for k in reversed(keys):
            self._device.emit(k, 0)

    def close(self) -> None:
        try:
            self._device.__exit__(None, None, None)
        except Exception:
            pass
