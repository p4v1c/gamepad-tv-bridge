"""Poll _NET_ACTIVE_WINDOW every 250ms to detect the focused window."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from Xlib import X, display as xdisplay
from Xlib.error import XError


@dataclass
class ActiveWindow:
    title: str
    wm_class: str   # "instance.Class" joined
    pid: int


def _get_active_window(disp: xdisplay.Display) -> ActiveWindow | None:
    try:
        root = disp.screen().root
        atom = disp.intern_atom("_NET_ACTIVE_WINDOW")
        prop = root.get_full_property(atom, X.AnyPropertyType)
        if prop is None or not prop.value:
            return None

        win_id = prop.value[0]
        if win_id == 0:
            return None

        win = disp.create_resource_object("window", win_id)

        # Title
        net_name_atom = disp.intern_atom("_NET_WM_NAME")
        title_prop = win.get_full_property(net_name_atom, X.AnyPropertyType)
        if title_prop:
            title = title_prop.value
            if isinstance(title, bytes):
                title = title.decode("utf-8", errors="replace")
        else:
            title_prop2 = win.get_full_property(X.AnyPropertyType, X.AnyPropertyType)
            title = getattr(title_prop2, "value", "") or ""
            if isinstance(title, bytes):
                title = title.decode("utf-8", errors="replace")

        # WM_CLASS
        wm_class = win.get_wm_class() or ()
        wm_class_str = ".".join(wm_class) if wm_class else ""

        # PID
        pid_atom = disp.intern_atom("_NET_WM_PID")
        pid_prop = win.get_full_property(pid_atom, X.AnyPropertyType)
        pid = pid_prop.value[0] if pid_prop and pid_prop.value else 0

        return ActiveWindow(title=str(title), wm_class=wm_class_str, pid=pid)
    except (XError, AttributeError, TypeError):
        return None


class WindowWatcher:
    """Polls active window every 250ms and calls on_change when it changes."""

    def __init__(self, on_change: Callable[[ActiveWindow | None], None]) -> None:
        self._on_change = on_change
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="window-watcher")
        self._last: ActiveWindow | None = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            disp = xdisplay.Display()
        except Exception:
            return

        while not self._stop.wait(0.25):
            current = _get_active_window(disp)
            if self._changed(current):
                self._last = current
                self._on_change(current)

        disp.close()

    def _changed(self, current: ActiveWindow | None) -> bool:
        if current is None and self._last is None:
            return False
        if current is None or self._last is None:
            return True
        return (
            current.title != self._last.title
            or current.wm_class != self._last.wm_class
        )
