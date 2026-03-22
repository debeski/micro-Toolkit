from __future__ import annotations

import re
import socket
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin


def parse_ports(port_expression: str) -> list[int]:
    ports: list[int] = []
    tokens = [token.strip() for token in port_expression.split(",") if token.strip()]
    for token in tokens:
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"Invalid range '{token}'")
            ports.extend(range(start, end + 1))
        else:
            ports.append(int(token))

    normalized = sorted({port for port in ports if 1 <= port <= 65535})
    if not normalized:
        raise ValueError("No valid ports were parsed from the expression.")
    return normalized


def run_network_scan(context, target_host: str, port_expression: str, timeout_seconds: float, output_dir: Path):
    ports = parse_ports(port_expression)
    context.log(f"Scanning {target_host} across {len(ports)} ports...")
    open_ports: list[int] = []

    for index, port in enumerate(ports, start=1):
        context.progress(index / float(len(ports)))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_seconds)
            result = sock.connect_ex((target_host, port))
            if result == 0:
                open_ports.append(port)
                context.log(f"Open port detected: {port}")

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_host = re.sub(r"[^A-Za-z0-9_.-]+", "_", target_host)
    report_path = output_dir / f"network_scan_{safe_host}.txt"
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(f"Target: {target_host}\n")
        handle.write(f"Ports scanned: {len(ports)}\n")
        handle.write("Open ports:\n")
        if open_ports:
            for port in open_ports:
                handle.write(f"{port}\n")
        else:
            handle.write("(none)\n")

    context.log(f"Scan complete. Report saved to {report_path}")
    return {
        "target_host": target_host,
        "open_ports": open_ports,
        "report_path": str(report_path),
        "ports_scanned": len(ports),
    }


class NetworkScannerPlugin(QtPlugin):
    plugin_id = "net_scan"
    name = "Network Port Scanner"
    description = "Scan a host for open TCP ports and save a plain-text report to the default output path."
    category = "IT Toolkit"

    def create_widget(self, services) -> QWidget:
        return NetworkScannerPage(services, self.plugin_id)


class NetworkScannerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._latest_report_path = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Network Port Scanner")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            "Enter a host and a port list such as `80,443,8080` or `1-1024`. The scan runs in the background and writes a report under your configured output path."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        host_row = QHBoxLayout()
        host_row.setSpacing(10)
        host_label = QLabel("Target Host")
        host_label.setFixedWidth(100)
        host_row.addWidget(host_label)
        self.host_input = QLineEdit("127.0.0.1")
        host_row.addWidget(self.host_input, 1)
        layout.addLayout(host_row)

        ports_row = QHBoxLayout()
        ports_row.setSpacing(10)
        ports_label = QLabel("Ports")
        ports_label.setFixedWidth(100)
        ports_row.addWidget(ports_label)
        self.ports_input = QLineEdit("80,443,3306")
        ports_row.addWidget(self.ports_input, 1)
        layout.addLayout(ports_row)

        timeout_row = QHBoxLayout()
        timeout_row.setSpacing(10)
        timeout_label = QLabel("Timeout")
        timeout_label.setFixedWidth(100)
        timeout_row.addWidget(timeout_label)
        self.timeout_input = QLineEdit("0.30")
        self.timeout_input.setPlaceholderText("Seconds per port")
        timeout_row.addWidget(self.timeout_input, 1)
        layout.addLayout(timeout_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Run Scan")
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_report_button = QPushButton("Open Report")
        self.open_report_button.setEnabled(False)
        self.open_report_button.clicked.connect(self._open_report)
        controls.addWidget(self.open_report_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.progress, 1)
        layout.addLayout(controls)

        summary_card = QFrame()
        summary_card.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }"
        )
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel("Ready to scan.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Open ports will appear here.")
        layout.addWidget(self.output, 1)

    def _run(self) -> None:
        host = self.host_input.text().strip()
        port_expression = self.ports_input.text().strip()
        timeout_text = self.timeout_input.text().strip()
        if not host or not port_expression:
            QMessageBox.warning(self, "Missing Input", "Enter a host and at least one port.")
            return

        try:
            timeout_seconds = float(timeout_text or "0.30")
        except ValueError:
            QMessageBox.warning(self, "Invalid Timeout", "Timeout must be a numeric value in seconds.")
            return

        self.run_button.setEnabled(False)
        self.open_report_button.setEnabled(False)
        self.progress.setValue(0)
        self.output.setPlainText("")
        self.summary_label.setText("Scanning target...")

        report_dir = self.services.default_output_path() / "network_scans"
        self.services.run_task(
            lambda context: run_network_scan(context, host, port_expression, timeout_seconds, report_dir),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            on_progress=self._handle_progress,
        )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_report_path = result["report_path"]
        open_ports = result["open_ports"]
        if open_ports:
            self.output.setPlainText("\n".join(str(port) for port in open_ports))
            self.summary_label.setText(
                f"Scanned {result['ports_scanned']} ports on {result['target_host']} and found {len(open_ports)} open ports."
            )
            self.services.record_run(
                self.plugin_id,
                "SUCCESS",
                f"Found {len(open_ports)} open ports on {result['target_host']}",
            )
        else:
            self.output.setPlainText("No open ports found.")
            self.summary_label.setText(
                f"Scanned {result['ports_scanned']} ports on {result['target_host']} with no open ports."
            )
            self.services.record_run(
                self.plugin_id,
                "WARNING",
                f"No open ports found on {result['target_host']}",
            )
        self.open_report_button.setEnabled(True)

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown scan error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Network scan failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_report(self) -> None:
        if self._latest_report_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_report_path))
