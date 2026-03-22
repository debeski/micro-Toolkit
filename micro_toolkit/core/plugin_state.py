from __future__ import annotations

import json
from pathlib import Path


class PluginStateManager:
    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.state_path.exists():
            return {}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save(self) -> None:
        self.state_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def get(self, plugin_id: str) -> dict:
        state = self._state.get(plugin_id, {})
        return {
            "enabled": bool(state.get("enabled", True)),
            "hidden": bool(state.get("hidden", False)),
        }

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        current = self.get(plugin_id)
        current["enabled"] = bool(enabled)
        self._state[plugin_id] = current
        self._save()

    def set_hidden(self, plugin_id: str, hidden: bool) -> None:
        current = self.get(plugin_id)
        current["hidden"] = bool(hidden)
        self._state[plugin_id] = current
        self._save()

    def reset(self, plugin_id: str) -> None:
        if plugin_id in self._state:
            del self._state[plugin_id]
            self._save()
