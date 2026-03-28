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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.page_style import apply_page_chrome
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr, tr


def run_deep_search_task(context, services, plugin_id: str, folder_path: str, query: str, use_regex: bool):
    def _ensure_western(text: str) -> str:
        eastern = "٠١٢٣٤٥٦٧٨٩"
        western = "0123456789"
        trans = str.maketrans(eastern, western)
        return text.translate(trans)

    context.log(tr(services, plugin_id, "log.start", "Searching '{folder}' for '{query}'...", folder=folder_path, query=query))

    try:
        compiled = re.compile(query) if use_regex else None
    except re.error as exc:
        raise ValueError(tr(services, plugin_id, "error.regex", "Invalid regular expression: {exc}", exc=str(exc))) from exc

    file_paths: list[str] = []
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            file_paths.append(os.path.join(root, file_name))

    if not file_paths:
        raise ValueError(tr(services, plugin_id, "error.no_files", "No files found in the selected folder."))

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
                # Use Western numerals for line numbers in report
                handle.write(f"[{file_path}:{_ensure_western(str(line_number))}] {content}\n")
        context.log(tr(services, plugin_id, "log.report", "Saved search report to {path}", path=report_path))

    context.log(tr(services, plugin_id, "log.done", "Deep search complete with {count} matches.", count=_ensure_western(str(len(matches)))))
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

        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        self.folder_input = QLineEdit()
        folder_row.addWidget(self.folder_input, 1)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.browse_button)
        self.main_layout.addLayout(folder_row)

        query_row = QHBoxLayout()
        query_row.setSpacing(10)
        self.query_label_widget = QLabel()
        self.query_label_widget.setFixedWidth(90)
        query_row.addWidget(self.query_label_widget)
        self.query_input = QLineEdit()
        query_row.addWidget(self.query_input, 1)
        self.main_layout.addLayout(query_row)

        self.regex_checkbox = QCheckBox()
        self.main_layout.addWidget(self.regex_checkbox, 0, Qt.AlignmentFlag.AlignLeft)

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
        self.title_label.setText(self.tr("title", "Deep File Searcher"))
        self.desc_label.setText(self.tr("description", "Search across text files under a folder and write a detailed plaintext report when matches are found."))
        self.folder_input.setPlaceholderText(self.tr("folder.placeholder", "Select a folder to search..."))
        self.browse_button.setText(self.tr("browse", "Browse"))
        self.query_label_widget.setText(self.tr("query.label", "Query"))
        self.query_input.setPlaceholderText(self.tr("query.placeholder", "String or regex pattern..."))
        self.regex_checkbox.setText(self.tr("regex.checkbox", "Use regex"))
        self.run_button.setText(self.tr("run.button", "Run Search"))
        self.open_report_button.setText(self.tr("report.button", "Open Report"))
        self.summary_label.setText(self.tr("summary.initial", "Choose a folder and query to begin."))
        self.output.setPlaceholderText(self.tr("output.placeholder", "Match preview will appear here."))
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

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("dialog.browse", "Select Folder To Search"),
            str(self.services.default_output_path()),
        )
        if folder:
            self.folder_input.setText(folder)

    def _run(self) -> None:
        folder_path = self.folder_input.text().strip()
        query = self.query_input.text().strip()
        if not folder_path or not query:
            QMessageBox.warning(
                self, 
                self.tr("dialog.missing.title", "Missing Input"), 
                self.tr("dialog.missing.body", "Choose a folder and enter a query.")
            )
            return

        self.run_button.setEnabled(False)
        self.open_report_button.setEnabled(False)
        self.output.setPlainText("")
        self.summary_label.setText(self.tr("summary.running", "Searching files..."))

        self.services.run_task(
            lambda context: run_deep_search_task(
                context, 
                self.services, 
                self.plugin_id, 
                folder_path, 
                query, 
                self.regex_checkbox.isChecked()
            ),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

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
                self.tr("summary.done", "Searched {files} files and found {matches} matches.", files=str(result['files_scanned']), matches=str(len(result['matches'])))
            )
            self.open_report_button.setEnabled(True)
            self.services.record_run(
                self.plugin_id,
                "SUCCESS",
                self.tr("summary.done", "Searched {files} files and found {matches} matches.", files=str(result['files_scanned']), matches=str(len(result['matches']))),
            )
        else:
            self.output.setPlainText(self.tr("output.none", "No matches found."))
            self.summary_label.setText(self.tr("summary.done", "Searched {files} files and found {matches} matches.", files=str(result['files_scanned']), matches="0"))
            self.services.record_run(
                self.plugin_id,
                "WARNING",
                self.tr("output.none", "No matches found."),
            )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown search error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "Deep search failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_report(self) -> None:
        if self._latest_report_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_report_path))
