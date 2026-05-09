"""Pydantic v2 models for profile YAML files."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator


class KeyAction(BaseModel):
    key: str | None = None
    combo: list[str] | None = None
    repeat: bool = True

    @model_validator(mode="after")
    def _check_key_or_combo(self) -> "KeyAction":
        if self.key is None and self.combo is None:
            raise ValueError("KeyAction must have 'key' or 'combo'")
        return self


class Binding(BaseModel):
    short_press: KeyAction | None = None
    long_press: KeyAction | None = None

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "key" in data or "combo" in data:
                # shorthand: treat as short_press only
                return {"short_press": data}
        return data


class ProfileConfig(BaseModel):
    deadzone: float = 0.25
    repeat_delay_ms: int = 400
    repeat_rate_ms: int = 130
    long_press_ms: int = 600
    stick_as_dpad: bool = True
    stick_threshold: float = 0.6


class MatchRule(BaseModel):
    title_contains: str | None = None
    title_regex: str | None = None
    wm_class_contains: str | None = None


class Profile(BaseModel):
    name: str
    description: str = ""
    match: list[MatchRule] = []
    config: ProfileConfig = ProfileConfig()
    bindings: dict[str, Binding | KeyAction] = {}

    def get_binding(self, button: str) -> Binding | None:
        raw = self.bindings.get(button)
        if raw is None:
            return None
        if isinstance(raw, KeyAction):
            return Binding(short_press=raw)
        return raw
