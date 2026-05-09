"""Pick the active profile based on the focused window."""
from __future__ import annotations

import re
import threading

from gamepad_bridge.profiles.schema import MatchRule, Profile
from gamepad_bridge.window.x11_detector import ActiveWindow


def _rule_matches(rule: MatchRule, window: ActiveWindow) -> bool:
    if rule.title_contains and rule.title_contains.lower() not in window.title.lower():
        return False
    if rule.title_regex and not re.search(rule.title_regex, window.title, re.IGNORECASE):
        return False
    if rule.wm_class_contains and rule.wm_class_contains.lower() not in window.wm_class.lower():
        return False
    return True


def _profile_matches(profile: Profile, window: ActiveWindow) -> bool:
    if not profile.match:
        return False
    return any(_rule_matches(rule, window) for rule in profile.match)


class ProfileMatcher:
    def __init__(self, profiles: list[Profile], default: Profile) -> None:
        self._profiles = profiles
        self._default = default
        self._active: Profile | None = None  # None = passthrough (no injection)
        self._lock = threading.Lock()

    def on_window_change(self, window: ActiveWindow | None) -> None:
        if window is None:
            matched: Profile | None = None
        else:
            matched = next(
                (p for p in self._profiles if _profile_matches(p, window)),
                None,
            )
            # Fall back to default only if it has explicit match rules
            if matched is None and _profile_matches(self._default, window):
                matched = self._default
        with self._lock:
            self._active = matched

    def get_active(self) -> Profile | None:
        """Returns None when no profile matches — daemon must skip injection."""
        with self._lock:
            return self._active

    def reload(self, profiles: list[Profile], default: Profile) -> None:
        with self._lock:
            self._profiles = profiles
            self._default = default
            if self._active and self._active.name not in {p.name for p in profiles}:
                self._active = None
