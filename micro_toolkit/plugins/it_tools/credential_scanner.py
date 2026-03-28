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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.page_style import apply_page_chrome
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr, tr


SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".pdf", ".zip", ".gz", ".7z",
    ".exe", ".dll", ".so", ".bin", ".woff", ".woff2", ".ttf", ".mp3", ".mp4",
}


def run_credential_scan(context, services, plugin_id: str, target_dir: str):
    def _ensure_western(text: str) -> str:
        eastern = "٠١٢٣٤٥٦٧٨٩"
        western = "0123456789"
        trans = str.maketrans(eastern, western)
        return text.translate(trans)

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
        raise ValueError(tr(services, plugin_id, "error.no_files", "No files found in the selected folder."))

    context.log(tr(services, plugin_id, "log.start", "Scanning {count} files for credential exposures...", count=_ensure_western(str(len(file_list)))))
    matches: list[str] = []
    match_label = tr(services, plugin_id, "match.label", "Match Detected")
    
    for index, path in enumerate(file_list, start=1):
        context.progress(index / float(len(file_list)))
        if Path(path).suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                for line_number, line in enumerate(handle, start=1):
                    for rule_name, pattern in rules.items():
                        if pattern.search(line):
                            # Ensure line numbers are Western
                            ln_str = _ensure_western(str(line_number))
                            matches.append(f"[{rule_name}] {path}:{ln_str} -> {match_label}")
        except Exception:
            continue

    report_path = None
    if matches:
        report_filename = tr(services, plugin_id, "report.filename", "Credential_Exposures.txt")
        report_path = os.path.join(target_dir, report_filename)
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(matches))
            handle.write("\n")
        
        matches_count = _ensure_western(str(len(matches)))
        context.log(tr(services, plugin_id, "log.matches", "Potential exposures found: {count}", count=matches_count))
        context.log(tr(services, plugin_id, "log.save", "Saved report to {path}", path=report_path))
    else:
        context.log(tr(services, plugin_id, "log.clean", "No credential-like strings detected."))

    return {
        "target_dir": target_dir,
        "matches": matches,
        "report_path": report_path,
        "scanned_files": _ensure_western(str(len(file_list))),
    }


class CredentialScannerPlugin(QtPlugin):
    plugin_id = "cred_scanner"
    name = "Credential Scanner"
    description = "Sweep a folder for likely exposed secrets and write a plaintext report when matches are found."
    category = "IT Utilities"

    def create_widget(self, services) -> QWidget:
        return CredentialScannerPage(services, self.plugin_id)


class CredentialScannerPage(QWidget):
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

        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        self.path_input = QLineEdit()
        path_row.addWidget(self.path_input, 1)

        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._browse_folder)
        path_row.addWidget(self.browse_button)
        self.main_layout.addLayout(path_row)

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
        self.title_label.setText(self.tr("title", "Credential Scanner"))
        self.desc_label.setText(self.tr("description", "A fast static scan for common secret patterns. It skips obvious binary formats and writes a report beside the scanned folder."))
        self.path_input.setPlaceholderText(self.tr("path.placeholder", "Select a folder to scan..."))
        self.browse_button.setText(self.tr("browse", "Browse"))
        self.run_button.setText(self.tr("run.button", "Scan Folder"))
        self.open_report_button.setText(self.tr("report.button", "Open Report"))
        self.summary_label.setText(self.tr("summary.initial", "Choose a folder to start a security sweep."))
        self.output.setPlaceholderText(self.tr("output.placeholder", "Potential matches will appear here."))
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
            self.tr("dialog.browse", "Select Folder To Scan"),
            str(self.services.default_output_path()),
        )
        if folder:
            self.path_input.setText(folder)

    def _run(self) -> None:
        target_dir = self.path_input.text().strip()
        if not target_dir:
            QMessageBox.warning(
                self, 
                self.tr("dialog.missing.title", "Missing Input"), 
                self.tr("dialog.missing.body", "Choose a folder to scan.")
            )
            return

        self.run_button.setEnabled(False)
        self.open_report_button.setEnabled(False)
        self.output.setPlainText("")
        self.summary_label.setText(self.tr("summary.running", "Scanning folder..."))

        self.services.run_task(
            lambda context: run_credential_scan(context, self.services, self.plugin_id, target_dir),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            status_text=self.tr("summary.running", "Scanning folder..."),
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_report_path = result["report_path"]
        
        eastern = "٠١٢٣٤٥٦٧٨٩"
        western = "0123456789"
        trans = str.maketrans(eastern, western)
        
        matches_count_str = str(len(result["matches"])).translate(trans)
        scanned_count_str = str(result["scanned_files"]).translate(trans)

        if result["matches"]:
            preview = "\n".join(result["matches"][:200])
            self.output.setPlainText(preview)
            self.summary_label.setText(
                self.tr("summary.done", "Scanned {count} files and found {matches} potential matches.", count=scanned_count_str, matches=matches_count_str)
            )
            self.open_report_button.setEnabled(True)
            self.services.record_run(
                self.plugin_id,
                "WARNING",
                self.tr("summary.done", "Detected {matches} potential exposures in {dir}", matches=matches_count_str, dir=result['target_dir']),
            )
        else:
            self.output.setPlainText(self.tr("log.clean", "No credential-like strings detected."))
            self.summary_label.setText(self.tr("summary.clean", "Scanned {count} files with no matches.", count=scanned_count_str))
            self.services.record_run(self.plugin_id, "SUCCESS", self.tr("summary.clean", "Clean scan for {dir}", dir=result['target_dir'], count=scanned_count_str))

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown scanner error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "Credential scan failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_report(self) -> None:
        if self._latest_report_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_report_path))
