from __future__ import annotations

import os
import re
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
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


def run_deep_search_task(context, folder_path: str, query: str, use_regex: bool):
    context.log(f"Searching '{folder_path}' for '{query}'...")

    try:
        compiled = re.compile(query) if use_regex else None
    except re.error as exc:
        raise ValueError(f"Invalid regular expression: {exc}") from exc

    file_paths: list[str] = []
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            file_paths.append(os.path.join(root, file_name))

    if not file_paths:
        raise ValueError("No files found in the selected folder.")

    matches: list[tuple[str, int, str]] = []
    for index, file_path in enumerate(file_paths, start=1):
        context.progress(index / float(len(file_paths)))
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if use_regex:
                        if compiled and compiled.search(line):
                            matches.append((file_path, line_number, line.strip()))
                    elif query in line:
                        matches.append((file_path, line_number, line.strip()))
        except Exception:
            continue

    report_path = None
    if matches:
        report_path = os.path.join(folder_path, "DeepSearch_Results.txt")
        with open(report_path, "w", encoding="utf-8") as handle:
            for file_path, line_number, content in matches:
                handle.write(f"[{file_path}:{line_number}] {content}\n")
        context.log(f"Saved search report to {report_path}")

    context.log(f"Deep search complete with {len(matches)} matches.")
    return {
        "query": query,
        "matches": matches,
        "report_path": report_path,
        "files_scanned": len(file_paths),
        "use_regex": use_regex,
    }


class DeepSearcherPlugin(QtPlugin):
    plugin_id = "deep_searcher"
    name = "Deep File Searcher"
    description = "Search file contents across a folder tree using plain text or regular expressions."
    category = "File Utilities"

    def create_widget(self, services) -> QWidget:
        return DeepSearcherPage(services, self.plugin_id)


class DeepSearcherPage(QWidget):
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

        title = QLabel("Deep File Searcher")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            "Search across text files under a folder and write a detailed plaintext report when matches are found."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("Select a folder to search...")
        folder_row.addWidget(self.folder_input, 1)
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_button)
        layout.addLayout(folder_row)

        query_row = QHBoxLayout()
        query_row.setSpacing(10)
        query_label = QLabel("Query")
        query_label.setFixedWidth(90)
        query_row.addWidget(query_label)
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("String or regex pattern...")
        query_row.addWidget(self.query_input, 1)
        layout.addLayout(query_row)

        self.regex_checkbox = QCheckBox("Use regex")
        layout.addWidget(self.regex_checkbox, 0, Qt.AlignmentFlag.AlignLeft)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Run Search")
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
        self.summary_label = QLabel("Choose a folder and query to begin.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Match preview will appear here.")
        layout.addWidget(self.output, 1)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder To Search",
            str(self.services.default_output_path()),
        )
        if folder:
            self.folder_input.setText(folder)

    def _run(self) -> None:
        folder_path = self.folder_input.text().strip()
        query = self.query_input.text().strip()
        if not folder_path or not query:
            QMessageBox.warning(self, "Missing Input", "Choose a folder and enter a query.")
            return

        self.run_button.setEnabled(False)
        self.open_report_button.setEnabled(False)
        self.progress.setValue(0)
        self.output.setPlainText("")
        self.summary_label.setText("Searching files...")

        self.services.run_task(
            lambda context: run_deep_search_task(context, folder_path, query, self.regex_checkbox.isChecked()),
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
            preview_lines = [
                f"{file_path}:{line_number} | {content}"
                for file_path, line_number, content in result["matches"][:200]
            ]
            self.output.setPlainText("\n".join(preview_lines))
            self.summary_label.setText(
                f"Searched {result['files_scanned']} files and found {len(result['matches'])} matches."
            )
            self.open_report_button.setEnabled(True)
            self.services.record_run(
                self.plugin_id,
                "SUCCESS",
                f"Found {len(result['matches'])} matches for '{result['query']}'",
            )
        else:
            self.output.setPlainText("No matches found.")
            self.summary_label.setText(f"Searched {result['files_scanned']} files with no matches.")
            self.services.record_run(
                self.plugin_id,
                "WARNING",
                f"No matches found for '{result['query']}'",
            )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown search error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Deep search failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_report(self) -> None:
        if self._latest_report_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_report_path))
