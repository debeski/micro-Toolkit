from __future__ import annotations

import os

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
from micro_toolkit.core.page_style import apply_page_chrome
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr, safe_tr

def sanitize_data_task(
    context,
    file_path: str,
    trim: bool,
    drop_empty: bool,
    fill_nulls: bool,
    output_dir: str,
    *,
    translate=None,
):
    import pandas as pd

    context.log(safe_tr(translate, "log.reading", "Reading {path}...", path=file_path))
    dataframe = pd.read_excel(file_path)
    start_rows = len(dataframe)
    context.progress(0.2)

    if trim:
        dataframe = dataframe.apply(lambda column: column.str.strip() if column.dtype == "object" else column)
        context.log(safe_tr(translate, "log.trimmed", "Trimmed whitespace in string cells."))
    context.progress(0.45)

    if drop_empty:
        dataframe = dataframe.dropna(how="all")
        context.log(safe_tr(translate, "log.dropped", "Dropped fully empty rows."))
    context.progress(0.65)

    if fill_nulls:
        dataframe = dataframe.fillna("NULL_VALUE")
        context.log(safe_tr(translate, "log.filled", "Filled null cells with NULL_VALUE."))
    context.progress(0.8)

    source_name = os.path.splitext(os.path.basename(file_path))[0]
    output_name = generate_output_filename("Cleaned", source_name, ".xlsx")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_name)
    dataframe.to_excel(output_path, index=False)
    context.progress(1.0)
    context.log(safe_tr(translate, "log.saved", "Saved cleaned workbook to {path}", path=output_path))

    return {
        "output_path": output_path,
        "start_rows": start_rows,
        "end_rows": len(dataframe),
        "file_name": os.path.basename(file_path),
    }


class DataCleanerPlugin(QtPlugin):
    plugin_id = "cleaner"
    name = "Data Cleaner"
    description = "Trim strings, drop empty rows, fill nulls, and save a cleaned workbook to the configured output path."
    category = "Office Utilities"

    def create_widget(self, services) -> QWidget:
        return DataCleanerPage(services, self.plugin_id)


class DataCleanerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self._latest_output_path = None
        self._build_ui()
        self._apply_texts()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        self.title_label = QLabel()
        layout.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        file_row = QHBoxLayout()
        file_row.setSpacing(10)
        self.file_input = QLineEdit()
        file_row.addWidget(self.file_input, 1)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._browse_file)
        file_row.addWidget(self.browse_button)
        layout.addLayout(file_row)

        self.options_card = QFrame()
        options_layout = QVBoxLayout(self.options_card)
        options_layout.setContentsMargins(16, 14, 16, 14)
        options_layout.setSpacing(8)

        self.trim_checkbox = QCheckBox()
        self.trim_checkbox.setChecked(True)
        options_layout.addWidget(self.trim_checkbox)

        self.drop_checkbox = QCheckBox()
        self.drop_checkbox.setChecked(True)
        options_layout.addWidget(self.drop_checkbox)

        self.fill_checkbox = QCheckBox()
        self.fill_checkbox.setChecked(True)
        options_layout.addWidget(self.fill_checkbox)
        layout.addWidget(self.options_card)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_output_button = QPushButton()
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self._open_output)
        controls.addWidget(self.open_output_button, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addLayout(controls)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(self.summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)

    def _apply_texts(self) -> None:
        self.title_label.setText(self.tr("title", "Data Cleaner"))
        self.description_label.setText(
            self.tr(
                "description",
                "Clean an Excel workbook and write the resulting file to your configured output directory.",
            )
        )
        self.file_input.setPlaceholderText(self.tr("placeholder.file", "Select an Excel workbook..."))
        self.browse_button.setText(self.tr("browse", "Browse"))
        self.trim_checkbox.setText(self.tr("option.trim", "Trim surrounding whitespace"))
        self.drop_checkbox.setText(self.tr("option.drop", "Drop rows that are completely empty"))
        self.fill_checkbox.setText(self.tr("option.fill", "Fill remaining null cells with NULL_VALUE"))
        self.run_button.setText(self.tr("run", "Run Cleaner"))
        self.open_output_button.setText(self.tr("open_result", "Open Result"))
        self.summary_label.setText(self.tr("summary.ready", "Choose a workbook to begin cleaning."))
        self.output.setPlaceholderText(self.tr("summary.placeholder", "Run details will appear here."))
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.options_card, self.summary_card),
            summary_label=self.summary_label,
        )

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("dialog.select_workbook", "Select Workbook"),
            str(self.services.default_output_path()),
            self.tr("dialog.excel_filter", "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)"),
        )
        if file_path:
            self.file_input.setText(file_path)

    def _run(self) -> None:
        file_path = self.file_input.text().strip()
        if not file_path:
            QMessageBox.warning(
                self,
                self.tr("error.missing_input.title", "Missing Input"),
                self.tr("error.missing_file", "Choose a workbook to clean."),
            )
            return

        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)
        self.output.setPlainText("")
        self.summary_label.setText(self.tr("summary.running", "Cleaning workbook..."))

        output_dir = str(self.services.default_output_path())
        self.services.run_task(
            lambda context: sanitize_data_task(
                context,
                file_path,
                self.trim_checkbox.isChecked(),
                self.drop_checkbox.isChecked(),
                self.fill_checkbox.isChecked(),
                output_dir,
                translate=self.tr,
            ),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_output_path = result["output_path"]
        self.summary_label.setText(
            self.tr(
                "summary.done",
                "Cleaned {file_name} and reduced rows from {start_rows} to {end_rows}.",
                file_name=result["file_name"],
                start_rows=result["start_rows"],
                end_rows=result["end_rows"],
            )
        )
        self.output.setPlainText(self.tr("output.saved", "Saved cleaned workbook to:\n{path}", path=result["output_path"]))
        self.open_output_button.setEnabled(True)
        self.services.record_run(self.plugin_id, "SUCCESS", self.tr("run.success", "Cleaned {file_name}", file_name=result["file_name"]))

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self.tr("error.unknown", "Unknown cleaner error")) if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.output.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "Data cleaner failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_output(self) -> None:
        if self._latest_output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_output_path))
