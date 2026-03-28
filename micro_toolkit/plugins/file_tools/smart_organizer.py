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
    QPushButton,
    QComboBox,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.page_style import apply_page_chrome
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr, tr
from micro_toolkit.core.widgets import ScrollSafeComboBox


QComboBox = ScrollSafeComboBox


UNDO_FILE = ".micro_undo.json"


def organize_files_task(context, services, plugin_id: str, folder_path: str, logic_type: str):
    def _ensure_western(text: str) -> str:
        eastern = "٠١٢٣٤٥٦٧٨٩"
        western = "0123456789"
        trans = str.maketrans(eastern, western)
        return text.translate(trans)

    files = [name for name in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, name))]
    if not files:
        raise ValueError(tr(services, plugin_id, "error.no_files", "No root-level files were found in the selected directory."))

    context.log(tr(services, plugin_id, "log.start", "Organizing '{folder}' using '{mode}' mode...", folder=folder_path, mode=logic_type))
    undo_map: dict[str, str] = {}

    for index, file_name in enumerate(files, start=1):
        context.progress(index / float(len(files)))
        ext = os.path.splitext(file_name)[1].lower().strip(".") or "unknown"
        target_subdir = f"{ext.upper()}_FILES"
        source_path = os.path.join(folder_path, file_name)

        if logic_type == "date":
            timestamp = os.path.getmtime(source_path)
            # Use Western numerals for the folder name
            target_subdir = _ensure_western(datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m"))

        target_dir = os.path.join(folder_path, target_subdir)
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, file_name)

        try:
            shutil.move(source_path, target_path)
            undo_map[source_path] = target_path
        except Exception as exc:
            context.log(tr(services, plugin_id, "log.warning.move", "Move failed for '{file}': {exc}", file=file_name, exc=str(exc)), "WARNING")

    undo_path = os.path.join(folder_path, UNDO_FILE)
    with open(undo_path, "w", encoding="utf-8") as handle:
        json.dump(undo_map, handle, indent=2)

    context.log(tr(services, plugin_id, "log.done", "Organization complete. Moved {count} files.", count=_ensure_western(str(len(undo_map)))))
    return {
        "moved_count": len(undo_map),
        "undo_path": undo_path,
        "folder_path": folder_path,
    }


