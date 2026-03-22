from __future__ import annotations

import json
import os
import platform

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin


def gather_system_audit(context) -> str:
    context.log("Resolving local platform details...")
    context.progress(0.15)

    root_disk_path = os.path.abspath(os.sep)
    audit = {
        "os_platform": platform.system(),
        "release_version": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor() or "Unknown",
        "logical_cpus": os.cpu_count(),
        "node_name": platform.node(),
        "python_version": platform.python_version(),
    }

    context.progress(0.45)

    try:
        import psutil

        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(root_disk_path)
        audit["ram_total_gb"] = round(memory.total / (1024**3), 2)
        audit["ram_available_gb"] = round(memory.available / (1024**3), 2)
        audit["root_disk_total_gb"] = round(disk.total / (1024**3), 2)
        audit["root_disk_free_gb"] = round(disk.free / (1024**3), 2)
        audit["root_disk_used_pct"] = disk.percent
    except ImportError:
        audit["psutil_warning"] = "Install psutil for RAM and disk metrics."

    context.progress(0.8)
    context.log("System audit complete.")
    context.progress(1.0)
    return json.dumps(audit, indent=4)


class SystemAuditPlugin(QtPlugin):
    plugin_id = "sys_audit"
    name = "System Hardware Audit"
    description = "Collect local OS, CPU, memory, and root disk details in a background worker."
    category = "IT Toolkit"

    def create_widget(self, services) -> QWidget:
        return SystemAuditPage(services, self.metadata().plugin_id)


class SystemAuditPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("System Hardware Audit")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        desc = QLabel(
            "This is the first tool ported into the new engine. It runs on a worker thread and writes results back into the page only when finished."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(desc)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Run Audit")
        self.run_button.clicked.connect(self._run_audit)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.progress, 1)
        layout.addLayout(controls)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Audit output will appear here.")
        layout.addWidget(self.output, 1)

    def _run_audit(self) -> None:
        self.run_button.setEnabled(False)
        self.progress.setValue(0)
        self.output.setPlainText("Running audit...")
        self.services.log("Starting system hardware audit.")

        self.services.run_task(
            gather_system_audit,
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            on_progress=self._update_progress,
        )

    def _update_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        result = str(payload)
        self.output.setPlainText(result)
        self.services.record_run(self.plugin_id, "SUCCESS", "Generated system audit")
        self.services.log("System hardware audit finished successfully.")

    def _handle_error(self, payload: object) -> None:
        if isinstance(payload, dict):
            message = payload.get("message", "Unknown error")
            trace = payload.get("traceback", "")
            error_text = message if not trace else f"{message}\n\n{trace}"
        else:
            error_text = str(payload)
        self.output.setPlainText(error_text)
        self.services.record_run(self.plugin_id, "ERROR", error_text[:500])
        self.services.log("System hardware audit failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
