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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.page_style import apply_page_chrome
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr, tr


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


def run_network_scan(context, services, plugin_id: str, target_host: str, port_expression: str, timeout_seconds: float, output_dir: Path):
    def _ensure_western(text: str) -> str:
        eastern = "٠١٢٣٤٥٦٧٨٩"
        western = "0123456789"
        trans = str.maketrans(eastern, western)
        return text.translate(trans)

    ports = parse_ports(port_expression)
    context.log(tr(services, plugin_id, "log.start", "Scanning {host} across {count} ports...", host=target_host, count=_ensure_western(str(len(ports)))))
    open_ports: list[int] = []

    for index, port in enumerate(ports, start=1):
        context.progress(index / float(len(ports)))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_seconds)
            result = sock.connect_ex((target_host, port))
            if result == 0:
                open_ports.append(port)
                context.log(tr(services, plugin_id, "log.detect", "Open port detected: {port}", port=_ensure_western(str(port))))

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_host = re.sub(r"[^A-Za-z0-9_.-]+", "_", target_host)
    
    report_filename = tr(services, plugin_id, "report.filename", "network_scan_{host}.txt", host=safe_host)
    report_path = output_dir / report_filename
    
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(tr(services, plugin_id, "report.target", "Target: {host}", host=target_host) + "\n")
        handle.write(tr(services, plugin_id, "report.count", "Ports scanned: {count}", count=_ensure_western(str(len(ports)))) + "\n")
        handle.write(tr(services, plugin_id, "report.heading", "Open ports:") + "\n")
        if open_ports:
            for port in open_ports:
                handle.write(_ensure_western(str(port)) + "\n")
        else:
            handle.write(tr(services, plugin_id, "report.none", "(none)") + "\n")

    context.log(tr(services, plugin_id, "log.done", "Scan complete. Report saved to {path}", path=str(report_path)))
    return {
        "target_host": target_host,
        "open_ports": open_ports,
        "report_path": str(report_path),
        "ports_scanned": _ensure_western(str(len(ports))),
    }


class NetworkScannerPlugin(QtPlugin):
    plugin_id = "net_scan"
    name = "Network Port Scanner"
    description = "Scan a host for open TCP ports and save a plain-text report to the default output path."
    category = "IT Utilities"

    def create_widget(self, services) -> QWidget:
        return NetworkScannerPage(services, self.plugin_id)


class NetworkScannerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self._latest_report_path = None
        self._build_ui()
        self.services.i18n.language_changed.connect(self._refresh)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _build_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(28, 28, 28, 28)
        self.main_layout.setSpacing(16)

        self.title_label = QLabel()
        self.main_layout.addWidget(self.title_label)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.main_layout.addWidget(self.desc_label)

        host_row = QHBoxLayout()
        host_row.setSpacing(10)
        self.host_label_widget = QLabel()
        self.host_label_widget.setFixedWidth(100)
        host_row.addWidget(self.host_label_widget)
        self.host_input = QLineEdit("127.0.0.1")
        host_row.addWidget(self.host_input, 1)
        self.main_layout.addLayout(host_row)

        ports_row = QHBoxLayout()
        ports_row.setSpacing(10)
        self.ports_label_widget = QLabel()
        self.ports_label_widget.setFixedWidth(100)
        ports_row.addWidget(self.ports_label_widget)
        self.ports_input = QLineEdit("80,443,3306")
        ports_row.addWidget(self.ports_input, 1)
        self.main_layout.addLayout(ports_row)

        timeout_row = QHBoxLayout()
        timeout_row.setSpacing(10)
        self.timeout_label_widget = QLabel()
        self.timeout_label_widget.setFixedWidth(100)
        timeout_row.addWidget(self.timeout_label_widget)
        self.timeout_input = QLineEdit("0.30")
        timeout_row.addWidget(self.timeout_input, 1)
        self.main_layout.addLayout(timeout_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_report_button = QPushButton()
        self.open_report_button.setEnabled(False)
        self.open_report_button.clicked.connect(self._open_report)
        controls.addWidget(self.open_report_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.main_layout.addLayout(controls)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        self.main_layout.addWidget(self.summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.main_layout.addWidget(self.output, 1)
        
        self._refresh()

    def _refresh(self) -> None:
        self.title_label.setText(self.tr("title", "Network Port Scanner"))
        self.desc_label.setText(self.tr("description", "Enter a host and a port list such as `80,443,8080` or `1-1024`. The scan runs in the background and writes a report under your configured output path."))
        self.host_label_widget.setText(self.tr("host.label", "Target Host"))
        self.ports_label_widget.setText(self.tr("ports.label", "Ports"))
        self.timeout_label_widget.setText(self.tr("timeout.label", "Timeout"))
        self.timeout_input.setPlaceholderText(self.tr("timeout.placeholder", "Seconds per port"))
        self.run_button.setText(self.tr("run.button", "Run Scan"))
        self.open_report_button.setText(self.tr("report.button", "Open Report"))
        self.summary_label.setText(self.tr("summary.initial", "Ready to scan."))
        self.output.setPlaceholderText(self.tr("output.placeholder", "Open ports will appear here."))
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.desc_label,
            cards=(self.summary_card,),
            summary_label=self.summary_label,
        )

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _run(self) -> None:
        host = self.host_input.text().strip()
        port_expression = self.ports_input.text().strip()
        timeout_text = self.timeout_input.text().strip()
        if not host or not port_expression:
            QMessageBox.warning(
                self, 
                self.tr("dialog.missing.title", "Missing Input"), 
                self.tr("dialog.missing.body", "Enter a host and at least one port.")
            )
            return

        try:
            timeout_seconds = float(timeout_text or "0.30")
        except ValueError:
            QMessageBox.warning(
                self, 
                self.tr("dialog.invalid_timeout.title", "Invalid Timeout"), 
                self.tr("dialog.invalid_timeout.body", "Timeout must be a numeric value in seconds.")
            )
            return

        self.run_button.setEnabled(False)
        self.open_report_button.setEnabled(False)
        self.output.setPlainText("")
        self.summary_label.setText(self.tr("summary.running", "Scanning target..."))

        report_dir = self.services.default_output_path() / "network_scans"
        self.services.run_task(
            lambda context: run_network_scan(context, self.services, self.plugin_id, host, port_expression, timeout_seconds, report_dir),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_report_path = result["report_path"]
        open_ports = result["open_ports"]
        
        eastern = "٠١٢٣٤٥٦٧٨٩"
        western = "0123456789"
        trans = str.maketrans(eastern, western)
        
        open_count_str = str(len(open_ports)).translate(trans)
        ports_scanned_str = str(result["ports_scanned"]).translate(trans)

        if open_ports:
            self.output.setPlainText("\n".join(str(port).translate(trans) for port in open_ports))
            self.summary_label.setText(
                self.tr("summary.done", "Scanned {count} ports on {host} and found {open} open ports.", count=ports_scanned_str, host=result['target_host'], open=open_count_str)
            )
            self.services.record_run(
                self.plugin_id,
                "SUCCESS",
                self.tr("summary.done", "Found {open} open ports on {host}", open=open_count_str, host=result['target_host']),
            )
        else:
            self.output.setPlainText(self.tr("output.no_open", "No open ports found."))
            self.summary_label.setText(
                self.tr("summary.no_open", "Scanned {count} ports on {host} with no open ports.", count=ports_scanned_str, host=result['target_host'])
            )
            self.services.record_run(
                self.plugin_id,
                "WARNING",
                self.tr("summary.no_open", "No open ports found on {host}", host=result['target_host']),
            )
        self.open_report_button.setEnabled(True)

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown scan error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "Network scan failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_report(self) -> None:
        if self._latest_report_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_report_path))
