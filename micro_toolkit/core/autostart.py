from __future__ import annotations

import os
import plistlib
import shlex
import sys
from pathlib import Path


class AutostartManager:
    def __init__(self, app_name: str = "Micro Toolkit"):
        self.app_name = app_name

    def is_enabled(self) -> bool:
        if os.name == "nt":
            return self._is_registry_enabled()
        return self._target_path().exists()

    def set_enabled(self, enabled: bool, *, start_minimized: bool = False) -> Path | None:
        if os.name == "nt":
            self._set_registry_enabled(enabled, start_minimized=start_minimized)
            self._cleanup_legacy_nt_autostart()
            return None

        target = self._target_path()
        if enabled:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._write_launcher(target, start_minimized=start_minimized)
        elif target.exists():
            target.unlink()
        return target

    def _target_path(self) -> Path:
        home = Path.home()
        if sys.platform.startswith("linux"):
            return home / ".config" / "autostart" / "micro-toolkit.desktop"
        if sys.platform == "darwin":
            return home / "Library" / "LaunchAgents" / "com.debeski.microtoolkit.plist"
        if os.name == "nt":
            # Legacy path for cleanup
            appdata = Path(os.environ.get("APPDATA", home))
            return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "micro-toolkit.cmd"
        return home / ".micro-toolkit-startup"

    def _is_registry_enabled(self) -> bool:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            ) as key:
                winreg.QueryValueEx(key, self.app_name)
                return True
        except OSError:
            return False

    def _set_registry_enabled(self, enabled: bool, *, start_minimized: bool = False) -> None:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        if enabled:
            command = self._launch_command(start_minimized=start_minimized)
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, command)
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
                    winreg.DeleteValue(key, self.app_name)
            except OSError:
                pass

    def _cleanup_legacy_nt_autostart(self) -> None:
        if os.name != "nt":
            return
        legacy = self._target_path()
        if legacy.exists():
            try:
                legacy.unlink()
            except OSError:
                pass

    def _write_launcher(self, target: Path, *, start_minimized: bool) -> None:
        command = self._launch_command(start_minimized=start_minimized)
        if sys.platform.startswith("linux"):
            target.write_text(
                "\n".join(
                    [
                        "[Desktop Entry]",
                        "Type=Application",
                        f"Name={self.app_name}",
                        f"Exec={command}",
                        "Terminal=false",
                        "X-GNOME-Autostart-enabled=true",
                    ]
                ),
                encoding="utf-8",
            )
            return
        if sys.platform == "darwin":
            payload = {
                "Label": "com.debeski.microtoolkit",
                "ProgramArguments": self._launch_args(start_minimized=start_minimized),
                "RunAtLoad": True,
            }
            with target.open("wb") as handle:
                plistlib.dump(payload, handle)
            return
        # NT handled via Registry now
        target.write_text(command + "\n", encoding="utf-8")

    def _launch_args(self, *, start_minimized: bool) -> list[str]:
        if getattr(sys, "frozen", False):
            args = [sys.executable]
        else:
            args = [sys.executable, "-m", "micro_toolkit", "gui"]
        if start_minimized:
            args.append("--start-minimized")
        return args

    def _launch_command(self, *, start_minimized: bool) -> str:
        return " ".join(shlex.quote(part) for part in self._launch_args(start_minimized=start_minimized))
