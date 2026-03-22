from __future__ import annotations

import ctypes
import json
import os
import shlex
import shutil
import subprocess
import sys


class ElevationManager:
    def is_elevated(self) -> bool:
        if sys.platform == "win32":
            try:
                return bool(ctypes.windll.shell32.IsUserAnAdmin())
            except Exception:
                return False
        geteuid = getattr(os, "geteuid", None)
        if callable(geteuid):
            try:
                return geteuid() == 0
            except Exception:
                return False
        return False

    def can_request_elevation(self) -> bool:
        if self.is_elevated():
            return False
        if sys.platform == "win32":
            return True
        if sys.platform == "darwin":
            return shutil.which("osascript") is not None
        return shutil.which("pkexec") is not None

    def relaunch_elevated(self) -> tuple[bool, str]:
        if self.is_elevated():
            return False, "The app is already running with elevated privileges."

        command = self._launch_command()
        if sys.platform == "win32":
            try:
                params = subprocess.list2cmdline(command[1:])
                result = ctypes.windll.shell32.ShellExecuteW(None, "runas", command[0], params, None, 1)
            except Exception as exc:
                return False, f"Unable to request elevation: {exc}"
            if result <= 32:
                return False, "Windows declined the elevation request."
            return True, "Restarting the app with administrator privileges."

        if sys.platform == "darwin":
            if shutil.which("osascript") is None:
                return False, "osascript is not available to request elevation on this macOS session."
            command_text = shlex.join(command)
            script = f"do shell script {json.dumps(command_text)} with administrator privileges"
            try:
                subprocess.Popen(["osascript", "-e", script])
            except Exception as exc:
                return False, f"Unable to request elevation: {exc}"
            return True, "Restarting the app with administrator privileges."

        pkexec_path = shutil.which("pkexec")
        if pkexec_path is None:
            return False, "pkexec is not installed, so the app cannot request elevation automatically on this Linux session."
        try:
            subprocess.Popen([pkexec_path, *command])
        except Exception as exc:
            return False, f"Unable to request elevation: {exc}"
        return True, "Restarting the app with elevated privileges."

    def _launch_command(self) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, *sys.argv[1:]]
        return [sys.executable, "-m", "micro_toolkit", *sys.argv[1:]]

