from __future__ import annotations

from datetime import datetime
import hashlib
import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.app_utils import generate_output_filename
from micro_toolkit.core.plugin_api import QtPlugin
from micro_toolkit.core.table_model import DataFrameTableModel
from micro_toolkit.core.widgets import ScrollSafeComboBox


QComboBox = ScrollSafeComboBox


def get_file_hash(filepath: str, chunk_size: int = 8192):
    hasher = hashlib.md5()
    try:
        with open(filepath, "rb") as handle:
            while chunk := handle.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


def parse_excel_columns(columns_text: str) -> list[str]:
    return [part.strip() for part in columns_text.split(",") if part.strip()]


def audit_excel_duplicates_task(context, workbook_specs: list[dict[str, str]], output_dir: str):
    import pandas as pd

    combined_duplicates = []
    total = len(workbook_specs)
    for index, spec in enumerate(workbook_specs, start=1):
        workbook_path = spec["path"]
        columns = parse_excel_columns(spec["columns"])
        context.progress((index - 1) / float(max(total, 1)))
        context.log(f"Reading Excel: {workbook_path}")
        dataframe = pd.read_excel(workbook_path)
        missing_columns = [column for column in columns if column not in dataframe.columns]
        if missing_columns:
            raise ValueError(
                f"Columns {', '.join(missing_columns)} were not found in workbook "
                f"'{os.path.basename(workbook_path)}'."
            )

        duplicates = dataframe[dataframe.duplicated(subset=columns, keep=False)]
        if duplicates.empty:
            continue

        duplicates = duplicates.sort_values(by=columns).reset_index(drop=True)
        duplicates.insert(0, "Workbook", os.path.basename(workbook_path))
        duplicates.insert(1, "Workbook Path", workbook_path)
        duplicates.insert(2, "Match Columns", ", ".join(columns))
        combined_duplicates.append(duplicates)

    if not combined_duplicates:
        raise ValueError("No duplicates were found in the selected workbook columns.")

    duplicates = pd.concat(combined_duplicates, ignore_index=True)
    os.makedirs(output_dir, exist_ok=True)
    output_name = generate_output_filename("DeepScanWorkbookAudit", "MultiWorkbook", ".xlsx")
    output_path = os.path.join(output_dir, output_name)
    duplicates.to_excel(output_path, index=False)
    context.progress(1.0)
    context.log(f"Saved workbook audit report to {output_path}")
    return {
        "dataframe": duplicates.head(300).copy(),
        "output_path": output_path,
        "row_count": len(duplicates),
        "source_count": len(workbook_specs),
        "mode": "excel",
    }


def audit_folder_duplicates_task(context, folder_paths: list[str], criteria: list[str], output_dir: str):
    import pandas as pd

    file_rows = []
    for folder_path in folder_paths:
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
                            "Created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                            "Folder": folder_path,
                        }
                    )
                except Exception:
                    continue

    dataframe = pd.DataFrame(file_rows)
    if dataframe.empty:
        raise ValueError("No files were found in the selected folders.")

    subset = []
    if "Name" in criteria:
        subset.append("Name")
    if "Size" in criteria:
        subset.append("Size")
    if "Created" in criteria:
        subset.append("Created")
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

    sort_columns = subset if subset else ["Path"]
    dataframe = dataframe.sort_values(by=sort_columns).reset_index(drop=True)
    os.makedirs(output_dir, exist_ok=True)
    output_name = generate_output_filename("DeepScanFolderAudit", "Folders", ".xlsx")
    output_path = os.path.join(output_dir, output_name)
    dataframe.to_excel(output_path, index=False)
    context.progress(1.0)
    context.log(f"Saved folder audit report to {output_path}")
    return {
        "dataframe": dataframe.head(300).copy(),
        "output_path": output_path,
        "row_count": len(dataframe),
        "source_count": len(folder_paths),
        "mode": "folder",
    }


class DeepScanAuditorPlugin(QtPlugin):
    plugin_id = "deep_scan_auditor"
    name = "Deep-Scan Auditor"
    description = "Audit duplicate files across folders or duplicate values across one or more Excel workbooks."
    category = "Validation & Analysis"

    def create_widget(self, services) -> QWidget:
        return DeepScanAuditorPage(services, self.plugin_id)


class DeepScanAuditorPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._latest_output_path = None
        self._table_model = None
        self._folder_sources: list[str] = []
        self._excel_sources: list[dict[str, str]] = []
        self._build_ui()

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel(self._pt("title", "Deep-Scan Auditor"))
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            self._pt("description", "Audit multiple folders for duplicate files or scan multiple Excel workbooks using per-file column names.")
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_label = QLabel(self._pt("label.mode", "Mode"))
        mode_label.setFixedWidth(90)
        mode_row.addWidget(mode_label)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(self._pt("mode.folder", "Folder"), "folder")
        self.mode_combo.addItem(self._pt("mode.excel", "Excel"), "excel")
        self.mode_combo.currentIndexChanged.connect(self._handle_mode_changed)
        mode_row.addWidget(self.mode_combo, 1)
        layout.addLayout(mode_row)

        self.sources_card = QFrame()
        self.sources_card.setStyleSheet("QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }")
        sources_layout = QVBoxLayout(self.sources_card)
        sources_layout.setContentsMargins(16, 14, 16, 14)
        sources_layout.setSpacing(10)
        sources_title = QLabel(self._pt("label.sources", "Selected Sources"))
        sources_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #10232c;")
        sources_layout.addWidget(sources_title)

        sources_actions = QHBoxLayout()
        sources_actions.setSpacing(8)
        self.browse_button = QPushButton(self._pt("button.add.folder", "Add Folder"))
        self.browse_button.clicked.connect(self._browse)
        sources_actions.addWidget(self.browse_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.remove_source_button = QPushButton(self._pt("button.remove", "Remove Selected"))
        self.remove_source_button.clicked.connect(self._remove_selected_sources)
        sources_actions.addWidget(self.remove_source_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.clear_sources_button = QPushButton(self._pt("button.clear", "Clear"))
        self.clear_sources_button.clicked.connect(self._clear_sources)
        sources_actions.addWidget(self.clear_sources_button, 0, Qt.AlignmentFlag.AlignLeft)
        sources_actions.addStretch(1)
        sources_layout.addLayout(sources_actions)

        self.sources_table = QTableWidget(0, 2)
        self.sources_table.verticalHeader().setVisible(False)
        self.sources_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sources_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sources_table.setAlternatingRowColors(True)
        self.sources_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.sources_table.horizontalHeader().setStretchLastSection(True)
        self.sources_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        sources_layout.addWidget(self.sources_table)
        layout.addWidget(self.sources_card)

        self.folder_criteria_card = QFrame()
        self.folder_criteria_card.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }"
        )
        folder_criteria_layout = QVBoxLayout(self.folder_criteria_card)
        folder_criteria_layout.setContentsMargins(16, 14, 16, 14)
        folder_criteria_layout.setSpacing(8)
        folder_criteria_title = QLabel(self._pt("label.criteria", "Folder Matching Criteria"))
        folder_criteria_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #10232c;")
        folder_criteria_layout.addWidget(folder_criteria_title)
        self.name_checkbox = QCheckBox(self._pt("criteria.name", "Name"))
        self.size_checkbox = QCheckBox(self._pt("criteria.size", "Size"))
        self.size_checkbox.setChecked(True)
        self.created_checkbox = QCheckBox(self._pt("criteria.created", "Created Date"))
        self.hash_checkbox = QCheckBox(self._pt("criteria.hash", "Hash"))
        self.hash_checkbox.setChecked(True)
        criteria_grid = QGridLayout()
        criteria_grid.setHorizontalSpacing(24)
        criteria_grid.setVerticalSpacing(8)
        criteria_grid.addWidget(self.name_checkbox, 0, 0)
        criteria_grid.addWidget(self.size_checkbox, 0, 1)
        criteria_grid.addWidget(self.created_checkbox, 1, 0)
        criteria_grid.addWidget(self.hash_checkbox, 1, 1)
        folder_criteria_layout.addLayout(criteria_grid)
        layout.addWidget(self.folder_criteria_card)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton(self._pt("button.run", "Run Audit"))
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
        self.summary_label = QLabel(self._pt("summary.empty", "Choose one or more sources, then run the deep-scan audit."))
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

    def _handle_mode_changed(self) -> None:
        self._sync_current_sources_from_table()
        self._update_mode_ui()

    def _update_mode_ui(self) -> None:
        is_excel = self._current_mode() == "excel"
        self.folder_criteria_card.setVisible(not is_excel)
        self.browse_button.setText(self._pt("button.add.excel", "Add Workbook(s)") if is_excel else self._pt("button.add.folder", "Add Folder"))
        self.sources_table.clearContents()
        self.sources_table.setRowCount(0)
        if is_excel:
            self.sources_table.setColumnCount(2)
            self.sources_table.setHorizontalHeaderLabels([self._pt("table.columns", "Columns"), self._pt("table.workbook", "Workbook")])
            self.sources_table.setColumnWidth(0, 220)
            for spec in self._excel_sources:
                self._append_excel_row(spec["path"], spec["columns"])
        else:
            self.sources_table.setColumnCount(1)
            self.sources_table.setHorizontalHeaderLabels([self._pt("table.folder", "Folder")])
            for folder_path in self._folder_sources:
                self._append_folder_row(folder_path)

    def _append_folder_row(self, folder_path: str) -> None:
        row = self.sources_table.rowCount()
        self.sources_table.insertRow(row)
        item = QTableWidgetItem(folder_path)
        item.setToolTip(folder_path)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        self.sources_table.setItem(row, 0, item)

    def _append_excel_row(self, file_path: str, columns: str) -> None:
        row = self.sources_table.rowCount()
        self.sources_table.insertRow(row)
        column_item = QTableWidgetItem(columns)
        column_item.setToolTip("Comma-separated column names")
        self.sources_table.setItem(row, 0, column_item)
        file_item = QTableWidgetItem(file_path)
        file_item.setToolTip(file_path)
        file_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        self.sources_table.setItem(row, 1, file_item)

    def _browse(self) -> None:
        if self._current_mode() == "excel":
            file_paths, _ = QFileDialog.getOpenFileNames(
                self,
                self._pt("dialog.browse.excel", "Select Workbooks"),
                str(self.services.default_output_path()),
                self._pt("dialog.browse.excel.filter", "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)"),
            )
            for file_path in file_paths:
                if any(spec["path"] == file_path for spec in self._excel_sources):
                    continue
                self._excel_sources.append({"path": file_path, "columns": ""})
        else:
            folder = QFileDialog.getExistingDirectory(
                self,
                self._pt("dialog.browse.folder", "Select Folder"),
                str(self.services.default_output_path()),
            )
            if folder and folder not in self._folder_sources:
                self._folder_sources.append(folder)
        self._update_mode_ui()

    def _sync_current_sources_from_table(self) -> None:
        if self._current_mode() == "excel":
            specs = []
            for row in range(self.sources_table.rowCount()):
                path_item = self.sources_table.item(row, 1)
                if not path_item:
                    continue
                column_item = self.sources_table.item(row, 0)
                specs.append(
                    {
                        "path": path_item.text().strip(),
                        "columns": column_item.text().strip() if column_item else "",
                    }
                )
            self._excel_sources = specs
            return

        folders = []
        for row in range(self.sources_table.rowCount()):
            folder_item = self.sources_table.item(row, 0)
            if folder_item and folder_item.text().strip():
                folders.append(folder_item.text().strip())
        self._folder_sources = folders

    def _remove_selected_sources(self) -> None:
        self._sync_current_sources_from_table()
        rows = sorted({index.row() for index in self.sources_table.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            return
        if self._current_mode() == "excel":
            for row in rows:
                if 0 <= row < len(self._excel_sources):
                    self._excel_sources.pop(row)
        else:
            for row in rows:
                if 0 <= row < len(self._folder_sources):
                    self._folder_sources.pop(row)
        self._update_mode_ui()

    def _clear_sources(self) -> None:
        if self._current_mode() == "excel":
            self._excel_sources = []
        else:
            self._folder_sources = []
        self._update_mode_ui()

    def _collect_excel_specs(self) -> list[dict[str, str]]:
        self._sync_current_sources_from_table()
        specs = []
        for spec in self._excel_sources:
            path = spec["path"].strip()
            columns_text = spec["columns"].strip()
            if not path:
                continue
            if not columns_text:
                raise ValueError(f"Enter one or more column names for workbook '{os.path.basename(path)}'.")
            columns = parse_excel_columns(columns_text)
            if not columns:
                raise ValueError(f"Enter valid column names for workbook '{os.path.basename(path)}'.")
            specs.append({"path": path, "columns": ", ".join(columns)})
        return specs

    def _run(self) -> None:
        mode = self._current_mode()
        self._sync_current_sources_from_table()
        try:
            excel_specs = self._collect_excel_specs() if mode == "excel" else []
        except ValueError as exc:
            QMessageBox.warning(self, "Missing Input", str(exc))
            return

        if mode == "excel" and not excel_specs:
            QMessageBox.warning(self, self._pt("dialog.error.title", "Missing Input"), self._pt("dialog.error.missing_excel", "Choose one or more workbooks."))
            return
        if mode == "folder" and not self._folder_sources:
            QMessageBox.warning(self, self._pt("dialog.error.title", "Missing Input"), self._pt("dialog.error.missing_folder", "Choose one or more folders."))
            return

        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)
        self.progress.setValue(0)
        self.table.setModel(None)
        self._table_model = None
        self.summary_label.setText(self._pt("summary.running", "Running deep-scan audit..."))

        if mode == "excel":
            task = lambda context: audit_excel_duplicates_task(
                context,
                excel_specs,
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
            if self.created_checkbox.isChecked():
                criteria.append("Created")
            task = lambda context: audit_folder_duplicates_task(
                context,
                list(self._folder_sources),
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
            self._pt(
                "summary.success",
                "Found {row_count} duplicate result rows across {source_count} source entries in {mode} mode. Previewing the first {preview_count} rows.",
                row_count=result['row_count'],
                source_count=result['source_count'],
                mode=self._pt(f"mode.{result['mode']}", result['mode']),
                preview_count=len(result['dataframe'])
            )
        )
        self.open_output_button.setEnabled(True)
        self.services.record_run(self.plugin_id, "SUCCESS", self._pt("log.task.success", "Generated deep-scan audit report in {mode} mode", mode=result['mode']))

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self._pt("error.unknown", "Unknown deep-scan auditor error")) if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self._pt("log.error", "Deep-Scan Auditor failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_output(self) -> None:
        if self._latest_output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_output_path))
