from __future__ import annotations

import os
import shutil
import re
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QListWidget,
)

from micro_toolkit.core.page_style import apply_page_chrome, section_title_style
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr, tr


def run_shred_task(context, services, plugin_id: str, paths: list[Path], passes: int):
    def _ensure_western(text: str) -> str:
        eastern = "٠١٢٣٤٥٦٧٨٩"
        western = "0123456789"
        trans = str.maketrans(eastern, western)
        return text.translate(trans)

    total = len(paths)
    context.log(tr(services, plugin_id, "log.start", "Starting secure shredding of {count} items with {passes} passes...", count=_ensure_western(str(total)), passes=_ensure_western(str(passes))))
    
    for i, path in enumerate(paths, 1):
        if not path.exists():
            context.log(tr(services, plugin_id, "log.not_found", "Skipping non-existent path: {path}", path=str(path)), "WARNING")
            continue
            
        context.log(tr(services, plugin_id, "log.shredding", "Shredding: {name}", name=path.name))
        try:
            if path.is_file():
                length = path.stat().st_size
                with open(path, "wb") as f:
                    for _ in range(passes):
                        f.seek(0)
                        f.write(os.urandom(length))
                        f.flush()
                        os.fsync(f.fileno())
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
            context.log(tr(services, plugin_id, "log.success", "Permanently deleted: {name}", name=path.name))
        except Exception as e:
            context.log(tr(services, plugin_id, "log.error", "Failed to shred {name}: {error}", name=path.name, error=str(e)), "ERROR")
            
        context.progress(i / total)

    context.log(tr(services, plugin_id, "log.done", "Privacy shredding operation complete."))
    return {"shredded_count": _ensure_western(str(total))}


class PrivacyShredderPlugin(QtPlugin):
    plugin_id = "privacy_shred"
    name = "Privacy Shredder"
    description = "Securely wipe files and directories by overwriting them multiple times before deletion."
    category = "IT Utilities"

    def create_widget(self, services) -> QWidget:
        return PrivacyShredderPage(services, self.plugin_id)


class PrivacyShredderPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self._paths: list[Path] = []
        self._build_ui()
        self._apply_texts()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._apply_theme_styles)

    def _build_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(28, 28, 28, 28)
        self.main_layout.setSpacing(16)

        self.title_label = QLabel()
        self.main_layout.addWidget(self.title_label)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.main_layout.addWidget(self.desc_label)

        list_header = QHBoxLayout()
        self.queue_label = QLabel()
        list_header.addWidget(self.queue_label)
        list_header.addStretch()
        
        self.add_file_btn = QPushButton()
        self.add_file_btn.clicked.connect(self._add_files)
        list_header.addWidget(self.add_file_btn)
        
        self.add_dir_btn = QPushButton()
        self.add_dir_btn.clicked.connect(self._add_dir)
        list_header.addWidget(self.add_dir_btn)
        
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self._clear_queue)
        list_header.addWidget(self.clear_btn)
        self.main_layout.addLayout(list_header)

        self.path_list = QListWidget()
        self.main_layout.addWidget(self.path_list, 1)

        pass_row = QHBoxLayout()
        self.passes_label_widget = QLabel()
        pass_row.addWidget(self.passes_label_widget)
        self.passes_input = QSpinBox()
        self.passes_input.setRange(1, 35)
        self.passes_input.setValue(3)
        pass_row.addWidget(self.passes_input)
        pass_row.addStretch()
        self.main_layout.addLayout(pass_row)

        controls = QHBoxLayout()
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button)

        self.main_layout.addLayout(controls)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.main_layout.addWidget(self.output, 1)
        
    def _apply_texts(self) -> None:
        self.title_label.setText(self.tr("title", "Privacy Shredder"))
        self.desc_label.setText(self.tr("description", "Permanently destroy sensitive files. Warning: Data deleted this way cannot be recovered even with specialized forensics software."))
        self.queue_label.setText(self.tr("queue.label", "Shredding Queue"))
        self.add_file_btn.setText(self.tr("button.add_files", "Add Files"))
        self.add_dir_btn.setText(self.tr("button.add_folder", "Add Folder"))
        self.clear_btn.setText(self.tr("button.clear", "Clear"))
        self.passes_label_widget.setText(self.tr("passes.label", "Overwriting Passes:"))
        self.run_button.setText(self.tr("button.run", "Wipe Selected Data"))
        self.output.setPlaceholderText(self.tr("output.placeholder", "Operation logs will appear here..."))
        self._apply_theme_styles()

    def _apply_theme_styles(self, *_args) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.desc_label,
            title_size=26,
            title_weight=700,
        )
        self.queue_label.setStyleSheet(section_title_style(palette, size=15, weight=700))

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, self.tr("dialog.select_files", "Select Files to Shred"))
        if files:
            for f in files:
                p = Path(f)
                if p not in self._paths:
                    self._paths.append(p)
                    self.path_list.addItem(str(p))

    def _add_dir(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, self.tr("dialog.select_folder", "Select Folder to Shred"))
        if dir_path:
            p = Path(dir_path)
            if p not in self._paths:
                self._paths.append(p)
                self.path_list.addItem(str(p))

    def _clear_queue(self) -> None:
        self._paths.clear()
        self.path_list.clear()

    def _run(self) -> None:
        if not self._paths:
            QMessageBox.information(self, self.tr("dialog.empty.title", "Queue Empty"), self.tr("dialog.empty.body", "Please add files or folders to shred first."))
            return

        confirm = QMessageBox.critical(
            self,
            self.tr("dialog.confirm.title", "Final Warning"),
            self.tr("dialog.confirm.body", "Are you absolutely sure? This will IRREVERSIBLY destroy {count} items. This cannot be undone.", count=str(len(self._paths))),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.run_button.setEnabled(False)
        self.add_file_btn.setEnabled(False)
        self.add_dir_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.output.setPlainText("")
        
        passes = self.passes_input.value()
        
        self.services.run_task(
            lambda context: run_shred_task(context, self.services, self.plugin_id, self._paths, passes),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            status_text=self.tr("log.start", "Starting secure shredding..."),
        )

    def _handle_result(self, payload: object) -> None:
        self._clear_queue()
        self.services.record_run(self.plugin_id, "SUCCESS", self.tr("log.done", "Privacy shredding operation complete."))

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown shred error") if isinstance(payload, dict) else str(payload)
        self.output.appendPlainText(f"\nERROR: {message}")
        self.services.record_run(self.plugin_id, "ERROR", message[:500])

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
        self.add_file_btn.setEnabled(True)
        self.add_dir_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
