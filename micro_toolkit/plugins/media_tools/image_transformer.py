from __future__ import annotations

import os
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
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

from micro_toolkit.core.media_utils import SUPPORTED_IMAGE_FILTER, pil_to_pixmap, safe_output_extension, transform_image
from micro_toolkit.core.plugin_api import QtPlugin


def run_image_transform_task(context, files: list[str], output_dir: str, options: dict):
    os.makedirs(output_dir, exist_ok=True)
    transformed_files = []
    for index, file_path in enumerate(files, start=1):
        context.progress(index / float(len(files)))
        context.log(f"Transforming {os.path.basename(file_path)}...")
        image = Image.open(file_path)
        transformed, requested_format = transform_image(
            image,
            rotate_value=options.get("rotate_value"),
            resize_enabled=options.get("resize_enabled", False),
            resize_type=options.get("resize_type", "pixels"),
            width_value=options.get("resize_width", ""),
            height_value=options.get("resize_height", ""),
            format_value=options.get("format_value"),
        )

        base_name = Path(file_path).stem
        output_ext = safe_output_extension(file_path, requested_format)
        output_name = f"trans_{base_name}{output_ext}"
        output_path = os.path.join(output_dir, output_name)

        save_format = output_ext.lstrip(".").upper()
        if save_format == "JPG":
            save_format = "JPEG"
        transformed.save(output_path, format=save_format)
        transformed_files.append(output_path)

    context.log(f"Batch transform complete. Wrote {len(transformed_files)} files.")
    return {
        "count": len(transformed_files),
        "output_dir": output_dir,
        "files": transformed_files,
    }


class ImageTransformerPlugin(QtPlugin):
    plugin_id = "img_trans"
    name = "Image Transformer"
    description = "Batch rotate, resize, and convert images with a cleaner desktop workflow and live preview."
    category = "Media Utilities"

    def create_widget(self, services) -> QWidget:
        return ImageTransformerPage(services, self.plugin_id)


class ImageTransformerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.files: list[str] = []
        self.current_preview_path: str | None = None
        self.current_aspect: float | None = None
        self._resizing_guard = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        title = QLabel("Image Transformer")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        outer.addWidget(title)

        description = QLabel(
            "Batch rotate, resize, and convert images with a more structured workflow and per-image preview."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        outer.addWidget(description)

        settings_card = QFrame()
        settings_card.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }"
        )
        settings_layout = QGridLayout(settings_card)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.setHorizontalSpacing(12)
        settings_layout.setVerticalSpacing(10)

        settings_layout.addWidget(QLabel("Rotate"), 0, 0)
        rotate_row = QHBoxLayout()
        self.rotate_enabled = QCheckBox("Enable")
        self.rotate_mode = QComboBox()
        self.rotate_mode.addItems(["90°", "180°", "270°"])
        self.rotate_mode.setEnabled(False)
        self.rotate_enabled.toggled.connect(self.rotate_mode.setEnabled)
        rotate_row.addWidget(self.rotate_enabled)
        rotate_row.addWidget(self.rotate_mode)
        rotate_row.addStretch(1)
        settings_layout.addLayout(rotate_row, 0, 1)

        settings_layout.addWidget(QLabel("Resize"), 1, 0)
        resize_row = QHBoxLayout()
        self.resize_enabled = QCheckBox("Enable")
        self.resize_mode = QComboBox()
        self.resize_mode.addItems(["pixels", "percent"])
        self.resize_mode.setEnabled(False)
        self.resize_width = QLineEdit()
        self.resize_width.setPlaceholderText("W")
        self.resize_width.setFixedWidth(70)
        self.resize_width.setEnabled(False)
        self.resize_height = QLineEdit()
        self.resize_height.setPlaceholderText("H")
        self.resize_height.setFixedWidth(70)
        self.resize_height.setEnabled(False)
        self.keep_aspect = QCheckBox("Keep aspect")
        self.keep_aspect.setChecked(True)
        self.keep_aspect.setEnabled(False)
        self.resize_enabled.toggled.connect(self._toggle_resize_controls)
        self.resize_width.textChanged.connect(self._sync_resize_from_width)
        self.resize_height.textChanged.connect(self._sync_resize_from_height)
        resize_row.addWidget(self.resize_enabled)
        resize_row.addWidget(self.resize_mode)
        resize_row.addWidget(self.resize_width)
        resize_row.addWidget(self.resize_height)
        resize_row.addWidget(self.keep_aspect)
        resize_row.addStretch(1)
        settings_layout.addLayout(resize_row, 1, 1)

        settings_layout.addWidget(QLabel("Format"), 2, 0)
        format_row = QHBoxLayout()
        self.format_enabled = QCheckBox("Enable")
        self.format_mode = QComboBox()
        self.format_mode.addItems(["PNG", "JPG", "WEBP"])
        self.format_mode.setEnabled(False)
        self.format_enabled.toggled.connect(self.format_mode.setEnabled)
        format_row.addWidget(self.format_enabled)
        format_row.addWidget(self.format_mode)
        format_row.addStretch(1)
        settings_layout.addLayout(format_row, 2, 1)

        actions_row = QHBoxLayout()
        add_button = QPushButton("Add Images")
        add_button.clicked.connect(self._add_files)
        clear_button = QPushButton("Clear All")
        clear_button.clicked.connect(self._clear_files)
        actions_row.addWidget(add_button)
        actions_row.addWidget(clear_button)
        actions_row.addStretch(1)
        settings_layout.addWidget(QLabel("Files"), 3, 0)
        settings_layout.addLayout(actions_row, 3, 1)

        outer.addWidget(settings_card)

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
        self.run_button = QPushButton("Run Transform")
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.progress, 1)
        outer.addLayout(controls)

        self.summary_output = QPlainTextEdit()
        self.summary_output.setReadOnly(True)
        self.summary_output.setPlaceholderText("Transform summary will appear here.")
        outer.addWidget(self.summary_output, 1)

    def _toggle_resize_controls(self, enabled: bool) -> None:
        self.resize_mode.setEnabled(enabled)
        self.resize_width.setEnabled(enabled)
        self.resize_height.setEnabled(enabled)
        self.keep_aspect.setEnabled(enabled)

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
        self.current_preview_path = None
        self.current_aspect = None
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
        self.current_preview_path = path
        try:
            image = Image.open(path)
            self.current_aspect = image.width / float(image.height) if image.height else None
            pixmap = pil_to_pixmap(image)
            self.preview_label.setPixmap(pixmap)
            self.preview_label.setText("")
            if self.keep_aspect.isChecked() and self.resize_enabled.isChecked() and self.resize_mode.currentText() == "pixels":
                if not self.resize_width.text() and not self.resize_height.text():
                    self._resizing_guard = True
                    self.resize_width.setText(str(image.width))
                    self.resize_height.setText(str(image.height))
                    self._resizing_guard = False
        except Exception as exc:
            self.preview_label.setPixmap(None)
            self.preview_label.setText(f"Preview error: {exc}")

    def _sync_resize_from_width(self, value: str) -> None:
        if self._resizing_guard or not self.keep_aspect.isChecked() or not self.current_aspect:
            return
        if not value.strip() or not value.replace(".", "", 1).isdigit():
            return
        self._resizing_guard = True
        if self.resize_mode.currentText() == "percent":
            self.resize_height.setText(value)
        else:
            self.resize_height.setText(str(int(float(value) / self.current_aspect)))
        self._resizing_guard = False

    def _sync_resize_from_height(self, value: str) -> None:
        if self._resizing_guard or not self.keep_aspect.isChecked() or not self.current_aspect:
            return
        if not value.strip() or not value.replace(".", "", 1).isdigit():
            return
        self._resizing_guard = True
        if self.resize_mode.currentText() == "percent":
            self.resize_width.setText(value)
        else:
            self.resize_width.setText(str(int(float(value) * self.current_aspect)))
        self._resizing_guard = False

    def _run(self) -> None:
        if not self.files:
            QMessageBox.warning(self, "Missing Input", "Add at least one image first.")
            return
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            str(self.services.default_output_path()),
        )
        if not output_dir:
            return

        options = {
            "rotate_value": self.rotate_mode.currentText() if self.rotate_enabled.isChecked() else None,
            "resize_enabled": self.resize_enabled.isChecked(),
            "resize_type": self.resize_mode.currentText(),
            "resize_width": self.resize_width.text().strip(),
            "resize_height": self.resize_height.text().strip(),
            "format_value": self.format_mode.currentText().lower() if self.format_enabled.isChecked() else None,
        }

        self.run_button.setEnabled(False)
        self.progress.setValue(0)
        self.summary_output.clear()
        self.services.run_task(
            lambda context: run_image_transform_task(context, list(self.files), output_dir, options),
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
            f"Batch transform complete.\nFiles written: {result['count']}\nOutput folder: {result['output_dir']}"
        )
        self.services.record_run(self.plugin_id, "SUCCESS", f"Transformed {result['count']} images")

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown image transformer error") if isinstance(payload, dict) else str(payload)
        self.summary_output.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Image transformer failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
