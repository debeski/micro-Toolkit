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
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.page_style import apply_page_chrome
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr, tr
from micro_toolkit.core.table_model import DataFrameTableModel


def analyze_usage_task(context, services, plugin_id: str, target_dir: str):
    import pandas as pd

    def _ensure_western(text: str) -> str:
        eastern = "٠١٢٣٤٥٦٧٨٩"
        western = "0123456789"
        trans = str.maketrans(eastern, western)
        return text.translate(trans)

    context.log(tr(services, plugin_id, "log.start", "Mapping disk footprint inside '{folder}'...", folder=target_dir))
    nodes = os.listdir(target_dir)
    if not nodes:
        raise ValueError(tr(services, plugin_id, "error.empty", "The selected directory is empty."))

    total_size = 0
    data: list[dict[str, object]] = []
    
    h_entity = tr(services, plugin_id, "table.header.entity", "Entity")
    h_type = tr(services, plugin_id, "table.header.type", "Type")
    h_size = tr(services, plugin_id, "table.header.size", "Size (MB)")
    
    t_file = tr(services, plugin_id, "type.file", "File")
    t_folder = tr(services, plugin_id, "type.folder", "Folder")

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
                    h_entity: node,
                    h_type: t_file,
                    h_size: round(node_size / (1024 * 1024), 2),
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
                    h_entity: node,
                    h_type: t_folder,
                    h_size: round(node_size / (1024 * 1024), 2),
                }
            )

    dataframe = pd.DataFrame(data)
    if dataframe.empty:
        raise ValueError(tr(services, plugin_id, "error.no_data", "No usable size data could be collected."))

    dataframe = dataframe.sort_values(by=h_size, ascending=False).reset_index(drop=True)
    context.progress(1.0)
    
    size_str = _ensure_western(str(round(total_size / (1024 * 1024), 2)))
    context.log(tr(services, plugin_id, "log.done", "Usage analysis complete. Total traced size: {size} MB", size=size_str))
    return {
        "dataframe": dataframe,
        "total_size_mb": size_str,
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
        self.tr = bind_tr(services, plugin_id)
        self._table_model = None
        self._latest_dataframe = None
        self._build_ui()
        self.services.i18n.language_changed.connect(self._refresh)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _build_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(28, 28, 28, 28)
        self.main_layout.setSpacing(16)

        self.title_label = QLabel()
        self.main_layout.addWidget(self.title_label)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.main_layout.addWidget(self.desc_label)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        self.folder_input = QLineEdit()
        folder_row.addWidget(self.folder_input, 1)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.browse_button)
        self.main_layout.addLayout(folder_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.export_button = QPushButton()
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_result)
        controls.addWidget(self.export_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.main_layout.addLayout(controls)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        self.main_layout.addWidget(self.summary_card)

        self.table = QTableView()
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.main_layout.addWidget(self.table, 1)
        
        self._refresh()

    def _refresh(self) -> None:
        self.title_label.setText(self.tr("title", "Disk Space Visualizer"))
        self.desc_label.setText(self.tr("description", "Inspect the immediate top-level files and folders inside a directory, sorted by size."))
        self.folder_input.setPlaceholderText(self.tr("folder.placeholder", "Select a directory to analyze..."))
        self.browse_button.setText(self.tr("browse", "Browse"))
        self.run_button.setText(self.tr("run.button", "Analyze Usage"))
        self.export_button.setText(self.tr("export.button", "Export XLSX"))
        self.summary_label.setText(self.tr("summary.initial", "Choose a directory to inspect."))
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.desc_label,
            cards=(self.summary_card,),
            summary_label=self.summary_label,
        )

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("dialog.browse", "Select Directory To Analyze"),
            str(self.services.default_output_path()),
        )
        if folder:
            self.folder_input.setText(folder)

    def _run(self) -> None:
        folder_path = self.folder_input.text().strip()
        if not folder_path:
            QMessageBox.warning(
                self, 
                self.tr("dialog.missing.title", "Missing Input"), 
                self.tr("dialog.missing.body", "Choose a directory to analyze.")
            )
            return

        self.run_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.table.setModel(None)
        self._table_model = None
        self.summary_label.setText(self.tr("summary.running", "Analyzing disk usage..."))

        self.services.run_task(
            lambda context: analyze_usage_task(context, self.services, self.plugin_id, folder_path),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_dataframe = result["dataframe"]
        self._table_model = DataFrameTableModel(self._latest_dataframe)
        self.table.setModel(self._table_model)
        
        count_str = str(len(self._latest_dataframe))
        eastern = "٠١٢٣٤٥٦٧٨٩"
        western = "0123456789"
        trans = str.maketrans(eastern, western)
        count_str = count_str.translate(trans)
        
        self.summary_label.setText(
            self.tr("summary.done", "Analyzed '{target}' and traced {size} MB across {count} entries.", target=result['target_name'], size=result['total_size_mb'], count=count_str)
        )
        self.export_button.setEnabled(True)
        self.services.record_run(self.plugin_id, "SUCCESS", self.tr("summary.done", "Analyzed usage for {target}", target=result['target_name'], size=result['total_size_mb'], count=count_str))

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown usage analysis error") if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "Disk usage analysis failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _export_result(self) -> None:
        if self._latest_dataframe is None:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("dialog.export", "Export Disk Usage"),
            str(self.services.default_output_path() / "disk_usage.xlsx"),
            "Excel Files (*.xlsx)",
        )
        if not save_path:
            return
        self._latest_dataframe.to_excel(save_path, index=False)
        self.services.log(self.tr("log.export", "Disk usage exported to {path}.", path=save_path))
