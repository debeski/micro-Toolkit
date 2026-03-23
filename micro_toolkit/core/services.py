from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from micro_toolkit.core.app_config import AppConfig
from micro_toolkit.core.autostart import AutostartManager
from micro_toolkit.core.clipboard_quick_panel import ClipboardQuickPanelController
from micro_toolkit.core.commands import CommandRegistry
from micro_toolkit.core.command_runtime import serialize_command_result
from micro_toolkit.core.elevated_broker import ElevatedBrokerManager
from micro_toolkit.core.elevation import ElevationManager
from micro_toolkit.core.hotkey_helper import HotkeyHelperManager
from micro_toolkit.core.i18n import TranslationManager
from micro_toolkit.core.plugin_manager import PluginManager
from micro_toolkit.core.plugin_packages import PluginPackageManager
from micro_toolkit.core.plugin_state import PluginStateManager
from micro_toolkit.core.session_manager import SessionManager
from micro_toolkit.core.shell_registry import DASHBOARD_PLUGIN_ID, NON_SIDEBAR_PLUGIN_IDS, SYSTEM_COMPONENT_PLUGIN_IDS, is_system_component
from micro_toolkit.core.shortcuts import ShortcutManager
from micro_toolkit.core.theme import ThemeManager
from micro_toolkit.core.tray import TrayManager
from micro_toolkit.core.workflows import WorkflowManager
from micro_toolkit.core.workers import Worker


class AppLogger(QObject):
    message_logged = Signal(str, str, str)
    status_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._history: list[tuple[str, str, str]] = []

    @Slot(str, str)
    def log(self, message: str, level: str = "INFO") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._history.append((timestamp, level, message))
        self.message_logged.emit(timestamp, level, message)
        self.status_changed.emit(message)

    def set_status(self, message: str) -> None:
        self.status_changed.emit(message)

    def history(self) -> list[tuple[str, str, str]]:
        return list(self._history)


