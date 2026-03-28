from __future__ import annotations

import datetime
import os
import re

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
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
from micro_toolkit.core.widgets import ScrollSafeComboBox


QComboBox = ScrollSafeComboBox


def get_date_taken(path: str) -> str:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
    except ImportError:
        return ""

    try:
        if path.lower().endswith((".jpg", ".jpeg", ".tiff", ".png")):
            with Image.open(path) as image:
                exif_data = image._getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        if TAGS.get(tag_id, tag_id) == "DateTimeOriginal":
                            return str(value)
    except Exception:
        return ""
    return ""


def extract_sequence_number(text):
    matches = re.findall(r"\d+", str(text))
    if matches:
        return int(matches[-1]), matches[-1]
    return None, None


def find_missing_sequence(dataframe, name_column: str):
    extracted = []
    for _, row in dataframe.iterrows():
        value = row[name_column]
        number, original = extract_sequence_number(value)
        if number is not None:
            extracted.append((number, original, row))

    if not extracted:
        raise ValueError("No sequential numbers were found in the selected data.")

    extracted.sort(key=lambda item: item[0])
    missing_rows = []
    for index in range(len(extracted) - 1):
        current_num, current_str, current_row = extracted[index]
        next_num, _, next_row = extracted[index + 1]
        if next_num <= current_num + 1:
            continue

        context_before = current_row.to_dict()
        context_before["_type"] = "context_before"
        missing_rows.append(context_before)

        padding = len(current_str)
        for missing_num in range(current_num + 1, next_num):
            formatted = str(missing_num).zfill(padding)
            missing_name = re.sub(r"\d+(?!.*\d)", formatted, str(current_row[name_column]))
            blank_row = {column: "" for column in current_row.keys()}
            blank_row[name_column] = f"[MISSING] {missing_name}"
            blank_row["_type"] = "missing"
            missing_rows.append(blank_row)

        context_after = next_row.to_dict()
        context_after["_type"] = "context_after"
        missing_rows.append(context_after)

    if not missing_rows:
        raise ValueError("No missing sequence entries were found.")

    result = dataframe.__class__(missing_rows)
    result.insert(
        0,
        "Status",
        result["_type"].apply(lambda value: "Missing" if value == "missing" else "Found (Context)"),
    )
    return result.drop(columns=["_type"])


def build_folder_dataframe(folder_path: str, context):
    import pandas as pd

    rows = []
    files_list = []
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            files_list.append((root, file_name))

    if not files_list:
        raise ValueError("No files were found in the selected folder.")

    for index, (root, file_name) in enumerate(files_list, start=1):
        path = os.path.join(root, file_name)
        try:
            stat = os.stat(path)
            rows.append(
                {
                    "Name": file_name,
                    "Size (Bytes)": stat.st_size,
                    "Type": os.path.splitext(file_name)[1].lower() or "File",
                    "Date Modified": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "Date Created": datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                    "Date Taken": get_date_taken(path),
                    "Path": path,
                    "Permissions": oct(stat.st_mode)[-3:],
                }
            )
        except Exception:
            continue
        context.progress(index / float(len(files_list)))

    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        raise ValueError("No readable files were found in the selected folder.")
    return dataframe


def sequence_auditor_task(context, mode: str, path_value: str, column_name: str, output_dir: str):
    import pandas as pd

    if mode == "folder":
        context.log(f"Scanning folder '{path_value}' for sequence gaps...")
        source_df = build_folder_dataframe(path_value, context)
        result_df = find_missing_sequence(source_df, "Name")
        base_name = os.path.basename(os.path.normpath(path_value)) or "Root"
    else:
        context.log(f"Reading Excel file '{path_value}'...")
        source_df = pd.read_excel(path_value)
        context.progress(0.3)
        if column_name not in source_df.columns:
            raise ValueError(f"Column '{column_name}' was not found in the workbook.")
        result_df = find_missing_sequence(source_df, column_name)
        base_name = os.path.splitext(os.path.basename(path_value))[0]

    os.makedirs(output_dir, exist_ok=True)
    output_name = generate_output_filename("SequenceAudit", base_name, ".xlsx")
    output_path = os.path.join(output_dir, output_name)
    result_df.to_excel(output_path, index=False)
    context.progress(1.0)
    context.log(f"Saved sequence report to {output_path}")

    return {
        "dataframe": result_df.head(300).copy(),
        "output_path": output_path,
        "row_count": len(result_df),
        "mode": mode,
    }


class SequenceAuditorPlugin(QtPlugin):
    plugin_id = "sequence_auditor"
    name = "Sequence Auditor"
    description = "Audit a folder listing or an Excel column for missing numbered items and export the result."
    category = "Data Utilities"

    def create_widget(self, services) -> QWidget:
        return SequenceAuditorPage(services, self.plugin_id)


