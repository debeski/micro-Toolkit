from __future__ import annotations

import os

from PySide6.QtCore import Qt
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

from micro_toolkit.core.plugin_api import QtPlugin
from micro_toolkit.core.table_model import DataFrameTableModel


def generate_analytics_report(context, file_path: str, group_cols: str):
    import pandas as pd

    context.log(f"Loading '{file_path}' for quick analytics...")
    dataframe = pd.read_excel(file_path)
    context.progress(0.35)

    valid_groups = [column.strip() for column in group_cols.split(",") if column.strip() in dataframe.columns]
    if not valid_groups:
        raise ValueError("None of the requested grouping columns exist in the workbook.")

    context.log(f"Grouping by: {', '.join(valid_groups)}")
    pivot = dataframe.groupby(valid_groups).size().reset_index(name="Total Count")
    context.progress(0.85)
    context.log(f"Generated {len(pivot)} grouped rows.")
    context.progress(1.0)

    return {
        "dataframe": pivot,
        "file_name": os.path.basename(file_path),
        "groups": valid_groups,
    }


class QuickAnalyticsPlugin(QtPlugin):
    plugin_id = "quick_analytics"
    name = "Quick Analytics"
    description = "Read an Excel file, group by selected columns, and inspect the resulting summary in a native table."
    category = "Validation & Analysis"

    def create_widget(self, services) -> QWidget:
        return QuickAnalyticsPage(services, self.plugin_id)


class QuickAnalyticsPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._table_model = None
        self._latest_result = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Quick Analytics")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            "This tool uses a real native table instead of rendering a giant text blob, so large summaries stay usable."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        file_row = QHBoxLayout()
        file_row.setSpacing(10)
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Select an Excel workbook...")
        file_row.addWidget(self.file_input, 1)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_file)
        file_row.addWidget(browse_button)
        layout.addLayout(file_row)

        group_row = QHBoxLayout()
        group_row.setSpacing(10)
        group_label = QLabel("Group Columns")
        group_label.setFixedWidth(110)
        group_row.addWidget(group_label)

        self.group_input = QLineEdit()
        self.group_input.setPlaceholderText("Example: Department, Status")
        group_row.addWidget(self.group_input, 1)
        layout.addLayout(group_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Run Analytics")
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.export_button = QPushButton("Export XLSX")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_result)
        controls.addWidget(self.export_button, 0, Qt.AlignmentFlag.AlignLeft)

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
        self.summary_label = QLabel("Run analytics to populate a native table view.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.table = QTableView()
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        layout.addWidget(self.table, 1)

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Excel Workbook",
            str(self.services.default_output_path()),
            "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)",
        )
        if file_path:
            self.file_input.setText(file_path)

    def _run(self) -> None:
        file_path = self.file_input.text().strip()
        group_cols = self.group_input.text().strip()
        if not file_path or not group_cols:
            QMessageBox.warning(self, "Missing Input", "Choose a workbook and enter at least one grouping column.")
            return

        self.run_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.progress.setValue(0)
        self.summary_label.setText("Running analytics...")
        self.table.setModel(None)
        self._table_model = None

        self.services.run_task(
            lambda context: generate_analytics_report(context, file_path, group_cols),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            on_progress=self._handle_progress,
        )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        dataframe = result["dataframe"]
        self._latest_result = result
        self._table_model = DataFrameTableModel(dataframe)
        self.table.setModel(self._table_model)
        self.summary_label.setText(
            f"{result['file_name']} grouped by {', '.join(result['groups'])}. "
            f"Produced {len(dataframe)} result rows."
        )
        self.export_button.setEnabled(True)
        self.services.record_run(self.plugin_id, "SUCCESS", f"Analyzed {result['file_name']}")
        self.services.log(f"Quick analytics complete for {result['file_name']}.")

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown analytics error") if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Quick analytics failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _export_result(self) -> None:
        if not self._latest_result:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Analytics",
            str(self.services.default_output_path() / "quick_analytics.xlsx"),
            "Excel Files (*.xlsx)",
        )
        if not save_path:
            return
        self._latest_result["dataframe"].to_excel(save_path, index=False)
        self.services.log(f"Analytics exported to {save_path}.")
