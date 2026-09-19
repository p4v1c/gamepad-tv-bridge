"""Detect the active browser via its Firefox profile (--profile) or an xprop scan.

"Active" here means *running and not frozen*, which is narrower than it used to
be and is the whole point. GameCore suspends an application by sending SIGSTOP
to its process group, and a stopped Firefox keeps everything this module used
to look at: it is still in /proc with its `--profile` argument, and its window
is still in `_NET_CLIENT_LIST`. So a YouTube or Twitch tile sent to the
background kept its profile active, and the daemon went on injecting KEY_UP,
KEY_DOWN and KEY_RETURN into whatever had the screen next — the GameCore
interface, which reads the pad itself. Every press counted twice.

A frozen app is not one a keystroke can reach, so it is not a match.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

# Every X11 failure below used to be swallowed silently, and that silence is
# what made the DISPLAY=:0 bug in the service unit undiagnosable: xprop failed
# on every call, _scan_firefox_window() returned None, the daemon dropped every
# event, and the only thing in the journal was a cheerful
# "Window: '(none)' → passthrough (no injection)". Warn once per distinct
# reason — this runs on a poll loop and must not fill the journal.
_warned: set[str] = set()


def _warn_once(key: str, message: str, *args) -> None:
    if key in _warned:
        return
    _warned.add(key)
    log.warning(message, *args)


#: Where the process table is read from. A module constant so the tests can
#: point it at a synthetic tree; nothing else ever changes it.
_PROC = '/proc'

#: /proc states that mean "this process cannot act on a keystroke".
#: `T` is SIGSTOP (how GameCore backgrounds a session), `t` is a tracing stop,
#: `Z` and `X` are a process on its way out.
_INERT_STATES = frozenset("TtZX")


def _proc_state(pid: str) -> str:
    """The scheduler state letter from /proc/<pid>/stat, or '' if unreadable.

    Parsed from the last ')' rather than by splitting on spaces: field 2 is the
    executable name in parentheses and may itself contain spaces and
    parentheses, so `line.split()[2]` is wrong for exactly the processes whose
    name is least predictable.
    """
    try:
        with open(f'{_PROC}/{pid}/stat', 'rb') as f:
            line = f.read().decode('utf-8', errors='replace')
    except (PermissionError, FileNotFoundError, ProcessLookupError):
        return ''
    end = line.rfind(')')
    if end == -1:
        return ''
    fields = line[end + 1:].split()
    return fields[0] if fields else ''


def _is_frozen(pid: str | int) -> bool:
    """True when the process is stopped or dying, so nothing can be typed into it.

    An unreadable state is NOT treated as frozen: a process we cannot inspect
    is more likely one we lack permission on than one that is suspended, and
    refusing to match there would break the daemon for a whole class of setups
    to fix a narrower bug than the one it causes.
    """
    return _proc_state(str(pid)) in _INERT_STATES


@dataclass
class ActiveWindow:
    title: str
    wm_class: str
    pid: int


def _get_firefox_profile() -> str | None:
    """Return the active Firefox --profile name from /proc, or None."""
    try:
        for pid in os.listdir(_PROC):
            if not pid.isdigit():
                continue
            try:
                with open(f'{_PROC}/{pid}/cmdline', 'rb') as f:
                    args = f.read().decode('utf-8', errors='replace').split('\x00')
                if 'firefox' not in os.path.basename(args[0]):
                    continue
                name = None
                for i, arg in enumerate(args):
                    if arg == '--profile' and i + 1 < len(args):
                        name = os.path.basename(args[i + 1])
                        break
                    if arg.startswith('--profile='):
                        name = os.path.basename(arg.split('=', 1)[1])
                        break
                if name is None:
                    continue
                # `continue`, not `return None`: a second kiosk may be running
                # while this one is suspended — YouTube frozen in the
                # background with Twitch on the screen is a normal state, and
                # the one still running is the one to match.
                if _is_frozen(pid):
                    continue
                return name
            except (PermissionError, FileNotFoundError):
                continue
    except Exception as e:
        _warn_once("proc-scan", "cannot scan %s for a Firefox profile: %s", _PROC, e)
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
    except FileNotFoundError:
        _warn_once("no-xprop", "xprop is not installed — window detection cannot work")
        return {}
    except Exception as e:
        _warn_once("xprop-window",
                   "xprop failed on window %s (DISPLAY=%r XAUTHORITY=%r): %s",
                   wid_hex, os.environ.get("DISPLAY"), os.environ.get("XAUTHORITY"), e)
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
    except FileNotFoundError:
        _warn_once("no-xprop", "xprop is not installed — window detection cannot work")
        return []
    except Exception as e:
        # The one that matters: cannot open the display. Without DISPLAY and a
        # matching XAUTHORITY, this fails on every poll and the daemon silently
        # passes every event through.
        _warn_once("xprop-root",
                   "cannot read the X11 window list (DISPLAY=%r XAUTHORITY=%r): %s — "
                   "the daemon will inject nothing. The session must export both; "
                   "see `systemctl --user import-environment DISPLAY XAUTHORITY`.",
                   os.environ.get("DISPLAY"), os.environ.get("XAUTHORITY"), e)
        return []


def _scan_firefox_window() -> ActiveWindow | None:
    """Enumerate all X11 windows and return info for the Firefox one."""
    for wid in _get_all_window_ids():
        props = _xprop_get(wid, '_NET_WM_NAME', 'WM_CLASS', '_NET_WM_PID')
        wm_class_line = props.get('WM_CLASS', '')
        if 'firefox' not in wm_class_line.lower() and 'Firefox' not in wm_class_line:
            continue
        # A suspended kiosk keeps its window mapped and listed, so this path
        # needs the same liveness check as the /proc one — see the module
        # docstring. The pid comes from the window rather than a second /proc
        # walk, and a window without one is matched as before.
        pid_m = re.search(r'=\s*(\d+)', props.get('_NET_WM_PID', ''))
        pid = int(pid_m.group(1)) if pid_m else 0
        if pid and _is_frozen(pid):
            continue
        # Found a Firefox window
        title_line = props.get('_NET_WM_NAME', '')
        # Extract value from: _NET_WM_NAME(UTF8_STRING) = "Some Title"
        m = re.search(r'"([^"]*)"', title_line)
        title = m.group(1) if m else ''
        return ActiveWindow(title=title, wm_class='firefox', pid=pid)
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
