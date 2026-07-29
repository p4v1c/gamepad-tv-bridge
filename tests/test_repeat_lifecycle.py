"""Auto-repeat has to stop exactly when the held button stops — no sooner, no later.

Two failures with the same shape: a single global AutoRepeat that the wrong
event could cancel, or that nothing could cancel at all.

Run:  python -m pytest tests/
Or:   python tests/test_repeat_lifecycle.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gamepad_bridge.core.repeat import AutoRepeat
from gamepad_bridge.core.state import ButtonStateMachine
from gamepad_bridge.profiles.schema import Binding, KeyAction


def _key(name: str = "KEY_DOWN") -> KeyAction:
    return KeyAction(key=name)


class Recorder:
    def __init__(self) -> None:
        self.fired: list[tuple[str, bool]] = []

    def __call__(self, action: KeyAction, is_repeat: bool) -> None:
        self.fired.append((action.key or str(action.combo), is_repeat))

    @property
    def repeats(self) -> int:
        return sum(1 for _, is_repeat in self.fired if is_repeat)


# ── #27 · an unmapped axis must not cancel someone else's repeat ─────────────

def test_stop_from_another_button_leaves_the_repeat_alone():
    """Brushing L2 to change the volume used to kill the scroll you were holding.

    One repeater serves the whole daemon and any below-threshold event cancelled
    it — including axes nobody mapped. An analog trigger emits a stream of those.
    """
    rec = Recorder()
    rep = AutoRepeat(rec)
    rep.start(_key(), delay_ms=20, rate_ms=20, owner="DPAD_DOWN")
    time.sleep(0.12)
    assert rec.repeats > 0, "the repeat should be running"

    rep.stop(owner="TRIGGER_L")          # a different button lets go
    before = rec.repeats
    time.sleep(0.12)
    assert rec.repeats > before, "another button's release must not stop this repeat"

    rep.stop(owner="DPAD_DOWN")          # the owner lets go
    settled = rec.repeats
    time.sleep(0.12)
    assert rec.repeats == settled, "its own release must stop it"


def test_an_ownerless_stop_always_stops():
    """The flush path has no owner and has to cancel whatever is running."""
    rec = Recorder()
    rep = AutoRepeat(rec)
    rep.start(_key(), delay_ms=10, rate_ms=20, owner="DPAD_DOWN")
    time.sleep(0.08)
    assert rec.repeats > 0

    rep.stop()
    settled = rec.repeats
    time.sleep(0.1)
    assert rec.repeats == settled


def test_starting_a_new_repeat_replaces_the_previous_owner():
    rec = Recorder()
    rep = AutoRepeat(rec)
    rep.start(_key("KEY_DOWN"), delay_ms=10, rate_ms=20, owner="DPAD_DOWN")
    time.sleep(0.06)
    rep.start(_key("KEY_UP"), delay_ms=10, rate_ms=20, owner="DPAD_UP")
    time.sleep(0.06)

    # The old owner letting go must not stop the new repeat.
    rep.stop(owner="DPAD_DOWN")
    before = rec.repeats
    time.sleep(0.1)
    assert rec.repeats > before

    rep.stop(owner="DPAD_UP")
    settled = rec.repeats
    time.sleep(0.08)
    assert rec.repeats == settled


# ── #26 · flushing must not fire anything ────────────────────────────────────

def test_cancelling_a_held_button_does_not_fire_its_action():
    """cancel() exists because on_release() fires.

    Flushing with on_release would inject the binding of a profile that has just
    disappeared — and for BUTTON_SELECT that binding is CTRL+W, which is what
    closed the window in the first place.
    """
    rec = Recorder()
    sm = ButtonStateMachine(button="BUTTON_SELECT", long_press_ms=400, fire_action=rec)
    sm.on_press(Binding(short_press=_key("KEY_ESC"), long_press=KeyAction(combo=["KEY_LEFTCTRL", "KEY_W"])))

    sm.cancel()
    assert rec.fired == [], "cancel must be silent"

    # And the machine is usable again afterwards.
    sm.on_press(Binding(short_press=_key("KEY_ESC")))
    sm.on_release()
    assert rec.fired == [("KEY_ESC", False)]


def test_release_still_fires_normally():
    rec = Recorder()
    sm = ButtonStateMachine(button="BUTTON_A", long_press_ms=400, fire_action=rec)
    sm.on_press(Binding(short_press=_key("KEY_ENTER")))
    sm.on_release()
    assert rec.fired == [("KEY_ENTER", False)]


def test_cancel_on_an_idle_button_is_harmless():
    rec = Recorder()
    sm = ButtonStateMachine(button="BUTTON_A", long_press_ms=400, fire_action=rec)
    sm.cancel()
    sm.cancel()
    assert rec.fired == []


# ── #26 · the daemon's flush ─────────────────────────────────────────────────

def test_flush_stops_a_repeat_left_running_by_a_vanished_profile():
    """Hold the D-pad to scroll, the kiosk closes under your thumb, you let go.

    _handle_event returned on `profile is None` before ever looking at the
    release, so the repeat kept injecting KEY_DOWN into the whole session — for
    ever, until the service was restarted.
    """
    from gamepad_bridge.daemon import Daemon

    rec = Recorder()
    d = Daemon()
    d._repeater = AutoRepeat(rec)
    sm = ButtonStateMachine(button="BUTTON_SELECT", long_press_ms=400, fire_action=rec)
    sm.on_press(Binding(short_press=_key("KEY_ESC")))
    d._state_machines = {"BUTTON_SELECT": sm}

    d._repeater.start(_key("KEY_DOWN"), delay_ms=10, rate_ms=20, owner="DPAD_DOWN")
    time.sleep(0.08)
    assert rec.repeats > 0

    d._flush_input_state()
    settled = len(rec.fired)
    time.sleep(0.12)
    assert len(rec.fired) == settled, "nothing may be injected after the flush"
    assert d._stick_dpads == {}


if __name__ == "__main__":
    for fn in (test_stop_from_another_button_leaves_the_repeat_alone,
               test_an_ownerless_stop_always_stops,
               test_starting_a_new_repeat_replaces_the_previous_owner,
               test_cancelling_a_held_button_does_not_fire_its_action,
               test_release_still_fires_normally,
               test_cancel_on_an_idle_button_is_harmless,
               test_flush_stops_a_repeat_left_running_by_a_vanished_profile):
        fn()
        print(f"[OK ] {fn.__name__}")
    print("\nAll tests passed.")