class SequenceAuditorPage(QWidget):
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

        self.title_label = QLabel(self.tr("title", "Sequence Auditor"))
        layout.addWidget(self.title_label)

        self.description_label = QLabel(
            self.tr("description", "Switch between folder mode and Excel mode to audit missing numbered entries and export a workbook with context rows.")
        )
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        self.mode_label_widget = QLabel(self.tr("label.mode", "Mode"))
        self.mode_label_widget.setFixedWidth(90)
        mode_row.addWidget(self.mode_label_widget)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(self.tr("mode.folder", "Folder"), "folder")
        self.mode_combo.addItem(self.tr("mode.excel", "Excel"), "excel")
        self.mode_combo.currentIndexChanged.connect(self._update_mode_ui)
        mode_row.addWidget(self.mode_combo, 1)
        layout.addLayout(mode_row)

        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(self.tr("path.placeholder.folder", "Select a folder..."))
        path_row.addWidget(self.path_input, 1)
        self.browse_button = QPushButton(self.tr("button.browse", "Browse"))
        self.browse_button.clicked.connect(self._browse)
        path_row.addWidget(self.browse_button)
        layout.addLayout(path_row)

        column_row = QHBoxLayout()
        column_row.setSpacing(10)
        self.column_label = QLabel(self.tr("label.column", "Column"))
        self.column_label.setFixedWidth(90)
        column_row.addWidget(self.column_label)
        self.column_input = QLineEdit()
        self.column_input.setPlaceholderText(self.tr("column.placeholder", "Column name"))
        column_row.addWidget(self.column_input, 1)
        layout.addLayout(column_row)
        self.column_row_layout = column_row

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton(self.tr("button.run", "Find Missing Sequence"))
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
        self.summary_label = QLabel(self.tr("summary.empty", "Choose a mode and source path."))
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(self.summary_card)

        self.table = QTableView()
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        self._update_mode_ui()
        self._apply_theme_styles()

    def _set_combo_items(self, combo: QComboBox, items: list[tuple[str, str]]) -> None:
        current_value = str(combo.currentData() or combo.currentText() or "")
        combo.blockSignals(True)
        combo.clear()
        for label, value in items:
            combo.addItem(label, value)
        index = combo.findData(current_value)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _apply_texts(self) -> None:
        self.title_label.setText(self.tr("title", "Sequence Auditor"))
        self.description_label.setText(
            self.tr("description", "Switch between folder mode and Excel mode to audit missing numbered entries and export a workbook with context rows.")
        )
        self.mode_label_widget.setText(self.tr("label.mode", "Mode"))
        self._set_combo_items(
            self.mode_combo,
            [
                (self.tr("mode.folder", "Folder"), "folder"),
                (self.tr("mode.excel", "Excel"), "excel"),
            ],
        )
        self.column_label.setText(self.tr("label.column", "Column"))
        self.column_input.setPlaceholderText(self.tr("column.placeholder", "Column name"))
        self.browse_button.setText(self.tr("button.browse", "Browse"))
        self.run_button.setText(self.tr("button.run", "Find Missing Sequence"))
        self.open_output_button.setText(self.tr("button.open", "Open Workbook"))
        self._update_mode_ui()
        if self._latest_result is not None:
            self._render_result_payload(self._latest_result)
        elif not self._has_run:
            self.summary_label.setText(self.tr("summary.empty", "Choose a mode and source path."))
        self._apply_theme_styles()

    def _current_mode(self) -> str:
        return self.mode_combo.currentData()

    def _update_mode_ui(self) -> None:
        is_excel = self._current_mode() == "excel"
        self.path_input.setPlaceholderText(self.tr("path.placeholder.excel", "Select an Excel workbook...") if is_excel else self.tr("path.placeholder.folder", "Select a folder..."))
        self.column_label.setVisible(is_excel)
        self.column_input.setVisible(is_excel)

    def _browse(self) -> None:
        if self._current_mode() == "excel":
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                self.tr("dialog.browse.excel", "Select Workbook"),
                str(self.services.default_output_path()),
                self.tr("dialog.browse.excel.filter", "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)"),
            )
            if file_path:
                self.path_input.setText(file_path)
        else:
            folder = QFileDialog.getExistingDirectory(
                self,
                self.tr("dialog.browse.folder", "Select Folder"),
                str(self.services.default_output_path()),
            )
            if folder:
                self.path_input.setText(folder)

    def _run(self) -> None:
        mode = self._current_mode()
        path_value = self.path_input.text().strip()
        column_name = self.column_input.text().strip()
        if not path_value:
            QMessageBox.warning(self, self.tr("dialog.error.title", "Missing Input"), self.tr("dialog.error.missing_path", "Choose a source folder or workbook."))
            return
        if mode == "excel" and not column_name:
            QMessageBox.warning(self, self.tr("dialog.error.title", "Missing Input"), self.tr("dialog.error.missing_column", "Enter the Excel column name to inspect."))
            return

        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)
        self.table.setModel(None)
        self._table_model = None
        self.summary_label.setText(self.tr("summary.running", "Auditing sequence gaps..."))

        self.services.run_task(
            lambda context: sequence_auditor_task(
                context,
                mode,
                path_value,
                column_name,
                str(self.services.default_output_path()),
            ),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._has_run = True
        self._latest_result = result
        self._render_result_payload(result)
        mode_text = self.tr(f"mode.{result['mode']}", result['mode'].title())
        self.services.record_run(self.plugin_id, "SUCCESS", self.tr("log.task.success", "Generated sequence audit report in {mode} mode", mode=mode_text))

    def _handle_error(self, payload: object) -> None:
        self._has_run = True
        self._latest_result = None
        message = payload.get("message", self.tr("error.unknown", "Unknown sequence auditor error")) if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.error", "Sequence Auditor failed."), "ERROR")

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
        mode_text = self.tr(f"mode.{result['mode']}", result["mode"].title())
        self.summary_label.setText(
            self.tr(
                "summary.success",
                "Found {row_count} result rows in {mode} mode. Previewing the first {preview_count} rows.",
                row_count=result["row_count"],
                mode=mode_text,
                preview_count=len(result["dataframe"]),
            )
        )
        self.open_output_button.setEnabled(True)

    def _open_output(self) -> None:
        if self._latest_output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_output_path))
