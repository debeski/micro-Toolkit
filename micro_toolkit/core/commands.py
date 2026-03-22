from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CommandSpec:
    command_id: str
    title: str
    description: str
    handler: Callable


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, CommandSpec] = {}

    def register(self, command_id: str, title: str, description: str, handler: Callable) -> None:
        self._commands[command_id] = CommandSpec(
            command_id=command_id,
            title=title,
            description=description,
            handler=handler,
        )

    def clear(self) -> None:
        self._commands.clear()

    def execute(self, command_id: str, **kwargs):
        spec = self._commands.get(command_id)
        if spec is None:
            raise KeyError(f"Unknown command: {command_id}")
        return spec.handler(**kwargs)

    def list_commands(self) -> list[CommandSpec]:
        return [self._commands[key] for key in sorted(self._commands)]
