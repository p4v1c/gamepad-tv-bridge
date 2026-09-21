"""A kiosk sent to the background must stop being the active profile.

GameCore suspends an application with SIGSTOP to its process group. Everything
this daemon used to look at survives that: the process is still in /proc with
its `--profile` argument, and its window is still in `_NET_CLIENT_LIST`. So a
YouTube or Twitch tile put in the background stayed "active", the daemon went
on injecting KEY_UP/KEY_DOWN/KEY_RETURN, and the GameCore interface — which
reads the pad itself — counted every press twice.

The first test is the one that matters: it stops a real process and asks the
real kernel, because the whole fix rests on how /proc spells "stopped".

Run:  python -m pytest tests/
Or:   python tests/test_suspended_kiosk.py
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gamepad_bridge.window import x11_detector
from gamepad_bridge.window.x11_detector import _is_frozen, _proc_state


def _wait_for_state(pid: int, wanted: str, timeout: float = 2.0) -> str:
    """Poll until the state letter is `wanted`, or give up and return the last.

    A signal is delivered asynchronously: without this the test races the
    scheduler and fails on a loaded box rather than on a broken change.
    """
    deadline = time.time() + timeout
    state = ''
    while time.time() < deadline:
        state = _proc_state(str(pid))
        if state == wanted:
            return state
        time.sleep(0.02)
    return state


def test_real_kernel_reports_a_sigstopped_process_as_frozen():
    proc = subprocess.Popen(['sleep', '30'])
    try:
        assert _wait_for_state(proc.pid, 'S') == 'S'
        assert not _is_frozen(proc.pid)

        os.kill(proc.pid, signal.SIGSTOP)
        assert _wait_for_state(proc.pid, 'T') == 'T'
        assert _is_frozen(proc.pid), "SIGSTOP must read as frozen"

        os.kill(proc.pid, signal.SIGCONT)
        assert _wait_for_state(proc.pid, 'S') == 'S'
        assert not _is_frozen(proc.pid), "SIGCONT must undo it"
    finally:
        try:
            os.kill(proc.pid, signal.SIGCONT)
        except ProcessLookupError:
            pass
        proc.kill()
        proc.wait()


def test_a_name_with_spaces_and_parens_does_not_shift_the_state_field():
    """`comm` is free-form, and splitting on spaces reads the wrong field.

    Not a curiosity: the state letter is what decides whether the daemon types
    into a frozen window, and a browser whose name contains a bracket would
    have silently re-created the bug.
    """
    stat = "42 (fire fox (tv)) T 1 42 42 0 -1 4194560 1234 0 0 0"
    assert stat.split()[2] != 'T'  # the naive parse everyone writes first
    assert _proc_state_from(stat) == 'T'


def _proc_state_from(line: str) -> str:
    """Run the module's parse over a literal stat line, via a fake /proc."""
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(f'{root}/42')
        Path(f'{root}/42/stat').write_text(line)
        old, x11_detector._PROC = x11_detector._PROC, root
        try:
            return _proc_state('42')
        finally:
            x11_detector._PROC = old


# ── the /proc walk, over a synthetic process table ────────────────────────────

def _fake_proc(root: str, entries: dict[int, tuple[list[str], str]]) -> None:
    """Write a process table: {pid: (argv, state letter)}."""
    for pid, (argv, state) in entries.items():
        os.makedirs(f'{root}/{pid}', exist_ok=True)
        Path(f'{root}/{pid}/cmdline').write_bytes(
            b'\x00'.join(a.encode() for a in argv) + b'\x00')
        Path(f'{root}/{pid}/stat').write_text(f'{pid} (firefox) {state} 1 {pid} {pid} 0 -1')


def _profile_with(entries: dict[int, tuple[list[str], str]]) -> str | None:
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        _fake_proc(root, entries)
        old, x11_detector._PROC = x11_detector._PROC, root
        try:
            return x11_detector._get_firefox_profile()
        finally:
            x11_detector._PROC = old


YOUTUBE = ['/usr/lib/firefox/firefox', '--profile',
           '/home/p/.mozilla/firefox/youtube-tv', '--kiosk', 'https://www.youtube.com/tv']
TWITCH = ['/usr/lib/firefox/firefox', '--profile',
          '/home/p/.mozilla/firefox/twitch-tv', '--kiosk', 'https://localhost:8097/']


def test_a_running_kiosk_is_still_matched():
    assert _profile_with({100: (YOUTUBE, 'S')}) == 'youtube-tv'


def test_a_suspended_kiosk_is_not_matched():
    """The bug, stated directly: YouTube in the background, pad doubled."""
    assert _profile_with({100: (YOUTUBE, 'T')}) is None


