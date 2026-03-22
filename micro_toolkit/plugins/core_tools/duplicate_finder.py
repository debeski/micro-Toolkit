from __future__ import annotations

import hashlib
import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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


def get_file_hash(filepath: str, chunk_size: int = 8192):
    hasher = hashlib.md5()
    try:
        with open(filepath, "rb") as handle:
            while chunk := handle.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


def find_duplicates_in_excel_task(context, xlsx_path: str, column_name: str, output_dir: str):
    import pandas as pd

    context.log(f"Reading Excel: {xlsx_path}")
    dataframe = pd.read_excel(xlsx_path)
    if column_name not in dataframe.columns:
        raise ValueError(f"Column '{column_name}' was not found in the workbook.")

    duplicates = dataframe[dataframe.duplicated(subset=[column_name], keep=False)]
    if duplicates.empty:
        raise ValueError("No duplicates were found in the selected column.")

    duplicates = duplicates.sort_values(by=[column_name]).reset_index(drop=True)
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(xlsx_path))[0]
    output_name = generate_output_filename("DuplicateRows", base_name, ".xlsx")
    output_path = os.path.join(output_dir, output_name)
    duplicates.to_excel(output_path, index=False)
    context.progress(1.0)
    context.log(f"Saved duplicate report to {output_path}")
    return {
        "dataframe": duplicates.head(300).copy(),
        "output_path": output_path,
        "row_count": len(duplicates),
        "mode": "excel",
    }


def find_duplicates_in_folders_task(context, folder_path: str, criteria: list[str], output_dir: str):
    import pandas as pd

    file_rows = []
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            path = os.path.join(root, file_name)
            try:
                stat = os.stat(path)
                file_rows.append(
                    {
                        "Name": file_name,
                        "Path": path,
                        "Size": stat.st_size,
                        "Folder": folder_path,
                    }
                )
            except Exception:
                continue

    dataframe = pd.DataFrame(file_rows)
    if dataframe.empty:
        raise ValueError("No files were found in the selected folder.")

    subset = []
    if "Name" in criteria:
        subset.append("Name")
    if "Size" in criteria:
        subset.append("Size")
    if not subset and "Hash" not in criteria:
        raise ValueError("Choose at least one duplicate matching criterion.")

    if subset:
        dataframe = dataframe[dataframe.duplicated(subset=subset, keep=False)]
    if dataframe.empty:
        raise ValueError("No duplicates were found after the initial duplicate pass.")

    if "Hash" in criteria:
        context.log("Calculating hashes for potential duplicate files...")
        hashes = []
        total = len(dataframe)
        for index, row in enumerate(dataframe.itertuples(), start=1):
            context.progress(index / float(total))
            hashes.append(get_file_hash(row.Path))
        dataframe["Hash"] = hashes
        subset = subset + ["Hash"]
        dataframe = dataframe[dataframe.duplicated(subset=subset, keep=False)]
        if dataframe.empty:
            raise ValueError("No duplicates remained after hash comparison.")

    dataframe = dataframe.sort_values(by=subset).reset_index(drop=True)
    os.makedirs(output_dir, exist_ok=True)
    output_name = generate_output_filename("DuplicateFiles", "Folders", ".xlsx")
    output_path = os.path.join(output_dir, output_name)
    dataframe.to_excel(output_path, index=False)
    context.progress(1.0)
    context.log(f"Saved duplicate report to {output_path}")
    return {
        "dataframe": dataframe.head(300).copy(),
        "output_path": output_path,
        "row_count": len(dataframe),
        "mode": "folder",
    }


class DuplicateFinderPlugin(QtPlugin):
    plugin_id = "dups"
    name = "Duplicate Finder"
    description = "Find duplicate files in a folder or duplicate values in an Excel column and export the results."
    category = "Validation & Analysis"

    def create_widget(self, services) -> QWidget:
        return DuplicateFinderPage(services, self.plugin_id)


class DuplicateFinderPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._latest_output_path = None
        self._table_model = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Duplicate Finder")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            "Switch between folder mode and Excel mode to locate duplicate files or duplicate column values."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_label = QLabel("Mode")
        mode_label.setFixedWidth(90)
        mode_row.addWidget(mode_label)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Folder", "folder")
        self.mode_combo.addItem("Excel", "excel")
        self.mode_combo.currentIndexChanged.connect(self._update_mode_ui)
        mode_row.addWidget(self.mode_combo, 1)
        layout.addLayout(mode_row)

        source_row = QHBoxLayout()
        source_row.setSpacing(10)
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Select a folder...")
        source_row.addWidget(self.source_input, 1)
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self._browse)
        source_row.addWidget(self.browse_button)
        layout.addLayout(source_row)

        self.folder_criteria_card = QFrame()
        self.folder_criteria_card.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }"
        )
        folder_criteria_layout = QVBoxLayout(self.folder_criteria_card)
        folder_criteria_layout.setContentsMargins(16, 14, 16, 14)
        folder_criteria_layout.setSpacing(8)
        folder_criteria_title = QLabel("Folder Matching Criteria")
        folder_criteria_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #10232c;")
        folder_criteria_layout.addWidget(folder_criteria_title)
        self.hash_checkbox = QCheckBox("Hash")
        self.hash_checkbox.setChecked(True)
        self.size_checkbox = QCheckBox("Size")
        self.size_checkbox.setChecked(True)
        self.name_checkbox = QCheckBox("Name")
        folder_criteria_layout.addWidget(self.hash_checkbox)
        folder_criteria_layout.addWidget(self.size_checkbox)
        folder_criteria_layout.addWidget(self.name_checkbox)
        layout.addWidget(self.folder_criteria_card)

        column_row = QHBoxLayout()
        column_row.setSpacing(10)
        self.column_label = QLabel("Column")
        self.column_label.setFixedWidth(90)
        column_row.addWidget(self.column_label)
        self.column_input = QLineEdit()
        self.column_input.setPlaceholderText("Column name")
        column_row.addWidget(self.column_input, 1)
        layout.addLayout(column_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Find Duplicates")
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_output_button = QPushButton("Open Workbook")
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
        self.summary_label = QLabel("Choose a source path and mode.")
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

        self._update_mode_ui()

    def _current_mode(self) -> str:
        return self.mode_combo.currentData()

    def _update_mode_ui(self) -> None:
        is_excel = self._current_mode() == "excel"
        self.folder_criteria_card.setVisible(not is_excel)
        self.column_label.setVisible(is_excel)
        self.column_input.setVisible(is_excel)
        self.source_input.setPlaceholderText("Select an Excel workbook..." if is_excel else "Select a folder...")

    def _browse(self) -> None:
        if self._current_mode() == "excel":
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Workbook",
                str(self.services.default_output_path()),
                "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)",
            )
            if file_path:
                self.source_input.setText(file_path)
        else:
            folder = QFileDialog.getExistingDirectory(
                self,
                "Select Folder",
                str(self.services.default_output_path()),
            )
            if folder:
                self.source_input.setText(folder)

    def _run(self) -> None:
        mode = self._current_mode()
        source = self.source_input.text().strip()
        column_name = self.column_input.text().strip()
        if not source:
            QMessageBox.warning(self, "Missing Input", "Choose a folder or workbook.")
            return
        if mode == "excel" and not column_name:
            QMessageBox.warning(self, "Missing Input", "Enter the Excel column name to inspect.")
            return

        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)
        self.progress.setValue(0)
        self.table.setModel(None)
        self._table_model = None
        self.summary_label.setText("Searching for duplicates...")

        if mode == "excel":
            task = lambda context: find_duplicates_in_excel_task(
                context,
                source,
                column_name,
                str(self.services.default_output_path()),
            )
        else:
            criteria = []
            if self.hash_checkbox.isChecked():
                criteria.append("Hash")
            if self.size_checkbox.isChecked():
                criteria.append("Size")
            if self.name_checkbox.isChecked():
                criteria.append("Name")
            task = lambda context: find_duplicates_in_folders_task(
                context,
                source,
                criteria,
                str(self.services.default_output_path()),
            )

        self.services.run_task(
            task,
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
            f"Found {result['row_count']} duplicate result rows in {result['mode']} mode. Previewing the first {len(result['dataframe'])} rows."
        )
        self.open_output_button.setEnabled(True)
        self.services.record_run(self.plugin_id, "SUCCESS", f"Generated duplicate report in {result['mode']} mode")

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown duplicate finder error") if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Duplicate finder failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_output(self) -> None:
        if self._latest_output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_output_path))
