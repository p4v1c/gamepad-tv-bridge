"""Typer CLI for gamepad-tv-bridge."""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="gamepad-bridge", add_completion=False, help="Gamepad → keyboard bridge for TV web apps.")
profile_app = typer.Typer(help="Profile management commands.")
app.add_typer(profile_app, name="profile")

console = Console()

_PID_FILE = Path("/tmp/gamepad-tv-bridge.pid")
_PROFILES_DIR = Path(__file__).parent.parent / "profiles"


@app.command()
def start(
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run in background."),
    profiles_dir: Optional[Path] = typer.Option(None, "--profiles", help="Path to profiles directory."),
) -> None:
    """Start the gamepad bridge daemon."""
    pdir = profiles_dir or _PROFILES_DIR

    if daemon:
        pid = os.fork()
        if pid > 0:
            _PID_FILE.write_text(str(pid))
            console.print(f"[green]Daemon started (PID {pid})[/green]")
            return
        # Child: detach
        os.setsid()

    from gamepad_bridge.daemon import Daemon
    d = Daemon(profiles_dir=pdir)

    def _shutdown(_sig: int, _frame: object) -> None:
        d.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        d.start()
    except PermissionError as e:
        console.print(f"[red]Permission error: {e}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        d.stop()


@app.command()
def stop() -> None:
    """Stop a background daemon started with --daemon."""
    if not _PID_FILE.exists():
        console.print("[yellow]No PID file found — is the daemon running?[/yellow]")
        raise typer.Exit(1)
    pid = int(_PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        _PID_FILE.unlink(missing_ok=True)
        console.print(f"[green]Sent SIGTERM to PID {pid}[/green]")
    except ProcessLookupError:
        console.print(f"[yellow]Process {pid} not found (already stopped?)[/yellow]")
        _PID_FILE.unlink(missing_ok=True)


@app.command(name="list-devices")
def list_devices() -> None:
    """List detected gamepads."""
    from gamepad_bridge.input.detector import detect_gamepads
    devices = detect_gamepads()
    if not devices:
        console.print("[yellow]No gamepads detected.[/yellow]")
        return
    t = Table(title="Detected Gamepads")
    t.add_column("Path", style="cyan")
    t.add_column("Name")
    t.add_column("Vendor ID")
    t.add_column("Product ID")
    for d in devices:
        t.add_row(d.path, d.name, f"0x{d.vendor_id:04x}", f"0x{d.product_id:04x}")
    console.print(t)


@app.command()
def test(
    profiles_dir: Optional[Path] = typer.Option(None, "--profiles", help="Path to profiles directory."),
) -> None:
    """Interactive test: press gamepad buttons and see what keys would fire."""
    from gamepad_bridge.input.detector import detect_gamepads
    from gamepad_bridge.input.evdev_reader import EvdevReader
    from gamepad_bridge.profiles.loader import load_profiles_dir
    from gamepad_bridge.profiles.matcher import ProfileMatcher
    from gamepad_bridge.profiles.schema import Profile

    pdir = profiles_dir or _PROFILES_DIR
    devices = detect_gamepads()
    if not devices:
        console.print("[red]No gamepads found.[/red]")
        raise typer.Exit(1)

    dev = devices[0]
    from rich.markup import escape
    console.print(f"[green]Using: {escape(str(dev))}[/green]")
    console.print("Press gamepad buttons (Ctrl-C to quit)...\n")

    profiles = load_profiles_dir(pdir)
    default = next((p for p in profiles if p.name.lower() == "default"), Profile(name="default"))
    non_default = [p for p in profiles if p.name.lower() != "default"]
    matcher = ProfileMatcher(non_default, default)

    reader = EvdevReader(dev)
    import select

    try:
        while True:
            r, _, _ = select.select([reader._dev.fd], [], [], 0.1)
            if not r:
                continue
            try:
                for ev in reader.read_events():
                    profile = matcher.get_active()
                    binding = profile.get_binding(ev.button)
                    action_str = ""
                    if binding:
                        sp = binding.short_press
                        lp = binding.long_press
                        if sp:
                            action_str += f"short={sp.key or sp.combo}"
                        if lp:
                            action_str += f" long={lp.key or lp.combo}"
                    console.print(
                        f"[cyan]{ev.button:20s}[/cyan] val=[yellow]{ev.value:+.2f}[/yellow]  {action_str}"
                    )
            except OSError:
                console.print("[red]Device disconnected.[/red]")
                break
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()


@profile_app.command(name="validate")
def profile_validate(
    profiles_dir: Optional[Path] = typer.Option(None, "--profiles", help="Path to profiles directory."),
) -> None:
    """Validate all YAML profiles."""
    from gamepad_bridge.profiles.loader import load_profile
    pdir = profiles_dir or _PROFILES_DIR
    if not pdir.exists():
        console.print(f"[red]Profiles directory not found: {pdir}[/red]")
        raise typer.Exit(1)

    ok = 0
    fail = 0
    for f in sorted(pdir.glob("*.yaml")):
        p = load_profile(f)
        if p is not None:
            console.print(f"[green]✓[/green] {f.name} — {p.name!r}")
            ok += 1
        else:
            console.print(f"[red]✗[/red] {f.name}")
            fail += 1

    console.print(f"\n{ok} valid, {fail} failed.")
    if fail:
        raise typer.Exit(1)


@profile_app.command(name="list")
def profile_list(
    profiles_dir: Optional[Path] = typer.Option(None, "--profiles", help="Path to profiles directory."),
) -> None:
    """List loaded profiles and their match rules."""
    from gamepad_bridge.profiles.loader import load_profiles_dir
    pdir = profiles_dir or _PROFILES_DIR
    profiles = load_profiles_dir(pdir)
    if not profiles:
        console.print("[yellow]No profiles found.[/yellow]")
        return

    for p in profiles:
        console.print(f"\n[bold]{p.name}[/bold] — {p.description}")
        if p.match:
            for rule in p.match:
                parts = []
                if rule.title_contains:
                    parts.append(f"title_contains={rule.title_contains!r}")
                if rule.title_regex:
                    parts.append(f"title_regex={rule.title_regex!r}")
                if rule.wm_class_contains:
                    parts.append(f"wm_class_contains={rule.wm_class_contains!r}")
                console.print(f"  match: {', '.join(parts)}")
        else:
            console.print("  match: [dim](default fallback)[/dim]")
        console.print(f"  bindings: {len(p.bindings)} button(s)")
