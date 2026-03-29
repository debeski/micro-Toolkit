from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from dngine import APP_NAME


class TrayManager:
    def __init__(self, services):
        self.services = services
        self.tray_icon: QSystemTrayIcon | None = None
        self._window = None
        self._menu: QMenu | None = None
        self._restore_action: QAction | None = None
        self._quick_clipboard_action: QAction | None = None
        self._clipboard_action: QAction | None = None
        self._settings_action: QAction | None = None
        self._workflows_action: QAction | None = None
        self._toggle_monitor_action: QAction | None = None
        self._quit_action: QAction | None = None

    def attach(self, window) -> None:
        self._window = window
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.services.log("System tray is not available in this session.", "WARNING")
            self._sync_application_quit_policy()
            return

        if self.tray_icon is None:
            icon = self._tray_icon(window)
            self.tray_icon = QSystemTrayIcon(icon, window)
            self.tray_icon.setToolTip(APP_NAME)
            self.tray_icon.activated.connect(self._handle_activation)
            self.tray_icon.setContextMenu(self._ensure_menu())
            self.services.i18n.language_changed.connect(self._refresh_menu)
        self.sync_visibility()

    def sync_visibility(self) -> None:
        if self.tray_icon is None:
            self._sync_application_quit_policy()
            return
        self._refresh_menu()
        self.tray_icon.setVisible(self.is_enabled())
        self._sync_application_quit_policy()

    def show_message(self, title: str, message: str) -> None:
        if self.tray_icon is not None:
            self.tray_icon.showMessage(title, message)

    def hide(self) -> None:
        if self.tray_icon is None:
            return
        self.tray_icon.hide()

    def is_enabled(self) -> bool:
        return self.tray_icon is not None

    def can_hide_to_tray(self) -> bool:
        return self.tray_icon is not None

    def _ensure_menu(self) -> QMenu:
        if self._menu is not None:
            return self._menu

        menu_parent = self._window
        self._menu = QMenu(menu_parent)

        self._restore_action = QAction(self._menu)
        self._restore_action.triggered.connect(lambda: self._defer(self._restore))
        self._menu.addAction(self._restore_action)

        self._quick_clipboard_action = QAction(self._menu)
        self._quick_clipboard_action.triggered.connect(lambda: self._defer(self.services.show_clipboard_quick_panel))
        self._menu.addAction(self._quick_clipboard_action)

        self._clipboard_action = QAction(self._menu)
        self._clipboard_action.triggered.connect(lambda: self._defer(self._open_window_plugin, "clip_snip"))
        self._menu.addAction(self._clipboard_action)

        self._settings_action = QAction(self._menu)
        self._settings_action.triggered.connect(lambda: self._defer(self._open_window_plugin, "command_center"))
        self._menu.addAction(self._settings_action)

        self._workflows_action = QAction(self._menu)
        self._workflows_action.triggered.connect(lambda: self._defer(self._open_window_plugin, "workflow_studio"))
        self._menu.addAction(self._workflows_action)

        self._menu.addSeparator()

        self._toggle_monitor_action = QAction(self._menu)
        self._toggle_monitor_action.triggered.connect(lambda: self._defer(self._toggle_monitor))
        self._menu.addAction(self._toggle_monitor_action)

        self._quit_action = QAction(self._menu)
        self._quit_action.triggered.connect(lambda: self._defer(self._quit_from_tray))
        self._menu.addAction(self._quit_action)

        self._refresh_menu()
        return self._menu

    def _refresh_menu(self) -> None:
        if self._menu is None:
            return
        tr = self.services.i18n.tr
        if self._restore_action is not None:
            self._restore_action.setText(tr("tray.menu.restore", "Restore"))
        if self._quick_clipboard_action is not None:
            self._quick_clipboard_action.setText(tr("tray.menu.clipboard_quick", "Quick Clipboard"))
        if self._clipboard_action is not None:
            self._clipboard_action.setText(tr("tray.menu.clipboard", "Clipboard"))
        if self._settings_action is not None:
            self._settings_action.setText(tr("tray.menu.settings", "Settings"))
        if self._workflows_action is not None:
            self._workflows_action.setText(tr("tray.menu.workflows", "Workflows"))
        if self._toggle_monitor_action is not None:
            self._toggle_monitor_action.setText(
                tr("tray.menu.stop_clip_monitor", "Stop Clip-Monitor")
                if self.services.clip_monitor_enabled()
                else tr("tray.menu.start_clip_monitor", "Enable Clip-Monitor")
            )
        if self._quit_action is not None:
            self._quit_action.setText(tr("tray.menu.quit_app", "Quit App"))

    def _handle_activation(self, reason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self._restore()

    def _restore(self) -> None:
        if self._window is None:
            return
        self._window.restore_from_tray()

    def _open_window_plugin(self, plugin_id: str) -> None:
        if self._window is None:
            return
        self._window.restore_from_tray()
        self._window.open_plugin(plugin_id)

    def _toggle_monitor(self) -> None:
        enabled = not self.services.clip_monitor_enabled()
        self.services.set_clip_monitor_enabled(enabled)
        self._refresh_menu()

    def _quit_from_tray(self) -> None:
        if self._window is None:
            return
        self._window.quit_from_tray()

    @staticmethod
    def _defer(callback, *args) -> None:
        QTimer.singleShot(0, lambda: callback(*args))

    def _tray_icon(self, window) -> QIcon:
        candidates = []
        if sys.platform == "darwin":
            candidates.extend(
                [
                    self.services.resource_path("icons/app-indicator.svg"),
                    self.services.resource_path("app.icns"),
                ]
            )
        candidates.append(self.services.resource_path("app.ico"))
        for icon_path in candidates:
            if icon_path.exists():
                icon = QIcon(str(icon_path))
                if not icon.isNull():
                    return icon
        return window.windowIcon()

    def _sync_application_quit_policy(self) -> None:
        app = self.services.application
        if app is None:
            return
        app.setQuitOnLastWindowClosed(not self.can_hide_to_tray())
