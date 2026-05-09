# gamepad-tv-bridge

Reads gamepad input and injects OS-level trusted keyboard events so any web app
(YouTube TV, Twitch, Deezer, Netflix, …) running in a kiosk browser responds to
a gamepad as if a real keyboard was used.

Web apps like `youtube.com/tv` reject synthetic `KeyboardEvent`s
(`isTrusted=false`). This daemon creates a virtual kernel-level keyboard via
`python-uinput`, so every injected keystroke is indistinguishable from a
physical key press.

## Requirements

- Manjaro / Arch Linux, X11
- Python 3.11+
- User in the `input` group: `sudo usermod -aG input $USER` (re-login after)

## Quick start

```bash
cd gamepad-tv-bridge
bash install/setup.sh
systemctl --user start gamepad-tv-bridge
journalctl --user -fu gamepad-tv-bridge
```

## CLI

```bash
# Foreground (verbose output)
python -m gamepad_bridge start

# Background daemon
python -m gamepad_bridge start --daemon
python -m gamepad_bridge stop

# Diagnostics
python -m gamepad_bridge list-devices
python -m gamepad_bridge test              # interactive button tester
python -m gamepad_bridge profile validate
python -m gamepad_bridge profile list
```

## Profiles

YAML files in `profiles/` define button→key mappings per app.
Active profile is selected by matching the focused window title or WM class.

```yaml
name: "YouTube TV"
match:
  - title_contains: "YouTube"
bindings:
  DPAD_UP:   { key: "KEY_UP" }
  BUTTON_A:  { key: "KEY_RETURN" }
  BUTTON_SELECT:
    short_press: { key: "KEY_M" }
    long_press:  { combo: ["KEY_LEFTCTRL", "KEY_W"] }
```

Profiles are hot-reloaded on change — no restart needed.

## Supported controllers

| Controller        | Vendor ID |
|-------------------|-----------|
| Sony DualShock 4  | 054c      |
| Sony DualSense    | 054c      |
| Xbox (all)        | 045e      |
| Logitech          | 046d      |
| 8BitDo            | 2dc8      |
| Generic (BTN_SOUTH fallback) | any |

## Button names

`BUTTON_A/B/X/Y`, `BUTTON_LB/RB/LT/RT`, `BUTTON_L3/R3`,
`BUTTON_START/SELECT/HOME`, `DPAD_UP/DOWN/LEFT/RIGHT`,
`LSTICK_X/Y`, `RSTICK_X/Y`

## Architecture

```
evdev device ──► EvdevReader ──► event Queue ──► Daemon._handle_event()
                                                        │
                                          ButtonStateMachine + AutoRepeat
                                                        │
                                               UinputInjector (uinput)
                                                        │
                                              /dev/uinput virtual kbd
                                           (isTrusted=true in browser)
```
