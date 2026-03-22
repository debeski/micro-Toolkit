from __future__ import annotations

import argparse
import ctypes
import json
import os
import secrets
import shlex
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from micro_toolkit.core.plugin_manager import PluginManager
from micro_toolkit.core.plugin_state import PluginStateManager


@dataclass(frozen=True)
class PrivilegedCapabilitySpec:
    capability_id: str
    title: str
    description: str
    provider: str = "core"


class PrivilegedCapabilityContext:
    def __init__(self, runtime, capability_id: str):
        self.runtime = runtime
        self.capability_id = capability_id
        self.log_messages: list[str] = []

    def log(self, message: str) -> None:
        text = str(message)
        self.log_messages.append(text)
        self.runtime.log(text)


class PrivilegedBrokerRuntime:
    def __init__(self, data_root: Path, output_root: Path, assets_root: Path):
        self.data_root = Path(data_root)
        self.output_root = Path(output_root)
        self.assets_root = Path(assets_root)
        self.runtime_root = self.data_root / "runtime"
        self.runtime_root.mkdir(parents=True, exist_ok=True)

    def resource_path(self, relative_path: str) -> Path:
        return self.assets_root / relative_path

    def log(self, message: str) -> None:
        print(f"[broker] {message}", file=sys.stderr)


class PrivilegedCapabilityRegistry:
    def __init__(self):
        self._capabilities: dict[str, tuple[PrivilegedCapabilitySpec, object]] = {}

    def register(self, capability_id: str, title: str, description: str, handler, *, provider: str = "core") -> None:
        self._capabilities[capability_id] = (
            PrivilegedCapabilitySpec(
                capability_id=capability_id,
                title=title,
                description=description,
                provider=provider,
            ),
            handler,
        )

    def list_capabilities(self) -> list[PrivilegedCapabilitySpec]:
        return [self._capabilities[key][0] for key in sorted(self._capabilities)]

    def execute(self, capability_id: str, payload: dict[str, object], runtime: PrivilegedBrokerRuntime) -> dict[str, object]:
        spec_and_handler = self._capabilities.get(capability_id)
        if spec_and_handler is None:
            raise KeyError(f"Unknown privileged capability: {capability_id}")
        spec, handler = spec_and_handler
        context = PrivilegedCapabilityContext(runtime, capability_id)
        result = handler(context, dict(payload))
        return {
            "capability_id": spec.capability_id,
            "provider": spec.provider,
            "result": result,
            "logs": list(context.log_messages),
        }


def _register_core_capabilities(registry: PrivilegedCapabilityRegistry) -> None:
    registry.register(
        "system.identity",
        "System Identity",
        "Return effective privilege and platform details from the broker process.",
        _system_identity_capability,
        provider="core",
    )
    registry.register(
        "filesystem.stat_path",
        "Filesystem Stat",
        "Return metadata for a path from the broker process.",
        _filesystem_stat_capability,
        provider="core",
    )


def _system_identity_capability(context: PrivilegedCapabilityContext, payload: dict[str, object]) -> dict[str, object]:
    geteuid = getattr(os, "geteuid", None)
    context.log("Collecting broker identity details.")
    return {
        "platform": sys.platform,
        "pid": os.getpid(),
        "is_root": bool(callable(geteuid) and geteuid() == 0),
        "user": os.environ.get("USER") or os.environ.get("USERNAME") or "",
        "payload": payload,
    }


def _filesystem_stat_capability(context: PrivilegedCapabilityContext, payload: dict[str, object]) -> dict[str, object]:
    raw_path = str(payload.get("path") or "").strip()
    if not raw_path:
        raise ValueError("payload.path is required")
    target = Path(raw_path).expanduser().resolve()
    context.log(f"Reading stat details for {target}")
    stat_result = target.stat()
    return {
        "path": str(target),
        "exists": target.exists(),
        "is_file": target.is_file(),
        "is_dir": target.is_dir(),
        "size": stat_result.st_size,
        "mode": stat_result.st_mode,
        "mtime": stat_result.st_mtime,
    }


