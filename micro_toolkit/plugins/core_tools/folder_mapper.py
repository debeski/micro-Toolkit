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
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.app_utils import generate_output_filename
from micro_toolkit.core.plugin_api import QtPlugin
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
    category = "Validation & Analysis"

    def create_widget(self, services) -> QWidget:
        return FolderMapperPage(services, self.plugin_id)


class FolderMapperPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._latest_output_path = None
        self._table_model = None
        self._build_ui()

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel(self._pt("title", "Folder Mapper"))
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            self._pt("description", "Map file metadata for an entire folder tree into Excel, with a preview of the first rows inside the app.")
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText(self._pt("folder.placeholder", "Select a folder to export..."))
        folder_row.addWidget(self.folder_input, 1)
        browse_button = QPushButton(self._pt("button.browse", "Browse"))
        browse_button.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_button)
        layout.addLayout(folder_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton(self._pt("button.run", "Map Folder"))
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_output_button = QPushButton(self._pt("button.open", "Open Workbook"))
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self._open_output)
        controls.addWidget(self.open_output_button, 0, Qt.AlignmentFlag.AlignLeft)

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
        self.summary_label = QLabel(self._pt("summary.empty", "Choose a folder to export."))
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.table = QTableView()
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self._pt("dialog.browse.title", "Select Folder To Export"),
            str(self.services.default_output_path()),
        )
        if folder:
            self.folder_input.setText(folder)

    def _run(self) -> None:
        folder_path = self.folder_input.text().strip()
        if not folder_path:
            QMessageBox.warning(self, self._pt("dialog.error.title", "Missing Input"), self._pt("dialog.error.missing_folder", "Choose a folder to export."))
            return

        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)
        self.progress.setValue(0)
        self.summary_label.setText(self._pt("summary.running", "Exporting folder contents..."))
        self.table.setModel(None)
        self._table_model = None

        output_dir = str(self.services.default_output_path())
        self.services.run_task(
            lambda context: map_folder_contents_task(context, folder_path, output_dir),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            on_progress=self._handle_progress,
        )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_output_path = result["output_path"]
        self._table_model = DataFrameTableModel(result["dataframe"])
        self.table.setModel(self._table_model)
        self.summary_label.setText(
            self._pt(
                "summary.success",
                "Exported {row_count} rows for {folder_name}. Previewing the first {preview_count} rows.",
                row_count=result['row_count'],
                folder_name=result['folder_name'],
                preview_count=len(result['dataframe'])
            )
        )
        self.open_output_button.setEnabled(True)
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            self._pt("log.task.success", "Exported folder metadata for {folder_name}", folder_name=result['folder_name']),
        )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self._pt("error.unknown", "Unknown folder mapper error")) if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self._pt("log.error", "Folder Mapper failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_output(self) -> None:
        if self._latest_output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_output_path))
