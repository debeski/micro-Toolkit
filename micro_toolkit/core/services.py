from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal, Slot

from micro_toolkit.core.app_config import AppConfig
from micro_toolkit.core.autostart import AutostartManager
from micro_toolkit.core.backup_manager import BackupManager
from micro_toolkit.core.clip_monitor import ClipMonitorManager
from micro_toolkit.core.clipboard_quick_panel import ClipboardQuickPanelController
from micro_toolkit.core.commands import CommandRegistry
from micro_toolkit.core.command_runtime import serialize_command_result
from micro_toolkit.core.elevated_broker import ElevatedBrokerManager
from micro_toolkit.core.elevation import ElevationManager
from micro_toolkit.core.hotkey_helper import HotkeyHelperManager
from micro_toolkit.core.i18n import TranslationManager
from micro_toolkit.core.plugin_dependencies import PluginDependencyManager
from micro_toolkit.core.plugin_manager import PluginManager
from micro_toolkit.core.plugin_packages import PluginPackageManager
from micro_toolkit.core.plugin_state import PluginStateManager
from micro_toolkit.core.session_manager import SessionManager
from micro_toolkit.core.shell_registry import DASHBOARD_PLUGIN_ID, NON_SIDEBAR_PLUGIN_IDS, SYSTEM_COMPONENT_PLUGIN_IDS, is_system_component
from micro_toolkit.core.shortcuts import ShortcutManager
from micro_toolkit.core.theme import ThemeManager
from micro_toolkit.core.tray import TrayManager
from micro_toolkit.core.ui_inspector import UIInspector
from micro_toolkit.core.workflows import WorkflowManager
from micro_toolkit.core.workers import Worker

PLUGIN_ID_MIGRATIONS = {
    "validator": "data_link_auditor",
    "seq": "sequence_auditor",
    "exporter": "folder_mapper",
    "dups": "deep_scan_auditor",
    "quick_analytics": "chart_builder",
    "about_center": "about_info",
    "clip_manager": "clip_snip",
    "inspector_center": "dev_lab",
    "settings_center": "command_center",
    "welcome_overview": "dash_hub",
}


def _standard_storage_root() -> Path:
    override = str(os.environ.get("MICRO_TOOLKIT_HOME", "")).strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Micro Toolkit"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Micro Toolkit"
    xdg_data_home = str(os.environ.get("XDG_DATA_HOME", "")).strip()
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / "micro-toolkit"
    return Path.home() / ".local" / "share" / "micro-toolkit"


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


class _ShellTaskBridge(QObject):
    def __init__(self, services: "AppServices", task_id: int):
        super().__init__(services)
        self._services = services
        self._task_id = task_id

    @Slot(float)
    def handle_progress(self, value: float) -> None:
        self._services._update_shell_task_progress(self._task_id, value)

    @Slot()
    def handle_finished(self) -> None:
        self._services._finish_shell_task_progress(self._task_id)

    @Slot(object)
    def handle_finished_payload(self, _payload: object) -> None:
        self._services._finish_shell_task_progress(self._task_id)


