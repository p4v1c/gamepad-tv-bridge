"""Normalize raw evdev codes to abstract button names."""
from __future__ import annotations

from evdev import ecodes

# Maps BTN_* evdev codes → abstract button names
BTN_MAP: dict[int, str] = {
    ecodes.BTN_SOUTH:  "BUTTON_A",
    ecodes.BTN_EAST:   "BUTTON_B",
    ecodes.BTN_WEST:   "BUTTON_X",
    ecodes.BTN_NORTH:  "BUTTON_Y",
    ecodes.BTN_TL:     "BUTTON_LB",
    ecodes.BTN_TR:     "BUTTON_RB",
    ecodes.BTN_TL2:    "BUTTON_LT",
    ecodes.BTN_TR2:    "BUTTON_RT",
    ecodes.BTN_SELECT: "BUTTON_SELECT",
    ecodes.BTN_START:  "BUTTON_START",
    ecodes.BTN_MODE:   "BUTTON_HOME",
    ecodes.BTN_THUMBL: "BUTTON_L3",
    ecodes.BTN_THUMBR: "BUTTON_R3",
}

# Maps ABS_* evdev codes → abstract axis names
ABS_MAP: dict[int, str] = {
    ecodes.ABS_X:     "LSTICK_X",
    ecodes.ABS_Y:     "LSTICK_Y",
    ecodes.ABS_RX:    "RSTICK_X",
    ecodes.ABS_RY:    "RSTICK_Y",
    ecodes.ABS_Z:     "TRIGGER_L",
    ecodes.ABS_RZ:    "TRIGGER_R",
    ecodes.ABS_HAT0X: "HAT0X",
    ecodes.ABS_HAT0Y: "HAT0Y",
}

# HAT axis value → dpad button name
HAT_MAP: dict[str, dict[int, str]] = {
    "HAT0X": {-1: "DPAD_LEFT", 1: "DPAD_RIGHT"},
    "HAT0Y": {-1: "DPAD_UP",   1: "DPAD_DOWN"},
}


def normalize_axis(raw: int, info) -> float:
    """Normalize an axis value from its raw integer to -1.0..1.0."""
    minimum = info.min
    maximum = info.max
    if maximum == minimum:
        return 0.0
    mid = (maximum + minimum) / 2.0
    half = (maximum - minimum) / 2.0
    return (raw - mid) / half
