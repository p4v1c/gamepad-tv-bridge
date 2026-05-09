from __future__ import annotations

from abc import ABC, abstractmethod


class KeyInjector(ABC):
    @abstractmethod
    def press_key(self, key_name: str) -> None:
        pass

    @abstractmethod
    def release_key(self, key_name: str) -> None:
        pass

    @abstractmethod
    def tap_key(self, key_name: str) -> None:
        pass

    @abstractmethod
    def tap_combo(self, key_names: list[str]) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass
