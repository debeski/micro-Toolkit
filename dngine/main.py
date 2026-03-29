from __future__ import annotations

import sys
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from dngine import APP_NAME, __version__
from dngine.app import DNgineWindow
from dngine.core.services import AppServices


_WIN_MUTEX = None


def _restore_macos_dock_icon() -> None:
    if sys.platform != "darwin":
        return
    try:
        import objc  # type: ignore[import-untyped]
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular  # type: ignore[import-untyped]

        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyRegular)
        return
    except Exception:
        pass
    try:
        import ctypes
        import ctypes.util

        objc_lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc") or "/usr/lib/libobjc.dylib")
        objc_lib.objc_getClass.restype = ctypes.c_void_p
        objc_lib.objc_getClass.argtypes = [ctypes.c_char_p]
        objc_lib.sel_registerName.restype = ctypes.c_void_p
        objc_lib.sel_registerName.argtypes = [ctypes.c_char_p]
        objc_lib.objc_msgSend.restype = ctypes.c_void_p
        objc_lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        nsapp_cls = objc_lib.objc_getClass(b"NSApplication")
        shared_sel = objc_lib.sel_registerName(b"sharedApplication")
        ns_app = objc_lib.objc_msgSend(nsapp_cls, shared_sel)
        policy_sel = objc_lib.sel_registerName(b"setActivationPolicy:")
        objc_lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        ns_application_activation_policy_regular = 0
        objc_lib.objc_msgSend(ns_app, policy_sel, ns_application_activation_policy_regular)
    except Exception:
        pass


def launch_gui(*, initial_plugin_id: str | None = None, start_minimized: bool = False, force_visible: bool = False) -> int:
    global _WIN_MUTEX
    if os.name == "nt":
        try:
            import ctypes
            _WIN_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "DNgineMutex")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Debeski")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(True)
    _restore_macos_dock_icon()

    services = AppServices()
    services.attach_application(app)
    app.setQuitOnLastWindowClosed(not services.tray_manager.is_enabled())
    icon_path = services.resource_path("app.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    style_hints = app.styleHints()
    try:
        style_hints.colorSchemeChanged.connect(lambda _scheme: services.theme_manager.refresh_system_mode(app))
    except Exception:
        pass

    window = DNgineWindow(services, initial_plugin_id=initial_plugin_id)
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
    window.show()
    should_start_minimized = False if force_visible else (start_minimized or bool(services.config.get("start_minimized")))
    if should_start_minimized:
        if services.tray_manager.can_hide_to_tray():
            window.hide()
        else:
            window.showMinimized()
    elif force_visible:
        window.showNormal()
        window.raise_()
        window.activateWindow()
    return app.exec()


def main() -> int:
    return launch_gui()
