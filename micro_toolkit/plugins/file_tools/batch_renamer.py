from __future__ import annotations

import os
import re

from PySide6.QtCore import Qt
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


def batch_rename_task(context, target_dir: str, search_rule: str, replace_str: str, use_regex: bool):
    context.log(f"Batch renaming files under '{target_dir}'...")
    total = sum(len(files) for _, _, files in os.walk(target_dir))
    if total == 0:
        raise ValueError("No files were found in the selected directory.")

    compiled = None
    if use_regex:
        try:
            compiled = re.compile(search_rule)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc

    renamed_pairs: list[tuple[str, str]] = []
    failures: list[str] = []
    processed = 0

    for root, _, files in os.walk(target_dir):
        for file_name in files:
            processed += 1
            context.progress(processed / float(total))

            old_path = os.path.join(root, file_name)
            new_name = compiled.sub(replace_str, file_name) if use_regex and compiled else file_name.replace(search_rule, replace_str)
            if new_name == file_name:
                continue

            new_path = os.path.join(root, new_name)
            try:
                os.rename(old_path, new_path)
                renamed_pairs.append((file_name, new_name))
            except Exception as exc:
                failures.append(f"{file_name} -> {new_name}: {exc}")

    context.log(f"Renaming complete. Updated {len(renamed_pairs)} files.")
    return {
        "renamed_pairs": renamed_pairs,
        "failures": failures,
        "target_dir": target_dir,
    }


class BatchRenamerPlugin(QtPlugin):
    plugin_id = "batch_renamer"
    name = "Batch File Renamer"
    description = "Rename many files under a directory using plain text replacement or regex substitution."
    category = "File Utilities"

    def create_widget(self, services) -> QWidget:
        return BatchRenamerPage(services, self.plugin_id)


class BatchRenamerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Batch File Renamer")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            "Apply a string replacement or regex substitution to filenames across a directory tree."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("Select a directory...")
        folder_row.addWidget(self.folder_input, 1)
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_button)
        layout.addLayout(folder_row)

        find_row = QHBoxLayout()
        find_row.setSpacing(10)
        find_label = QLabel("Find")
        find_label.setFixedWidth(90)
        find_row.addWidget(find_label)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Text or regex pattern")
        find_row.addWidget(self.find_input, 1)
        layout.addLayout(find_row)

        replace_row = QHBoxLayout()
        replace_row.setSpacing(10)
        replace_label = QLabel("Replace")
        replace_label.setFixedWidth(90)
        replace_row.addWidget(replace_label)
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replacement string")
        replace_row.addWidget(self.replace_input, 1)
        layout.addLayout(replace_row)

        self.regex_checkbox = QCheckBox("Use regex")
        layout.addWidget(self.regex_checkbox, 0, Qt.AlignmentFlag.AlignLeft)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Run Renamer")
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

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
        self.summary_label = QLabel("Choose a directory and naming rule to begin.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Rename preview will appear here.")
        layout.addWidget(self.output, 1)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Directory",
            str(self.services.default_output_path()),
        )
        if folder:
            self.folder_input.setText(folder)

    def _run(self) -> None:
        target_dir = self.folder_input.text().strip()
        search_rule = self.find_input.text().strip()
        replace_str = self.replace_input.text()
        if not target_dir or not search_rule:
            QMessageBox.warning(self, "Missing Input", "Choose a directory and enter a find rule.")
            return

        self.run_button.setEnabled(False)
        self.progress.setValue(0)
        self.output.setPlainText("")
        self.summary_label.setText("Renaming files...")

        self.services.run_task(
            lambda context: batch_rename_task(
                context,
                target_dir,
                search_rule,
                replace_str,
                self.regex_checkbox.isChecked(),
            ),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            on_progress=self._handle_progress,
        )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        preview = [f"{old} -> {new}" for old, new in result["renamed_pairs"][:300]]
        if result["failures"]:
            preview.extend(["", "Failures:"])
            preview.extend(result["failures"][:50])
        self.output.setPlainText("\n".join(preview) if preview else "No files required renaming.")
        self.summary_label.setText(
            f"Renamed {len(result['renamed_pairs'])} files in {result['target_dir']}."
        )
        status = "SUCCESS" if result["renamed_pairs"] else "WARNING"
        self.services.record_run(
            self.plugin_id,
            status,
            f"Renamed {len(result['renamed_pairs'])} files in {result['target_dir']}",
        )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown batch renamer error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Batch renamer failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
