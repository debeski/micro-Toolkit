from __future__ import annotations

import sys
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from micro_toolkit import __version__
from micro_toolkit.app import MicroToolkitWindow
from micro_toolkit.core.services import AppServices


_WIN_MUTEX = None


def launch_gui(*, initial_plugin_id: str | None = None, start_minimized: bool = False) -> int:
    global _WIN_MUTEX
    if os.name == "nt":
        try:
            import ctypes
            _WIN_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "MicroToolkitMutex")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("Micro Toolkit")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Debeski")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(True)

    services = AppServices()
    services.attach_application(app)
    icon_path = services.resource_path("app.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    style_hints = app.styleHints()
    try:
        style_hints.colorSchemeChanged.connect(lambda _scheme: services.theme_manager.refresh_system_mode(app))
    except Exception:
        pass

    window = MicroToolkitWindow(services, initial_plugin_id=initial_plugin_id)
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
    window.show()
    should_start_minimized = start_minimized or bool(services.config.get("start_minimized"))
    if should_start_minimized:
        if services.tray_manager.tray_icon is not None:
            window.hide()
        else:
            window.showMinimized()
    return app.exec()


def main() -> int:
    return launch_gui()