def undo_organization_task(context, services, plugin_id: str, folder_path: str):
    def _ensure_western(text: str) -> str:
        eastern = "٠١٢٣٤٥٦٧٨٩"
        western = "0123456789"
        trans = str.maketrans(eastern, western)
        return text.translate(trans)

    undo_path = os.path.join(folder_path, UNDO_FILE)
    if not os.path.exists(undo_path):
        raise ValueError(tr(services, plugin_id, "error.no_undo", "No undo registry was found in the selected directory."))

    with open(undo_path, "r", encoding="utf-8") as handle:
        undo_map = json.load(handle)

    if not undo_map:
        raise ValueError(tr(services, plugin_id, "error.empty_undo", "Undo registry exists but is empty."))

    restored = 0
    items = list(undo_map.items())
    context.log(tr(services, plugin_id, "log.undo_start", "Restoring files from undo registry..."))
    for index, (original_path, moved_path) in enumerate(items, start=1):
        context.progress(index / float(len(items)))
        if not os.path.exists(moved_path):
            continue
        os.makedirs(os.path.dirname(original_path), exist_ok=True)
        try:
            shutil.move(moved_path, original_path)
            restored += 1
        except Exception as exc:
            context.log(tr(services, plugin_id, "log.warning.undo", "Undo failed for '{file}': {exc}", file=moved_path, exc=str(exc)), "WARNING")

    os.remove(undo_path)
    context.log(tr(services, plugin_id, "log.undo_done", "Rollback complete. Restored {count} files.", count=_ensure_western(str(restored))))
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

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        self.mode_label_widget = QLabel()
        self.mode_label_widget.setFixedWidth(90)
        mode_row.addWidget(self.mode_label_widget)
        self.mode_combo = ScrollSafeComboBox()
        mode_row.addWidget(self.mode_combo, 1)
        self.main_layout.addLayout(mode_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.organize_button = QPushButton()
        self.organize_button.clicked.connect(self._run_organize)
        controls.addWidget(self.organize_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.undo_button = QPushButton()
        self.undo_button.clicked.connect(self._run_undo)
        controls.addWidget(self.undo_button, 0, Qt.AlignmentFlag.AlignLeft)

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
        self.title_label.setText(self.tr("title", "Smart File Organizer"))
        self.desc_label.setText(self.tr("description", "Organize root-level files by extension or last modified date, then reverse the operation later using the saved undo registry."))
        self.folder_input.setPlaceholderText(self.tr("folder.placeholder", "Select a directory..."))
        self.browse_button.setText(self.tr("browse", "Browse"))
        self.mode_label_widget.setText(self.tr("mode.label", "Mode"))
        
        current_mode = self.mode_combo.currentData()
        self.mode_combo.clear()
        self.mode_combo.addItem(self.tr("mode.extension", "extension"), "extension")
        self.mode_combo.addItem(self.tr("mode.date", "date"), "date")
        
        if current_mode:
            idx = self.mode_combo.findData(current_mode)
            if idx >= 0:
                self.mode_combo.setCurrentIndex(idx)
        
        self.organize_button.setText(self.tr("run.organize", "Organize Files"))
        self.undo_button.setText(self.tr("run.undo", "Undo Organization"))
        self.summary_label.setText(self.tr("summary.initial", "Choose a directory to organize."))
        self.output.setPlaceholderText(self.tr("output.placeholder", "Organizer activity will appear here."))
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

    def _set_busy(self, busy: bool) -> None:
        self.organize_button.setEnabled(not busy)
        self.undo_button.setEnabled(not busy)

    def _run_organize(self) -> None:
        folder_path = self.folder_input.text().strip()
        if not folder_path:
            QMessageBox.warning(
                self, 
                self.tr("dialog.missing.title", "Missing Input"), 
                self.tr("dialog.missing.body.organize", "Choose a directory to organize.")
            )
            return

        self._set_busy(True)
        self.output.setPlainText("")
        self.summary_label.setText(self.tr("summary.organizing", "Organizing files..."))

        self.services.run_task(
            lambda context: organize_files_task(
                context, 
                self.services, 
                self.plugin_id, 
                folder_path, 
                self.mode_combo.currentData()
            ),
            on_result=self._handle_organize_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _run_undo(self) -> None:
        folder_path = self.folder_input.text().strip()
        if not folder_path:
            QMessageBox.warning(
                self, 
                self.tr("dialog.missing.title", "Missing Input"), 
                self.tr("dialog.missing.body.undo", "Choose a directory to restore.")
            )
            return

        self._set_busy(True)
        self.output.setPlainText("")
        self.summary_label.setText(self.tr("summary.undoing", "Restoring organized files..."))

        self.services.run_task(
            lambda context: undo_organization_task(
                context, 
                self.services, 
                self.plugin_id, 
                folder_path
            ),
            on_result=self._handle_undo_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_organize_result(self, payload: object) -> None:
        result = dict(payload)
        self.summary_label.setText(
            self.tr("summary.done", "Moved {count} files and wrote an undo registry to {path}.", count=str(result['moved_count']), path=result['undo_path'])
        )
        self.output.setPlainText(
            self.tr("output.done", "Organization complete.\nFolder: {folder}\nUndo registry: {path}", folder=result['folder_path'], path=result['undo_path'])
        )
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            self.tr("summary.done", "Moved {count} files in {folder}", count=str(result['moved_count']), folder=result['folder_path']),
        )

    def _handle_undo_result(self, payload: object) -> None:
        result = dict(payload)
        self.summary_label.setText(
            self.tr("summary.undo_done", "Restored {count} files in {folder}.", count=str(result['restored_count']), folder=result['folder_path'])
        )
        self.output.setPlainText(
            self.tr("output.undo_done", "Rollback complete.\nFolder: {folder}\nRestored files: {count}", folder=result['folder_path'], count=str(result['restored_count']))
        )
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            self.tr("summary.undo_done", "Restored {count} files in {folder}", count=str(result['restored_count']), folder=result['folder_path']),
        )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown organizer error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "Smart organizer failed."), "ERROR")

    def _finish_run(self) -> None:
        self._set_busy(False)
