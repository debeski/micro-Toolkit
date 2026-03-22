from __future__ import annotations

import datetime
import json
import os
import shutil

from PySide6.QtCore import Qt
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
    QComboBox,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin


UNDO_FILE = ".micro_undo.json"


def organize_files_task(context, folder_path: str, logic_type: str):
    files = [name for name in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, name))]
    if not files:
        raise ValueError("No root-level files were found in the selected directory.")

    context.log(f"Organizing '{folder_path}' using '{logic_type}' mode...")
    undo_map: dict[str, str] = {}

    for index, file_name in enumerate(files, start=1):
        context.progress(index / float(len(files)))
        ext = os.path.splitext(file_name)[1].lower().strip(".") or "unknown"
        target_subdir = f"{ext.upper()}_FILES"
        source_path = os.path.join(folder_path, file_name)

        if logic_type == "date":
            timestamp = os.path.getmtime(source_path)
            target_subdir = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m")

        target_dir = os.path.join(folder_path, target_subdir)
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, file_name)

        try:
            shutil.move(source_path, target_path)
            undo_map[source_path] = target_path
        except Exception as exc:
            context.log(f"Move failed for '{file_name}': {exc}", "WARNING")

    undo_path = os.path.join(folder_path, UNDO_FILE)
    with open(undo_path, "w", encoding="utf-8") as handle:
        json.dump(undo_map, handle, indent=2)

    context.log(f"Organization complete. Moved {len(undo_map)} files.")
    return {
        "moved_count": len(undo_map),
        "undo_path": undo_path,
        "folder_path": folder_path,
    }


def undo_organization_task(context, folder_path: str):
    undo_path = os.path.join(folder_path, UNDO_FILE)
    if not os.path.exists(undo_path):
        raise ValueError("No undo registry was found in the selected directory.")

    with open(undo_path, "r", encoding="utf-8") as handle:
        undo_map = json.load(handle)

    if not undo_map:
        raise ValueError("Undo registry exists but is empty.")

    restored = 0
    items = list(undo_map.items())
    for index, (original_path, moved_path) in enumerate(items, start=1):
        context.progress(index / float(len(items)))
        if not os.path.exists(moved_path):
            continue
        os.makedirs(os.path.dirname(original_path), exist_ok=True)
        try:
            shutil.move(moved_path, original_path)
            restored += 1
        except Exception as exc:
            context.log(f"Undo failed for '{moved_path}': {exc}", "WARNING")

    os.remove(undo_path)
    context.log(f"Rollback complete. Restored {restored} files.")
    return {
        "restored_count": restored,
        "folder_path": folder_path,
    }


class SmartOrganizerPlugin(QtPlugin):
    plugin_id = "smart_org"
    name = "Smart File Organizer"
    description = "Move root-level files into extension-based or date-based folders, with rollback support."
    category = "File Utilities"

    def create_widget(self, services) -> QWidget:
        return SmartOrganizerPage(services, self.plugin_id)


class SmartOrganizerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Smart File Organizer")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            "Organize root-level files by extension or last modified date, then reverse the operation later using the saved undo registry."
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

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_label = QLabel("Mode")
        mode_label.setFixedWidth(90)
        mode_row.addWidget(mode_label)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["extension", "date"])
        mode_row.addWidget(self.mode_combo, 1)
        layout.addLayout(mode_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.organize_button = QPushButton("Organize Files")
        self.organize_button.clicked.connect(self._run_organize)
        controls.addWidget(self.organize_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.undo_button = QPushButton("Undo Organization")
        self.undo_button.clicked.connect(self._run_undo)
        controls.addWidget(self.undo_button, 0, Qt.AlignmentFlag.AlignLeft)

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
        self.summary_label = QLabel("Choose a directory to organize.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Organizer activity will appear here.")
        layout.addWidget(self.output, 1)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Directory",
            str(self.services.default_output_path()),
        )
        if folder:
            self.folder_input.setText(folder)

    def _set_busy(self, busy: bool) -> None:
        self.organize_button.setEnabled(not busy)
        self.undo_button.setEnabled(not busy)

    def _run_organize(self) -> None:
        folder_path = self.folder_input.text().strip()
        if not folder_path:
            QMessageBox.warning(self, "Missing Input", "Choose a directory to organize.")
            return

        self._set_busy(True)
        self.progress.setValue(0)
        self.output.setPlainText("")
        self.summary_label.setText("Organizing files...")

        self.services.run_task(
            lambda context: organize_files_task(context, folder_path, self.mode_combo.currentText()),
            on_result=self._handle_organize_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            on_progress=self._handle_progress,
        )

    def _run_undo(self) -> None:
        folder_path = self.folder_input.text().strip()
        if not folder_path:
            QMessageBox.warning(self, "Missing Input", "Choose a directory to restore.")
            return

        self._set_busy(True)
        self.progress.setValue(0)
        self.output.setPlainText("")
        self.summary_label.setText("Restoring organized files...")

        self.services.run_task(
            lambda context: undo_organization_task(context, folder_path),
            on_result=self._handle_undo_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            on_progress=self._handle_progress,
        )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_organize_result(self, payload: object) -> None:
        result = dict(payload)
        self.summary_label.setText(
            f"Moved {result['moved_count']} files and wrote an undo registry to {result['undo_path']}."
        )
        self.output.setPlainText(
            f"Organization complete.\nFolder: {result['folder_path']}\nUndo registry: {result['undo_path']}"
        )
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            f"Organized {result['moved_count']} files in {result['folder_path']}",
        )

    def _handle_undo_result(self, payload: object) -> None:
        result = dict(payload)
        self.summary_label.setText(
            f"Restored {result['restored_count']} files in {result['folder_path']}."
        )
        self.output.setPlainText(
            f"Rollback complete.\nFolder: {result['folder_path']}\nRestored files: {result['restored_count']}"
        )
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            f"Restored {result['restored_count']} files in {result['folder_path']}",
        )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown organizer error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Smart organizer failed.", "ERROR")

    def _finish_run(self) -> None:
        self._set_busy(False)
