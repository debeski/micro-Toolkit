from __future__ import annotations

import os
import re
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
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


SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".pdf", ".zip", ".gz", ".7z",
    ".exe", ".dll", ".so", ".bin", ".woff", ".woff2", ".ttf", ".mp3", ".mp4",
}


def run_credential_scan(context, target_dir: str):
    rules = {
        "AWS Access Key": re.compile(r"AKIA[0-9A-Z]{16}"),
        "Generic Token": re.compile(
            r"(?i)(?:password|secret|token|api_key)[\s:=]+[\"']?([a-zA-Z0-9_\-\+]{16,})[\"']?"
        ),
    }

    file_list: list[str] = []
    for root, _, files in os.walk(target_dir):
        for file_name in files:
            file_list.append(os.path.join(root, file_name))

    if not file_list:
        raise ValueError("No files found in the selected folder.")

    context.log(f"Scanning {len(file_list)} files for credential exposures...")
    matches: list[str] = []
    for index, path in enumerate(file_list, start=1):
        context.progress(index / float(len(file_list)))
        if Path(path).suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                for line_number, line in enumerate(handle, start=1):
                    for rule_name, pattern in rules.items():
                        if pattern.search(line):
                            matches.append(f"[{rule_name}] {path}:{line_number} -> Match Detected")
        except Exception:
            continue

    report_path = None
    if matches:
        report_path = os.path.join(target_dir, "Credential_Exposures.txt")
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(matches))
            handle.write("\n")
        context.log(f"Potential exposures found: {len(matches)}")
        context.log(f"Saved report to {report_path}")
    else:
        context.log("No credential-like strings detected.")

    return {
        "target_dir": target_dir,
        "matches": matches,
        "report_path": report_path,
        "scanned_files": len(file_list),
    }


class CredentialScannerPlugin(QtPlugin):
    plugin_id = "cred_scanner"
    name = "Credential Scanner"
    description = "Sweep a folder for likely exposed secrets and write a plaintext report when matches are found."
    category = "IT Toolkit"

    def create_widget(self, services) -> QWidget:
        return CredentialScannerPage(services, self.plugin_id)


class CredentialScannerPage(QWidget):
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

        title = QLabel("Credential Scanner")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            "A fast static scan for common secret patterns. It skips obvious binary formats and writes a report beside the scanned folder."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Select a folder to scan...")
        path_row.addWidget(self.path_input, 1)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_folder)
        path_row.addWidget(browse_button)
        layout.addLayout(path_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Scan Folder")
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
        self.summary_label = QLabel("Choose a folder to start a security sweep.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Potential matches will appear here.")
        layout.addWidget(self.output, 1)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder To Scan",
            str(self.services.default_output_path()),
        )
        if folder:
            self.path_input.setText(folder)

    def _run(self) -> None:
        target_dir = self.path_input.text().strip()
        if not target_dir:
            QMessageBox.warning(self, "Missing Input", "Choose a folder to scan.")
            return

        self.run_button.setEnabled(False)
        self.open_report_button.setEnabled(False)
        self.progress.setValue(0)
        self.output.setPlainText("")
        self.summary_label.setText("Scanning folder...")

        self.services.run_task(
            lambda context: run_credential_scan(context, target_dir),
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
        if result["matches"]:
            preview = "\n".join(result["matches"][:200])
            self.output.setPlainText(preview)
            self.summary_label.setText(
                f"Scanned {result['scanned_files']} files and found {len(result['matches'])} potential matches."
            )
            self.open_report_button.setEnabled(True)
            self.services.record_run(
                self.plugin_id,
                "WARNING",
                f"Detected {len(result['matches'])} potential exposures in {result['target_dir']}",
            )
        else:
            self.output.setPlainText("No credential-like strings detected.")
            self.summary_label.setText(f"Scanned {result['scanned_files']} files with no matches.")
            self.services.record_run(self.plugin_id, "SUCCESS", f"Clean scan for {result['target_dir']}")

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown scanner error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Credential scan failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_report(self) -> None:
        if self._latest_report_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_report_path))