class AppServices(QObject):
    quick_access_changed = Signal()
    plugin_visuals_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.app_root = Path(__file__).resolve().parents[1]
        self.runtime_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else self.app_root.parent
        # Determine data and output roots based on frozen state and platform
        if getattr(sys, "frozen", False):
            if os.name == "nt":
                base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Micro Toolkit"
            elif sys.platform == "darwin":
                base = Path.home() / "Library" / "Application Support" / "Micro Toolkit"
            else:
                base = Path.home() / ".local" / "share" / "micro-toolkit"
            
            self.data_root = base / "data"
            self.output_root = base / "output"
        else:
            self.data_root = self.runtime_root / "data"
            self.output_root = self.runtime_root / "output"

        self.assets_root = self.app_root / "assets"
        self.locales_root = self.app_root / "i18n"
        self.plugins_root = self.app_root / "plugins"
        self.builtin_manifest_path = self.app_root / "builtin_plugin_manifest.json"
        self.custom_plugins_root = self.data_root / "plugins"
        self.workflows_root = self.data_root / "workflows"
        self.config_path = self.data_root / "micro_toolkit_config.json"
        self.database_path = self.data_root / "micro_toolkit.db"
        self.plugin_state_path = self.data_root / "plugin_state.json"
        self._migrate_legacy_runtime_files()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.custom_plugins_root.mkdir(parents=True, exist_ok=True)
        self.config = AppConfig(self.config_path, self.output_root)
        self.session_manager = SessionManager(self.database_path)
        self.logger = AppLogger()
        self.thread_pool = QThreadPool.globalInstance()
        self.application = None
        self.main_window = None
        self.hotkey_helper_manager = HotkeyHelperManager(self.data_root, self.logger)
        self.elevated_broker = ElevatedBrokerManager(
            self.data_root,
            self.output_root,
            self.assets_root,
            self.plugins_root,
            self.builtin_manifest_path,
            self.custom_plugins_root,
            self.plugin_state_path,
            self.logger,
        )
        self.plugin_state_manager = PluginStateManager(self.plugin_state_path)
        self.plugin_manager = PluginManager(
            self.plugins_root,
            self.custom_plugins_root,
            self.plugin_state_manager,
            builtin_manifest_path=self.builtin_manifest_path,
            enforce_builtin_manifest=getattr(sys, "frozen", False),
        )
        self.plugin_package_manager = PluginPackageManager(
            self.plugin_manager,
            self.custom_plugins_root,
            self.plugin_state_manager,
        )
        self.command_registry = CommandRegistry()
        self._plugin_commands_registered = False
        self.elevation_manager = ElevationManager()
        self.i18n = TranslationManager(self.config, self.locales_root)
        self.theme_manager = ThemeManager(self.config, self.assets_root)
        self.autostart_manager = AutostartManager()
        self.workflow_manager = WorkflowManager(self.workflows_root)
        self.shortcut_manager = ShortcutManager(self.config, self.logger, helper_manager=self.hotkey_helper_manager)
        self.clipboard_quick_panel = ClipboardQuickPanelController(self)
        self.tray_manager = TrayManager(self)
        self.reset_command_registry()

    def resource_path(self, relative_path: str) -> Path:
        return self.assets_root / relative_path

    def plugin_text(self, plugin_id: str, key: str, default: str | None = None, **kwargs) -> str:
        return self.plugin_manager.plugin_text(plugin_id, self.i18n.current_language(), key, default, **kwargs)

    def plugin_display_name(self, spec_or_plugin_id) -> str:
        spec = spec_or_plugin_id if hasattr(spec_or_plugin_id, "plugin_id") else self.plugin_manager.get_spec(str(spec_or_plugin_id))
        if spec is None:
            return str(spec_or_plugin_id)
        default_name = spec.localized_name(self.i18n.current_language())
        if is_system_component(spec.plugin_id):
            return default_name
        if not spec.allow_name_override:
            return default_name
        overrides = self.config.get("plugin_overrides") or {}
        if not isinstance(overrides, dict):
            return default_name
        plugin_override = overrides.get(spec.plugin_id, {})
        if not isinstance(plugin_override, dict):
            return default_name
        custom_name = str(plugin_override.get("display_name", "")).strip()
        return custom_name or default_name

    def plugin_icon_override(self, spec: PluginSpec) -> str:
        if is_system_component(spec.plugin_id):
            return ""
        if not spec.allow_icon_override:
            return ""
        overrides = self.config.get("plugin_overrides") or {}
        if not isinstance(overrides, dict):
            return ""
        plugin_override = overrides.get(spec.plugin_id, {})
        if not isinstance(plugin_override, dict):
            return ""
        return str(plugin_override.get("icon", "")).strip()

    def plugin_override(self, plugin_id: str) -> dict[str, str]:
        if is_system_component(plugin_id):
            return {"display_name": "", "icon": ""}
        overrides = self.config.get("plugin_overrides") or {}
        if not isinstance(overrides, dict):
            return {"display_name": "", "icon": ""}
        plugin_override = overrides.get(plugin_id, {})
        if not isinstance(plugin_override, dict):
            return {"display_name": "", "icon": ""}
        return {
            "display_name": str(plugin_override.get("display_name", "")).strip(),
            "icon": str(plugin_override.get("icon", "")).strip(),
        }

    def set_plugin_override(self, plugin_id: str, *, display_name: str = "", icon: str = "") -> dict[str, str]:
        if is_system_component(plugin_id):
            return {"display_name": "", "icon": ""}
        overrides = self.config.get("plugin_overrides") or {}
        if not isinstance(overrides, dict):
            overrides = {}
        current = dict(overrides.get(plugin_id, {})) if isinstance(overrides.get(plugin_id, {}), dict) else {}
        display_name = str(display_name).strip()
        icon = str(icon).strip()
        if display_name:
            current["display_name"] = display_name
        else:
            current.pop("display_name", None)
        if icon:
            current["icon"] = icon
        else:
            current.pop("icon", None)
        if current:
            overrides[plugin_id] = current
        else:
            overrides.pop(plugin_id, None)
        self.config.set("plugin_overrides", overrides)
        self.plugin_visuals_changed.emit(plugin_id)
        if self.main_window is not None:
            self.main_window.refresh_plugin_visuals(plugin_id)
        return self.plugin_override(plugin_id)

    def attach_application(self, application) -> None:
        self.application = application
        self.i18n.apply(application)
        self.theme_manager.apply(application)

    def attach_main_window(self, main_window) -> None:
        self.main_window = main_window
        self.shortcut_manager.attach(main_window)
        self.tray_manager.attach(main_window)

    def log(self, message: str, level: str = "INFO") -> None:
        self.logger.log(message, level)

    def record_run(self, tool_id: str, status: str, details: str = "") -> None:
        self.session_manager.log_run(tool_id, status, details)

    def request_elevated(self, capability_id: str, payload: dict[str, object] | None = None, *, timeout_seconds: float = 20.0):
        return self.elevated_broker.request(capability_id, payload, timeout_seconds=timeout_seconds)

    def default_output_path(self) -> Path:
        configured = self.config.get("default_output_path")
        if configured:
            output_path = Path(configured)
            output_path.mkdir(parents=True, exist_ok=True)
            return output_path
        self.output_root.mkdir(parents=True, exist_ok=True)
        return self.output_root

    def set_theme(self, mode: str) -> str:
        self.theme_manager.set_mode(mode)
        if self.application is not None:
            self.theme_manager.apply(self.application)
        return self.theme_manager.current_mode()

    def set_language(self, language: str) -> str:
        self.i18n.set_language(language)
        if self.application is not None:
            self.i18n.apply(self.application)
        return self.i18n.current_language()

    def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> None:
        if is_system_component(plugin_id):
            return
        self.plugin_state_manager.set_enabled(plugin_id, enabled)
        self.reload_plugins()

    def set_plugin_hidden(self, plugin_id: str, hidden: bool) -> None:
        if is_system_component(plugin_id):
            return
        self.plugin_state_manager.set_hidden(plugin_id, hidden)
        self.reload_plugins()

    def manageable_plugin_specs(self, *, include_disabled: bool = False):
        return [
            spec
            for spec in self.plugin_manager.discover_plugins(include_disabled=include_disabled)
            if spec.plugin_id not in SYSTEM_COMPONENT_PLUGIN_IDS
        ]

    def pinnable_plugin_specs(self):
        return [
            spec
            for spec in self.plugin_manager.sidebar_plugins()
            if spec.plugin_id not in NON_SIDEBAR_PLUGIN_IDS
            and spec.plugin_id != DASHBOARD_PLUGIN_ID
        ]

    def quick_access_ids(self) -> list[str]:
        raw = self.config.get("quick_access") or []
        if not isinstance(raw, list):
            raw = []
        allowed = {spec.plugin_id for spec in self.pinnable_plugin_specs()}
        seen: set[str] = set()
        ordered: list[str] = []
        for plugin_id in raw:
            normalized = str(plugin_id).strip()
            if not normalized or normalized not in allowed or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    def set_quick_access_ids(self, plugin_ids: list[str]) -> list[str]:
        normalized: list[str] = []
        allowed = {spec.plugin_id for spec in self.pinnable_plugin_specs()}
        seen: set[str] = set()
        for plugin_id in plugin_ids:
            value = str(plugin_id).strip()
            if not value or value not in allowed or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        self.config.set("quick_access", normalized)
        self.quick_access_changed.emit()
        if self.main_window is not None:
            self.main_window.refresh_sidebar()
        return normalized

    def toggle_quick_access(self, plugin_id: str) -> bool:
        current = self.quick_access_ids()
        if plugin_id in current:
            updated = [item for item in current if item != plugin_id]
            self.set_quick_access_ids(updated)
            return False
        current.append(plugin_id)
        self.set_quick_access_ids(current)
        return True

    def is_quick_access(self, plugin_id: str) -> bool:
        return plugin_id in self.quick_access_ids()

    def reset_command_registry(self) -> None:
        self.command_registry.clear()
        self._plugin_commands_registered = False
        self.register_core_commands()

    def ensure_plugin_commands_registered(self) -> None:
        if self._plugin_commands_registered:
            return

        from micro_toolkit.core.builtin_tool_commands import register_builtin_tool_commands

        register_builtin_tool_commands(self.command_registry, self)

        for spec in self.plugin_manager.discover_plugins():
            try:
                plugin = self.plugin_manager.load_plugin(spec.plugin_id)
                plugin.register_commands(self.command_registry, self)
            except Exception as exc:
                if spec.source_type == "custom":
                    self.plugin_state_manager.record_failure(spec.plugin_id, str(exc))
                self.log(f"Skipping command registration for plugin '{spec.plugin_id}': {exc}", "WARNING")

        self._plugin_commands_registered = True

    def serialize_result(self, payload: object):
        return serialize_command_result(payload)

    def _migrate_legacy_runtime_files(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        legacy_data_root = self.app_root / "data"
        legacy_pairs = [
            (self.data_root / "qt_toolkit_config.json", self.config_path),
            (self.data_root / "micro_toolkit_qt.db", self.database_path),
            (legacy_data_root / "micro_toolkit_config.json", self.config_path),
            (legacy_data_root / "micro_toolkit.db", self.database_path),
            (legacy_data_root / "plugin_state.json", self.plugin_state_path),
        ]
        for legacy_path, target_path in legacy_pairs:
            if legacy_path.exists() and not target_path.exists():
                try:
                    shutil.move(str(legacy_path), str(target_path))
                except Exception:
                    pass
        legacy_plugins_root = legacy_data_root / "plugins"
        if legacy_plugins_root.exists() and not self.custom_plugins_root.exists():
            try:
                shutil.move(str(legacy_plugins_root), str(self.custom_plugins_root))
            except Exception:
                pass
        legacy_workflows_root = legacy_data_root / "workflows"
        if legacy_workflows_root.exists() and not self.workflows_root.exists():
            try:
                shutil.move(str(legacy_workflows_root), str(self.workflows_root))
            except Exception:
                pass

    def reload_plugins(self) -> None:
        self.plugin_manager.invalidate_cache(clear_instances=True)
        self.reset_command_registry()
        if self.main_window is not None:
            self.main_window.reload_plugin_catalog(preferred_plugin_id="settings_center")

    def register_core_commands(self) -> None:
        self.command_registry.register(
            "plugins.list",
            "List Plugins",
            "Return all discovered plugins.",
            lambda: [
                {
                    "plugin_id": spec.plugin_id,
                    "name": spec.localized_name(self.i18n.current_language()),
                    "category": spec.localized_category(self.i18n.current_language()),
                    "standalone": spec.standalone,
                    "enabled": spec.enabled,
                    "hidden": spec.hidden,
                    "source_type": spec.source_type,
                }
                for spec in self.plugin_manager.discover_plugins(include_disabled=True)
            ],
        )
        self.command_registry.register(
            "plugins.info",
            "Plugin Details",
            "Return metadata for one plugin.",
            lambda plugin_id: self._plugin_info(plugin_id),
        )
        self.command_registry.register(
            "broker.elevated.capabilities",
            "Elevated Broker Capabilities",
            "Return the elevated broker capability catalog.",
            lambda: self.elevated_broker.list_capabilities(),
        )
        self.command_registry.register(
            "history.show",
            "History",
            "Return recent session history.",
            lambda limit=20: self.session_manager.get_history(limit=max(1, int(limit))),
        )
        self.command_registry.register(
            "app.set_theme",
            "Set Theme",
            "Switch theme mode.",
            lambda mode: {"theme": self.set_theme(mode)},
        )
        self.command_registry.register(
            "app.set_language",
            "Set Language",
            "Switch application language and layout direction.",
            lambda language: {"language": self.set_language(language)},
        )
        self.command_registry.register(
            "app.focus_search",
            "Focus Search",
            "Focus the sidebar filter box.",
            lambda: self._require_window().focus_search(),
        )
        self.command_registry.register(
            "app.toggle_activity",
            "Toggle Activity",
            "Show or hide the activity dock.",
            lambda: self._require_window().toggle_activity_dock(),
        )
        self.command_registry.register(
            "app.restore_window",
            "Restore Window",
            "Restore the main window.",
            lambda: self._require_window().restore_from_tray(),
        )
        self.command_registry.register(
            "app.open_plugin",
            "Open Plugin",
            "Open a plugin page in the shell.",
            lambda plugin_id: self._command_open_plugin(plugin_id),
        )
        self.command_registry.register(
            "app.show_settings",
            "Open Settings",
            "Open the settings page.",
            lambda: self._command_open_plugin("settings_center"),
        )
        self.command_registry.register(
            "app.show_workflows",
            "Open Workflows",
            "Open the workflows page.",
            lambda: self._command_open_plugin("workflow_studio"),
        )
        self.command_registry.register(
            "app.show_clipboard",
            "Open Clipboard",
            "Open the clipboard page.",
            lambda: self._command_open_plugin("clip_manager"),
        )
        self.command_registry.register(
            "app.show_clipboard_quick_panel",
            "Toggle Clipboard Quick Panel",
            "Show or hide the quick clipboard history panel.",
            lambda: self._toggle_clipboard_quick_panel(),
        )
        self.command_registry.register(
            "app.start_hotkey_helper",
            "Start Hotkey Helper",
            "Start the elevated hotkey helper for this session.",
            lambda: self._start_hotkey_helper(),
        )
        self.command_registry.register(
            "app.stop_hotkey_helper",
            "Stop Hotkey Helper",
            "Stop the elevated hotkey helper for this session.",
            lambda: self._stop_hotkey_helper(),
        )
        self.command_registry.register(
            "app.start_elevated_broker",
            "Start Elevated Broker",
            "Start the capability-based elevated broker for this session.",
            lambda: self._start_elevated_broker(),
        )
        self.command_registry.register(
            "app.stop_elevated_broker",
            "Stop Elevated Broker",
            "Stop the capability-based elevated broker for this session.",
            lambda: self._stop_elevated_broker(),
        )
        self.command_registry.register(
            "app.restart_elevated",
            "Restart Elevated",
            "Relaunch the app with elevation when the platform supports it.",
            lambda: self._restart_elevated(),
        )

    def run_task(
        self,
        task_fn,
        *,
        on_result=None,
        on_error=None,
        on_finished=None,
        on_progress=None,
    ) -> Worker:
        worker = Worker(task_fn)
        worker.signals.log.connect(self.logger.log)
        if on_result is not None:
            worker.signals.result.connect(on_result)
        if on_error is not None:
            worker.signals.error.connect(on_error)
        else:
            worker.signals.error.connect(self._default_worker_error)
        if on_finished is not None:
            worker.signals.finished.connect(on_finished)
        if on_progress is not None:
            worker.signals.progress.connect(on_progress)
        self.thread_pool.start(worker)
        return worker

    @Slot(object)
    def _default_worker_error(self, payload: object) -> None:
        if isinstance(payload, dict):
            message = payload.get("message", "Unknown worker error")
            trace = payload.get("traceback", "")
            self.logger.log(message, "ERROR")
            if trace:
                self.logger.log(trace, "ERROR")
            return
        self.logger.log(str(payload), "ERROR")

    def _plugin_info(self, plugin_id: str) -> dict:
        spec = self.plugin_manager.get_spec(plugin_id)
        if spec is None:
            raise KeyError(f"Unknown plugin id: {plugin_id}")
        return {
            "plugin_id": spec.plugin_id,
            "name": spec.localized_name(self.i18n.current_language()),
            "description": spec.localized_description(self.i18n.current_language()),
            "category": spec.localized_category(self.i18n.current_language()),
            "version": spec.version,
            "standalone": spec.standalone,
            "enabled": spec.enabled,
            "hidden": spec.hidden,
            "trusted": spec.trusted,
            "quarantined": spec.quarantined,
            "signature_status": spec.signature_status,
            "signer": spec.signer,
            "risk_level": spec.risk_level,
            "risk_summary": spec.risk_summary,
            "last_error": spec.last_error,
            "failure_count": spec.failure_count,
            "source_type": spec.source_type,
            "file_path": str(spec.file_path),
        }

    def _command_open_plugin(self, plugin_id: str):
        window = self._require_window()
        window.open_plugin(plugin_id)
        return {"plugin_id": plugin_id}

    def _toggle_clipboard_quick_panel(self):
        self._require_window()
        self.clipboard_quick_panel.toggle()
        return {"visible": True}

    def _restart_elevated(self):
        success, message = self.elevation_manager.relaunch_elevated()
        if not success:
            raise RuntimeError(message)
        if self.application is not None:
            self.application.quit()
        return {"restarted": True, "message": message}

    def _start_hotkey_helper(self):
        bindings = self.shortcut_manager.global_binding_sequences()
        success, message = self.hotkey_helper_manager.enable_for_session(bindings)
        if not success:
            raise RuntimeError(message)
        self.shortcut_manager.apply()
        return {"started": True, "message": message}

    def _stop_hotkey_helper(self):
        self.hotkey_helper_manager.disable_for_session()
        self.shortcut_manager.apply()
        return {"stopped": True, "message": "Hotkey helper stopped."}

    def _start_elevated_broker(self):
        success, message = self.elevated_broker.start()
        if not success:
            raise RuntimeError(message)
        return {"started": True, "message": message}

    def _stop_elevated_broker(self):
        success, message = self.elevated_broker.stop()
        if not success:
            raise RuntimeError(message)
        return {"stopped": True, "message": message}

    def _require_window(self):
        if self.main_window is None:
            raise RuntimeError("This command requires the GUI main window.")
        return self.main_window
