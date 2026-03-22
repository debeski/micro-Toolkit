from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal


def _keyboard_backend():
    try:
        import keyboard
    except Exception:
        return None
    return keyboard


class _HotkeyEventHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        manager = self.server.manager  # type: ignore[attr-defined]
        while True:
            line = self.rfile.readline()
            if not line:
                break
            try:
                payload = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            if payload.get("token") != manager.token:
                continue
            action_id = str(payload.get("action_id") or "").strip()
            if action_id:
                manager.action_requested.emit(action_id)


class _ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class HotkeyHelperManager(QObject):
    action_requested = Signal(str)
    active_changed = Signal(bool)
    status_changed = Signal(str)

    def __init__(self, data_root: Path, logger):
        super().__init__()
        self.data_root = Path(data_root)
        self.logger = logger
        self.runtime_root = self.data_root / "runtime"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_hex(24)
        self._helper_enabled_for_session = False
        self._active = False
        self._last_status = ""
        self._current_bindings: dict[str, str] = {}
        self._running_bindings: dict[str, str] = {}
        self._process: subprocess.Popen | None = None
        self._server = None
        self._server_thread = None
        self.port: int | None = None
        self._server_error = ""
        self._server, self._server_thread = self._start_server()
        if self._server is not None:
            self.port = int(self._server.server_address[1])
        self.mapping_path = self.runtime_root / "hotkey_helper_bindings.json"
        self.pid_path = self.runtime_root / "hotkey_helper.pid"

    def _start_server(self):
        try:
            server = _ThreadedTCPServer(("127.0.0.1", 0), _HotkeyEventHandler)
        except OSError as exc:
            self._server_error = str(exc)
            self.logger.log(
                f"Hotkey helper IPC is unavailable in this environment: {exc}",
                "WARNING",
            )
            return None, None
        server.manager = self  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True, name="microtk-hotkey-helper-listener")
        thread.start()
        return server, thread

    def supports_helper(self) -> bool:
        return (
            sys.platform.startswith("linux")
            and _keyboard_backend() is not None
            and shutil.which("pkexec") is not None
            and self.port is not None
        )

    def can_request_helper(self) -> bool:
        return self.supports_helper() and not self._is_root()

    def helper_reason(self) -> str:
        if _keyboard_backend() is None:
            return "The global hotkey backend is not installed."
        if not sys.platform.startswith("linux"):
            return "The privileged helper is only needed on Linux."
        if self.port is None:
            return f"The local IPC channel for the helper is unavailable in this session: {self._server_error or 'unknown error'}"
        if self._is_root():
            return "The app already has elevated privileges, so a separate hotkey helper is unnecessary."
        if shutil.which("pkexec") is None:
            return "pkexec is not installed, so the helper cannot request elevated input access."
        return "Global shortcuts on Linux need elevated access to input devices. The helper can request that access without elevating the main app."

    def is_active(self) -> bool:
        return self._active and self._helper_pid() is not None

    def global_scope_available(self) -> bool:
        return self.is_active() or self.can_request_helper()

    def enable_for_session(self, bindings: dict[str, str]) -> tuple[bool, str]:
        if not bindings:
            self._helper_enabled_for_session = True
            return False, "No global hotkey bindings are currently configured."
        self._helper_enabled_for_session = True
        return self._launch_helper(bindings)

    def disable_for_session(self) -> None:
        self._helper_enabled_for_session = False
        self.stop_helper()

    def apply_bindings(self, bindings: dict[str, str]) -> bool:
        normalized = {action_id: sequence.strip() for action_id, sequence in bindings.items() if sequence.strip()}
        self._current_bindings = normalized
        if not normalized:
            self.stop_helper()
            return False
        if self._is_root():
            return False
        if not self.supports_helper():
            return False
        if not self._helper_enabled_for_session:
            return self.is_active()
        return self._launch_helper(normalized)[0]

    def stop_helper(self) -> None:
        helper_pid = self._helper_pid()
        if helper_pid is not None:
            try:
                os.kill(helper_pid, signal.SIGTERM)
            except Exception:
                pass
        if self._process is not None:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._process = None
        if self.pid_path.exists():
            try:
                self.pid_path.unlink()
            except Exception:
                pass
        self._running_bindings = {}
        self._set_active(False, "Hotkey helper stopped.")

    def _launch_helper(self, bindings: dict[str, str]) -> tuple[bool, str]:
        if not self.supports_helper():
            message = self.helper_reason()
            self._set_active(False, message)
            return False, message

        if self.is_active() and bindings == self._running_bindings:
            message = "Privileged hotkey helper is active for this session."
            self._set_active(True, message)
            return True, message

        self.mapping_path.write_text(json.dumps(bindings, indent=2), encoding="utf-8")
        if self.pid_path.exists():
            try:
                self.pid_path.unlink()
            except Exception:
                pass

        helper_pid = self._helper_pid()
        if self.is_active() and helper_pid is not None:
            self.stop_helper()

        pkexec_path = shutil.which("pkexec")
        if pkexec_path is None:
            message = self.helper_reason()
            self._set_active(False, message)
            return False, message

        command = [
            pkexec_path,
            *self._helper_command(),
        ]
        try:
            self._process = subprocess.Popen(command)
        except Exception as exc:
            message = f"Unable to start the hotkey helper: {exc}"
            self._set_active(False, message)
            return False, message

        deadline = time.time() + 12.0
        while time.time() < deadline:
            helper_pid = self._helper_pid()
            if helper_pid is not None:
                self._running_bindings = dict(bindings)
                message = "Privileged hotkey helper is active for this session."
                self._set_active(True, message)
                return True, message
            if self._process.poll() is not None:
                message = "The hotkey helper did not start. Authentication may have been cancelled."
                self._set_active(False, message)
                return False, message
            time.sleep(0.1)

        message = "Timed out while waiting for the hotkey helper to start."
        self._set_active(False, message)
        return False, message

    def _helper_command(self) -> list[str]:
        base = [sys.executable]
        if getattr(sys, "frozen", False):
            return [
                *base,
                "hotkey-helper",
                "--ipc-port",
                str(self.port or 0),
                "--ipc-token",
                self.token,
                "--mappings",
                str(self.mapping_path),
                "--pid-file",
                str(self.pid_path),
                "--parent-pid",
                str(os.getpid()),
            ]
        return [
            *base,
            "-m",
            "micro_toolkit",
            "hotkey-helper",
            "--ipc-port",
            str(self.port or 0),
            "--ipc-token",
            self.token,
            "--mappings",
            str(self.mapping_path),
            "--pid-file",
            str(self.pid_path),
            "--parent-pid",
            str(os.getpid()),
        ]

    def _helper_pid(self) -> int | None:
        if not self.pid_path.exists():
            return None
        try:
            return int(self.pid_path.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    def _set_active(self, active: bool, message: str) -> None:
        state_changed = self._active != active
        if self._active != active:
            self._active = active
            self.active_changed.emit(active)
        if message != self._last_status:
            self.status_changed.emit(message)
        if message and (state_changed or message != self._last_status):
            level = "INFO" if active else "WARNING"
            self.logger.log(message, level)
        self._last_status = message

    @staticmethod
    def _is_root() -> bool:
        geteuid = getattr(os, "geteuid", None)
        return bool(callable(geteuid) and geteuid() == 0)


def build_helper_parser(subparsers) -> None:
    helper = subparsers.add_parser("hotkey-helper", help=argparse.SUPPRESS)
    helper.add_argument("--ipc-port", required=True, type=int)
    helper.add_argument("--ipc-token", required=True)
    helper.add_argument("--mappings", required=True)
    helper.add_argument("--pid-file", required=True)
    helper.add_argument("--parent-pid", required=True, type=int)


def run_hotkey_helper_service(args) -> int:
    keyboard = _keyboard_backend()
    if keyboard is None:
        print("keyboard backend is not available.", file=sys.stderr)
        return 2

    mapping_path = Path(args.mappings)
    pid_path = Path(args.pid_file)
    try:
        mappings = json.loads(mapping_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Unable to read helper mappings: {exc}", file=sys.stderr)
        return 2
    if not isinstance(mappings, dict) or not mappings:
        print("No hotkey mappings were provided.", file=sys.stderr)
        return 2

    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")

    stop_event = threading.Event()

    def _cleanup(*_args):
        stop_event.set()

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    def notify(action_id: str) -> None:
        payload = json.dumps({"token": args.ipc_token, "action_id": action_id}).encode("utf-8") + b"\n"
        try:
            with socket.create_connection(("127.0.0.1", args.ipc_port), timeout=1.5) as connection:
                connection.sendall(payload)
        except OSError:
            pass

    for action_id, sequence in mappings.items():
        try:
            keyboard.add_hotkey(
                str(sequence),
                lambda action_id=action_id: notify(str(action_id)),
            )
        except Exception as exc:
            print(f"Unable to register global hotkey '{sequence}': {exc}", file=sys.stderr)

    try:
        while not stop_event.wait(0.5):
            if not _parent_alive(args.parent_pid):
                break
    finally:
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        try:
            pid_path.unlink()
        except Exception:
            pass
    return 0


def _parent_alive(parent_pid: int) -> bool:
    try:
        os.kill(parent_pid, 0)
    except OSError:
        return False
    return True
