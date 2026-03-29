from __future__ import annotations

import os
import plistlib
import shlex
import sys
from pathlib import Path

from dngine import APP_NAME, DIST_NAME
from dngine.core.runtime_launch import build_gui_launch_args

LEGACY_APP_NAME = "Micro Toolkit"
LEGACY_DIST_NAME = "micro-toolkit"
MAC_AUTOSTART_LABEL = "com.debeski.dngine"
LEGACY_MAC_AUTOSTART_LABEL = "com.debeski.microtoolkit"


class AutostartManager:
    def __init__(self, app_name: str = APP_NAME):
        self.app_name = app_name

    def cleanup_legacy_clip_monitor_entries(self) -> None:
        if os.name == "nt":
            for name in self._clip_monitor_registry_names():
                self._set_registry_enabled(False, name, "")
            return
        for path in self._clip_monitor_target_paths():
            if not path.exists():
                continue
            try:
                path.unlink()
            except OSError:
                pass

    def is_enabled(self) -> bool:
        if os.name == "nt":
            return any(self._is_registry_enabled(name) for name in self._registry_names())
        return any(path.exists() for path in self._target_paths())

    def set_enabled(self, enabled: bool, *, start_minimized: bool = False) -> Path | None:
        if os.name == "nt":
            command = self._launch_command(start_minimized=start_minimized)
            self._set_registry_enabled(enabled, self.app_name, command)
            for legacy_name in self._registry_names()[1:]:
                self._set_registry_enabled(False, legacy_name, command)
            self._cleanup_legacy_nt_autostart()
            return None

        target = self._target_path()
        if enabled:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._write_launcher(target, self._launch_command(start_minimized=start_minimized), self._launch_args(start_minimized=start_minimized), label=MAC_AUTOSTART_LABEL)
        self._cleanup_legacy_targets(keep_current=enabled)
        return target

    def _target_path(self) -> Path:
        return self._target_paths()[0]

    def _target_paths(self) -> list[Path]:
        home = Path.home()
        paths: list[Path] = []
        if sys.platform.startswith("linux"):
            current_name = f"{DIST_NAME}.desktop"
            legacy_name = f"{LEGACY_DIST_NAME}.desktop"
            base = home / ".config" / "autostart"
            paths.extend([base / current_name, base / legacy_name])
        elif sys.platform == "darwin":
            current_name = f"{MAC_AUTOSTART_LABEL}.plist"
            legacy_name = f"{LEGACY_MAC_AUTOSTART_LABEL}.plist"
            base = home / "Library" / "LaunchAgents"
            paths.extend([base / current_name, base / legacy_name])
        elif os.name == "nt":
            appdata = Path(os.environ.get("APPDATA", home))
            base = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            paths.extend([base / f"{DIST_NAME}.cmd", base / f"{LEGACY_DIST_NAME}.cmd"])
        else:
            paths.extend([home / f".{DIST_NAME}-startup", home / f".{LEGACY_DIST_NAME}-startup"])

        ordered_paths: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            if path not in seen:
                ordered_paths.append(path)
                seen.add(path)
        return ordered_paths

    def _clip_monitor_target_paths(self) -> list[Path]:
        home = Path.home()
        paths: list[Path] = []
        if sys.platform.startswith("linux"):
            base = home / ".config" / "autostart"
            paths.extend(
                [
                    base / f"{DIST_NAME}-clip-monitor.desktop",
                    base / f"{LEGACY_DIST_NAME}-clip-monitor.desktop",
                ]
            )
        elif sys.platform == "darwin":
            base = home / "Library" / "LaunchAgents"
            paths.extend(
                [
                    base / f"{MAC_AUTOSTART_LABEL}.clipmonitor.plist",
                    base / f"{LEGACY_MAC_AUTOSTART_LABEL}.clipmonitor.plist",
                ]
            )
        return paths

    def _registry_names(self) -> tuple[str, ...]:
        current_name = self.app_name
        legacy_name = LEGACY_APP_NAME
        if current_name == legacy_name:
            return (current_name,)
        return current_name, legacy_name

    def _clip_monitor_registry_names(self) -> tuple[str, ...]:
        current_name = f"{self.app_name} Clip Monitor"
        legacy_name = f"{LEGACY_APP_NAME} Clip Monitor"
        if current_name == legacy_name:
            return (current_name,)
        return current_name, legacy_name

    def _is_registry_enabled(self, name: str | None = None) -> bool:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            ) as key:
                winreg.QueryValueEx(key, name or self.app_name)
                return True
        except OSError:
            return False

    def _set_registry_enabled(self, enabled: bool, name: str, command: str) -> None:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        if enabled:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
                    winreg.DeleteValue(key, name)
            except OSError:
                pass

    def _cleanup_legacy_nt_autostart(self) -> None:
        if os.name != "nt":
            return
        for legacy in self._target_paths()[1:]:
            if not legacy.exists():
                continue
            try:
                legacy.unlink()
            except OSError:
                pass

    def _cleanup_legacy_targets(self, *, keep_current: bool) -> None:
        for index, target in enumerate(self._target_paths()):
            if keep_current and index == 0:
                continue
            if not target.exists():
                continue
            try:
                target.unlink()
            except OSError:
                pass

    def _write_launcher(self, target: Path, command: str, launch_args: list[str], *, label: str) -> None:
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
                "Label": label,
                "ProgramArguments": launch_args,
                "RunAtLoad": True,
                "LimitLoadToSessionType": ["Aqua"],
                "ProcessType": "Interactive",
                "WorkingDirectory": str(Path.home()),
            }
            with target.open("wb") as handle:
                plistlib.dump(payload, handle)
            return
        # NT handled via Registry now
        target.write_text(command + "\n", encoding="utf-8")

    def _launch_args(self, *, start_minimized: bool) -> list[str]:
        if sys.platform == "darwin":
            mac_bundle_path = self._mac_bundle_path()
            if mac_bundle_path is not None:
                args = ["/usr/bin/open", str(mac_bundle_path), "--args"]
                args.append("gui")
                if start_minimized:
                    args.append("--start-minimized")
                return args
        return build_gui_launch_args(start_minimized=start_minimized)

    def _launch_command(self, *, start_minimized: bool) -> str:
        return " ".join(shlex.quote(part) for part in self._launch_args(start_minimized=start_minimized))

    def _mac_bundle_path(self) -> Path | None:
        if sys.platform != "darwin" or not getattr(sys, "frozen", False):
            return None
        executable_path = Path(sys.executable).resolve()
        for parent in executable_path.parents:
            if parent.suffix == ".app":
                return parent
        return None
