"""Auto-detect connected gamepads and watch for hotplug events."""
from __future__ import annotations

import os
import threading
import time
from typing import Callable

import evdev
from rich.console import Console

from gamepad_bridge.input.base import GamepadDevice

console = Console()

KNOWN_VENDORS = {
    0x054c,  # Sony (DualShock, DualSense)
    0x045e,  # Microsoft (Xbox)
    0x046d,  # Logitech
    0x2dc8,  # 8BitDo
    0x0079,  # Generic USB gamepad
}


def _is_gamepad(dev: evdev.InputDevice) -> bool:
    caps = dev.capabilities()
    has_abs = evdev.ecodes.EV_ABS in caps
    has_key = evdev.ecodes.EV_KEY in caps
    if not (has_abs and has_key):
        return False

    keys = caps.get(evdev.ecodes.EV_KEY, [])
    if evdev.ecodes.BTN_SOUTH in keys:
        return True

    try:
        info = dev.info
        return info.vendor in KNOWN_VENDORS
    except Exception:
        return False


def detect_gamepads() -> list[GamepadDevice]:
    devices = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            if _is_gamepad(dev):
                info = dev.info
                devices.append(GamepadDevice(
                    path=path,
                    name=dev.name,
                    vendor_id=info.vendor,
                    product_id=info.product,
                ))
                dev.close()
        except (PermissionError, OSError):
            continue
    return devices


class HotplugWatcher:
    """Watches /dev/input/ for new gamepad devices via inotify (watchdog)."""

    def __init__(
        self,
        on_connect: Callable[[GamepadDevice], None],
        on_disconnect: Callable[[str], None],
    ) -> None:
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._known: dict[str, GamepadDevice] = {
            d.path: d for d in detect_gamepads()
        }

    def start(self) -> None:
        self._thread = threading.Thread(target=self._watch, daemon=True, name="hotplug-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _watch(self) -> None:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        watcher = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                path = event.src_path
                if not os.path.basename(path).startswith("event"):
                    return
                for attempt in range(6):
                    try:
                        dev = evdev.InputDevice(path)
                        if _is_gamepad(dev):
                            info = dev.info
                            gd = GamepadDevice(
                                path=path,
                                name=dev.name,
                                vendor_id=info.vendor,
                                product_id=info.product,
                            )
                            dev.close()
                            watcher._known[path] = gd
                            watcher._on_connect(gd)
                        else:
                            dev.close()
                        return
                    except (PermissionError, OSError):
                        if attempt < 5:
                            time.sleep(0.3)

            def on_deleted(self, event):
                path = event.src_path
                if path in watcher._known:
                    del watcher._known[path]
                    watcher._on_disconnect(path)

        observer = Observer()
        observer.schedule(_Handler(), "/dev/input", recursive=False)
        observer.start()
        self._stop.wait()
        observer.stop()
        observer.join()
