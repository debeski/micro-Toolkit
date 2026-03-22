from __future__ import annotations

import os
import shutil
import unicodedata

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.app_utils import generate_output_filename
from micro_toolkit.core.plugin_api import QtPlugin


def normalize_string(value):
    return unicodedata.normalize("NFKD", str(value)).strip() if value is not None else None


def validate_files_task(
    context,
    xlsx_path: str,
    source_folders: list[str],
    column_names: list[str],
    dest_folder: str | None,
    split_folders: bool,
    output_dir: str,
):
    import pandas as pd

    if dest_folder and not os.path.exists(dest_folder):
        os.makedirs(dest_folder, exist_ok=True)

    context.log(f"Reading Excel file: {xlsx_path}")
    dataframe = pd.read_excel(xlsx_path)
    valid_columns = [column for column in column_names if column in dataframe.columns]
    if not valid_columns:
        raise ValueError(f"None of the specified columns were found: {', '.join(column_names)}")

    missing_values = []
    missing_files = []
    found_files = 0
    total_rows = len(dataframe)

    for index, row in dataframe.iterrows():
        context.progress((index + 1) / float(max(1, total_rows)))
        row_num = index + 2
        for column in valid_columns:
            filename = normalize_string(row[column])
            if not filename:
                missing_values.append({"Row": row_num, "Column": column, "Issue": "Empty cell"})
                continue

            matched_folder = None
            for folder in source_folders:
                candidate_path = os.path.join(folder, filename)
                if os.path.exists(candidate_path):
                    matched_folder = folder
                    break

            if not matched_folder:
                missing_files.append(
                    {
                        "Row": row_num,
                        "Column": column,
                        "Filename": filename,
                        "Issue": "Not found in any source folder",
                    }
                )
                continue

            found_files += 1
            if dest_folder:
                if split_folders:
                    target_dir = os.path.join(dest_folder, os.path.basename(os.path.normpath(matched_folder)))
                else:
                    target_dir = dest_folder
                os.makedirs(target_dir, exist_ok=True)
                source_path = os.path.join(matched_folder, filename)
                target_path = os.path.join(target_dir, filename)
                try:
                    if os.path.exists(source_path):
                        shutil.move(source_path, target_path)
                except Exception as exc:
                    if not os.path.exists(target_path):
                        context.log(f"Could not move '{filename}' from '{matched_folder}': {exc}", "WARNING")

    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(xlsx_path))[0]
    created_reports = []

    missing_values_df = pd.DataFrame(missing_values)
    if not missing_values_df.empty:
        report_name = generate_output_filename("MissingValues", base_name, ".xlsx")
        report_path = os.path.join(output_dir, report_name)
        missing_values_df.to_excel(report_path, index=False)
        created_reports.append(("Missing Values", report_path, len(missing_values_df)))

    missing_files_df = pd.DataFrame(missing_files)
    if not missing_files_df.empty:
        report_name = generate_output_filename("MissingFiles", base_name, ".xlsx")
        report_path = os.path.join(output_dir, report_name)
        missing_files_df.to_excel(report_path, index=False)
        created_reports.append(("Missing Files", report_path, len(missing_files_df)))

    context.log(f"Validation complete. Found files handled: {found_files}")
    return {
        "reports": created_reports,
        "total_rows": total_rows,
        "found_files": found_files,
        "missing_values": len(missing_values),
        "missing_files": len(missing_files),
    }


class ValidatorPlugin(QtPlugin):
    plugin_id = "validator"
    name = "File Validator"
    description = "Check Excel rows against one or more source folders and export missing-value or missing-file reports."
    category = "Validation & Analysis"

    def create_widget(self, services) -> QWidget:
        return ValidatorPage(services, self.plugin_id)


class ValidatorPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.source_folders: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("File Validator")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            "Validate filenames referenced in an Excel workbook against multiple source folders, then optionally move found files into a destination structure."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        excel_row = QHBoxLayout()
        excel_row.setSpacing(10)
        self.excel_input = QLineEdit()
        self.excel_input.setPlaceholderText("Select an Excel workbook...")
        excel_row.addWidget(self.excel_input, 1)
        excel_browse = QPushButton("Browse")
        excel_browse.clicked.connect(self._browse_excel)
        excel_row.addWidget(excel_browse)
        layout.addLayout(excel_row)

        col_row = QHBoxLayout()
        col_row.setSpacing(10)
        col_label = QLabel("Columns")
        col_label.setFixedWidth(90)
        col_row.addWidget(col_label)
        self.columns_input = QLineEdit("pdf_file, attach")
        self.columns_input.setPlaceholderText("Comma-separated column names")
        col_row.addWidget(self.columns_input, 1)
        layout.addLayout(col_row)

        folders_card = QFrame()
        folders_card.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }"
        )
        folders_layout = QVBoxLayout(folders_card)
        folders_layout.setContentsMargins(16, 14, 16, 14)
        folders_layout.setSpacing(10)
        folders_title = QLabel("Source Folders")
        folders_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #10232c;")
        folders_layout.addWidget(folders_title)

        folder_buttons = QHBoxLayout()
        folder_buttons.setSpacing(10)
        add_folder_button = QPushButton("Add Folder")
        add_folder_button.clicked.connect(self._add_folder)
        folder_buttons.addWidget(add_folder_button, 0, Qt.AlignmentFlag.AlignLeft)
        clear_folder_button = QPushButton("Clear Folders")
        clear_folder_button.clicked.connect(self._clear_folders)
        folder_buttons.addWidget(clear_folder_button, 0, Qt.AlignmentFlag.AlignLeft)
        folder_buttons.addStretch(1)
        folders_layout.addLayout(folder_buttons)

        self.folders_output = QPlainTextEdit()
        self.folders_output.setReadOnly(True)
        self.folders_output.setPlaceholderText("No folders selected.")
        self.folders_output.setMaximumBlockCount(200)
        folders_layout.addWidget(self.folders_output)
        layout.addWidget(folders_card)

        dest_row = QHBoxLayout()
        dest_row.setSpacing(10)
        self.dest_input = QLineEdit()
        self.dest_input.setPlaceholderText("Optional destination folder for moved matches...")
        dest_row.addWidget(self.dest_input, 1)
        dest_browse = QPushButton("Browse Dest")
        dest_browse.clicked.connect(self._browse_dest)
        dest_row.addWidget(dest_browse)
        layout.addLayout(dest_row)

        self.split_checkbox = QCheckBox("Split moved files into source-based subfolders")
        self.split_checkbox.setChecked(True)
        layout.addWidget(self.split_checkbox, 0, Qt.AlignmentFlag.AlignLeft)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Run Validator")
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

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
        self.summary_label = QLabel("Choose a workbook and at least one source folder.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.results_host = QFrame()
        self.results_layout = QVBoxLayout(self.results_host)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(10)
        layout.addWidget(self.results_host)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Validation summary will appear here.")
        layout.addWidget(self.output, 1)

    def _browse_excel(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Workbook",
            str(self.services.default_output_path()),
            "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)",
        )
        if file_path:
            self.excel_input.setText(file_path)

    def _browse_dest(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Destination Folder",
            str(self.services.default_output_path()),
        )
        if folder:
            self.dest_input.setText(folder)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Source Folder",
            str(self.services.default_output_path()),
        )
        if folder and folder not in self.source_folders:
            self.source_folders.append(folder)
            self._render_folders()

    def _clear_folders(self) -> None:
        self.source_folders = []
        self._render_folders()

    def _render_folders(self) -> None:
        if not self.source_folders:
            self.folders_output.setPlainText("")
            return
        self.folders_output.setPlainText("\n".join(self.source_folders))

    def _clear_result_buttons(self) -> None:
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _run(self) -> None:
        xlsx_path = self.excel_input.text().strip()
        columns = [item.strip() for item in self.columns_input.text().split(",") if item.strip()]
        if not xlsx_path:
            QMessageBox.warning(self, "Missing Input", "Choose an Excel workbook to validate.")
            return
        if not self.source_folders:
            QMessageBox.warning(self, "Missing Input", "Add at least one source folder.")
            return
        if not columns:
            QMessageBox.warning(self, "Missing Input", "Enter at least one column name.")
            return

        self.run_button.setEnabled(False)
        self.progress.setValue(0)
        self.output.setPlainText("")
        self._clear_result_buttons()
        self.summary_label.setText("Validating workbook references...")

        self.services.run_task(
            lambda context: validate_files_task(
                context,
                xlsx_path,
                list(self.source_folders),
                columns,
                self.dest_input.text().strip() or None,
                self.split_checkbox.isChecked(),
                str(self.services.default_output_path()),
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
        lines = [
            f"Total rows: {result['total_rows']}",
            f"Files found and handled: {result['found_files']}",
            f"Missing values: {result['missing_values']}",
            f"Missing files: {result['missing_files']}",
        ]
        if result["reports"]:
            lines.append("")
            for label, path, row_count in result["reports"]:
                lines.append(f"{label}: {row_count} rows -> {path}")
                button = QPushButton(f"Open {label} Report")
                button.clicked.connect(lambda _checked=False, file_path=path: QDesktopServices.openUrl(QUrl.fromLocalFile(file_path)))
                self.results_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        else:
            lines.append("")
            lines.append("No report workbooks were generated.")

        self.output.setPlainText("\n".join(lines))
        self.summary_label.setText(
            f"Validation complete. Generated {len(result['reports'])} report file(s)."
        )
        self.services.record_run(self.plugin_id, "SUCCESS", f"Validated workbook with {result['total_rows']} rows")

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown validator error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Validator failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
