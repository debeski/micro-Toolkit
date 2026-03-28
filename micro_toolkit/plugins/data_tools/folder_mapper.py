from __future__ import annotations

import datetime
import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.app_utils import generate_output_filename
from micro_toolkit.core.page_style import apply_page_chrome
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr
from micro_toolkit.core.table_model import DataFrameTableModel


try:
    from PIL import Image
    from PIL.ExifTags import TAGS

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def get_date_taken(path: str):
    if not HAS_PIL:
        return None
    try:
        if path.lower().endswith((".jpg", ".jpeg", ".tiff", ".png")):
            with Image.open(path) as image:
                exif_data = image._getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag == "DateTimeOriginal":
                            return value
    except Exception:
        return None
    return None


def map_folder_contents_task(context, folder_path: str, output_dir: str):
    import pandas as pd

    if not os.path.isdir(folder_path):
        raise ValueError(f"{folder_path} is not a valid directory.")

    try:
        total_files = sum(len(files) for _, _, files in os.walk(folder_path))
    except Exception:
        total_files = 0

    if total_files == 0:
        raise ValueError("No files were found to export.")

    context.log(f"Scanning folder: {folder_path}")
    processed = 0
    data: list[dict[str, object]] = []

    for root, _, files in os.walk(folder_path):
        for file_name in files:
            path = os.path.join(root, file_name)
            try:
                stat = os.stat(path)
                data.append(
                    {
                        "Name": file_name,
                        "Size (Bytes)": stat.st_size,
                        "Type": os.path.splitext(file_name)[1].lower() or "File",
                        "Date Modified": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "Date Created": datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                        "Date Taken": get_date_taken(path) or "",
                        "Path": path,
                        "Permissions": oct(stat.st_mode)[-3:],
                    }
                )
            except Exception as exc:
                context.log(f"Error reading {path}: {exc}", "WARNING")

            processed += 1
            context.progress(processed / float(total_files))

    dataframe = pd.DataFrame(data)
    folder_name = os.path.basename(os.path.normpath(folder_path)) or "Root"
    os.makedirs(output_dir, exist_ok=True)
    output_name = generate_output_filename("FolderMap", folder_name, ".xlsx")
    output_path = os.path.join(output_dir, output_name)
    dataframe.to_excel(output_path, index=False)
    context.log(f"Exported folder contents to {output_path}")

    preview = dataframe.head(300).copy()
    return {
        "dataframe": preview,
        "output_path": output_path,
        "row_count": len(dataframe),
        "folder_name": folder_name,
    }


class FolderMapperPlugin(QtPlugin):
    plugin_id = "folder_mapper"
    name = "Folder Mapper"
    description = "Scan a folder tree and map file metadata, paths, permissions, and dates into an Excel workbook."
    category = "Data Utilities"

    def create_widget(self, services) -> QWidget:
        return FolderMapperPage(services, self.plugin_id)


class FolderMapperPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self._latest_output_path = None
        self._latest_result = None
        self._has_run = False
        self._table_model = None
        self._build_ui()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self._apply_texts()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        self.title_label = QLabel(self.tr("title", "Folder Mapper"))
        layout.addWidget(self.title_label)

        self.description_label = QLabel(
            self.tr("description", "Map file metadata for an entire folder tree into Excel, with a preview of the first rows inside the app.")
        )
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText(self.tr("folder.placeholder", "Select a folder to export..."))
        folder_row.addWidget(self.folder_input, 1)
        self.browse_button = QPushButton(self.tr("button.browse", "Browse"))
        self.browse_button.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.browse_button)
        layout.addLayout(folder_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton(self.tr("button.run", "Map Folder"))
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_output_button = QPushButton(self.tr("button.open", "Open Workbook"))
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self._open_output)
        controls.addWidget(self.open_output_button, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addLayout(controls)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel(self.tr("summary.empty", "Choose a folder to export."))
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(self.summary_card)

        self.table = QTableView()
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)
        self._apply_theme_styles()

    def _apply_texts(self) -> None:
        self.title_label.setText(self.tr("title", "Folder Mapper"))
        self.description_label.setText(
            self.tr("description", "Map file metadata for an entire folder tree into Excel, with a preview of the first rows inside the app.")
        )
        self.folder_input.setPlaceholderText(self.tr("folder.placeholder", "Select a folder to export..."))
        self.browse_button.setText(self.tr("button.browse", "Browse"))
        self.run_button.setText(self.tr("button.run", "Map Folder"))
        self.open_output_button.setText(self.tr("button.open", "Open Workbook"))
        if self._latest_result is not None:
            self._render_result_payload(self._latest_result)
        elif not self._has_run:
            self.summary_label.setText(self.tr("summary.empty", "Choose a folder to export."))
        self._apply_theme_styles()

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("dialog.browse.title", "Select Folder To Export"),
            str(self.services.default_output_path()),
        )
        if folder:
            self.folder_input.setText(folder)

    def _run(self) -> None:
        folder_path = self.folder_input.text().strip()
        if not folder_path:
            QMessageBox.warning(self, self.tr("dialog.error.title", "Missing Input"), self.tr("dialog.error.missing_folder", "Choose a folder to export."))
            return

        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)
        self.summary_label.setText(self.tr("summary.running", "Exporting folder contents..."))
        self.table.setModel(None)
        self._table_model = None

        output_dir = str(self.services.default_output_path())
        self.services.run_task(
            lambda context: map_folder_contents_task(context, folder_path, output_dir),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._has_run = True
        self._latest_result = result
        self._render_result_payload(result)
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            self.tr("log.task.success", "Exported folder metadata for {folder_name}", folder_name=result['folder_name']),
        )

    def _handle_error(self, payload: object) -> None:
        self._has_run = True
        self._latest_result = None
        message = payload.get("message", self.tr("error.unknown", "Unknown folder mapper error")) if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.error", "Folder Mapper failed."), "ERROR")

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.summary_card,),
            summary_label=self.summary_label,
        )

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _render_result_payload(self, result: dict[str, object]) -> None:
        self._latest_output_path = str(result["output_path"])
        self._table_model = DataFrameTableModel(result["dataframe"])
        self.table.setModel(self._table_model)
        self.summary_label.setText(
            self.tr(
                "summary.success",
                "Exported {row_count} rows for {folder_name}. Previewing the first {preview_count} rows.",
                row_count=result["row_count"],
                folder_name=result["folder_name"],
                preview_count=len(result["dataframe"]),
            )
        )
        self.open_output_button.setEnabled(True)

    def _open_output(self) -> None:
        if self._latest_output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_output_path))
