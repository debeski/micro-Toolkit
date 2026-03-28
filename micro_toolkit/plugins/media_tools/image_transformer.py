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
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.media_utils import SUPPORTED_IMAGE_FILTER, pil_to_pixmap, safe_output_extension, transform_image
from micro_toolkit.core.page_style import apply_page_chrome, label_surface_style, muted_text_style
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr, safe_tr
from micro_toolkit.core.widgets import ScrollSafeComboBox


QComboBox = ScrollSafeComboBox

def run_image_transform_task(context, files: list[str], output_dir: str, options: dict, *, translate=None):
    os.makedirs(output_dir, exist_ok=True)
    transformed_files = []
    for index, file_path in enumerate(files, start=1):
        context.progress(index / float(len(files)))
        context.log(safe_tr(translate, "log.transforming", "Transforming {file}...", file=os.path.basename(file_path)))
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

    context.log(safe_tr(translate, "log.done", "Batch transform complete. Wrote {count} files.", count=len(transformed_files)))
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
        self.tr = bind_tr(services, plugin_id)
        self.files: list[str] = []
        self.current_preview_path: str | None = None
        self.current_aspect: float | None = None
        self._resizing_guard = False
        self._build_ui()
        self._apply_texts()
        self.services.i18n.language_changed.connect(self._handle_language_change)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        outer.addWidget(self.description_label)

        self.settings_card = QFrame()
        settings_layout = QGridLayout(self.settings_card)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.setHorizontalSpacing(12)
        settings_layout.setVerticalSpacing(10)

        self.rotate_label = QLabel()
        settings_layout.addWidget(self.rotate_label, 0, 0)
        rotate_row = QHBoxLayout()
        self.rotate_enabled = QCheckBox()
        self.rotate_mode = QComboBox()
        self.rotate_mode.addItems(["90°", "180°", "270°"])
        self.rotate_mode.setEnabled(False)
        self.rotate_enabled.toggled.connect(self.rotate_mode.setEnabled)
        rotate_row.addWidget(self.rotate_enabled)
        rotate_row.addWidget(self.rotate_mode)
        rotate_row.addStretch(1)
        settings_layout.addLayout(rotate_row, 0, 1)

        self.resize_label = QLabel()
        settings_layout.addWidget(self.resize_label, 1, 0)
        resize_row = QHBoxLayout()
        self.resize_enabled = QCheckBox()
        self.resize_mode = QComboBox()
        self.resize_mode.setEnabled(False)
        self.resize_width = QLineEdit()
        self.resize_width.setFixedWidth(70)
        self.resize_width.setEnabled(False)
        self.resize_height = QLineEdit()
        self.resize_height.setFixedWidth(70)
        self.resize_height.setEnabled(False)
        self.keep_aspect = QCheckBox()
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

        self.format_label = QLabel()
        settings_layout.addWidget(self.format_label, 2, 0)
        format_row = QHBoxLayout()
        self.format_enabled = QCheckBox()
        self.format_mode = QComboBox()
        self.format_mode.setEnabled(False)
        self.format_enabled.toggled.connect(self.format_mode.setEnabled)
        format_row.addWidget(self.format_enabled)
        format_row.addWidget(self.format_mode)
        format_row.addStretch(1)
        settings_layout.addLayout(format_row, 2, 1)

        actions_row = QHBoxLayout()
        self.add_button = QPushButton()
        self.add_button.clicked.connect(self._add_files)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self._clear_files)
        actions_row.addWidget(self.add_button)
        actions_row.addWidget(self.clear_button)
        actions_row.addStretch(1)
        self.files_label = QLabel()
        settings_layout.addWidget(self.files_label, 3, 0)
        settings_layout.addLayout(actions_row, 3, 1)

        outer.addWidget(self.settings_card)

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
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(320)
        right_layout.addWidget(self.preview_label, 1)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        controls = QHBoxLayout()
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)
        outer.addLayout(controls)

        self.summary_output = QPlainTextEdit()
        self.summary_output.setReadOnly(True)
        outer.addWidget(self.summary_output, 1)
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.settings_card,),
            title_size=26,
            title_weight=700,
            card_radius=14,
        )
        self.preview_label.setStyleSheet(label_surface_style(palette, radius=14) + muted_text_style(palette))

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _set_combo_items(self, combo: QComboBox, items: list[tuple[str, str]]) -> None:
        current_value = str(combo.currentData() or combo.currentText() or "")
        combo.blockSignals(True)
        combo.clear()
        for value, label in items:
            combo.addItem(label, value)
        index = combo.findData(current_value)
        if index < 0:
            index = 0
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _resize_mode_value(self) -> str:
        return str(self.resize_mode.currentData() or self.resize_mode.currentText() or "pixels")

    def _format_mode_value(self) -> str:
        return str(self.format_mode.currentData() or self.format_mode.currentText() or "png")

    def _handle_language_change(self) -> None:
        self._apply_texts()
        self._refresh_file_list()
        if self.file_list.currentRow() >= 0:
            self._show_preview_for_row(self.file_list.currentRow())

    def _apply_texts(self) -> None:
        self.title_label.setText(self.tr("title", "Image Transformer"))
        self.description_label.setText(
            self.tr(
                "description",
                "Batch rotate, resize, and convert images with a more structured workflow and per-image preview.",
            )
        )
        self.rotate_label.setText(self.tr("label.rotate", "Rotate"))
        self.resize_label.setText(self.tr("label.resize", "Resize"))
        self.format_label.setText(self.tr("label.format", "Format"))
        self.files_label.setText(self.tr("label.files", "Files"))
        self.rotate_enabled.setText(self.tr("toggle.enable", "Enable"))
        self.resize_enabled.setText(self.tr("toggle.enable", "Enable"))
        self.format_enabled.setText(self.tr("toggle.enable", "Enable"))
        self.keep_aspect.setText(self.tr("toggle.keep_aspect", "Keep aspect"))
        self.resize_width.setPlaceholderText(self.tr("placeholder.width", "W"))
        self.resize_height.setPlaceholderText(self.tr("placeholder.height", "H"))
        self._set_combo_items(
            self.resize_mode,
            [
                ("pixels", self.tr("resize_mode.pixels", "Pixels")),
                ("percent", self.tr("resize_mode.percent", "Percent")),
            ],
        )
        self._set_combo_items(
            self.format_mode,
            [
                ("png", "PNG"),
                ("jpg", "JPG"),
                ("webp", "WEBP"),
            ],
        )
        self.add_button.setText(self.tr("add", "Add Images"))
        self.clear_button.setText(self.tr("clear", "Clear All"))
        self.run_button.setText(self.tr("run", "Run Transform"))
        if not self.preview_label.pixmap():
            self.preview_label.setText(self.tr("preview.empty", "Select an image to preview."))
        self.summary_output.setPlaceholderText(self.tr("summary.placeholder", "Transform summary will appear here."))

    def _toggle_resize_controls(self, enabled: bool) -> None:
        self.resize_mode.setEnabled(enabled)
        self.resize_width.setEnabled(enabled)
        self.resize_height.setEnabled(enabled)
        self.keep_aspect.setEnabled(enabled)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self.tr("dialog.select_images", "Select Images"),
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
        self.preview_label.setText(self.tr("preview.empty", "Select an image to preview."))

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
            if self.keep_aspect.isChecked() and self.resize_enabled.isChecked() and self._resize_mode_value() == "pixels":
                if not self.resize_width.text() and not self.resize_height.text():
                    self._resizing_guard = True
                    self.resize_width.setText(str(image.width))
                    self.resize_height.setText(str(image.height))
                    self._resizing_guard = False
        except Exception as exc:
            self.preview_label.setPixmap(None)
            self.preview_label.setText(self.tr("preview.error", "Preview error: {message}", message=exc))

    def _sync_resize_from_width(self, value: str) -> None:
        if self._resizing_guard or not self.keep_aspect.isChecked() or not self.current_aspect:
            return
        if not value.strip() or not value.replace(".", "", 1).isdigit():
            return
        self._resizing_guard = True
        if self._resize_mode_value() == "percent":
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
        if self._resize_mode_value() == "percent":
            self.resize_width.setText(value)
        else:
            self.resize_width.setText(str(int(float(value) * self.current_aspect)))
        self._resizing_guard = False

    def _run(self) -> None:
        if not self.files:
            QMessageBox.warning(
                self,
                self.tr("error.missing_input.title", "Missing Input"),
                self.tr("error.missing_files", "Add at least one image first."),
            )
            return
        output_dir = QFileDialog.getExistingDirectory(
            self,
            self.tr("dialog.select_output", "Select Output Folder"),
            str(self.services.default_output_path()),
        )
        if not output_dir:
            return

        options = {
            "rotate_value": self.rotate_mode.currentText() if self.rotate_enabled.isChecked() else None,
            "resize_enabled": self.resize_enabled.isChecked(),
            "resize_type": self._resize_mode_value(),
            "resize_width": self.resize_width.text().strip(),
            "resize_height": self.resize_height.text().strip(),
            "format_value": self._format_mode_value() if self.format_enabled.isChecked() else None,
        }

        self.run_button.setEnabled(False)
        self.summary_output.clear()
        self.services.run_task(
            lambda context: run_image_transform_task(context, list(self.files), output_dir, options, translate=self.tr),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self.summary_output.setPlainText(
            self.tr(
                "summary.done",
                "Batch transform complete.\nFiles written: {count}\nOutput folder: {output_dir}",
                count=result["count"],
                output_dir=result["output_dir"],
            )
        )
        self.services.record_run(self.plugin_id, "SUCCESS", self.tr("run.success", "Transformed {count} images", count=result["count"]))

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self.tr("error.unknown", "Unknown image transformer error")) if isinstance(payload, dict) else str(payload)
        self.summary_output.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "Image transformer failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
