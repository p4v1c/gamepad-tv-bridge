"""Load and validate YAML profiles."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError
from rich.console import Console

from gamepad_bridge.profiles.schema import Profile

console = Console()


def load_profile(path: Path) -> Profile | None:
    try:
        raw = yaml.safe_load(path.read_text())
        return Profile.model_validate(raw)
    except (yaml.YAMLError, ValidationError, OSError) as e:
        console.print(f"[red]Error loading profile {path.name}: {e}[/red]")
        return None


def load_profiles_dir(directory: Path) -> list[Profile]:
    profiles = []
    if not directory.exists():
        return profiles
    for yaml_file in sorted(directory.glob("*.yaml")):
        profile = load_profile(yaml_file)
        if profile is not None:
            profiles.append(profile)
    return profiles
