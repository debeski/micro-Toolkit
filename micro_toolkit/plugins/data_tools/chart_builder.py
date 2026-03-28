from __future__ import annotations

import base64
from io import BytesIO
import os

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QLineSeries, QPieSeries, QScatterSeries, QValueAxis
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QPainter, QPen
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
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin, bind_tr
from micro_toolkit.core.page_style import apply_page_chrome, apply_semantic_class
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
    category = "Data Utilities"

    def create_widget(self, services) -> QWidget:
        return ChartBuilderPage(services, self.plugin_id)


class ChartBuilderPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self._table_model = None
        self._latest_result = None
        self._has_run = False
        self._build_ui()
        self.services.i18n.language_changed.connect(self._handle_language_change)
        self.services.theme_manager.theme_changed.connect(self._apply_theme_styles)
        self._apply_texts()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        self.title_label = QLabel(self.tr("title", "Chart Builder"))
        layout.addWidget(self.title_label)

        self.description_label = QLabel(
            self.tr("description", "Build charts and analysis tables from Excel workbooks using a guided pipeline. "
            "Start simple with grouped summaries, or enable advanced controls for pivots, melts, joins, filters, slicing, and export workflows.")
        )
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        source_card = QFrame()
        self.source_card = source_card
        source_layout = QGridLayout(source_card)
        source_layout.setContentsMargins(16, 14, 16, 14)
        source_layout.setHorizontalSpacing(10)
        source_layout.setVerticalSpacing(10)

        self.primary_input = QLineEdit()
        self.primary_input.setPlaceholderText(self.tr("primary.placeholder", "Select primary Excel workbook..."))
        self.primary_label = QLabel(self.tr("label.primary", "Primary"))
        source_layout.addWidget(self.primary_label, 0, 0)
        source_layout.addWidget(self.primary_input, 0, 1)
        self.primary_browse_button = QPushButton(self.tr("button.browse_primary", "Browse"))
        self.primary_browse_button.clicked.connect(self._browse_primary)
        source_layout.addWidget(self.primary_browse_button, 0, 2)

        self.operation_combo = QComboBox()
        for label, value in OPERATIONS:
            self.operation_combo.addItem(self.tr(f"op.{value}", label), value)
        self.operation_combo.currentIndexChanged.connect(self._update_operation_ui)
        self.operation_label = QLabel(self.tr("label.operation", "Operation"))
        source_layout.addWidget(self.operation_label, 1, 0)
        source_layout.addWidget(self.operation_combo, 1, 1)

        self.advanced_checkbox = QCheckBox(self.tr("checkbox.advanced", "Advanced mode"))
        self.advanced_checkbox.toggled.connect(self._update_advanced_ui)
        source_layout.addWidget(self.advanced_checkbox, 1, 2)
        layout.addWidget(source_card)

        self.operation_card = QFrame()
        operation_layout = QVBoxLayout(self.operation_card)
        operation_layout.setContentsMargins(16, 14, 16, 14)
        operation_layout.setSpacing(0)

        self.operation_stack = QStackedWidget()
        apply_semantic_class(self.operation_stack, "transparent_class")
        operation_layout.addWidget(self.operation_stack)
        layout.addWidget(self.operation_card)

        self._build_summarize_page()
        self._build_pivot_page()
        self._build_melt_page()
        self._build_transpose_page()
        self._build_merge_page()
        for index in range(self.operation_stack.count()):
            page = self.operation_stack.widget(index)
            if page is not None:
                apply_semantic_class(page, "transparent_class")

        chart_card = QFrame()
        self.chart_card = chart_card
        chart_layout = QGridLayout(chart_card)
        chart_layout.setContentsMargins(16, 14, 16, 14)
        chart_layout.setHorizontalSpacing(10)
        chart_layout.setVerticalSpacing(10)

        self.chart_type_combo = QComboBox()
        for label, value in CHART_TYPES:
            self.chart_type_combo.addItem(self.tr(f"chart.{value}", label), value)
        self.chart_type_label = QLabel(self.tr("label.chart", "Chart"))
        chart_layout.addWidget(self.chart_type_label, 0, 0)
        chart_layout.addWidget(self.chart_type_combo, 0, 1)

        self.palette_combo = QComboBox()
        for key in PALETTES:
            self.palette_combo.addItem(key.title(), key)
        self.palette_label = QLabel(self.tr("label.palette", "Palette"))
        chart_layout.addWidget(self.palette_label, 0, 2)
        chart_layout.addWidget(self.palette_combo, 0, 3)

        self.x_axis_input = QLineEdit()
        self.x_axis_input.setPlaceholderText(self.tr("x_column.placeholder", "Optional X column"))
        self.x_axis_label = QLabel(self.tr("label.x_column", "X Column"))
        chart_layout.addWidget(self.x_axis_label, 1, 0)
        chart_layout.addWidget(self.x_axis_input, 1, 1)

        self.y_axis_input = QLineEdit()
        self.y_axis_input.setPlaceholderText(self.tr("y_columns.placeholder", "Optional Y column(s), comma-separated"))
        self.y_axis_label = QLabel(self.tr("label.y_columns", "Y Column(s)"))
        chart_layout.addWidget(self.y_axis_label, 1, 2)
        chart_layout.addWidget(self.y_axis_input, 1, 3)
        layout.addWidget(chart_card)

        self.advanced_card = QFrame()
        advanced_layout = QGridLayout(self.advanced_card)
        advanced_layout.setContentsMargins(16, 14, 16, 14)
        advanced_layout.setHorizontalSpacing(10)
        advanced_layout.setVerticalSpacing(10)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText(self.tr("filter.placeholder", "Optional pandas query filter, e.g. Status == 'Open'"))
        self.filter_label = QLabel(self.tr("label.filter", "Filter"))
        advanced_layout.addWidget(self.filter_label, 0, 0)
        advanced_layout.addWidget(self.filter_input, 0, 1, 1, 3)

        self.slice_input = QLineEdit()
        self.slice_input.setPlaceholderText(self.tr("slice.placeholder", "Optional slice, e.g. 0:100"))
        self.slice_label = QLabel(self.tr("label.slice", "Slice"))
        advanced_layout.addWidget(self.slice_label, 1, 0)
        advanced_layout.addWidget(self.slice_input, 1, 1)

        self.sort_input = QLineEdit()
        self.sort_input.setPlaceholderText(self.tr("sort.placeholder", "Optional sort column(s)"))
        self.sort_label = QLabel(self.tr("label.sort", "Sort"))
        advanced_layout.addWidget(self.sort_label, 1, 2)
        advanced_layout.addWidget(self.sort_input, 1, 3)

        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(0, 50000)
        self.top_n_spin.setValue(0)
        self.top_n_label = QLabel(self.tr("label.top_n", "Top N"))
        advanced_layout.addWidget(self.top_n_label, 2, 0)
        advanced_layout.addWidget(self.top_n_spin, 2, 1)

        self.sort_desc_checkbox = QCheckBox(self.tr("checkbox.sort_desc", "Sort descending"))
        advanced_layout.addWidget(self.sort_desc_checkbox, 2, 2, 1, 2)
        layout.addWidget(self.advanced_card)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton(self.tr("button.run", "Run Builder"))
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.export_xlsx_button = QPushButton(self.tr("button.export_xlsx", "Export XLSX"))
        self.export_xlsx_button.setEnabled(False)
        self.export_xlsx_button.clicked.connect(self._export_xlsx)
        controls.addWidget(self.export_xlsx_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.export_html_button = QPushButton(self.tr("button.export_html", "Export HTML"))
        self.export_html_button.setEnabled(False)
        self.export_html_button.clicked.connect(self._export_html)
        controls.addWidget(self.export_html_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.export_png_button = QPushButton(self.tr("button.export_png", "Export PNG"))
        self.export_png_button.setEnabled(False)
        self.export_png_button.clicked.connect(self._export_png)
        controls.addWidget(self.export_png_button, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addLayout(controls)

        summary_card = QFrame()
        self.summary_card = summary_card
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel(self.tr("summary.empty", "Configure the pipeline, then run the builder to preview a chart and result table."))
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.chart_view = QChartView()
        apply_semantic_class(self.chart_view, "chart_class")
        self.chart_view.setFrameShape(QFrame.Shape.NoFrame)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(260)
        viewport = self.chart_view.viewport()
        if viewport is not None:
            apply_semantic_class(viewport, "chart_class")
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

        self._set_placeholder_chart(self.tr("preview.placeholder", "Chart preview will appear here."))
        self._update_operation_ui()
        self._update_advanced_ui()

    def _apply_theme_styles(self, *_args) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.source_card, self.operation_card, self.chart_card, self.advanced_card, self.summary_card),
            summary_label=self.summary_label,
            title_size=26,
            title_weight=800,
            description_size=14,
            card_radius=14,
        )
        chart = self.chart_view.chart()
        if chart is not None:
            self._configure_chart_theme(chart)

    def _build_summarize_page(self) -> None:
        page = QWidget()
        form = QGridLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.group_input = QLineEdit()
        self.group_input.setPlaceholderText(self.tr("group_cols.placeholder", "Group columns, e.g. Department, Status"))
        self.group_label = QLabel(self.tr("label.group_cols", "Group Columns"))
        form.addWidget(self.group_label, 0, 0)
        form.addWidget(self.group_input, 0, 1)

        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText(self.tr("value_cols.placeholder", "Optional numeric value column(s)"))
        self.value_label = QLabel(self.tr("label.value_cols", "Value Columns"))
        form.addWidget(self.value_label, 1, 0)
        form.addWidget(self.value_input, 1, 1)

        self.agg_combo = QComboBox()
        for value in AGGREGATIONS:
            self.agg_combo.addItem(value.title(), value)
        self.agg_label = QLabel(self.tr("label.agg", "Aggregate"))
        form.addWidget(self.agg_label, 2, 0)
        form.addWidget(self.agg_combo, 2, 1)

        self.operation_stack.addWidget(page)

    def _build_pivot_page(self) -> None:
        page = QWidget()
        form = QGridLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.pivot_index_input = QLineEdit()
        self.pivot_index_input.setPlaceholderText(self.tr("pivot_index.placeholder", "Pivot index column(s)"))
        self.pivot_index_label = QLabel(self.tr("label.pivot_index", "Index"))
        form.addWidget(self.pivot_index_label, 0, 0)
        form.addWidget(self.pivot_index_input, 0, 1)

        self.pivot_columns_input = QLineEdit()
        self.pivot_columns_input.setPlaceholderText(self.tr("pivot_cols.placeholder", "Pivot column(s)"))
        self.pivot_columns_label = QLabel(self.tr("label.pivot_cols", "Columns"))
        form.addWidget(self.pivot_columns_label, 1, 0)
        form.addWidget(self.pivot_columns_input, 1, 1)

        self.pivot_values_input = QLineEdit()
        self.pivot_values_input.setPlaceholderText(self.tr("pivot_vals.placeholder", "Pivot value column(s)"))
        self.pivot_values_label = QLabel(self.tr("label.pivot_vals", "Values"))
        form.addWidget(self.pivot_values_label, 2, 0)
        form.addWidget(self.pivot_values_input, 2, 1)

        self.operation_stack.addWidget(page)

    def _build_melt_page(self) -> None:
        page = QWidget()
        form = QGridLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.melt_id_input = QLineEdit()
        self.melt_id_input.setPlaceholderText(self.tr("melt_id.placeholder", "Optional id column(s)"))
        self.melt_id_label = QLabel(self.tr("label.melt_id", "ID Vars"))
        form.addWidget(self.melt_id_label, 0, 0)
        form.addWidget(self.melt_id_input, 0, 1)

        self.melt_values_input = QLineEdit()
        self.melt_values_input.setPlaceholderText(self.tr("melt_vals.placeholder", "Value column(s) to melt"))
        self.melt_values_label = QLabel(self.tr("label.melt_vals", "Value Vars"))
        form.addWidget(self.melt_values_label, 1, 0)
        form.addWidget(self.melt_values_input, 1, 1)

        self.operation_stack.addWidget(page)

    def _build_transpose_page(self) -> None:
        page = QWidget()
        form = QGridLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.transpose_input = QLineEdit()
        self.transpose_input.setPlaceholderText(self.tr("transpose_cols.placeholder", "Optional columns to transpose"))
        self.transpose_label = QLabel(self.tr("label.transpose_cols", "Columns"))
        form.addWidget(self.transpose_label, 0, 0)
        form.addWidget(self.transpose_input, 0, 1)

        self.operation_stack.addWidget(page)

    def _build_merge_page(self) -> None:
        page = QWidget()
        form = QGridLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.secondary_input = QLineEdit()
        self.secondary_input.setPlaceholderText(self.tr("secondary.placeholder", "Select secondary Excel workbook..."))
        self.secondary_label = QLabel(self.tr("label.secondary", "Secondary"))
        form.addWidget(self.secondary_label, 0, 0)
        form.addWidget(self.secondary_input, 0, 1)
        self.secondary_browse_button = QPushButton(self.tr("button.browse_secondary", "Browse"))
        self.secondary_browse_button.clicked.connect(self._browse_secondary)
        form.addWidget(self.secondary_browse_button, 0, 2)

        self.join_left_input = QLineEdit()
        self.join_left_input.setPlaceholderText(self.tr("left_keys.placeholder", "Primary join column(s)"))
        self.join_left_label = QLabel(self.tr("label.left_keys", "Left Keys"))
        form.addWidget(self.join_left_label, 1, 0)
        form.addWidget(self.join_left_input, 1, 1, 1, 2)

        self.join_right_input = QLineEdit()
        self.join_right_input.setPlaceholderText(self.tr("right_keys.placeholder", "Optional secondary join column(s)"))
        self.join_right_label = QLabel(self.tr("label.right_keys", "Right Keys"))
        form.addWidget(self.join_right_label, 2, 0)
        form.addWidget(self.join_right_input, 2, 1, 1, 2)

        self.join_type_combo = QComboBox()
        for value in JOIN_TYPES:
            self.join_type_combo.addItem(value.title(), value)
        self.join_type_label = QLabel(self.tr("label.join_type", "Join Type"))
        form.addWidget(self.join_type_label, 3, 0)
        form.addWidget(self.join_type_combo, 3, 1)

        self.operation_stack.addWidget(page)

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
        self.title_label.setText(self.tr("title", "Chart Builder"))
        self.description_label.setText(
            self.tr(
                "description",
                "Build charts and analysis tables from Excel workbooks using a guided pipeline. Start simple with grouped summaries, or enable advanced controls for pivots, melts, joins, filters, slicing, and export workflows.",
            )
        )
        self.primary_label.setText(self.tr("label.primary", "Primary"))
        self.primary_input.setPlaceholderText(self.tr("primary.placeholder", "Select primary Excel workbook..."))
        self.primary_browse_button.setText(self.tr("button.browse_primary", "Browse"))
        self.operation_label.setText(self.tr("label.operation", "Operation"))
        self._set_combo_items(
            self.operation_combo,
            [(self.tr(f"op.{value}", label), value) for label, value in OPERATIONS],
        )
        self.advanced_checkbox.setText(self.tr("checkbox.advanced", "Advanced mode"))
        self.chart_type_label.setText(self.tr("label.chart", "Chart"))
        self._set_combo_items(
            self.chart_type_combo,
            [(self.tr(f"chart.{value}", label), value) for label, value in CHART_TYPES],
        )
        self.palette_label.setText(self.tr("label.palette", "Palette"))
        self.x_axis_label.setText(self.tr("label.x_column", "X Column"))
        self.x_axis_input.setPlaceholderText(self.tr("x_column.placeholder", "Optional X column"))
        self.y_axis_label.setText(self.tr("label.y_columns", "Y Column(s)"))
        self.y_axis_input.setPlaceholderText(self.tr("y_columns.placeholder", "Optional Y column(s), comma-separated"))
        self.filter_label.setText(self.tr("label.filter", "Filter"))
        self.filter_input.setPlaceholderText(self.tr("filter.placeholder", "Optional pandas query filter, e.g. Status == 'Open'"))
        self.slice_label.setText(self.tr("label.slice", "Slice"))
        self.slice_input.setPlaceholderText(self.tr("slice.placeholder", "Optional slice, e.g. 0:100"))
        self.sort_label.setText(self.tr("label.sort", "Sort"))
        self.sort_input.setPlaceholderText(self.tr("sort.placeholder", "Optional sort column(s)"))
        self.top_n_label.setText(self.tr("label.top_n", "Top N"))
        self.sort_desc_checkbox.setText(self.tr("checkbox.sort_desc", "Sort descending"))
        self.run_button.setText(self.tr("button.run", "Run Builder"))
        self.export_xlsx_button.setText(self.tr("button.export_xlsx", "Export XLSX"))
        self.export_html_button.setText(self.tr("button.export_html", "Export HTML"))
        self.export_png_button.setText(self.tr("button.export_png", "Export PNG"))
        self.group_label.setText(self.tr("label.group_cols", "Group Columns"))
        self.group_input.setPlaceholderText(self.tr("group_cols.placeholder", "Group columns, e.g. Department, Status"))
        self.value_label.setText(self.tr("label.value_cols", "Value Columns"))
        self.value_input.setPlaceholderText(self.tr("value_cols.placeholder", "Optional numeric value column(s)"))
        self.agg_label.setText(self.tr("label.agg", "Aggregate"))
        self._set_combo_items(self.agg_combo, [(value.title(), value) for value in AGGREGATIONS])
        self.pivot_index_label.setText(self.tr("label.pivot_index", "Index"))
        self.pivot_index_input.setPlaceholderText(self.tr("pivot_index.placeholder", "Pivot index column(s)"))
        self.pivot_columns_label.setText(self.tr("label.pivot_cols", "Columns"))
        self.pivot_columns_input.setPlaceholderText(self.tr("pivot_cols.placeholder", "Pivot column(s)"))
        self.pivot_values_label.setText(self.tr("label.pivot_vals", "Values"))
        self.pivot_values_input.setPlaceholderText(self.tr("pivot_vals.placeholder", "Pivot value column(s)"))
        self.melt_id_label.setText(self.tr("label.melt_id", "ID Vars"))
        self.melt_id_input.setPlaceholderText(self.tr("melt_id.placeholder", "Optional id column(s)"))
        self.melt_values_label.setText(self.tr("label.melt_vals", "Value Vars"))
        self.melt_values_input.setPlaceholderText(self.tr("melt_vals.placeholder", "Value column(s) to melt"))
        self.transpose_label.setText(self.tr("label.transpose_cols", "Columns"))
        self.transpose_input.setPlaceholderText(self.tr("transpose_cols.placeholder", "Optional columns to transpose"))
        self.secondary_label.setText(self.tr("label.secondary", "Secondary"))
        self.secondary_input.setPlaceholderText(self.tr("secondary.placeholder", "Select secondary Excel workbook..."))
        self.secondary_browse_button.setText(self.tr("button.browse_secondary", "Browse"))
        self.join_left_label.setText(self.tr("label.left_keys", "Left Keys"))
        self.join_left_input.setPlaceholderText(self.tr("left_keys.placeholder", "Primary join column(s)"))
        self.join_right_label.setText(self.tr("label.right_keys", "Right Keys"))
        self.join_right_input.setPlaceholderText(self.tr("right_keys.placeholder", "Optional secondary join column(s)"))
        self.join_type_label.setText(self.tr("label.join_type", "Join Type"))
        self._set_combo_items(self.join_type_combo, [(value.title(), value) for value in JOIN_TYPES])
        self._update_operation_ui()
        self._update_advanced_ui()
        if self._latest_result is not None:
            self._render_result_payload(self._latest_result)
        elif not self._has_run:
            self.summary_label.setText(self.tr("summary.empty", "Configure the pipeline, then run the builder to preview a chart and result table."))
            self._set_placeholder_chart(self.tr("preview.placeholder", "Chart preview will appear here."))
        self._apply_theme_styles()

    def _handle_language_change(self) -> None:
        self._apply_texts()

    def _current_operation(self) -> str:
        return self.operation_combo.currentData()

    def _update_operation_ui(self) -> None:
        self.operation_stack.setCurrentIndex(self.operation_combo.currentIndex())

    def _update_advanced_ui(self) -> None:
        self.advanced_card.setVisible(self.advanced_checkbox.isChecked())

    def _browse_primary(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("dialog.browse.excel", "Select Excel Workbook"),
            str(self.services.default_output_path()),
            self.tr("dialog.browse.excel.filter", "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)"),
        )
        if file_path:
            self.primary_input.setText(file_path)

    def _browse_secondary(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("dialog.browse.secondary", "Select Secondary Excel Workbook"),
            str(self.services.default_output_path()),
            self.tr("dialog.browse.excel.filter", "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)"),
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
            QMessageBox.warning(self, self.tr("dialog.error.title", "Missing Input"), self.tr("dialog.error.missing_primary", "Choose a primary workbook."))
            return

        config = self._build_config()
        operation = str(config["operation"])
        if operation == "summarize" and not config["group_columns"]:
            QMessageBox.warning(self, self.tr("dialog.error.title", "Missing Input"), self.tr("dialog.error.missing_group", "Enter at least one grouping column."))
            return
        if operation == "pivot" and (not config["pivot_index"] or not config["pivot_columns"] or not config["pivot_values"]):
            QMessageBox.warning(self, self.tr("dialog.error.title", "Missing Input"), self.tr("dialog.error.missing_pivot", "Enter pivot index, columns, and values."))
            return
        if operation == "melt" and not config["melt_values"]:
            QMessageBox.warning(self, self.tr("dialog.error.title", "Missing Input"), self.tr("dialog.error.missing_melt", "Enter at least one melt value column."))
            return
        if operation == "merge" and (not config["secondary_file"] or not config["left_keys"]):
            QMessageBox.warning(self, self.tr("dialog.error.title", "Missing Input"), self.tr("dialog.error.missing_merge", "Choose the secondary workbook and enter join keys."))
            return

        self.run_button.setEnabled(False)
        self.export_xlsx_button.setEnabled(False)
        self.export_html_button.setEnabled(False)
        self.export_png_button.setEnabled(False)
        self.summary_label.setText(self.tr("summary.running", "Running chart builder..."))
        self.table.setModel(None)
        self._table_model = None
        self._latest_result = None
        self._set_placeholder_chart(self.tr("preview.building", "Building chart preview..."))

        self.services.run_task(
            lambda context: run_chart_builder_task(context, primary_file, config),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._has_run = True
        self._latest_result = result
        self._render_result_payload(result)
        self.services.record_run(self.plugin_id, "SUCCESS", self.tr("log.task.success", "Built chart result for {primary}", primary=result['primary_file']))
        self.services.log(self.tr("log.task.complete", "Chart Builder complete for {primary}.", primary=result['primary_file']))

    def _handle_error(self, payload: object) -> None:
        self._has_run = True
        self._latest_result = None
        message = payload.get("message", self.tr("error.unknown", "Unknown chart builder error")) if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self._set_placeholder_chart(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.error", "Chart Builder failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _render_result_payload(self, result: dict[str, object]) -> None:
        dataframe = result["dataframe"]
        self._table_model = DataFrameTableModel(dataframe)
        self.table.setModel(self._table_model)
        self.summary_label.setText(
            self.tr(
                "summary.success",
                "{primary} processed with {operation} mode. Produced {row_count} result rows.",
                primary=result["primary_file"],
                operation=str(result["operation"]).replace("_", " "),
                row_count=result["row_count"],
            )
        )
        self._refresh_chart_preview()
        self.export_xlsx_button.setEnabled(True)
        self.export_html_button.setEnabled(True)
        self.export_png_button.setEnabled(self.chart_type_combo.currentData() != "none")

    def _set_placeholder_chart(self, title: str) -> None:
        chart = QChart()
        chart.setTitle(title)
        chart.legend().hide()
        self._configure_chart_theme(chart)
        self.chart_view.setChart(chart)

    def _refresh_chart_preview(self) -> None:
        if not self._latest_result:
            self._set_placeholder_chart(self.tr("preview.placeholder", "Chart preview will appear here."))
            return
        chart_type = self.chart_type_combo.currentData()
        if chart_type == "none":
            self._set_placeholder_chart(self.tr("preview.disabled", "Chart preview disabled."))
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
            chart.setTitle(self.tr("preview.error.nodata", "No data available for chart preview."))
            chart.legend().hide()
            self._configure_chart_theme(chart)
            return chart

        if chart_type in {"bar", "line"} and (not x_column or not y_columns):
            chart.setTitle(self.tr("preview.error.cols", "Choose chart columns or produce at least one numeric result column."))
            chart.legend().hide()
            return chart

        if chart_type in {"pie", "donut"}:
            if not x_column or not y_columns:
                chart.setTitle(self.tr("preview.error.pie", "Pie charts need one label column and one numeric value column."))
                chart.legend().hide()
                self._configure_chart_theme(chart)
                return chart
            series = QPieSeries()
            if chart_type == "donut":
                series.setHoleSize(0.42)
            subset = dataframe[[x_column, y_columns[0]]].head(12)
            for index, row in subset.iterrows():
                slice_ = series.append(str(row[x_column]), float(row[y_columns[0]]))
                slice_.setBrush(colors[index % len(colors)])
            chart.addSeries(series)
            chart.setTitle(f"{self.tr(f'chart.{chart_type}', chart_type.title())}: {x_column} vs {y_columns[0]}")
            self._configure_chart_theme(chart)
            return chart

        if chart_type == "scatter":
            if not y_columns:
                chart.setTitle(self.tr("preview.error.scatter", "Scatter charts need at least one numeric Y column."))
                chart.legend().hide()
                self._configure_chart_theme(chart)
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
            chart.setTitle(f"{self.tr('chart.scatter', 'Scatter')}: {', '.join(y_columns[:3])}")
            self._configure_chart_theme(chart)
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
            chart.setTitle(f"{self.tr('chart.line', 'Line')}: {', '.join(y_columns[:4])}")
            self._configure_chart_theme(chart)
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
        chart.setTitle(f"{self.tr('chart.bar', 'Bar')}: {', '.join(y_columns[:4])}")
        self._configure_chart_theme(chart)
        return chart

    def _configure_chart_theme(self, chart: QChart) -> None:
        palette = self.services.theme_manager.current_palette()
        border = QColor(palette.border)
        text = QColor(palette.text_primary)
        surface = QColor(palette.surface_bg)
        plot_surface = QColor(palette.window_bg)
        chart.setBackgroundVisible(True)
        chart.setBackgroundBrush(surface)
        chart.setBackgroundPen(QPen(border))
        chart.setPlotAreaBackgroundVisible(True)
        chart.setPlotAreaBackgroundBrush(plot_surface)
        chart.setPlotAreaBackgroundPen(QPen(border))
        chart.setTitleBrush(text)
        chart.legend().setLabelColor(text)
        for axis in chart.axes():
            try:
                axis.setLabelsColor(text)
            except Exception:
                pass
            try:
                axis.setTitleBrush(text)
            except Exception:
                pass
            try:
                axis.setGridLineColor(border)
            except Exception:
                pass
            try:
                axis.setLinePen(QPen(border))
            except Exception:
                pass

    def _export_xlsx(self) -> None:
        if not self._latest_result:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("dialog.export.xlsx", "Export Result Workbook"),
            str(self.services.default_output_path() / "chart_builder.xlsx"),
            self.tr("dialog.export.xlsx.filter", "Excel Files (*.xlsx)"),
        )
        if not save_path:
            return
        self._latest_result["dataframe"].to_excel(save_path, index=False)
        self.services.log(self.tr("log.export.xlsx", "Chart Builder workbook exported to {path}.", path=save_path))

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
            self.tr("dialog.export.png", "Export Chart Image"),
            str(self.services.default_output_path() / "chart_builder.png"),
            self.tr("dialog.export.png.filter", "PNG Files (*.png)"),
        )
        if not save_path:
            return
        pixmap = self.chart_view.grab()
        if pixmap.isNull():
            QMessageBox.warning(self, self.tr("dialog.export.failed.title", "Export Failed"), self.tr("dialog.export.failed.msg", "No chart preview is available to export."))
            return
        pixmap.save(save_path, "PNG")
        self.services.log(self.tr("log.export.png", "Chart Builder image exported to {path}.", path=save_path))

    def _export_html(self) -> None:
        if not self._latest_result:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("dialog.export.html", "Export HTML Report"),
            str(self.services.default_output_path() / "chart_builder.html"),
            self.tr("dialog.export.html.filter", "HTML Files (*.html)"),
        )
        if not save_path:
            return
        dataframe = self._latest_result["dataframe"]
        chart_bytes = self._chart_png_bytes()
        chart_html = ""
        if chart_bytes:
            encoded = base64.b64encode(chart_bytes).decode("ascii")
            chart_html = f'<img alt="{self.tr("report.img_alt", "Chart Preview")}" src="data:image/png;base64,{encoded}" style="max-width: 100%; border-radius: 12px;" />'
        
        report_title = self.tr("report.title", "Chart Builder Report")
        source_label = self.tr("report.source", "Source workbook:")
        op_label = self.tr("report.operation", "Operation:")
        rows_label = self.tr("report.rows", "Rows:")
        preview_h2 = self.tr("report.h2.preview", "Chart Preview")
        table_h2 = self.tr("report.h2.table", "Result Table")
        no_chart_msg = self.tr("report.no_chart", "No chart image was generated for the current preview.")

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
        self.services.log(self.tr("log.export.html", "Chart Builder HTML report exported to {path}.", path=save_path))
