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

> ### The unit needs `DISPLAY` and `XAUTHORITY` from the session
>
> `_detect_active()` has **two** paths, and only the second needs X:
>
> 1. **The Firefox `--profile` name**, read from `/proc/*/cmdline`. No X at all.
>    This is how a GameCore kiosk tile is matched, since it launches
>    `firefox --profile <name> --kiosk …`.
> 2. **`xprop`**, scanning window titles. The fallback for anything that is not
>    a named-profile Firefox.
>
> So a broken X11 connection does **not** make the daemon inert: profile-based
> matching keeps working, and only the title fallback dies. The journal shows
> `Window: '(none)' → passthrough` when *neither* path resolves.
>
> The unit deliberately does **not** set `Environment=DISPLAY=:0`: that is the
> display manager's server, not the session's, and it carries no matching
> `XAUTHORITY`. On a box with both `X0` and `X1` sockets — which is what SDDM
> plus a session produces — `:0` is often the one that does not answer, so the
> fallback is silently dead. Both variables must be imported into the user
> manager by the session:
>
> ```bash
> systemctl --user import-environment DISPLAY XAUTHORITY
> ```
>
> Plasma does this itself. On a session that does not, add it to the autostart
> before this service. If the X11 connection fails, the daemon now says so at
> WARNING level instead of failing silently.
>
> It also does not set `SupplementaryGroups=input` — that directive is not
> supported in a `--user` unit and makes systemd refuse to start the service at
> all (`status=216/GROUP`). `install/fix-permissions.sh` puts the user in the
> `input` group, which the session inherits.
- The `twitch_tv_local` profile drives [EmberTV](https://github.com/p4v1c/Twitch-TV)
  (window title "Twitch TV", Firefox kiosk at `https://localhost:8097`) — the
  in-page JS gamepad handling was removed from EmberTV in favour of this daemon.

## Stremio

Stremio is no longer handled here. Its desktop client reads the gamepad
natively, and its window is Wayland-native — invisible to the X11 title
detection this daemon matches profiles on, so no profile would ever apply to
it. The on-screen keyboard it was missing now lives in
[stremio-gamepad-keyboard](https://github.com/p4v1c/stremio-gamepad-keyboard),
which injects it into Stremio's own interface without touching the client.

The forked web UI in a Firefox kiosk that used to live here — three user
services, plus a streaming server pushed onto the host's node to work around
the Flatpak runtime's missing HEVC decoder — went with it. That diagnosis is
kept in GameCore's `docs/STREMIO.md`.

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
