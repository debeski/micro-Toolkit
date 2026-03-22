from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut

try:
    import keyboard as keyboard_backend
except Exception:
    keyboard_backend = None


@dataclass
class ShortcutBinding:
    action_id: str
    title: str
    default_sequence: str
    callback: callable
    sequence: str = ""
    scope: str = "application"


class ShortcutManager(QObject):
    action_triggered = Signal(str)

    def __init__(self, config, logger, helper_manager=None):
        super().__init__()
        self.config = config
        self.logger = logger
        self.helper_manager = helper_manager
        self._actions: dict[str, ShortcutBinding] = {}
        self._local_shortcuts: list[QShortcut] = []
        self._global_hotkeys: list[object] = []
        self._window = None
        self._global_support_logged = False
        self.action_triggered.connect(self._dispatch_action)
        if self.helper_manager is not None:
            self.helper_manager.action_requested.connect(self.action_triggered.emit)

    def register_action(
        self,
        action_id: str,
        title: str,
        default_sequence: str,
        callback,
        *,
        default_scope: str = "application",
    ) -> None:
        saved = (self.config.get("hotkeys") or {}).get(action_id, {})
        requested_scope = saved.get("scope", default_scope)
        self._actions[action_id] = ShortcutBinding(
            action_id=action_id,
            title=title,
            default_sequence=default_sequence,
            callback=callback,
            sequence=saved.get("sequence", default_sequence),
            scope=self._normalize_scope(requested_scope),
        )

    def attach(self, window) -> None:
        self._window = window
        self.apply()

    def apply(self) -> None:
        self._clear_bindings()
        if self._window is None:
            return
        for binding in self._actions.values():
            sequence = (binding.sequence or binding.default_sequence or "").strip()
            if not sequence:
                continue

        helper_bindings = self.global_binding_sequences()
        helper_active = False
        if helper_bindings and self.helper_manager is not None and not self.direct_global_hotkeys_supported():
            helper_active = self.helper_manager.apply_bindings(helper_bindings)

        for binding in self._actions.values():
            sequence = (binding.sequence or binding.default_sequence or "").strip()
            if not sequence:
                continue
            if binding.scope == "global" and self.direct_global_hotkeys_supported():
                try:
                    hotkey_handle = keyboard_backend.add_hotkey(
                        sequence,
                        lambda action_id=binding.action_id: self.action_triggered.emit(action_id),
                    )
                    self._global_hotkeys.append(hotkey_handle)
                    continue
                except Exception as exc:
                    self.logger.log(
                        f"Global hotkey '{sequence}' could not be registered, using application scope instead: {exc}",
                        "WARNING",
                    )
            elif binding.scope == "global" and helper_active and binding.action_id in helper_bindings:
                continue
            elif binding.scope == "global":
                self._log_global_support_fallback(sequence, helper_ready=bool(helper_bindings and self.helper_manager is not None))
            shortcut = QShortcut(QKeySequence(sequence), self._window)
            shortcut.activated.connect(lambda action_id=binding.action_id: self.action_triggered.emit(action_id))
            self._local_shortcuts.append(shortcut)

    def update_binding(self, action_id: str, sequence: str, scope: str) -> None:
        binding = self._actions[action_id]
        binding.sequence = sequence.strip()
        binding.scope = self._normalize_scope(scope)
        saved = self.config.get("hotkeys") or {}
        saved[action_id] = {"sequence": binding.sequence, "scope": binding.scope}
        self.config.set("hotkeys", saved)
        self.apply()

    def update_bindings(self, bindings: dict[str, dict[str, str]]) -> None:
        saved = dict(self.config.get("hotkeys") or {})
        changed = False
        for action_id, payload in bindings.items():
            binding = self._actions.get(action_id)
            if binding is None:
                continue
            sequence = str(payload.get("sequence", binding.sequence or binding.default_sequence)).strip()
            scope = self._normalize_scope(str(payload.get("scope", binding.scope or "application")))
            if binding.sequence != sequence or binding.scope != scope:
                binding.sequence = sequence
                binding.scope = scope
                changed = True
            if saved.get(action_id) != {"sequence": sequence, "scope": scope}:
                saved[action_id] = {"sequence": sequence, "scope": scope}
                changed = True
        if changed:
            self.config.set("hotkeys", saved)
            self.apply()

    def list_bindings(self) -> list[ShortcutBinding]:
        return [self._actions[key] for key in sorted(self._actions)]

    def global_binding_sequences(self) -> dict[str, str]:
        bindings: dict[str, str] = {}
        for binding in self._actions.values():
            if binding.scope != "global":
                continue
            sequence = (binding.sequence or binding.default_sequence or "").strip()
            if sequence:
                bindings[binding.action_id] = sequence
        return bindings

    def available_scopes(self) -> list[tuple[str, str]]:
        scopes = [("application", "Application")]
        if self.global_scope_available():
            scopes.append(("global", "Global"))
        return scopes

    def global_hotkeys_supported(self) -> bool:
        return self.global_hotkey_support_reason() is None

    def direct_global_hotkeys_supported(self) -> bool:
        return self.direct_global_hotkey_reason() is None

    def global_scope_available(self) -> bool:
        if self.direct_global_hotkeys_supported():
            return True
        return bool(self.helper_manager is not None and self.helper_manager.global_scope_available())

    def global_hotkey_support_reason(self) -> str | None:
        if self.direct_global_hotkeys_supported():
            return None
        if self.helper_manager is not None and self.helper_manager.is_active():
            return None
        if self.helper_manager is not None and self.helper_manager.can_request_helper():
            return self.helper_manager.helper_reason()
        return self.direct_global_hotkey_reason()

    def direct_global_hotkey_reason(self) -> str | None:
        if keyboard_backend is None:
            return "The global hotkey backend is not installed."
        if sys.platform.startswith("linux"):
            geteuid = getattr(os, "geteuid", None)
            if callable(geteuid) and geteuid() != 0:
                return "Global hotkeys on Linux currently require root-level input access with the active backend."
        return None

    def _normalize_scope(self, scope: str) -> str:
        if (scope or "").strip().lower() == "global" and self.global_scope_available():
            return "global"
        return "application"

    def _log_global_support_fallback(self, sequence: str, *, helper_ready: bool = False) -> None:
        if self._global_support_logged:
            return
        reason = self.global_hotkey_support_reason()
        if reason:
            suffix = " Start the hotkey helper from Settings to enable true global capture." if helper_ready else ""
            self.logger.log(
                f"Global hotkeys are unavailable in this session, so '{sequence}' is using application scope. {reason}{suffix}",
                "INFO",
            )
            self._global_support_logged = True

    def _clear_bindings(self) -> None:
        for shortcut in self._local_shortcuts:
            shortcut.setParent(None)
            shortcut.deleteLater()
        self._local_shortcuts.clear()
        if keyboard_backend is not None:
            for hotkey_handle in self._global_hotkeys:
                try:
                    keyboard_backend.remove_hotkey(hotkey_handle)
                except Exception:
                    pass
        self._global_hotkeys.clear()

    @Slot(str)
    def _dispatch_action(self, action_id: str) -> None:
        binding = self._actions.get(action_id)
        if binding is None:
            return
        try:
            binding.callback()
        except Exception as exc:
            self.logger.log(f"Shortcut '{action_id}' failed: {exc}", "ERROR")
