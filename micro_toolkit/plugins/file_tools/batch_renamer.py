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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.page_style import apply_page_chrome
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr, tr


def batch_rename_task(context, services, plugin_id: str, target_dir: str, search_rule: str, replace_str: str, use_regex: bool):
    context.log(tr(services, plugin_id, "log.start", "Batch renaming files under '{target_dir}'...", target_dir=target_dir))
    total = sum(len(files) for _, _, files in os.walk(target_dir))
    if total == 0:
        raise ValueError(tr(services, plugin_id, "error.no_files", "No files were found in the selected directory."))

    compiled = None
    if use_regex:
        try:
            compiled = re.compile(search_rule)
        except re.error as exc:
            raise ValueError(tr(services, plugin_id, "error.regex", "Invalid regular expression: {exc}", exc=str(exc))) from exc

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

    context.log(tr(services, plugin_id, "log.done", "Renaming complete. Updated {count} files.", count=str(len(renamed_pairs))))
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
        self.tr = bind_tr(services, plugin_id)
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

        find_row = QHBoxLayout()
        find_row.setSpacing(10)
        self.find_label = QLabel()
        self.find_label.setFixedWidth(90)
        find_row.addWidget(self.find_label)
        self.find_input = QLineEdit()
        find_row.addWidget(self.find_input, 1)
        self.main_layout.addLayout(find_row)

        replace_row = QHBoxLayout()
        replace_row.setSpacing(10)
        self.replace_label = QLabel()
        self.replace_label.setFixedWidth(90)
        replace_row.addWidget(self.replace_label)
        self.replace_input = QLineEdit()
        replace_row.addWidget(self.replace_input, 1)
        self.main_layout.addLayout(replace_row)

        self.regex_checkbox = QCheckBox()
        self.main_layout.addWidget(self.regex_checkbox, 0, Qt.AlignmentFlag.AlignLeft)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

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
        self.title_label.setText(self.tr("title", "Batch File Renamer"))
        self.desc_label.setText(self.tr("description", "Apply a string replacement or regex substitution to filenames across a directory tree."))
        self.folder_input.setPlaceholderText(self.tr("folder.placeholder", "Select a directory..."))
        self.browse_button.setText(self.tr("browse", "Browse"))
        self.find_label.setText(self.tr("find.label", "Find"))
        self.find_input.setPlaceholderText(self.tr("find.placeholder", "Text or regex pattern"))
        self.replace_label.setText(self.tr("replace.label", "Replace"))
        self.replace_input.setPlaceholderText(self.tr("replace.placeholder", "Replacement string"))
        self.regex_checkbox.setText(self.tr("regex.checkbox", "Use regex"))
        self.run_button.setText(self.tr("run.button", "Run Renamer"))
        self.summary_label.setText(self.tr("summary.initial", "Choose a directory and naming rule to begin."))
        self.output.setPlaceholderText(self.tr("output.placeholder", "Rename preview will appear here."))
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
            self.tr("dialog.browse", "Select Directory"),
            str(self.services.default_output_path()),
        )
        if folder:
            self.folder_input.setText(folder)

    def _run(self) -> None:
        target_dir = self.folder_input.text().strip()
        search_rule = self.find_input.text().strip()
        replace_str = self.replace_input.text()
        if not target_dir or not search_rule:
            QMessageBox.warning(
                self, 
                self.tr("dialog.missing.title", "Missing Input"), 
                self.tr("dialog.missing.body", "Choose a directory and enter a find rule.")
            )
            return

        self.run_button.setEnabled(False)
        self.output.setPlainText("")
        self.summary_label.setText(self.tr("summary.running", "Renaming files..."))

        self.services.run_task(
            lambda context: batch_rename_task(
                context,
                self.services,
                self.plugin_id,
                target_dir,
                search_rule,
                replace_str,
                self.regex_checkbox.isChecked(),
            ),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        preview = [f"{old} -> {new}" for old, new in result["renamed_pairs"][:300]]
        if result["failures"]:
            preview.extend(["", "Failures:"])
            preview.extend(result["failures"][:50])
        self.output.setPlainText("\n".join(preview) if preview else self.tr("output.none", "No files required renaming."))
        self.summary_label.setText(
            self.tr("summary.done", "Renamed {count} files in {target_dir}.", count=str(len(result['renamed_pairs'])), target_dir=result['target_dir'])
        )
        status = "SUCCESS" if result["renamed_pairs"] else "WARNING"
        self.services.record_run(
            self.plugin_id,
            status,
            self.tr("summary.done", "Renamed {count} files in {target_dir}.", count=str(len(result['renamed_pairs'])), target_dir=result['target_dir']),
        )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown batch renamer error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "Batch renamer failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
