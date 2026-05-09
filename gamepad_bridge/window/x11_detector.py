"""Detect active browser via Firefox profile (--profile flag) or xprop window scan."""
from __future__ import annotations

import os
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable


@dataclass
class ActiveWindow:
    title: str
    wm_class: str
    pid: int


def _get_firefox_profile() -> str | None:
    """Return the active Firefox --profile name from /proc, or None."""
    try:
        for pid in os.listdir('/proc'):
            if not pid.isdigit():
                continue
            try:
                with open(f'/proc/{pid}/cmdline', 'rb') as f:
                    args = f.read().decode('utf-8', errors='replace').split('\x00')
                if 'firefox' not in os.path.basename(args[0]):
                    continue
                for i, arg in enumerate(args):
                    if arg == '--profile' and i + 1 < len(args):
                        return os.path.basename(args[i + 1])
                    if arg.startswith('--profile='):
                        return os.path.basename(arg.split('=', 1)[1])
            except (PermissionError, FileNotFoundError):
                continue
    except Exception:
        pass
    return None


def _xprop_get(wid_hex: str, *props: str) -> dict[str, str]:
    """Run xprop on a window and return requested properties."""
    try:
        out = subprocess.check_output(
            ['xprop', '-id', wid_hex] + list(props),
            stderr=subprocess.DEVNULL,
            timeout=1,
        ).decode('utf-8', errors='replace')
        result = {}
        for line in out.splitlines():
            for prop in props:
                if line.startswith(prop):
                    result[prop] = line
        return result
    except Exception:
        return {}


def _get_all_window_ids() -> list[str]:
    """Return all window IDs from _NET_CLIENT_LIST via xprop."""
    try:
        out = subprocess.check_output(
            ['xprop', '-root', '_NET_CLIENT_LIST'],
            stderr=subprocess.DEVNULL,
            timeout=1,
        ).decode('utf-8', errors='replace')
        # "_NET_CLIENT_LIST(WINDOW): window id # 0x123, 0x456"
        ids = re.findall(r'0x[0-9a-fA-F]+', out)
        return ids
    except Exception:
        return []


def _scan_firefox_window() -> ActiveWindow | None:
    """Enumerate all X11 windows and return info for the Firefox one."""
    for wid in _get_all_window_ids():
        props = _xprop_get(wid, '_NET_WM_NAME', 'WM_CLASS')
        wm_class_line = props.get('WM_CLASS', '')
        if 'firefox' not in wm_class_line.lower() and 'Firefox' not in wm_class_line:
            continue
        # Found a Firefox window
        title_line = props.get('_NET_WM_NAME', '')
        # Extract value from: _NET_WM_NAME(UTF8_STRING) = "Some Title"
        m = re.search(r'"([^"]*)"', title_line)
        title = m.group(1) if m else ''
        return ActiveWindow(title=title, wm_class='firefox', pid=0)
    return None


def _detect_active() -> ActiveWindow | None:
    # Priority 1: named Firefox profile (most specific)
    profile = _get_firefox_profile()
    if profile:
        return ActiveWindow(title=profile, wm_class='firefox', pid=0)

    # Priority 2: scan X11 windows for Firefox + title
    return _scan_firefox_window()


class WindowWatcher:
    """Polls every 500ms via /proc + xprop — no dependency on _NET_ACTIVE_WINDOW."""

    def __init__(self, on_change: Callable[[ActiveWindow | None], None]) -> None:
        self._on_change = on_change
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="window-watcher")
        self._last_key: str = ''

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _key(self, w: ActiveWindow | None) -> str:
        if w is None:
            return ''
        return f'{w.title}|{w.wm_class}'

    def _run(self) -> None:
        # Emit immediately
        current = _detect_active()
        self._last_key = self._key(current)
        self._on_change(current)

        while not self._stop.wait(0.5):
            current = _detect_active()
            key = self._key(current)
            if key != self._last_key:
                self._last_key = key
                self._on_change(current)
