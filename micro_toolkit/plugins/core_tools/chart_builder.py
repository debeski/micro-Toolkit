from __future__ import annotations

import base64
from io import BytesIO
import os

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QLineSeries, QPieSeries, QScatterSeries, QValueAxis
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin
from micro_toolkit.core.table_model import DataFrameTableModel
from micro_toolkit.core.widgets import ScrollSafeComboBox


QComboBox = ScrollSafeComboBox


PALETTES = {
    "ocean": ["#3b82f6", "#06b6d4", "#38bdf8", "#0f766e", "#1d4ed8"],
    "rose": ["#e11d48", "#fb7185", "#f472b6", "#be185d", "#f9a8d4"],
    "forest": ["#15803d", "#22c55e", "#65a30d", "#16a34a", "#84cc16"],
    "amber": ["#d97706", "#f59e0b", "#fbbf24", "#f97316", "#facc15"],
    "slate": ["#334155", "#475569", "#64748b", "#0f172a", "#94a3b8"],
}

AGGREGATIONS = ("count", "sum", "mean", "min", "max", "median", "nunique")
JOIN_TYPES = ("inner", "left", "right", "outer")
OPERATIONS = (
    ("Summarize", "summarize"),
    ("Pivot", "pivot"),
    ("Melt", "melt"),
    ("Transpose", "transpose"),
    ("Merge / Join", "merge"),
)
CHART_TYPES = (
    ("None", "none"),
    ("Bar", "bar"),
    ("Line", "line"),
    ("Pie", "pie"),
    ("Donut", "donut"),
    ("Scatter", "scatter"),
)


