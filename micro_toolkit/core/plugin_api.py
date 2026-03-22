from __future__ import annotations

import abc
from dataclasses import dataclass

from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class PluginMetadata:
    plugin_id: str
    name: str
    description: str
    category: str
    version: str = "0.1.0"
    standalone: bool = False


class QtPlugin(abc.ABC):
    plugin_id = ""
    name = "Unnamed Tool"
    description = ""
    category = "General"
    version = "0.1.0"
    standalone = False
    translations: dict[str, dict[str, str]] = {}

    @classmethod
    def metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            plugin_id=cls.plugin_id,
            name=cls.name,
            description=cls.description,
            category=cls.category,
            version=cls.version,
            standalone=cls.standalone,
        )

    def register_commands(self, registry, services) -> None:
        return None

    def register_privileged_capabilities(self, registry, runtime) -> None:
        return None

    @abc.abstractmethod
    def create_widget(self, services) -> QWidget:
        raise NotImplementedError
