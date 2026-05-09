"""Main daemon: orchestrates readers, injector, profile matcher, state machines."""
from __future__ import annotations

import queue
import threading
from pathlib import Path

from rich.console import Console

from gamepad_bridge.core.deadzone import StickToDpad, apply_deadzone
from gamepad_bridge.core.repeat import AutoRepeat
from gamepad_bridge.core.state import ButtonStateMachine
from gamepad_bridge.input.base import GamepadDevice, GamepadEvent
from gamepad_bridge.input.detector import HotplugWatcher, detect_gamepads
from gamepad_bridge.input.evdev_reader import EvdevReader
from gamepad_bridge.output.uinput_injector import UinputInjector
from gamepad_bridge.profiles.loader import load_profiles_dir
from gamepad_bridge.profiles.matcher import ProfileMatcher
from gamepad_bridge.profiles.schema import KeyAction, Profile
from gamepad_bridge.window.x11_detector import ActiveWindow, WindowWatcher

console = Console()

_STICK_AXES = {"LSTICK_X", "LSTICK_Y", "RSTICK_X", "RSTICK_Y"}

_PROFILES_DIR = Path(__file__).parent.parent / "profiles"


class Daemon:
    def __init__(self, profiles_dir: Path = _PROFILES_DIR) -> None:
        self._profiles_dir = profiles_dir
        self._stop = threading.Event()
        self._event_queue: queue.Queue[GamepadEvent] = queue.Queue()
        self._injector: UinputInjector | None = None
        self._matcher: ProfileMatcher | None = None
        self._reader_threads: dict[str, threading.Thread] = {}
        self._readers: dict[str, EvdevReader] = {}
        self._state_machines: dict[str, ButtonStateMachine] = {}
        self._repeater: AutoRepeat | None = None
        self._hotplug: HotplugWatcher | None = None
        self._window_watcher: WindowWatcher | None = None
        self._stick_dpads: dict[str, StickToDpad] = {}
        self._readers_lock = threading.Lock()

    def start(self) -> None:
        console.print("[green]Starting gamepad-tv-bridge...[/green]")

        # Load profiles
        profiles = load_profiles_dir(self._profiles_dir)
        default = next((p for p in profiles if p.name.lower() == "default"), None)
        if default is None:
            from gamepad_bridge.profiles.schema import Profile as P
            default = P(name="default", description="Empty fallback")
        non_default = [p for p in profiles if p.name.lower() != "default"]

        self._matcher = ProfileMatcher(non_default, default)
        console.print(f"[blue]Loaded {len(profiles)} profile(s)[/blue]")

        # Create virtual keyboard
        self._injector = UinputInjector()
        self._repeater = AutoRepeat(self._fire_action)
        console.print("[green]Virtual keyboard created: gamepad-tv-bridge[/green]")

        # Start window watcher
        self._window_watcher = WindowWatcher(self._on_window_change)
        self._window_watcher.start()

        # Detect and start readers
        devices = detect_gamepads()
        if not devices:
            console.print("[yellow]No gamepads detected yet — waiting for hotplug[/yellow]")
        for dev in devices:
            self._connect_device(dev)

        # Hotplug watcher
        self._hotplug = HotplugWatcher(
            on_connect=self._connect_device,
            on_disconnect=self._disconnect_device,
        )
        self._hotplug.start()

        # Start profile hot-reload watcher
        self._start_profile_watcher()

        # Main processing loop
        self._process_loop()

    def _process_loop(self) -> None:
        while not self._stop.is_set():
            try:
                ev = self._event_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            self._handle_event(ev)

    def _handle_event(self, ev: GamepadEvent) -> None:
        assert self._matcher is not None
        profile = self._matcher.get_active()
        if profile is None:
            # No browser profile active — passthrough, don't inject anything
            return

        cfg = profile.config
        button = ev.button
        value = ev.value

        # Stick → DPAD conversion
        if cfg.stick_as_dpad and button in _STICK_AXES:
            normalized = apply_deadzone(value, cfg.deadzone)
            device_key = button.split("_")[0]  # LSTICK / RSTICK
            dpad = self._stick_dpads.setdefault(device_key, StickToDpad(cfg.stick_threshold))
            for dpad_btn, dpad_val in dpad.process(button, normalized):
                synthetic = GamepadEvent(button=dpad_btn, value=dpad_val)
                self._handle_button(synthetic, profile)
            return

        self._handle_button(ev, profile)

    def _handle_button(self, ev: GamepadEvent, profile: Profile) -> None:
        assert self._repeater is not None
        button = ev.button
        value = ev.value
        binding = profile.get_binding(button)
        cfg = profile.config

        sm = self._state_machines.setdefault(
            button,
            ButtonStateMachine(
                button=button,
                long_press_ms=cfg.long_press_ms,
                fire_action=self._fire_action,
            ),
        )

        if value >= 0.5:  # pressed
            sm.on_press(binding)
            if binding and binding.short_press and getattr(binding.short_press, "repeat", True):
                self._repeater.start(
                    binding.short_press,
                    delay_ms=cfg.repeat_delay_ms,
                    rate_ms=cfg.repeat_rate_ms,
                )
        else:  # released
            self._repeater.stop()
            sm.on_release()

    def _fire_action(self, action: KeyAction, is_repeat: bool) -> None:
        assert self._injector is not None
        label = "[dim](repeat)[/dim]" if is_repeat else ""
        if action.combo:
            console.print(f"[yellow]→ combo {action.combo} {label}[/yellow]")
            self._injector.tap_combo(action.combo)
        elif action.key:
            console.print(f"[yellow]→ {action.key} {label}[/yellow]")
            self._injector.tap_key(action.key)

    def _on_window_change(self, window: ActiveWindow | None) -> None:
        assert self._matcher is not None
        self._matcher.on_window_change(window)
        active = self._matcher.get_active()
        title = window.title if window else "(none)"
        profile_name = active.name if active else "passthrough (no injection)"
        from rich.markup import escape
        console.print(f"[blue]Window: {escape(title)!r} → {profile_name}[/blue]")

    def _connect_device(self, dev: GamepadDevice) -> None:
        with self._readers_lock:
            if dev.path in self._readers:
                return
            try:
                reader = EvdevReader(dev)
                self._readers[dev.path] = reader
            except OSError as e:
                console.print(f"[red]Cannot open {dev.path}: {e}[/red]")
                return
        t = threading.Thread(
            target=self._reader_loop,
            args=(dev.path, reader),
            daemon=True,
            name=f"reader-{dev.path}",
        )
        with self._readers_lock:
            self._reader_threads[dev.path] = t
        t.start()
        from rich.markup import escape
        console.print(f"[green]Connected: {escape(str(dev))}[/green]")

    def _disconnect_device(self, path: str) -> None:
        with self._readers_lock:
            reader = self._readers.pop(path, None)
            self._reader_threads.pop(path, None)
        if reader:
            reader.close()
        from rich.markup import escape
        console.print(f"[red]Disconnected: {escape(path)}[/red]")

    def _reader_loop(self, path: str, reader: EvdevReader) -> None:
        while not self._stop.is_set():
            try:
                for ev in reader.read_events():
                    self._event_queue.put(ev)
            except OSError:
                break
        self._disconnect_device(path)

    def _start_profile_watcher(self) -> None:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        daemon = self

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if not event.src_path.endswith(".yaml"):
                    return
                console.print(f"[blue]Reloading profiles (changed: {event.src_path})[/blue]")
                daemon._reload_profiles()

        if not self._profiles_dir.exists():
            return

        observer = Observer()
        observer.schedule(_Handler(), str(self._profiles_dir), recursive=False)
        observer.start()

    def _reload_profiles(self) -> None:
        assert self._matcher is not None
        profiles = load_profiles_dir(self._profiles_dir)
        default = next((p for p in profiles if p.name.lower() == "default"), None)
        if default is None:
            from gamepad_bridge.profiles.schema import Profile as P
            default = P(name="default", description="Empty fallback")
        non_default = [p for p in profiles if p.name.lower() != "default"]
        self._matcher.reload(non_default, default)
        console.print(f"[blue]Reloaded {len(profiles)} profile(s)[/blue]")

    def stop(self) -> None:
        self._stop.set()
        if self._window_watcher:
            self._window_watcher.stop()
        if self._hotplug:
            self._hotplug.stop()
        with self._readers_lock:
            readers = list(self._readers.values())
        for reader in readers:
            reader.close()
        if self._injector:
            self._injector.close()
        console.print("[red]Daemon stopped[/red]")