def parse_columns(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def parse_slice(value: str) -> tuple[int | None, int | None]:
    text = str(value or "").strip()
    if not text:
        return None, None
    if ":" not in text:
        index = int(text)
        return index, index + 1
    start_text, end_text = text.split(":", 1)
    start = int(start_text) if start_text.strip() else None
    end = int(end_text) if end_text.strip() else None
    return start, end


def _validate_columns(dataframe, columns: list[str], label: str, *, allow_empty: bool = False) -> list[str]:
    if allow_empty and not columns:
        return []
    valid = [column for column in columns if column in dataframe.columns]
    if not valid:
        raise ValueError(f"None of the requested {label} columns exist in the workbook.")
    missing = [column for column in columns if column not in dataframe.columns]
    if missing:
        raise ValueError(f"Missing {label} columns: {', '.join(missing)}")
    return valid


def _preprocess_dataframe(dataframe, config: dict[str, object]):
    filter_expr = str(config.get("filter_expr", "")).strip()
    if filter_expr:
        try:
            dataframe = dataframe.query(filter_expr, engine="python")
        except Exception as exc:
            raise ValueError(f"Filter expression failed: {exc}") from exc

    slice_expr = str(config.get("slice_expr", "")).strip()
    if slice_expr:
        try:
            start, end = parse_slice(slice_expr)
        except Exception as exc:
            raise ValueError(f"Invalid slice expression '{slice_expr}'. Use forms like 0:100 or 25.") from exc
        dataframe = dataframe.iloc[slice(start, end)]
    return dataframe


def _postprocess_dataframe(dataframe, config: dict[str, object]):
    sort_by = str(config.get("sort_by", "")).strip()
    if sort_by:
        sort_columns = _validate_columns(dataframe, parse_columns(sort_by), "sort", allow_empty=False)
        dataframe = dataframe.sort_values(by=sort_columns, ascending=not bool(config.get("sort_descending", False)))

    top_n = int(config.get("top_n", 0) or 0)
    if top_n > 0:
        dataframe = dataframe.head(top_n)
    return dataframe.reset_index(drop=True)


def run_chart_builder_task(context, primary_file: str, config: dict[str, object]):
    import pandas as pd

    context.log(f"Loading '{primary_file}' for chart building...")
    primary = pd.read_excel(primary_file)
    context.progress(0.15)
    primary = _preprocess_dataframe(primary, config)
    operation = str(config.get("operation", "summarize"))

    if operation == "summarize":
        group_columns = _validate_columns(primary, parse_columns(config.get("group_columns", "")), "group")
        value_columns = _validate_columns(primary, parse_columns(config.get("value_columns", "")), "value", allow_empty=True)
        agg = str(config.get("aggregate", "count"))
        context.log(f"Running summarize operation with aggregate '{agg}'.")
        if value_columns:
            result = primary.groupby(group_columns)[value_columns].agg(agg).reset_index()
        else:
            result = primary.groupby(group_columns).size().reset_index(name="Count")
    elif operation == "pivot":
        index_columns = _validate_columns(primary, parse_columns(config.get("pivot_index", "")), "pivot index")
        column_columns = _validate_columns(primary, parse_columns(config.get("pivot_columns", "")), "pivot column")
        value_columns = _validate_columns(primary, parse_columns(config.get("pivot_values", "")), "pivot value")
        agg = str(config.get("aggregate", "count"))
        context.log(f"Running pivot operation with aggregate '{agg}'.")
        result = pd.pivot_table(
            primary,
            index=index_columns,
            columns=column_columns,
            values=value_columns,
            aggfunc=agg,
            fill_value=0,
        ).reset_index()
        if hasattr(result.columns, "to_flat_index"):
            result.columns = [
                " / ".join(str(part) for part in item if str(part) != "")
                if isinstance(item, tuple)
                else str(item)
                for item in result.columns.to_flat_index()
            ]
    elif operation == "melt":
        id_columns = _validate_columns(primary, parse_columns(config.get("melt_id", "")), "melt id", allow_empty=True)
        value_columns = _validate_columns(primary, parse_columns(config.get("melt_values", "")), "melt value", allow_empty=True)
        if not value_columns:
            raise ValueError("Choose one or more value columns to melt.")
        context.log("Running melt operation.")
        result = primary.melt(id_vars=id_columns or None, value_vars=value_columns)
    elif operation == "transpose":
        transpose_columns = _validate_columns(primary, parse_columns(config.get("transpose_columns", "")), "transpose", allow_empty=True)
        context.log("Running transpose operation.")
        base = primary[transpose_columns].copy() if transpose_columns else primary.copy()
        result = base.transpose().reset_index()
        result.rename(columns={"index": "Field"}, inplace=True)
    elif operation == "merge":
        secondary_file = str(config.get("secondary_file", "")).strip()
        if not secondary_file:
            raise ValueError("Choose a second workbook for merge/join mode.")
        context.log(f"Loading secondary workbook '{secondary_file}'...")
        secondary = pd.read_excel(secondary_file)
        context.progress(0.28)
        left_keys = _validate_columns(primary, parse_columns(config.get("left_keys", "")), "left join")
        right_keys = parse_columns(config.get("right_keys", ""))
        right_keys = _validate_columns(secondary, right_keys or left_keys, "right join")
        join_type = str(config.get("join_type", "inner"))
        context.log(f"Running {join_type} join.")
        result = primary.merge(
            secondary,
            how=join_type,
            left_on=left_keys,
            right_on=right_keys,
            suffixes=("_left", "_right"),
        )
    else:
        raise ValueError(f"Unsupported operation: {operation}")

    context.progress(0.82)
    result = _postprocess_dataframe(result, config)
    context.progress(1.0)
    context.log(f"Prepared {len(result)} result rows.")
    return {
        "dataframe": result,
        "operation": operation,
        "primary_file": os.path.basename(primary_file),
        "row_count": len(result),
        "config": dict(config),
    }


class ChartBuilderPlugin(QtPlugin):
    plugin_id = "chart_builder"
    name = "Chart Builder"
    description = "Shape workbook data, aggregate it, join it, and build charts with exportable results."
    category = "Validation & Analysis"

    def create_widget(self, services) -> QWidget:
        return ChartBuilderPage(services, self.plugin_id)


class ChartBuilderPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._table_model = None
        self._latest_result = None
        self._build_ui()

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel(self._pt("title", "Chart Builder"))
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            self._pt("description", "Build charts and analysis tables from Excel workbooks using a guided pipeline. "
            "Start simple with grouped summaries, or enable advanced controls for pivots, melts, joins, filters, slicing, and export workflows.")
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        source_card = QFrame()
        source_card.setStyleSheet("QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }")
        source_layout = QGridLayout(source_card)
        source_layout.setContentsMargins(16, 14, 16, 14)
        source_layout.setHorizontalSpacing(10)
        source_layout.setVerticalSpacing(10)

        self.primary_input = QLineEdit()
        self.primary_input.setPlaceholderText(self._pt("primary.placeholder", "Select primary Excel workbook..."))
        source_layout.addWidget(QLabel(self._pt("label.primary", "Primary")), 0, 0)
        source_layout.addWidget(self.primary_input, 0, 1)
        primary_browse = QPushButton(self._pt("button.browse_primary", "Browse"))
        primary_browse.clicked.connect(self._browse_primary)
        source_layout.addWidget(primary_browse, 0, 2)

        self.operation_combo = QComboBox()
        for label, value in OPERATIONS:
            self.operation_combo.addItem(self._pt(f"op.{value}", label), value)
        self.operation_combo.currentIndexChanged.connect(self._update_operation_ui)
        source_layout.addWidget(QLabel(self._pt("label.operation", "Operation")), 1, 0)
        source_layout.addWidget(self.operation_combo, 1, 1)

        self.advanced_checkbox = QCheckBox(self._pt("checkbox.advanced", "Advanced mode"))
        self.advanced_checkbox.toggled.connect(self._update_advanced_ui)
        source_layout.addWidget(self.advanced_checkbox, 1, 2)
        layout.addWidget(source_card)

        self.operation_stack = QStackedWidget()
        layout.addWidget(self.operation_stack)

        self._build_summarize_page()
        self._build_pivot_page()
        self._build_melt_page()
        self._build_transpose_page()
        self._build_merge_page()

        chart_card = QFrame()
        chart_card.setStyleSheet("QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }")
        chart_layout = QGridLayout(chart_card)
        chart_layout.setContentsMargins(16, 14, 16, 14)
        chart_layout.setHorizontalSpacing(10)
        chart_layout.setVerticalSpacing(10)

        self.chart_type_combo = QComboBox()
        for label, value in CHART_TYPES:
            self.chart_type_combo.addItem(self._pt(f"chart.{value}", label), value)
        chart_layout.addWidget(QLabel(self._pt("label.chart", "Chart")), 0, 0)
        chart_layout.addWidget(self.chart_type_combo, 0, 1)

        self.palette_combo = QComboBox()
        for key in PALETTES:
            self.palette_combo.addItem(key.title(), key)
        chart_layout.addWidget(QLabel(self._pt("label.palette", "Palette")), 0, 2)
        chart_layout.addWidget(self.palette_combo, 0, 3)

        self.x_axis_input = QLineEdit()
        self.x_axis_input.setPlaceholderText(self._pt("x_column.placeholder", "Optional X column"))
        chart_layout.addWidget(QLabel(self._pt("label.x_column", "X Column")), 1, 0)
        chart_layout.addWidget(self.x_axis_input, 1, 1)

        self.y_axis_input = QLineEdit()
        self.y_axis_input.setPlaceholderText(self._pt("y_columns.placeholder", "Optional Y column(s), comma-separated"))
        chart_layout.addWidget(QLabel(self._pt("label.y_columns", "Y Column(s)")), 1, 2)
        chart_layout.addWidget(self.y_axis_input, 1, 3)
        layout.addWidget(chart_card)

        self.advanced_card = QFrame()
        self.advanced_card.setStyleSheet("QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }")
        advanced_layout = QGridLayout(self.advanced_card)
        advanced_layout.setContentsMargins(16, 14, 16, 14)
        advanced_layout.setHorizontalSpacing(10)
        advanced_layout.setVerticalSpacing(10)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText(self._pt("filter.placeholder", "Optional pandas query filter, e.g. Status == 'Open'"))
        advanced_layout.addWidget(QLabel(self._pt("label.filter", "Filter")), 0, 0)
        advanced_layout.addWidget(self.filter_input, 0, 1, 1, 3)

        self.slice_input = QLineEdit()
        self.slice_input.setPlaceholderText(self._pt("slice.placeholder", "Optional slice, e.g. 0:100"))
        advanced_layout.addWidget(QLabel(self._pt("label.slice", "Slice")), 1, 0)
        advanced_layout.addWidget(self.slice_input, 1, 1)

        self.sort_input = QLineEdit()
        self.sort_input.setPlaceholderText(self._pt("sort.placeholder", "Optional sort column(s)"))
        advanced_layout.addWidget(QLabel(self._pt("label.sort", "Sort")), 1, 2)
        advanced_layout.addWidget(self.sort_input, 1, 3)

        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(0, 50000)
        self.top_n_spin.setValue(0)
        advanced_layout.addWidget(QLabel(self._pt("label.top_n", "Top N")), 2, 0)
        advanced_layout.addWidget(self.top_n_spin, 2, 1)

        self.sort_desc_checkbox = QCheckBox(self._pt("checkbox.sort_desc", "Sort descending"))
        advanced_layout.addWidget(self.sort_desc_checkbox, 2, 2, 1, 2)
        layout.addWidget(self.advanced_card)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton(self._pt("button.run", "Run Builder"))
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.export_xlsx_button = QPushButton(self._pt("button.export_xlsx", "Export XLSX"))
        self.export_xlsx_button.setEnabled(False)
        self.export_xlsx_button.clicked.connect(self._export_xlsx)
        controls.addWidget(self.export_xlsx_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.export_html_button = QPushButton(self._pt("button.export_html", "Export HTML"))
        self.export_html_button.setEnabled(False)
        self.export_html_button.clicked.connect(self._export_html)
        controls.addWidget(self.export_html_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.export_png_button = QPushButton(self._pt("button.export_png", "Export PNG"))
        self.export_png_button.setEnabled(False)
        self.export_png_button.clicked.connect(self._export_png)
        controls.addWidget(self.export_png_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.progress, 1)
        layout.addLayout(controls)

        summary_card = QFrame()
        summary_card.setStyleSheet("QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel(self._pt("summary.empty", "Configure the pipeline, then run the builder to preview a chart and result table."))
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(260)
        splitter.addWidget(self.chart_view)

        self.table = QTableView()
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        self._set_placeholder_chart(self._pt("preview.placeholder", "Chart preview will appear here."))
        self._update_operation_ui()
        self._update_advanced_ui()

    def _build_summarize_page(self) -> None:
        page = QWidget()
        form = QGridLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.group_input = QLineEdit()
        self.group_input.setPlaceholderText(self._pt("group_cols.placeholder", "Group columns, e.g. Department, Status"))
        form.addWidget(QLabel(self._pt("label.group_cols", "Group Columns")), 0, 0)
        form.addWidget(self.group_input, 0, 1)

        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText(self._pt("value_cols.placeholder", "Optional numeric value column(s)"))
        form.addWidget(QLabel(self._pt("label.value_cols", "Value Columns")), 1, 0)
        form.addWidget(self.value_input, 1, 1)

        self.agg_combo = QComboBox()
        for value in AGGREGATIONS:
            self.agg_combo.addItem(value.title(), value)
        form.addWidget(QLabel(self._pt("label.agg", "Aggregate")), 2, 0)
        form.addWidget(self.agg_combo, 2, 1)

        self.operation_stack.addWidget(page)

    def _build_pivot_page(self) -> None:
        page = QWidget()
        form = QGridLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.pivot_index_input = QLineEdit()
        self.pivot_index_input.setPlaceholderText(self._pt("pivot_index.placeholder", "Pivot index column(s)"))
        form.addWidget(QLabel(self._pt("label.pivot_index", "Index")), 0, 0)
        form.addWidget(self.pivot_index_input, 0, 1)

        self.pivot_columns_input = QLineEdit()
        self.pivot_columns_input.setPlaceholderText(self._pt("pivot_cols.placeholder", "Pivot column(s)"))
        form.addWidget(QLabel(self._pt("label.pivot_cols", "Columns")), 1, 0)
        form.addWidget(self.pivot_columns_input, 1, 1)

        self.pivot_values_input = QLineEdit()
        self.pivot_values_input.setPlaceholderText(self._pt("pivot_vals.placeholder", "Pivot value column(s)"))
        form.addWidget(QLabel(self._pt("label.pivot_vals", "Values")), 2, 0)
        form.addWidget(self.pivot_values_input, 2, 1)

        self.operation_stack.addWidget(page)

    def _build_melt_page(self) -> None:
        page = QWidget()
        form = QGridLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.melt_id_input = QLineEdit()
        self.melt_id_input.setPlaceholderText(self._pt("melt_id.placeholder", "Optional id column(s)"))
        form.addWidget(QLabel(self._pt("label.melt_id", "ID Vars")), 0, 0)
        form.addWidget(self.melt_id_input, 0, 1)

        self.melt_values_input = QLineEdit()
        self.melt_values_input.setPlaceholderText(self._pt("melt_vals.placeholder", "Value column(s) to melt"))
        form.addWidget(QLabel(self._pt("label.melt_vals", "Value Vars")), 1, 0)
        form.addWidget(self.melt_values_input, 1, 1)

        self.operation_stack.addWidget(page)

    def _build_transpose_page(self) -> None:
        page = QWidget()
        form = QGridLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.transpose_input = QLineEdit()
        self.transpose_input.setPlaceholderText(self._pt("transpose_cols.placeholder", "Optional columns to transpose"))
        form.addWidget(QLabel(self._pt("label.transpose_cols", "Columns")), 0, 0)
        form.addWidget(self.transpose_input, 0, 1)

        self.operation_stack.addWidget(page)

    def _build_merge_page(self) -> None:
        page = QWidget()
        form = QGridLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.secondary_input = QLineEdit()
        self.secondary_input.setPlaceholderText(self._pt("secondary.placeholder", "Select secondary Excel workbook..."))
        form.addWidget(QLabel(self._pt("label.secondary", "Secondary")), 0, 0)
        form.addWidget(self.secondary_input, 0, 1)
        secondary_browse = QPushButton(self._pt("button.browse_secondary", "Browse"))
        secondary_browse.clicked.connect(self._browse_secondary)
        form.addWidget(secondary_browse, 0, 2)

        self.join_left_input = QLineEdit()
        self.join_left_input.setPlaceholderText(self._pt("left_keys.placeholder", "Primary join column(s)"))
        form.addWidget(QLabel(self._pt("label.left_keys", "Left Keys")), 1, 0)
        form.addWidget(self.join_left_input, 1, 1, 1, 2)

        self.join_right_input = QLineEdit()
        self.join_right_input.setPlaceholderText(self._pt("right_keys.placeholder", "Optional secondary join column(s)"))
        form.addWidget(QLabel(self._pt("label.right_keys", "Right Keys")), 2, 0)
        form.addWidget(self.join_right_input, 2, 1, 1, 2)

        self.join_type_combo = QComboBox()
        for value in JOIN_TYPES:
            self.join_type_combo.addItem(value.title(), value)
        form.addWidget(QLabel(self._pt("label.join_type", "Join Type")), 3, 0)
        form.addWidget(self.join_type_combo, 3, 1)

        self.operation_stack.addWidget(page)

    def _current_operation(self) -> str:
        return self.operation_combo.currentData()

    def _update_operation_ui(self) -> None:
        self.operation_stack.setCurrentIndex(self.operation_combo.currentIndex())

    def _update_advanced_ui(self) -> None:
        self.advanced_card.setVisible(self.advanced_checkbox.isChecked())

    def _browse_primary(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._pt("dialog.browse.excel", "Select Excel Workbook"),
            str(self.services.default_output_path()),
            self._pt("dialog.browse.excel.filter", "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)"),
        )
        if file_path:
            self.primary_input.setText(file_path)

    def _browse_secondary(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._pt("dialog.browse.secondary", "Select Secondary Excel Workbook"),
            str(self.services.default_output_path()),
            self._pt("dialog.browse.excel.filter", "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)"),
        )
        if file_path:
            self.secondary_input.setText(file_path)

    def _build_config(self) -> dict[str, object]:
        config = {
            "operation": self._current_operation(),
            "group_columns": self.group_input.text().strip(),
            "value_columns": self.value_input.text().strip(),
            "aggregate": self.agg_combo.currentData(),
            "pivot_index": self.pivot_index_input.text().strip(),
            "pivot_columns": self.pivot_columns_input.text().strip(),
            "pivot_values": self.pivot_values_input.text().strip(),
            "melt_id": self.melt_id_input.text().strip(),
            "melt_values": self.melt_values_input.text().strip(),
            "transpose_columns": self.transpose_input.text().strip(),
            "secondary_file": self.secondary_input.text().strip(),
            "left_keys": self.join_left_input.text().strip(),
            "right_keys": self.join_right_input.text().strip(),
            "join_type": self.join_type_combo.currentData(),
            "chart_type": self.chart_type_combo.currentData(),
            "palette": self.palette_combo.currentData(),
            "x_column": self.x_axis_input.text().strip(),
            "y_columns": self.y_axis_input.text().strip(),
            "filter_expr": self.filter_input.text().strip(),
            "slice_expr": self.slice_input.text().strip(),
            "sort_by": self.sort_input.text().strip(),
            "sort_descending": self.sort_desc_checkbox.isChecked(),
            "top_n": self.top_n_spin.value(),
            "advanced": self.advanced_checkbox.isChecked(),
        }
        return config

    def _run(self) -> None:
        primary_file = self.primary_input.text().strip()
        if not primary_file:
            QMessageBox.warning(self, self._pt("dialog.error.title", "Missing Input"), self._pt("dialog.error.missing_primary", "Choose a primary workbook."))
            return

        config = self._build_config()
        operation = str(config["operation"])
        if operation == "summarize" and not config["group_columns"]:
            QMessageBox.warning(self, self._pt("dialog.error.title", "Missing Input"), self._pt("dialog.error.missing_group", "Enter at least one grouping column."))
            return
        if operation == "pivot" and (not config["pivot_index"] or not config["pivot_columns"] or not config["pivot_values"]):
            QMessageBox.warning(self, self._pt("dialog.error.title", "Missing Input"), self._pt("dialog.error.missing_pivot", "Enter pivot index, columns, and values."))
            return
        if operation == "melt" and not config["melt_values"]:
            QMessageBox.warning(self, self._pt("dialog.error.title", "Missing Input"), self._pt("dialog.error.missing_melt", "Enter at least one melt value column."))
            return
        if operation == "merge" and (not config["secondary_file"] or not config["left_keys"]):
            QMessageBox.warning(self, self._pt("dialog.error.title", "Missing Input"), self._pt("dialog.error.missing_merge", "Choose the secondary workbook and enter join keys."))
            return

        self.run_button.setEnabled(False)
        self.export_xlsx_button.setEnabled(False)
        self.export_html_button.setEnabled(False)
        self.export_png_button.setEnabled(False)
        self.progress.setValue(0)
        self.summary_label.setText(self._pt("summary.running", "Running chart builder..."))
        self.table.setModel(None)
        self._table_model = None
        self._latest_result = None
        self._set_placeholder_chart(self._pt("preview.building", "Building chart preview..."))

        self.services.run_task(
            lambda context: run_chart_builder_task(context, primary_file, config),
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
            self._pt(
                "summary.success",
                "{primary} processed with {operation} mode. Produced {row_count} result rows.",
                primary=result['primary_file'],
                operation=str(result['operation']).replace('_', ' '),
                row_count=result['row_count']
            )
        )
        self._refresh_chart_preview()
        self.export_xlsx_button.setEnabled(True)
        self.export_html_button.setEnabled(True)
        self.export_png_button.setEnabled(self.chart_type_combo.currentData() != "none")
        self.services.record_run(self.plugin_id, "SUCCESS", self._pt("log.task.success", "Built chart result for {primary}", primary=result['primary_file']))
        self.services.log(self._pt("log.task.complete", "Chart Builder complete for {primary}.", primary=result['primary_file']))

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self._pt("error.unknown", "Unknown chart builder error")) if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self._set_placeholder_chart(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self._pt("log.error", "Chart Builder failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _set_placeholder_chart(self, title: str) -> None:
        chart = QChart()
        chart.setTitle(title)
        chart.legend().hide()
        self.chart_view.setChart(chart)

    def _refresh_chart_preview(self) -> None:
        if not self._latest_result:
            self._set_placeholder_chart(self._pt("preview.placeholder", "Chart preview will appear here."))
            return
        chart_type = self.chart_type_combo.currentData()
        if chart_type == "none":
            self._set_placeholder_chart(self._pt("preview.disabled", "Chart preview disabled."))
            return
        chart = self._build_chart(self._latest_result["dataframe"])
        self.chart_view.setChart(chart)

    def _palette_colors(self) -> list[QColor]:
        palette_key = self.palette_combo.currentData() or "ocean"
        return [QColor(value) for value in PALETTES.get(palette_key, PALETTES["ocean"])]

    def _chart_columns(self, dataframe):
        numeric_columns = [column for column in dataframe.columns if getattr(dataframe[column], "dtype", None) is not None and str(dataframe[column].dtype) != "object"]
        x_column = self.x_axis_input.text().strip()
        if not x_column or x_column not in dataframe.columns:
            x_column = dataframe.columns[0] if len(dataframe.columns) > 0 else ""
        y_columns = parse_columns(self.y_axis_input.text().strip())
        y_columns = [column for column in y_columns if column in dataframe.columns]
        if not y_columns:
            y_columns = [column for column in numeric_columns if column != x_column]
        return x_column, y_columns

    def _build_chart(self, dataframe) -> QChart:
        colors = self._palette_colors()
        x_column, y_columns = self._chart_columns(dataframe)
        chart_type = self.chart_type_combo.currentData()
        chart = QChart()
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        chart.legend().setVisible(True)

        if dataframe.empty:
            chart.setTitle(self._pt("preview.error.nodata", "No data available for chart preview."))
            chart.legend().hide()
            return chart

        if chart_type in {"bar", "line"} and (not x_column or not y_columns):
            chart.setTitle(self._pt("preview.error.cols", "Choose chart columns or produce at least one numeric result column."))
            chart.legend().hide()
            return chart

        if chart_type in {"pie", "donut"}:
            if not x_column or not y_columns:
                chart.setTitle(self._pt("preview.error.pie", "Pie charts need one label column and one numeric value column."))
                chart.legend().hide()
                return chart
            series = QPieSeries()
            if chart_type == "donut":
                series.setHoleSize(0.42)
            subset = dataframe[[x_column, y_columns[0]]].head(12)
            for index, row in subset.iterrows():
                slice_ = series.append(str(row[x_column]), float(row[y_columns[0]]))
                slice_.setBrush(colors[index % len(colors)])
            chart.addSeries(series)
            chart.setTitle(f"{self._pt(f'chart.{chart_type}', chart_type.title())}: {x_column} vs {y_columns[0]}")
            return chart

        if chart_type == "scatter":
            if not y_columns:
                chart.setTitle(self._pt("preview.error.scatter", "Scatter charts need at least one numeric Y column."))
                chart.legend().hide()
                return chart
            x_values = dataframe[x_column] if x_column in dataframe.columns else dataframe.index
            try:
                numeric_x = [float(value) for value in x_values]
            except Exception:
                numeric_x = list(range(len(dataframe)))
            axis_x = QValueAxis()
            axis_y = QValueAxis()
            chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
            chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
            for index, column in enumerate(y_columns[:3]):
                series = QScatterSeries()
                series.setName(column)
                series.setMarkerSize(10.0)
                series.setColor(colors[index % len(colors)])
                for x_value, y_value in zip(numeric_x, dataframe[column]):
                    try:
                        series.append(float(x_value), float(y_value))
                    except Exception:
                        continue
                chart.addSeries(series)
                series.attachAxis(axis_x)
                series.attachAxis(axis_y)
            chart.setTitle(f"{self._pt('chart.scatter', 'Scatter')}: {', '.join(y_columns[:3])}")
            return chart

        if chart_type == "line":
            categories = [str(value) for value in dataframe[x_column].head(20)]
            axis_x = QBarCategoryAxis()
            axis_x.append(categories)
            axis_y = QValueAxis()
            chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
            chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
            for index, column in enumerate(y_columns[:4]):
                series = QLineSeries()
                series.setName(column)
                series.setColor(colors[index % len(colors)])
                for point_index, y_value in enumerate(dataframe[column].head(20)):
                    try:
                        series.append(point_index, float(y_value))
                    except Exception:
                        continue
                chart.addSeries(series)
                series.attachAxis(axis_x)
                series.attachAxis(axis_y)
            chart.setTitle(f"{self._pt('chart.line', 'Line')}: {', '.join(y_columns[:4])}")
            return chart

        series = QBarSeries()
        categories = [str(value) for value in dataframe[x_column].head(20)]
        for index, column in enumerate(y_columns[:4]):
            bar_set = QBarSet(column)
            bar_set.setColor(colors[index % len(colors)])
            for value in dataframe[column].head(20):
                try:
                    bar_set.append(float(value))
                except Exception:
                    bar_set.append(0.0)
            series.append(bar_set)
        chart.addSeries(series)
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_y = QValueAxis()
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        chart.setTitle(f"{self._pt('chart.bar', 'Bar')}: {', '.join(y_columns[:4])}")
        return chart

    def _export_xlsx(self) -> None:
        if not self._latest_result:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            self._pt("dialog.export.xlsx", "Export Result Workbook"),
            str(self.services.default_output_path() / "chart_builder.xlsx"),
            self._pt("dialog.export.xlsx.filter", "Excel Files (*.xlsx)"),
        )
        if not save_path:
            return
        self._latest_result["dataframe"].to_excel(save_path, index=False)
        self.services.log(self._pt("log.export.xlsx", "Chart Builder workbook exported to {path}.", path=save_path))

    def _chart_png_bytes(self) -> bytes:
        pixmap = self.chart_view.grab()
        if pixmap.isNull():
            return b""
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        buffer.close()
        return bytes(byte_array.data())

    def _export_png(self) -> None:
        if not self._latest_result:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            self._pt("dialog.export.png", "Export Chart Image"),
            str(self.services.default_output_path() / "chart_builder.png"),
            self._pt("dialog.export.png.filter", "PNG Files (*.png)"),
        )
        if not save_path:
            return
        pixmap = self.chart_view.grab()
        if pixmap.isNull():
            QMessageBox.warning(self, self._pt("dialog.export.failed.title", "Export Failed"), self._pt("dialog.export.failed.msg", "No chart preview is available to export."))
            return
        pixmap.save(save_path, "PNG")
        self.services.log(self._pt("log.export.png", "Chart Builder image exported to {path}.", path=save_path))

    def _export_html(self) -> None:
        if not self._latest_result:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            self._pt("dialog.export.html", "Export HTML Report"),
            str(self.services.default_output_path() / "chart_builder.html"),
            self._pt("dialog.export.html.filter", "HTML Files (*.html)"),
        )
        if not save_path:
            return
        dataframe = self._latest_result["dataframe"]
        chart_bytes = self._chart_png_bytes()
        chart_html = ""
        if chart_bytes:
            encoded = base64.b64encode(chart_bytes).decode("ascii")
            chart_html = f'<img alt="{self._pt("report.img_alt", "Chart Preview")}" src="data:image/png;base64,{encoded}" style="max-width: 100%; border-radius: 12px;" />'
        
        report_title = self._pt("report.title", "Chart Builder Report")
        source_label = self._pt("report.source", "Source workbook:")
        op_label = self._pt("report.operation", "Operation:")
        rows_label = self._pt("report.rows", "Rows:")
        preview_h2 = self._pt("report.h2.preview", "Chart Preview")
        table_h2 = self._pt("report.h2.table", "Result Table")
        no_chart_msg = self._pt("report.no_chart", "No chart image was generated for the current preview.")

        report = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{report_title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #10232c; background: #f8fafc; }}
    .card {{ background: white; border-radius: 16px; padding: 18px; margin-bottom: 18px; box-shadow: 0 8px 26px rgba(15, 23, 42, 0.08); }}
    h1, h2 {{ margin-top: 0; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 8px 10px; text-align: left; }}
    th {{ background: #eef4ff; }}
    .meta {{ color: #526370; font-size: 14px; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{report_title}</h1>
    <div class="meta">{source_label} {self._latest_result['primary_file']}</div>
    <div class="meta">{op_label} {str(self._latest_result['operation']).replace('_', ' ').title()}</div>
    <div class="meta">{rows_label} {self._latest_result['row_count']}</div>
  </div>
  <div class="card">
    <h2>{preview_h2}</h2>
    {chart_html or f'<div class="meta">{no_chart_msg}</div>'}
  </div>
  <div class="card">
    <h2>{table_h2}</h2>
    {dataframe.to_html(index=False, border=0)}
  </div>
</body>
</html>
"""
        with open(save_path, "w", encoding="utf-8") as handle:
            handle.write(report)
        self.services.log(self._pt("log.export.html", "Chart Builder HTML report exported to {path}.", path=save_path))
