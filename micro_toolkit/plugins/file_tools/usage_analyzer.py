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


def analyze_usage_task(context, target_dir: str):
    import pandas as pd

    context.log(f"Mapping disk footprint inside '{target_dir}'...")
    nodes = os.listdir(target_dir)
    if not nodes:
        raise ValueError("The selected directory is empty.")

    total_size = 0
    data: list[dict[str, object]] = []
    for index, node in enumerate(nodes, start=1):
        context.progress(index / float(len(nodes)))
        path = os.path.join(target_dir, node)
        node_size = 0

        if os.path.isfile(path):
            try:
                node_size = os.path.getsize(path)
            except Exception:
                continue
            total_size += node_size
            data.append(
                {
                    "Entity": node,
                    "Type": "File",
                    "Size (MB)": round(node_size / (1024 * 1024), 2),
                }
            )
            continue

        if os.path.isdir(path):
            try:
                for root, _, files in os.walk(path):
                    for file_name in files:
                        file_path = os.path.join(root, file_name)
                        try:
                            file_size = os.path.getsize(file_path)
                        except Exception:
                            continue
                        node_size += file_size
                        total_size += file_size
            except Exception:
                continue
            data.append(
                {
                    "Entity": node,
                    "Type": "Folder",
                    "Size (MB)": round(node_size / (1024 * 1024), 2),
                }
            )

    dataframe = pd.DataFrame(data)
    if dataframe.empty:
        raise ValueError("No usable size data could be collected.")

    dataframe = dataframe.sort_values(by="Size (MB)", ascending=False).reset_index(drop=True)
    context.progress(1.0)
    context.log(f"Usage analysis complete. Total traced size: {round(total_size / (1024 * 1024), 2)} MB")
    return {
        "dataframe": dataframe,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "target_name": os.path.basename(target_dir.rstrip(os.sep)) or target_dir,
    }


class UsageAnalyzerPlugin(QtPlugin):
    plugin_id = "usage_analyzer"
    name = "Disk Space Visualizer"
    description = "Summarize immediate files and folders by size using a native desktop table."
    category = "File Utilities"

    def create_widget(self, services) -> QWidget:
        return UsageAnalyzerPage(services, self.plugin_id)


class UsageAnalyzerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._table_model = None
        self._latest_dataframe = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Disk Space Visualizer")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            "Inspect the immediate top-level files and folders inside a directory, sorted by size."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("Select a directory to analyze...")
        folder_row.addWidget(self.folder_input, 1)
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_button)
        layout.addLayout(folder_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Analyze Usage")
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
        self.summary_label = QLabel("Choose a directory to inspect.")
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
            "Select Directory To Analyze",
            str(self.services.default_output_path()),
        )
        if folder:
            self.folder_input.setText(folder)

    def _run(self) -> None:
        folder_path = self.folder_input.text().strip()
        if not folder_path:
            QMessageBox.warning(self, "Missing Input", "Choose a directory to analyze.")
            return

        self.run_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.progress.setValue(0)
        self.table.setModel(None)
        self._table_model = None
        self.summary_label.setText("Analyzing disk usage...")

        self.services.run_task(
            lambda context: analyze_usage_task(context, folder_path),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            on_progress=self._handle_progress,
        )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_dataframe = result["dataframe"]
        self._table_model = DataFrameTableModel(self._latest_dataframe)
        self.table.setModel(self._table_model)
        self.summary_label.setText(
            f"Analyzed '{result['target_name']}' and traced {result['total_size_mb']} MB across {len(self._latest_dataframe)} entries."
        )
        self.export_button.setEnabled(True)
        self.services.record_run(self.plugin_id, "SUCCESS", f"Analyzed usage for {result['target_name']}")

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown usage analysis error") if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Disk usage analysis failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _export_result(self) -> None:
        if self._latest_dataframe is None:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Disk Usage",
            str(self.services.default_output_path() / "disk_usage.xlsx"),
            "Excel Files (*.xlsx)",
        )
        if not save_path:
            return
        self._latest_dataframe.to_excel(save_path, index=False)
        self.services.log(f"Disk usage exported to {save_path}.")
