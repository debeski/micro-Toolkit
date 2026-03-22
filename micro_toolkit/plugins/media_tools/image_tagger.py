from __future__ import annotations

import os
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.media_utils import SUPPORTED_IMAGE_FILTER, apply_tag, pil_to_pixmap, safe_output_extension
from micro_toolkit.core.plugin_api import QtPlugin


def run_image_tagger_task(context, files: list[str], output_dir: str, name: str, date_mode: str, custom_date: str):
    os.makedirs(output_dir, exist_ok=True)
    output_files = []
    for index, file_path in enumerate(files, start=1):
        context.progress(index / float(len(files)))
        context.log(f"Tagging {os.path.basename(file_path)}...")
        image = Image.open(file_path)
        tagged = apply_tag(image, name, date_mode, custom_date)
        output_ext = safe_output_extension(file_path, None)
        output_name = f"tagged_{Path(file_path).stem}{output_ext}"
        output_path = os.path.join(output_dir, output_name)
        save_format = output_ext.lstrip(".").upper()
        if save_format == "JPG":
            save_format = "JPEG"
        tagged.save(output_path, format=save_format)
        output_files.append(output_path)

    context.log(f"Batch tagging complete. Wrote {len(output_files)} files.")
    return {
        "count": len(output_files),
        "output_dir": output_dir,
        "files": output_files,
    }


class ImageTaggerPlugin(QtPlugin):
    plugin_id = "tagger"
    name = "Image Tagger"
    description = "Batch-apply a smart glassmorphic date/name tag to images with live preview and cleaner controls."
    category = "Media Utilities"

    def create_widget(self, services) -> QWidget:
        return ImageTaggerPage(services, self.plugin_id)


class ImageTaggerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.files: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        title = QLabel("Image Tagger")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        outer.addWidget(title)

        description = QLabel(
            "Apply a clean bottom-right tag using EXIF date, today's date, or a custom date while previewing the selected image."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        outer.addWidget(description)

        form_card = QFrame()
        form_card.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }"
        )
        form = QFormLayout(form_card)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(10)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Name or signature")
        form.addRow("Tag Name", self.name_input)

        self.date_mode = QComboBox()
        self.date_mode.addItems(["taken", "today", "custom"])
        self.date_mode.currentTextChanged.connect(self._update_custom_date_visibility)
        form.addRow("Date Source", self.date_mode)

        self.custom_date_input = QLineEdit()
        self.custom_date_input.setPlaceholderText("YYYY-MM-DD or any parseable date")
        form.addRow("Custom Date", self.custom_date_input)
        outer.addWidget(form_card)

        files_row = QHBoxLayout()
        add_button = QPushButton("Add Images")
        add_button.clicked.connect(self._add_files)
        clear_button = QPushButton("Clear All")
        clear_button.clicked.connect(self._clear_files)
        files_row.addWidget(add_button)
        files_row.addWidget(clear_button)
        files_row.addStretch(1)
        outer.addLayout(files_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        self.file_list = QListWidget()
        self.file_list.currentRowChanged.connect(self._show_preview_for_row)
        left_layout.addWidget(self.file_list, 1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        self.preview_label = QLabel("Select an image to preview.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(320)
        self.preview_label.setStyleSheet(
            "QLabel { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; color: #56646b; }"
        )
        right_layout.addWidget(self.preview_label, 1)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        controls = QHBoxLayout()
        self.run_button = QPushButton("Run Tagger")
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.progress, 1)
        outer.addLayout(controls)

        self.summary_output = QPlainTextEdit()
        self.summary_output.setReadOnly(True)
        self.summary_output.setPlaceholderText("Tagger summary will appear here.")
        outer.addWidget(self.summary_output, 1)

        self._update_custom_date_visibility()

    def _update_custom_date_visibility(self) -> None:
        is_custom = self.date_mode.currentText() == "custom"
        self.custom_date_input.setVisible(is_custom)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            str(self.services.default_output_path()),
            SUPPORTED_IMAGE_FILTER,
        )
        if not files:
            return
        for file_path in files:
            if file_path not in self.files:
                self.files.append(file_path)
        self._refresh_file_list()
        if self.files and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)

    def _clear_files(self) -> None:
        self.files = []
        self.file_list.clear()
        self.preview_label.setPixmap(None)
        self.preview_label.setText("Select an image to preview.")

    def _refresh_file_list(self) -> None:
        self.file_list.clear()
        for file_path in self.files:
            item = QListWidgetItem(os.path.basename(file_path))
            item.setToolTip(file_path)
            self.file_list.addItem(item)

    def _show_preview_for_row(self, row: int) -> None:
        if row < 0 or row >= len(self.files):
            return
        path = self.files[row]
        try:
            image = Image.open(path)
            preview_name = self.name_input.text().strip() or "PREVIEW"
            custom_date = self.custom_date_input.text().strip()
            tagged_preview = apply_tag(image, preview_name, self.date_mode.currentText(), custom_date)
            self.preview_label.setPixmap(pil_to_pixmap(tagged_preview))
            self.preview_label.setText("")
        except Exception as exc:
            self.preview_label.setPixmap(None)
            self.preview_label.setText(f"Preview error: {exc}")

    def _run(self) -> None:
        if not self.files:
            QMessageBox.warning(self, "Missing Input", "Add at least one image first.")
            return
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Input", "Enter a tag name first.")
            return
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            str(self.services.default_output_path()),
        )
        if not output_dir:
            return

        date_mode = self.date_mode.currentText()
        custom_date = self.custom_date_input.text().strip()

        self.run_button.setEnabled(False)
        self.progress.setValue(0)
        self.summary_output.clear()
        self.services.run_task(
            lambda context: run_image_tagger_task(
                context,
                list(self.files),
                output_dir,
                name,
                date_mode,
                custom_date,
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
        self.summary_output.setPlainText(
            f"Batch tagging complete.\nFiles written: {result['count']}\nOutput folder: {result['output_dir']}"
        )
        self.services.record_run(self.plugin_id, "SUCCESS", f"Tagged {result['count']} images")

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown image tagger error") if isinstance(payload, dict) else str(payload)
        self.summary_output.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Image tagger failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
