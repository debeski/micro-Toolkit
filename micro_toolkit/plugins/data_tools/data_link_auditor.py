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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.app_utils import generate_output_filename
from micro_toolkit.core.page_style import apply_page_chrome, section_title_style
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr


def normalize_string(value):
    return unicodedata.normalize("NFKD", str(value)).strip() if value is not None else None


def audit_data_links_task(
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
        report_name = generate_output_filename("DataLinkAudit_MissingValues", base_name, ".xlsx")
        report_path = os.path.join(output_dir, report_name)
        missing_values_df.to_excel(report_path, index=False)
        created_reports.append(("Missing Values", report_path, len(missing_values_df)))

    missing_files_df = pd.DataFrame(missing_files)
    if not missing_files_df.empty:
        report_name = generate_output_filename("DataLinkAudit_MissingFiles", base_name, ".xlsx")
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


class DataLinkAuditorPlugin(QtPlugin):
    plugin_id = "data_link_auditor"
    name = "Data-Link Auditor"
    description = "Audit workbook-linked filenames against one or more source folders and export missing-value or missing-file reports."
    category = "Data Utilities"

    def create_widget(self, services) -> QWidget:
        return DataLinkAuditorPage(services, self.plugin_id)


class DataLinkAuditorPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self.source_folders: list[str] = []
        self._latest_result = None
        self._has_run = False
        self._build_ui()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self._apply_texts()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        self.title_label = QLabel(self.tr("title", "Data-Link Auditor"))
        layout.addWidget(self.title_label)

        self.description_label = QLabel(
            self.tr("description", "Audit filenames referenced in an Excel workbook against multiple source folders, then optionally move confirmed matches into a destination structure.")
        )
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        excel_row = QHBoxLayout()
        excel_row.setSpacing(10)
        self.excel_input = QLineEdit()
        self.excel_input.setPlaceholderText(self.tr("excel.placeholder", "Select an Excel workbook..."))
        excel_row.addWidget(self.excel_input, 1)
        self.excel_browse_button = QPushButton(self.tr("button.browse_excel", "Browse"))
        self.excel_browse_button.clicked.connect(self._browse_excel)
        excel_row.addWidget(self.excel_browse_button)
        layout.addLayout(excel_row)

        col_row = QHBoxLayout()
        col_row.setSpacing(10)
        self.columns_label = QLabel(self.tr("label.columns", "Columns"))
        self.columns_label.setFixedWidth(90)
        col_row.addWidget(self.columns_label)
        self.columns_input = QLineEdit("pdf_file, attach")
        self.columns_input.setPlaceholderText(self.tr("columns.placeholder", "Comma-separated column names"))
        col_row.addWidget(self.columns_input, 1)
        layout.addLayout(col_row)

        self.folders_card = QFrame()
        folders_layout = QVBoxLayout(self.folders_card)
        folders_layout.setContentsMargins(16, 14, 16, 14)
        folders_layout.setSpacing(10)
        self.folders_title_label = QLabel(self.tr("label.folders", "Source Folders"))
        folders_layout.addWidget(self.folders_title_label)

        folder_buttons = QHBoxLayout()
        folder_buttons.setSpacing(10)
        self.add_folder_button = QPushButton(self.tr("button.add_folder", "Add Folder"))
        self.add_folder_button.clicked.connect(self._add_folder)
        folder_buttons.addWidget(self.add_folder_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.clear_folders_button = QPushButton(self.tr("button.clear_folders", "Clear Folders"))
        self.clear_folders_button.clicked.connect(self._clear_folders)
        folder_buttons.addWidget(self.clear_folders_button, 0, Qt.AlignmentFlag.AlignLeft)
        folder_buttons.addStretch(1)
        folders_layout.addLayout(folder_buttons)

        self.folders_output = QPlainTextEdit()
        self.folders_output.setReadOnly(True)
        self.folders_output.setPlaceholderText(self.tr("folders.placeholder", "No folders selected."))
        self.folders_output.setMaximumBlockCount(200)
        folders_layout.addWidget(self.folders_output)
        layout.addWidget(self.folders_card)

        dest_row = QHBoxLayout()
        dest_row.setSpacing(10)
        self.dest_input = QLineEdit()
        self.dest_input.setPlaceholderText(self.tr("dest.placeholder", "Optional destination folder for moved matches..."))
        dest_row.addWidget(self.dest_input, 1)
        self.dest_browse_button = QPushButton(self.tr("button.browse_dest", "Browse Dest"))
        self.dest_browse_button.clicked.connect(self._browse_dest)
        dest_row.addWidget(self.dest_browse_button)
        layout.addLayout(dest_row)

        self.split_checkbox = QCheckBox(self.tr("checkbox.split", "Split moved files into source-based subfolders"))
        self.split_checkbox.setChecked(True)
        layout.addWidget(self.split_checkbox, 0, Qt.AlignmentFlag.AlignLeft)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton(self.tr("button.run", "Run Audit"))
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addLayout(controls)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel(self.tr("summary.empty", "Choose a workbook and at least one source folder."))
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(self.summary_card)

        self.results_host = QFrame()
        self.results_layout = QVBoxLayout(self.results_host)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(10)
        layout.addWidget(self.results_host)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText(self.tr("output.placeholder", "Validation summary will appear here."))
        layout.addWidget(self.output, 1)
        self._apply_theme_styles()

    def _apply_texts(self) -> None:
        self.title_label.setText(self.tr("title", "Data-Link Auditor"))
        self.description_label.setText(
            self.tr("description", "Audit filenames referenced in an Excel workbook against multiple source folders, then optionally move confirmed matches into a destination structure.")
        )
        self.excel_input.setPlaceholderText(self.tr("excel.placeholder", "Select an Excel workbook..."))
        self.excel_browse_button.setText(self.tr("button.browse_excel", "Browse"))
        self.columns_label.setText(self.tr("label.columns", "Columns"))
        self.columns_input.setPlaceholderText(self.tr("columns.placeholder", "Comma-separated column names"))
        self.folders_title_label.setText(self.tr("label.folders", "Source Folders"))
        self.add_folder_button.setText(self.tr("button.add_folder", "Add Folder"))
        self.clear_folders_button.setText(self.tr("button.clear_folders", "Clear Folders"))
        self.dest_input.setPlaceholderText(self.tr("dest.placeholder", "Optional destination folder for moved matches..."))
        self.dest_browse_button.setText(self.tr("button.browse_dest", "Browse Dest"))
        self.split_checkbox.setText(self.tr("checkbox.split", "Split moved files into source-based subfolders"))
        self.run_button.setText(self.tr("button.run", "Run Audit"))
        self.output.setPlaceholderText(self.tr("output.placeholder", "Validation summary will appear here."))
        if self._latest_result is not None:
            self._render_result_payload(self._latest_result)
        elif not self._has_run:
            self.summary_label.setText(self.tr("summary.empty", "Choose a workbook and at least one source folder."))
        self._apply_theme_styles()

    def _browse_excel(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("dialog.browse.excel", "Select Workbook"),
            str(self.services.default_output_path()),
            self.tr("dialog.browse.excel.filter", "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)"),
        )
        if file_path:
            self.excel_input.setText(file_path)

    def _browse_dest(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("dialog.browse.dest", "Select Destination Folder"),
            str(self.services.default_output_path()),
        )
        if folder:
            self.dest_input.setText(folder)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("dialog.browse.folder", "Select Source Folder"),
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
            QMessageBox.warning(self, self.tr("dialog.error.title", "Missing Input"), self.tr("dialog.error.missing_excel", "Choose an Excel workbook to validate."))
            return
        if not self.source_folders:
            QMessageBox.warning(self, self.tr("dialog.error.title", "Missing Input"), self.tr("dialog.error.missing_folders", "Add at least one source folder."))
            return
        if not columns:
            QMessageBox.warning(self, self.tr("dialog.error.title", "Missing Input"), self.tr("dialog.error.missing_columns", "Enter at least one column name."))
            return

        self.run_button.setEnabled(False)
        self.output.setPlainText("")
        self._clear_result_buttons()
        self.summary_label.setText(self.tr("summary.running", "Validating workbook references..."))

        self.services.run_task(
            lambda context: audit_data_links_task(
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
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._has_run = True
        self._latest_result = result
        self._render_result_payload(result)
        self.services.record_run(self.plugin_id, "SUCCESS", self.tr("log.task.success", "Audited workbook with {count} rows", count=result['total_rows']))

    def _handle_error(self, payload: object) -> None:
        self._has_run = True
        self._latest_result = None
        message = payload.get("message", self.tr("error.unknown", "Unknown data-link auditor error")) if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.error", "Data-Link Auditor failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.folders_card, self.summary_card),
            summary_label=self.summary_label,
            title_size=26,
            title_weight=700,
            card_radius=14,
        )
        self.folders_title_label.setStyleSheet(section_title_style(palette, size=14, weight=700))

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _render_result_payload(self, result: dict[str, object]) -> None:
        self._clear_result_buttons()
        lines = [
            self.tr("report.total_rows", "Total rows: {count}", count=result["total_rows"]),
            self.tr("report.found_files", "Files found and handled: {count}", count=result["found_files"]),
            self.tr("report.missing_values", "Missing values: {count}", count=result["missing_values"]),
            self.tr("report.missing_files", "Missing files: {count}", count=result["missing_files"]),
        ]
        reports = result.get("reports") or []
        if reports:
            lines.append("")
            for pt_label, path, row_count in reports:
                label = self.tr(f"report.{pt_label.replace(' ', '_').lower()}", pt_label)
                lines.append(
                    self.tr("report.line", "{label}: {row_count} rows -> {path}", label=label, row_count=row_count, path=path)
                )
                button = QPushButton(self.tr("button.open_report", "Open {label} Report", label=label))
                button.clicked.connect(lambda _checked=False, file_path=path: QDesktopServices.openUrl(QUrl.fromLocalFile(file_path)))
                self.results_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        else:
            lines.extend(["", self.tr("report.none", "No report workbooks were generated.")])
        self.output.setPlainText("\n".join(lines))
        self.summary_label.setText(
            self.tr("summary.success", "Validation complete. Generated {count} report file(s).", count=len(reports))
        )