def test_the_running_kiosk_wins_over_a_suspended_one():
    """Twitch on the screen while YouTube is frozen behind it is a normal state.

    This is why the walk continues past a frozen match instead of giving up on
    the first Firefox it finds.
    """
    assert _profile_with({100: (YOUTUBE, 'T'), 101: (TWITCH, 'S')}) == 'twitch-tv'
    assert _profile_with({100: (TWITCH, 'S'), 101: (YOUTUBE, 'T')}) == 'twitch-tv'


def test_both_suspended_means_no_profile():
    assert _profile_with({100: (YOUTUBE, 'T'), 101: (TWITCH, 'T')}) is None


def test_a_firefox_without_a_profile_flag_is_ignored():
    assert _profile_with({100: (['/usr/lib/firefox/firefox'], 'S')}) is None


def test_a_zombie_kiosk_is_not_matched():
    """A kiosk that has exited but not been reaped cannot receive a keystroke."""
    assert _profile_with({100: (YOUTUBE, 'Z')}) is None


def test_an_unreadable_state_still_matches():
    """Absence of evidence is not a suspended process.

    A /proc entry we cannot read is far more likely to be a permissions quirk
    than a frozen kiosk, and treating it as frozen would break matching
    outright for a whole class of setups to fix a narrower bug.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(f'{root}/100')
        Path(f'{root}/100/cmdline').write_bytes(
            b'\x00'.join(a.encode() for a in YOUTUBE) + b'\x00')
        # no stat file at all
        old, x11_detector._PROC = x11_detector._PROC, root
        try:
            assert x11_detector._get_firefox_profile() == 'youtube-tv'
        finally:
            x11_detector._PROC = old


# ── the screen owner, not merely a browser which exists ──────────────────────

def test_gamecore_on_screen_overrides_a_running_firefox():
    """The bridge must never type into GameCore, even during a suspend race."""
    with patch.object(x11_detector, '_screen_owner', return_value='gamecore'), \
         patch.object(x11_detector, '_get_firefox_profile', return_value='youtube-tv'):
        assert x11_detector._detect_active() is None


def test_a_focused_firefox_still_gets_its_profile():
    with patch.object(x11_detector, '_screen_owner', return_value='firefox'), \
         patch.object(x11_detector, '_get_firefox_profile', return_value='youtube-tv'):
        active = x11_detector._detect_active()
    assert active is not None
    assert active.title == 'youtube-tv'


def test_no_x11_answer_keeps_the_proc_fallback_working():
    """The service starts before X on some boxes; absence is not GameCore."""
    with patch.object(x11_detector, '_screen_owner', return_value=None), \
         patch.object(x11_detector, '_get_firefox_profile', return_value='twitch-tv'):
        active = x11_detector._detect_active()
    assert active is not None
    assert active.title == 'twitch-tv'


def test_another_focused_window_is_also_passthrough():
    with patch.object(x11_detector, '_screen_owner', return_value='other'), \
         patch.object(x11_detector, '_get_firefox_profile', return_value='youtube-tv'):
        assert x11_detector._detect_active() is None


def test_stacking_fallback_sees_gamecore_above_firefox():
    """Openbox may publish no _NET_ACTIVE_WINDOW, but still publishes stacking."""
    def output(args, **_kwargs):
        if args[-1] == '_NET_ACTIVE_WINDOW':
            return b'_NET_ACTIVE_WINDOW(WINDOW): window id # 0x0\n'
        if args[-1] == '_NET_CLIENT_LIST_STACKING':
            return b'_NET_CLIENT_LIST_STACKING(WINDOW): window id # 0x10, 0x20\n'
        if args[2] == '0x20':
            return b'WM_CLASS(STRING) = "gamecore-electron", "GameCore-electron"\n'
        return b'WM_CLASS(STRING) = "Navigator", "firefox"\n'

    with patch.object(x11_detector.subprocess, 'check_output', side_effect=output):
        assert x11_detector._screen_owner() == 'gamecore'


def test_stacking_fallback_allows_firefox_above_gamecore():
    def output(args, **_kwargs):
        if args[-1] == '_NET_ACTIVE_WINDOW':
            return b'_NET_ACTIVE_WINDOW(WINDOW): window id # 0x0\n'
        if args[-1] == '_NET_CLIENT_LIST_STACKING':
            return b'_NET_CLIENT_LIST_STACKING(WINDOW): window id # 0x20, 0x10\n'
        if args[2] == '0x10':
            return b'WM_CLASS(STRING) = "Navigator", "firefox"\n'
        return b'WM_CLASS(STRING) = "gamecore-electron", "GameCore-electron"\n'

    with patch.object(x11_detector.subprocess, 'check_output', side_effect=output):
        assert x11_detector._screen_owner() == 'firefox'


if __name__ == '__main__':
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith('test_') or not callable(fn):
            continue
        try:
            fn()
            print(f'  ok   {name}')
        except AssertionError as e:
            failures += 1
            print(f'  FAIL {name}: {e}')
    print(f'\n{"FAILED" if failures else "all passed"} ({failures} failure(s))')
    sys.exit(1 if failures else 0)