def load_privileged_capability_registry(
    plugins_root: Path,
    custom_plugins_root: Path,
    plugin_state_path: Path,
    data_root: Path,
    output_root: Path,
    assets_root: Path,
) -> PrivilegedCapabilityRegistry:
    runtime = PrivilegedBrokerRuntime(data_root, output_root, assets_root)
    registry = PrivilegedCapabilityRegistry()
    _register_core_capabilities(registry)

    state_manager = PluginStateManager(plugin_state_path)
    plugin_manager = PluginManager(plugins_root, custom_plugins_root, state_manager)
    for spec in plugin_manager.discover_plugins():
        try:
            plugin = plugin_manager.load_plugin(spec.plugin_id)
            plugin.register_privileged_capabilities(registry, runtime)
        except Exception as exc:
            runtime.log(f"Skipping privileged capability registration for '{spec.plugin_id}': {exc}")
    return registry


class _PrivilegedBrokerRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server = self.server  # type: ignore[assignment]
        line = self.rfile.readline()
        if not line:
            return
        try:
            payload = json.loads(line.decode("utf-8"))
        except Exception:
            self._write({"ok": False, "error": "Invalid JSON payload."})
            return

        if payload.get("token") != server.auth_token:  # type: ignore[attr-defined]
            self._write({"ok": False, "error": "Authentication failed."})
            return

        action = str(payload.get("action") or "execute")
        if action == "stop":
            self._write({"ok": True, "stopped": True})
            threading.Thread(target=server.shutdown, daemon=True).start()  # type: ignore[attr-defined]
            return
        if action == "list":
            specs = [
                {
                    "capability_id": spec.capability_id,
                    "title": spec.title,
                    "description": spec.description,
                    "provider": spec.provider,
                }
                for spec in server.registry.list_capabilities()  # type: ignore[attr-defined]
            ]
            self._write({"ok": True, "capabilities": specs})
            return

        capability_id = str(payload.get("capability_id") or "").strip()
        request_payload = payload.get("payload") or {}
        if not capability_id:
            self._write({"ok": False, "error": "capability_id is required."})
            return
        if not isinstance(request_payload, dict):
            self._write({"ok": False, "error": "payload must be a JSON object."})
            return

        try:
            result = server.registry.execute(capability_id, request_payload, server.runtime)  # type: ignore[attr-defined]
        except Exception as exc:
            self._write({"ok": False, "error": str(exc)})
            return
        self._write({"ok": True, **result})

    def _write(self, payload: dict[str, object]) -> None:
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
        self.wfile.flush()


