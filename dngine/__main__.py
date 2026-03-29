import sys


def _suppress_macos_dock_icon() -> None:
    """Hide the dock icon for this process on macOS.

    Must be called BEFORE any PySide6/Qt imports, as importing PySide6
    on macOS can initialize NSApplication and create a dock entry.
    """
    if sys.platform != "darwin":
        return
    try:
        import objc  # type: ignore[import-untyped]
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory  # type: ignore[import-untyped]
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
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
        NSApp_cls = objc_lib.objc_getClass(b"NSApplication")
        shared_sel = objc_lib.sel_registerName(b"sharedApplication")
        ns_app = objc_lib.objc_msgSend(NSApp_cls, shared_sel)
        policy_sel = objc_lib.sel_registerName(b"setActivationPolicy:")
        objc_lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        NSApplicationActivationPolicyAccessory = 1
        objc_lib.objc_msgSend(ns_app, policy_sel, NSApplicationActivationPolicyAccessory)
    except Exception:
        pass


# ── Early dock-icon suppression for background sub-processes ──────────
# This MUST run before any PySide6 import, because importing PySide6 on
# macOS initializes NSApplication which immediately creates a dock icon.
if len(sys.argv) >= 2 and sys.argv[1] in {"hotkey-helper", "elevated-broker"}:
    _suppress_macos_dock_icon()


from dngine.core.cli import build_parser, execute_cli
from dngine.main import launch_gui


def main() -> int:
    if len(sys.argv) == 1:
        return launch_gui()

    parser = build_parser()
    parsed = parser.parse_args()
    if parsed.command in {None, "gui"}:
        return launch_gui(
            initial_plugin_id=getattr(parsed, "plugin_id", None),
            start_minimized=getattr(parsed, "start_minimized", False),
            force_visible=getattr(parsed, "force_visible", False),
        )
    return execute_cli(parsed)


if __name__ == "__main__":
    raise SystemExit(main())
