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

Sticks are converted to dpad presses with hysteresis (release at 65% of the
press threshold) and a dominant-axis lock, so diagonal wobble never fires the
perpendicular direction.

## Deployment on the GameCore box

How this runs on the [GameCore](https://github.com/p4v1c/GamecoreRenew) living-room box:

- Cloned in `/opt/gamepad-tv-bridge`, installed **editable** in the user venv:
  `~/.venv/bin/pip install -e /opt/gamepad-tv-bridge`
- User unit `~/.config/systemd/user/gamepad-tv-bridge.service` runs
  `%h/.venv/bin/python -m gamepad_bridge start` with `Restart=on-failure`,
  `WantedBy=graphical-session.target` (see `install/gamepad-tv-bridge.service`).
- The `twitch_tv_local` profile drives [EmberTV](https://github.com/p4v1c/Twitch-TV)
  (window title "Twitch TV", Firefox kiosk at `https://localhost:8097`) — the
  in-page JS gamepad handling was removed from EmberTV in favour of this daemon.

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