class _ThreadedBrokerServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class PrivilegedBrokerManager(QObject):
    status_changed = Signal(str)
    active_changed = Signal(bool)

    def __init__(
        self,
        data_root: Path,
        output_root: Path,
        assets_root: Path,
        plugins_root: Path,
        custom_plugins_root: Path,
        plugin_state_path: Path,
        logger,
    ):
        super().__init__()
        self.data_root = Path(data_root)
        self.output_root = Path(output_root)
        self.assets_root = Path(assets_root)
        self.plugins_root = Path(plugins_root)
        self.custom_plugins_root = Path(custom_plugins_root)
        self.plugin_state_path = Path(plugin_state_path)
        self.logger = logger
        self.runtime_root = self.data_root / "runtime"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.status_path = self.runtime_root / "privileged_broker_status.json"
        self.token = secrets.token_hex(24)
        self._active = False
        self._last_status = ""
        self._process: subprocess.Popen | None = None
        self._cached_capabilities: list[dict[str, object]] | None = None

    def supports_broker(self) -> bool:
        if not getattr(sys, "frozen", False) and not Path(sys.executable).exists():
            return False
        if sys.platform == "win32":
            return True
        if sys.platform == "darwin":
            return shutil.which("osascript") is not None
        return shutil.which("pkexec") is not None

    def reason(self) -> str:
        if sys.platform == "win32":
            return "The broker can request administrator rights through UAC when a capability needs them."
        if sys.platform == "darwin":
            if shutil.which("osascript") is None:
                return "osascript is not available, so the broker cannot request elevated privileges on this macOS session."
            return "The broker can request administrator privileges through macOS authentication when a capability needs them."
        if shutil.which("pkexec") is None:
            return "pkexec is not installed, so the broker cannot request elevated privileges on this Linux session."
        return "The broker can request elevated privileges through pkexec when a capability needs them."

    def list_capabilities(self) -> list[dict[str, object]]:
        if self._cached_capabilities is None:
            registry = load_privileged_capability_registry(
                self.plugins_root,
                self.custom_plugins_root,
                self.plugin_state_path,
                self.data_root,
                self.output_root,
                self.assets_root,
            )
            self._cached_capabilities = [
                {
                    "capability_id": spec.capability_id,
                    "title": spec.title,
                    "description": spec.description,
                    "provider": spec.provider,
                }
                for spec in registry.list_capabilities()
            ]
        return list(self._cached_capabilities)

    def request(self, capability_id: str, payload: dict[str, object] | None = None, *, timeout_seconds: float = 20.0):
        payload = dict(payload or {})
        if not capability_id.strip():
            raise ValueError("capability_id is required")
        self.ensure_running(timeout_seconds=timeout_seconds)
        response = self._send_request(
            {
                "token": self.token,
                "action": "execute",
                "capability_id": capability_id,
                "payload": payload,
            },
            timeout_seconds=timeout_seconds,
        )
        if not response.get("ok"):
            raise RuntimeError(str(response.get("error") or "Privileged broker request failed."))
        return response

    def start(self, *, timeout_seconds: float = 15.0) -> tuple[bool, str]:
        if not self.supports_broker():
            message = self.reason()
            self._set_active(False, message)
            return False, message
        if self.is_active():
            message = "Privileged broker is already active for this session."
            self._set_active(True, message)
            return True, message

        if self.status_path.exists():
            try:
                self.status_path.unlink()
            except Exception:
                pass

        command = self._build_launch_command()
        try:
            if sys.platform == "win32":
                params = subprocess.list2cmdline(command[1:])
                result = ctypes.windll.shell32.ShellExecuteW(None, "runas", command[0], params, None, 1)
                if result <= 32:
                    message = "Windows declined the elevated broker elevation request."
                    self._set_active(False, message)
                    return False, message
            elif sys.platform == "darwin":
                command_text = shlex.join(command)
                script = f"do shell script {json.dumps(command_text)} with administrator privileges"
                subprocess.Popen(["osascript", "-e", script])
            else:
                self._process = subprocess.Popen([shutil.which("pkexec") or "pkexec", *command])
        except Exception as exc:
            message = f"Unable to start the elevated broker: {exc}"
            self._set_active(False, message)
            return False, message

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            status = self._read_status()
            if status is not None:
                message = "Privileged broker is active for this session."
                self._set_active(True, message)
                return True, message
            time.sleep(0.1)
        message = "Timed out while waiting for the elevated broker to start."
        self._set_active(False, message)
        return False, message

    def stop(self, *, timeout_seconds: float = 5.0) -> tuple[bool, str]:
        if not self.status_path.exists():
            self._set_active(False, "Privileged broker is not active.")
            return True, "Privileged broker is not active."
        try:
            self._send_request({"token": self.token, "action": "stop"}, timeout_seconds=timeout_seconds)
        except Exception:
            status = self._read_status()
            pid = int(status.get("pid", 0)) if status else 0
            if pid > 0:
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
        if self.status_path.exists():
            try:
                self.status_path.unlink()
            except Exception:
                pass
        self._set_active(False, "Privileged broker stopped.")
        return True, "Privileged broker stopped."

    def ensure_running(self, *, timeout_seconds: float = 15.0) -> None:
        if self.is_active():
            return
        success, message = self.start(timeout_seconds=timeout_seconds)
        if not success:
            raise RuntimeError(message)

    def is_active(self) -> bool:
        status = self._read_status()
        active = bool(status and status.get("port"))
        if active != self._active:
            self._set_active(active, "Privileged broker is active for this session." if active else "Privileged broker is not active.")
        return active

    def _send_request(self, payload: dict[str, object], *, timeout_seconds: float) -> dict[str, object]:
        status = self._read_status()
        if status is None:
            raise RuntimeError("Privileged broker is not available.")
        host = str(status.get("host") or "127.0.0.1")
        port = int(status.get("port") or 0)
        if port <= 0:
            raise RuntimeError("Privileged broker did not expose a valid IPC port.")
        with socket.create_connection((host, port), timeout=timeout_seconds) as connection:
            connection.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
            connection.shutdown(socket.SHUT_WR)
            response = b""
            while True:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                response += chunk
        if not response:
            raise RuntimeError("Privileged broker returned an empty response.")
        return json.loads(response.decode("utf-8").strip())

    def _read_status(self) -> dict[str, object] | None:
        if not self.status_path.exists():
            return None
        try:
            payload = json.loads(self.status_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _build_launch_command(self) -> list[str]:
        if getattr(sys, "frozen", False):
            return [
                sys.executable,
                "elevated-broker",
                "--status-file",
                str(self.status_path),
                "--token",
                self.token,
                "--data-root",
                str(self.data_root),
                "--output-root",
                str(self.output_root),
                "--assets-root",
                str(self.assets_root),
                "--plugins-root",
                str(self.plugins_root),
                "--custom-plugins-root",
                str(self.custom_plugins_root),
                "--plugin-state-path",
                str(self.plugin_state_path),
            ]
        return [
            sys.executable,
            "-m",
            "micro_toolkit",
            "elevated-broker",
            "--status-file",
            str(self.status_path),
            "--token",
            self.token,
            "--data-root",
            str(self.data_root),
            "--output-root",
            str(self.output_root),
            "--assets-root",
            str(self.assets_root),
            "--plugins-root",
            str(self.plugins_root),
            "--custom-plugins-root",
            str(self.custom_plugins_root),
            "--plugin-state-path",
            str(self.plugin_state_path),
        ]

    def _set_active(self, active: bool, message: str) -> None:
        state_changed = self._active != active
        if state_changed:
            self._active = active
            self.active_changed.emit(active)
        if message and (state_changed or message != self._last_status):
            self.status_changed.emit(message)
            self.logger.log(message, "INFO" if active else "WARNING")
        self._last_status = message


def build_broker_parser(subparsers) -> None:
    broker = subparsers.add_parser("elevated-broker", help=argparse.SUPPRESS)
    broker.add_argument("--status-file", required=True)
    broker.add_argument("--token", required=True)
    broker.add_argument("--data-root", required=True)
    broker.add_argument("--output-root", required=True)
    broker.add_argument("--assets-root", required=True)
    broker.add_argument("--plugins-root", required=True)
    broker.add_argument("--custom-plugins-root", required=True)
    broker.add_argument("--plugin-state-path", required=True)


def run_broker_service(args) -> int:
    runtime = PrivilegedBrokerRuntime(Path(args.data_root), Path(args.output_root), Path(args.assets_root))
    registry = load_privileged_capability_registry(
        Path(args.plugins_root),
        Path(args.custom_plugins_root),
        Path(args.plugin_state_path),
        Path(args.data_root),
        Path(args.output_root),
        Path(args.assets_root),
    )

    try:
        server = _ThreadedBrokerServer(("127.0.0.1", 0), _PrivilegedBrokerRequestHandler)
    except OSError as exc:
        print(f"Unable to start elevated broker IPC server: {exc}", file=sys.stderr)
        return 2

    server.auth_token = args.token  # type: ignore[attr-defined]
    server.registry = registry  # type: ignore[attr-defined]
    server.runtime = runtime  # type: ignore[attr-defined]
    host, port = server.server_address

    status_path = Path(args.status_file)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "host": host,
                "port": port,
                "token": args.token,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    def _cleanup(*_args):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            status_path.unlink()
        except Exception:
            pass
    return 0
