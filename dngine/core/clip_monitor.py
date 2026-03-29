from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication

from dngine.core.clipboard_store import ClipboardStore


class ClipboardMonitor(QObject):
    captured = Signal()

    def __init__(self, store: ClipboardStore, clipboard, logger=None):
        super().__init__()
        self.store = store
        self.clipboard = clipboard
        self.logger = logger
        self._enabled = True
        self._ignore_once = False
        self.clipboard.dataChanged.connect(self._handle_clipboard_changed)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def ignore_next_change(self) -> None:
        self._ignore_once = True

    def capture_current(self) -> bool:
        inserted = self.store.add_mime_entry(self.clipboard.mimeData())
        if inserted and self.logger is not None:
            self.logger.log("Clipboard entry captured.")
        if inserted:
            self.captured.emit()
        return inserted

    def _handle_clipboard_changed(self) -> None:
        if self._ignore_once:
            self._ignore_once = False
            return
        if not self._enabled:
            return
        self.capture_current()


class ClipMonitorManager(QObject):
    status_changed = Signal()

    def __init__(self, config, data_root: Path, database_path: Path, logger):
        super().__init__()
        self.config = config
        self.data_root = Path(data_root)
        self.database_path = Path(database_path)
        self.logger = logger
        self.runtime_root = self.data_root / "runtime"
        self._store: ClipboardStore | None = None
        self._monitor: ClipboardMonitor | None = None

    def attach_application(self, _application) -> None:
        if self._monitor is not None:
            return
        self.cleanup_legacy_monitor_process()
        clipboard = QGuiApplication.clipboard()
        self._store = ClipboardStore(self.database_path)
        self._monitor = ClipboardMonitor(self._store, clipboard, logger=self.logger)
        self._monitor.captured.connect(self.status_changed)
        self.refresh_preferences()

    def is_enabled(self) -> bool:
        return bool(self.config.get("clip_monitor_enabled"))

    def is_running(self) -> bool:
        return self._monitor is not None

    def ignore_next_change(self) -> None:
        if self._monitor is not None:
            self._monitor.ignore_next_change()

    def refresh_preferences(self) -> None:
        if self._monitor is not None:
            self._monitor.set_enabled(self.is_enabled())
        self.status_changed.emit()

    def stop(self, *, persist_disabled: bool = True) -> bool:
        if persist_disabled:
            self.config.set("clip_monitor_enabled", False)
        self.cleanup_legacy_monitor_process()
        self.refresh_preferences()
        return True

    def cleanup_legacy_monitor_process(self) -> None:
        runtime_path = self.runtime_root / "clip_monitor_runtime.json"
        pid_path = self.runtime_root / "clip_monitor.pid"

        monitor_pid: int | None = None
        for path in (runtime_path, pid_path):
            if not path.exists():
                continue
            try:
                payload = path.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            try:
                if path == runtime_path:
                    data = json.loads(payload)
                    if isinstance(data, dict):
                        monitor_pid = int(data.get("pid"))
                elif payload:
                    monitor_pid = int(payload)
            except Exception:
                continue
            if monitor_pid:
                break

        if monitor_pid is not None:
            self._terminate_pid(monitor_pid)

        for path in (runtime_path, pid_path):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

    @staticmethod
    def _pid_alive(pid: int | None) -> bool:
        if not pid:
            return False
        try:
            os.kill(int(pid), 0)
        except OSError:
            return False
        return True

    def _terminate_pid(self, pid: int) -> None:
        if not self._pid_alive(pid):
            return
        for sig in (signal.SIGTERM, signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM):
            try:
                os.kill(pid, sig)
            except OSError:
                return
            deadline = time.time() + 1.5
            while time.time() < deadline:
                if not self._pid_alive(pid):
                    return
                time.sleep(0.05)