class AppServices(QObject):
    quick_access_changed = Signal()
    plugin_visuals_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.app_root = Path(__file__).resolve().parents[1]
        self.runtime_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else self.app_root.parent
        self.storage_root = _standard_storage_root()
        self.data_root = self.storage_root / "data"
        self.output_root = self.storage_root / "output"

        self.assets_root = self.app_root / "assets"
        self.locales_root = self.app_root / "i18n"
        self.plugins_root = self.app_root / "plugins"
        self.builtin_manifest_path = self.app_root / "builtin_plugin_manifest.json"
        self.custom_plugins_root = self.data_root / "plugins"
        self.workflows_root = self.data_root / "workflows"
        self.config_path = self.data_root / "micro_toolkit_config.json"
        self.database_path = self.data_root / "micro_toolkit.db"
        self.plugin_state_path = self.data_root / "plugin_state.json"
        self.plugin_dependency_state_path = self.data_root / "plugin_dependency_state.json"
        self.plugin_dependency_root = self.data_root / "plugin_deps"
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.custom_plugins_root.mkdir(parents=True, exist_ok=True)
        self.plugin_dependency_root.mkdir(parents=True, exist_ok=True)
        self.config = AppConfig(self.config_path, self.output_root)
        self.config.migrate_plugin_ids(PLUGIN_ID_MIGRATIONS)
        self.session_manager = SessionManager(self.database_path)
        self.logger = AppLogger()
        self.thread_pool = QThreadPool.globalInstance()
        self.application = None
        self.main_window = None
        self._visual_refresh_pending = False
        self._shell_task_sequence = 0
        self._shell_task_entries: dict[int, dict[str, object]] = {}
        self._visual_refresh_timer = QTimer(self)
        self._visual_refresh_timer.setSingleShot(True)
        self._visual_refresh_timer.timeout.connect(self._apply_pending_visual_refresh)
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
        self.plugin_state_manager.migrate_plugin_ids(PLUGIN_ID_MIGRATIONS)
        self.plugin_manager = PluginManager(
            self.plugins_root,
            self.custom_plugins_root,
            self.plugin_state_manager,
            builtin_manifest_path=self.builtin_manifest_path,
            enforce_builtin_manifest=getattr(sys, "frozen", False),
        )
        self.plugin_dependency_manager = PluginDependencyManager(
            self.plugin_manager,
            self.plugin_dependency_root,
            self.plugin_dependency_state_path,
        )
        self.plugin_dependency_manager.migrate_plugin_ids(PLUGIN_ID_MIGRATIONS)
        self.plugin_manager.dependency_paths_resolver = self.plugin_dependency_manager.dependency_paths_for_spec
        self.plugin_manager.dependency_summary_resolver = self.plugin_dependency_manager.summary_for_spec
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
        self.backup_manager = BackupManager(self.config, self.runtime_root, self.app_root, self.data_root, self.output_root, self.logger)
        self.autostart_manager = AutostartManager()
        self.workflow_manager = WorkflowManager(self.workflows_root)
        self.shortcut_manager = ShortcutManager(self.config, self.logger, helper_manager=self.hotkey_helper_manager)
        self.clip_monitor_manager = ClipMonitorManager(self.config, self.data_root)
        self.clipboard_quick_panel = ClipboardQuickPanelController(self)
        self.tray_manager = TrayManager(self)
        self.ui_inspector = UIInspector()
        self.ui_inspector.set_enabled(self.developer_mode_enabled())
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
        self.ui_inspector.attach_application(application)
        try:
            self.backup_manager.maybe_create_scheduled_backup()
        except Exception as exc:
            self.logger.log(f"Scheduled backup skipped: {exc}", "WARNING")

    def attach_main_window(self, main_window) -> None:
        self.main_window = main_window
        self.shortcut_manager.attach(main_window)
        self.tray_manager.attach(main_window)
        self.ui_inspector.attach_main_window(main_window)
        self._sync_clip_monitor_runtime()

    def log(self, message: str, level: str = "INFO") -> None:
        self.logger.log(message, level)

    def record_run(self, tool_id: str, status: str, details: str = "") -> None:
        self.session_manager.log_run(tool_id, status, details)

    def request_elevated(self, capability_id: str, payload: dict[str, object] | None = None, *, timeout_seconds: float = 20.0):
        return self.elevated_broker.request(capability_id, payload, timeout_seconds=timeout_seconds)

    def developer_mode_enabled(self) -> bool:
        env_value = str(os.environ.get("MICRO_TOOLKIT_DEV", "")).strip().lower()
        if env_value in {"1", "true", "yes", "on"}:
            return True
        return bool(self.config.get("developer_mode"))

    def set_developer_mode(self, enabled: bool) -> bool:
        persisted = bool(enabled)
        self.config.set("developer_mode", persisted)
        active = self.developer_mode_enabled()
        self.ui_inspector.set_enabled(active)
        if self.main_window is not None:
            refresh = getattr(self.main_window, "refresh_system_toolbar_visibility", None)
            if callable(refresh):
                refresh()
        return active

    def create_backup(self, *, reason: str = "manual") -> Path:
        return self.backup_manager.create_backup(reason=reason)

    def restore_backup(self, backup_path: Path) -> dict[str, object]:
        return self.backup_manager.restore_backup(backup_path, elevated_requester=self.request_elevated)

    def default_output_path(self) -> Path:
        configured = self.config.get("default_output_path")
        if configured:
            output_path = Path(configured)
            output_path.mkdir(parents=True, exist_ok=True)
            return output_path
        self.output_root.mkdir(parents=True, exist_ok=True)
        return self.output_root

    def set_theme(self, theme_name: str) -> str:
        selected = self.theme_manager.set_color(theme_name)
        self.theme_manager.save_to_config()
        self._schedule_visual_refresh("Applying theme...")
        return selected

    def set_theme_selection(self, color_key: str, dark_enabled: bool) -> str:
        selected = self.theme_manager.theme_name_for(color_key, dark_enabled)
        self.theme_manager.set_theme(selected)
        self.theme_manager.save_to_config()
        self._schedule_visual_refresh("Applying theme...")
        return selected

    def set_dark_mode(self, enabled: bool) -> str:
        selected = self.theme_manager.set_dark_mode(enabled)
        self.theme_manager.save_to_config()
        self._schedule_visual_refresh("Applying theme...")
        return selected

    def set_density_scale(self, density: int) -> int:
        selected = self.theme_manager.set_density_scale(density)
        self.theme_manager.save_to_config()
        self._schedule_visual_refresh("Refreshing layout...")
        return selected

    def set_ui_scaling(self, scale: float) -> float:
        normalized = self.theme_manager.set_ui_scaling(scale)
        self.theme_manager.save_to_config()
        self._schedule_visual_refresh("Refreshing layout...")
        return normalized

    def set_language(self, language: str) -> str:
        self.i18n.set_language(language)
        self.i18n.save_to_config()
        if self.application is not None:
            self.i18n.apply(self.application)
        self.clip_monitor_manager.refresh_preferences()
        return self.i18n.current_language()

    def restore_live_preferences_from_config(self) -> None:
        self.theme_manager.load_from_config()
        self.i18n.load_from_config()
        if self.application is not None:
            self.theme_manager.apply(self.application)
            self.i18n.apply(self.application)

    def _schedule_visual_refresh(self, message: str) -> None:
        if self.application is None:
            return
        if self.main_window is not None and not self._visual_refresh_pending:
            self.main_window.begin_visual_refresh(message)
            self._visual_refresh_pending = True
        self._visual_refresh_timer.start(90)

    def _apply_pending_visual_refresh(self) -> None:
        if self.application is None:
            self._visual_refresh_pending = False
            return
        try:
            self.theme_manager.apply(self.application)
            self.clip_monitor_manager.refresh_preferences()
        finally:
            if self.main_window is not None and self._visual_refresh_pending:
                self.main_window.end_visual_refresh()
            self._visual_refresh_pending = False

    def _start_shell_task_progress(self, status_text: str | None = None) -> int | None:
        if self.main_window is None:
            return None
        self._shell_task_sequence += 1
        task_id = self._shell_task_sequence
        self._shell_task_entries[task_id] = {
            "has_progress": False,
            "progress": 0.0,
        }
        if status_text:
            self.logger.set_status(status_text)
        self._refresh_shell_task_progress()
        return task_id

    def _update_shell_task_progress(self, task_id: int, value: float) -> None:
        entry = self._shell_task_entries.get(task_id)
        if entry is None:
            return
        entry["has_progress"] = True
        entry["progress"] = max(0.0, min(1.0, float(value)))
        self._refresh_shell_task_progress()

    def _finish_shell_task_progress(self, task_id: int) -> None:
        self._shell_task_entries.pop(task_id, None)
        self._refresh_shell_task_progress()

    def _refresh_shell_task_progress(self) -> None:
        if self.main_window is None:
            return
        if not self._shell_task_entries:
            self.main_window.hide_task_progress()
            return
        task_id = next(reversed(self._shell_task_entries))
        entry = self._shell_task_entries.get(task_id, {})
        if entry.get("has_progress"):
            self.main_window.show_task_progress(int(round(float(entry.get("progress", 0.0)) * 100)))
        else:
            self.main_window.show_task_progress(None)

    def clip_monitor_enabled(self) -> bool:
        return bool(self.config.get("clip_monitor_enabled"))

    def set_clip_monitor_enabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        self.config.set("clip_monitor_enabled", enabled)
        self.autostart_manager.set_clip_monitor_enabled(enabled)
        self._sync_clip_monitor_runtime()
        self.tray_manager.sync_visibility()
        return enabled

    def show_clipboard_quick_panel(self) -> bool:
        if self.main_window is not None:
            self.clipboard_quick_panel.toggle()
            return True
        if self.clip_monitor_enabled() and self.clip_monitor_manager.ensure_running():
            return self.clip_monitor_manager.toggle_quick_panel()
        return True

    def notify_clip_monitor_app_state(self, active: bool) -> None:
        if not self.clip_monitor_enabled():
            return
        if self.clip_monitor_manager.ensure_running():
            self.clip_monitor_manager.set_app_active(
                active,
                os.getpid() if active else None,
                prefer_helper=self.hotkey_helper_manager.is_active(),
            )

    def _sync_clip_monitor_runtime(self) -> None:
        if self.clip_monitor_enabled():
            self.clip_monitor_manager.ensure_running()
            self.clip_monitor_manager.set_app_active(
                self.main_window is not None,
                os.getpid() if self.main_window is not None else None,
                prefer_helper=self.hotkey_helper_manager.is_active(),
            )
            self.clip_monitor_manager.refresh_preferences()
        else:
            if self.clip_monitor_manager.is_running():
                self.clip_monitor_manager.stop(persist_disabled=False)

    def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> None:
        if is_system_component(plugin_id):
            return
        self.plugin_state_manager.set_enabled(plugin_id, enabled)
        self.refresh_plugin_catalog_views()

    def set_plugin_hidden(self, plugin_id: str, hidden: bool) -> None:
        if is_system_component(plugin_id):
            return
        self.plugin_state_manager.set_hidden(plugin_id, hidden)
        self.refresh_plugin_catalog_views()

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

    def reload_plugins(self) -> None:
        self.plugin_manager.invalidate_cache(clear_instances=True)
        self.reset_command_registry()
        if self.main_window is not None:
            self.main_window.reload_plugin_catalog(preferred_plugin_id="command_center")

    def refresh_plugin_catalog_views(self) -> None:
        self.plugin_manager.invalidate_cache(clear_instances=True)
        self.reset_command_registry()
        if self.main_window is not None:
            self.main_window.refresh_sidebar()

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
            "Switch the active theme color family.",
            lambda mode: {"theme": self.set_theme(mode)},
        )
        self.command_registry.register(
            "app.set_dark_mode",
            "Set Dark Mode",
            "Enable or disable dark mode.",
            lambda enabled=False: {"theme": self.set_dark_mode(bool(enabled))},
        )
        self.command_registry.register(
            "app.set_density",
            "Set Density",
            "Adjust Qt-Material density scale.",
            lambda density=0: {"density_scale": self.set_density_scale(int(density))},
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
            "app.toggle_terminal",
            "Toggle Terminal",
            "Show or hide the terminal dock.",
            lambda: self._require_window().toggle_terminal_dock(),
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
            lambda: self._command_open_plugin("command_center"),
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
            lambda: self._command_open_plugin("clip_snip"),
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
        status_text: str | None = None,
    ) -> Worker:
        worker = Worker(task_fn)
        shell_task_id = self._start_shell_task_progress(status_text)
        worker.signals.log.connect(self.logger.log)
        if shell_task_id is not None:
            shell_task_bridge = _ShellTaskBridge(self, shell_task_id)
            worker._shell_task_bridge = shell_task_bridge
            worker.signals.progress.connect(shell_task_bridge.handle_progress)
            worker.signals.result.connect(shell_task_bridge.handle_finished_payload)
            worker.signals.error.connect(shell_task_bridge.handle_finished_payload)
            worker.signals.finished.connect(shell_task_bridge.handle_finished)
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
        self.show_clipboard_quick_panel()
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
