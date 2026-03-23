from __future__ import annotations
from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QPieSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin
from micro_toolkit.core.page_style import card_style, muted_text_style, page_title_style, section_title_style


class WelcomeOverviewPlugin(QtPlugin):
    plugin_id = "welcome_overview"
    name = "Dashboard"
    description = "A live dashboard for your toolkit activity, system snapshot, and quick access shortcuts."
    category = "General"
    translations = {
        "en": {
            "plugin.name": "Dashboard",
            "plugin.description": "A live dashboard for your toolkit activity, system snapshot, and quick access shortcuts.",
        },
        "ar": {
            "plugin.name": "لوحة التحكم",
            "plugin.description": "لوحة حية لنشاط الأدوات ولمحة النظام واختصارات الوصول السريع.",
        },
    }

    def create_widget(self, services) -> QWidget:
        return DashboardPage(services, self.plugin_id)


class DashboardPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.quick_bar_layout: QHBoxLayout | None = None
        self.quick_access_list: QListWidget | None = None
        self.quick_access_combo: QComboBox | None = None
        self.hero_card: QFrame | None = None
        self.quick_access_card: QFrame | None = None
        self._build_ui()
        self._refresh()
        self.services.i18n.language_changed.connect(self._refresh)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self.services.quick_access_changed.connect(self._render_quick_access)
        self.services.plugin_visuals_changed.connect(self._handle_plugin_visuals_changed)

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(18)

        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(14)
        self.stats_grid.setVerticalSpacing(14)
        outer.addLayout(self.stats_grid)

        charts_row = QHBoxLayout()
        charts_row.setSpacing(14)
        self.top_tools_card = QFrame()
        top_tools_layout = QVBoxLayout(self.top_tools_card)
        top_tools_layout.setContentsMargins(18, 16, 18, 16)
        top_tools_layout.setSpacing(0)
        self.top_tools_chart = QChartView()
        self.top_tools_chart.setRenderHint(QPainter.RenderHint.Antialiasing)
        top_tools_layout.addWidget(self.top_tools_chart)
        charts_row.addWidget(self.top_tools_card, 2)

        self.status_card = QFrame()
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(18, 16, 18, 16)
        status_layout.setSpacing(0)
        self.status_chart = QChartView()
        self.status_chart.setRenderHint(QPainter.RenderHint.Antialiasing)
        status_layout.addWidget(self.status_chart)
        charts_row.addWidget(self.status_card, 1)
        outer.addLayout(charts_row, 1)

        self.quick_access_card = QFrame()
        quick_layout = QVBoxLayout(self.quick_access_card)
        quick_layout.setContentsMargins(20, 20, 20, 20)
        quick_layout.setSpacing(14)

        top_row = QHBoxLayout()
        self.quick_access_title = QLabel()
        self.quick_access_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        top_row.addWidget(self.quick_access_title)
        top_row.addStretch(1)
        quick_layout.addLayout(top_row)

        self.quick_bar_frame = QFrame()
        self.quick_bar_layout = QHBoxLayout(self.quick_bar_frame)
        self.quick_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_bar_layout.setSpacing(10)
        quick_layout.addWidget(self.quick_bar_frame)

        editor_row = QHBoxLayout()
        editor_row.setSpacing(14)

        self.quick_access_list = QListWidget()
        self.quick_access_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.quick_access_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.quick_access_list.model().rowsMoved.connect(self._persist_quick_access_from_list)
        editor_row.addWidget(self.quick_access_list, 1)

        editor_side = QVBoxLayout()
        editor_side.setSpacing(10)
        self.quick_access_combo = QComboBox()
        editor_side.addWidget(self.quick_access_combo)

        self.add_button = QPushButton()
        self.add_button.clicked.connect(self._add_selected_plugin)
        editor_side.addWidget(self.add_button)

        self.remove_button = QPushButton()
        self.remove_button.clicked.connect(self._remove_selected_plugin)
        editor_side.addWidget(self.remove_button)

        self.open_button = QPushButton()
        self.open_button.clicked.connect(self._open_selected_plugin)
        editor_side.addWidget(self.open_button)
        editor_side.addStretch(1)
        editor_row.addLayout(editor_side)
        quick_layout.addLayout(editor_row)

        outer.addWidget(self.quick_access_card, 1)

    def _refresh(self) -> None:
        self.quick_access_title.setText(self._pt("quick.title", "Quick Access"))
        self.add_button.setText(self._pt("quick.add", "Add to quick access"))
        self.remove_button.setText(self._pt("quick.remove", "Remove selected"))
        self.open_button.setText(self._pt("quick.open", "Open selected"))
        self._render_stats()
        self._render_charts()
        self._render_quick_access()
        self._apply_card_styles()

    def _handle_theme_change(self, _mode: str) -> None:
        self._refresh()

    def _handle_plugin_visuals_changed(self, _plugin_id: str) -> None:
        self._refresh()

    def _apply_card_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        for frame in (
            self.top_tools_card,
            self.status_card,
            self.quick_access_card,
        ):
            if frame is not None:
                frame.setStyleSheet(card_style(palette))
        self.quick_access_title.setStyleSheet(section_title_style(palette))

    def _render_stats(self) -> None:
        while self.stats_grid.count():
            item = self.stats_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        summary = self.services.session_manager.get_summary(days=7)
        total_tools = len(self.services.pinnable_plugin_specs())
        quick_count = len(self.services.quick_access_ids())
        workflow_count = len(self.services.workflow_manager.list_workflows())
        status_counts = summary.get("status_counts", {})
        success_count = int(status_counts.get("success", 0))

        cards = [
            (self._pt("stats.tools", "Available tools"), str(total_tools)),
            (self._pt("stats.quick", "Quick access"), str(quick_count)),
            (self._pt("stats.runs", "Tracked runs"), str(summary.get("total_runs", 0))),
            (self._pt("stats.success", "Successful runs"), str(success_count)),
            (self._pt("stats.workflows", "Saved workflows"), str(workflow_count)),
            (self._pt("stats.unique", "Tools used"), str(summary.get("unique_tools", 0))),
        ]

        for index, (label, value) in enumerate(cards):
            card = QFrame()
            palette = self.services.theme_manager.current_palette()
            card.setStyleSheet(card_style(palette))
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 16, 18, 16)
            card_layout.setSpacing(4)
            value_label = QLabel(value)
            value_label.setStyleSheet(page_title_style(palette, size=28, weight=700))
            card_layout.addWidget(value_label)
            text_label = QLabel(label)
            text_label.setStyleSheet(muted_text_style(palette, size=13))
            card_layout.addWidget(text_label)
            self.stats_grid.addWidget(card, index // 3, index % 3)

    def _render_charts(self) -> None:
        summary = self.services.session_manager.get_summary(days=7)
        self.top_tools_chart.setChart(self._build_top_tools_chart(summary.get("top_tools", [])))
        self.status_chart.setChart(self._build_status_chart(summary.get("status_counts", {})))

    def _build_top_tools_chart(self, rows) -> QChart:
        chart = QChart()
        chart.setTitle(self._pt("chart.top_tools", "Most used tools"))
        chart.legend().hide()

        categories = []
        values = []
        for row in rows or []:
            spec = self.services.plugin_manager.get_spec(str(row.get("tool_id")))
            label = self.services.plugin_display_name(spec) if spec is not None else str(row.get("tool_id"))
            categories.append(label)
            values.append(int(row.get("count", 0)))

        if not categories:
            categories = [self._pt("chart.none", "No data yet")]
            values = [0]

        series = QBarSeries()
        bar_set = QBarSet(self._pt("chart.runs", "Runs"))
        bar_set.append(values)
        series.append(bar_set)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%d")
        axis_y.setRange(0, max(values + [1]))
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        return chart

    def _build_status_chart(self, status_counts) -> QChart:
        chart = QChart()
        chart.setTitle(self._pt("chart.status", "Run outcomes"))
        series = QPieSeries()
        if not status_counts:
            series.append(self._pt("chart.none", "No data yet"), 1)
        else:
            for status, count in status_counts.items():
                series.append(str(status).title(), int(count))
        chart.addSeries(series)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        return chart

    def _render_quick_access(self) -> None:
        while self.quick_bar_layout.count():
            item = self.quick_bar_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        quick_ids = self.services.quick_access_ids()
        for plugin_id in quick_ids:
            spec = self.services.plugin_manager.get_spec(plugin_id)
            if spec is None:
                continue
            button = QToolButton()
            button.setText(self.services.plugin_display_name(spec))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setAutoRaise(True)
            button.clicked.connect(lambda _checked=False, pid=plugin_id: self._open_plugin(pid))
            self.quick_bar_layout.addWidget(button)
        self.quick_bar_layout.addStretch(1)

        self.quick_access_list.blockSignals(True)
        self.quick_access_list.clear()
        for plugin_id in quick_ids:
            spec = self.services.plugin_manager.get_spec(plugin_id)
            if spec is None:
                continue
            item = QListWidgetItem(self.services.plugin_display_name(spec))
            item.setData(Qt.ItemDataRole.UserRole, plugin_id)
            self.quick_access_list.addItem(item)
        self.quick_access_list.blockSignals(False)

        self.quick_access_combo.clear()
        pinned = set(quick_ids)
        for spec in self.services.pinnable_plugin_specs():
            if spec.plugin_id in pinned:
                continue
            self.quick_access_combo.addItem(self.services.plugin_display_name(spec), spec.plugin_id)

    def _persist_quick_access_from_list(self, *args) -> None:
        plugin_ids = []
        for row in range(self.quick_access_list.count()):
            item = self.quick_access_list.item(row)
            if item is not None:
                plugin_ids.append(str(item.data(Qt.ItemDataRole.UserRole)))
        self.services.set_quick_access_ids(plugin_ids)
        self._render_quick_access()

    def _add_selected_plugin(self) -> None:
        plugin_id = self.quick_access_combo.currentData()
        if not plugin_id:
            return
        updated = self.services.quick_access_ids() + [str(plugin_id)]
        self.services.set_quick_access_ids(updated)
        self._render_quick_access()

    def _remove_selected_plugin(self) -> None:
        item = self.quick_access_list.currentItem()
        if item is None:
            return
        plugin_id = str(item.data(Qt.ItemDataRole.UserRole))
        updated = [value for value in self.services.quick_access_ids() if value != plugin_id]
        self.services.set_quick_access_ids(updated)
        self._render_quick_access()

    def _open_selected_plugin(self) -> None:
        item = self.quick_access_list.currentItem()
        if item is None:
            return
        self._open_plugin(str(item.data(Qt.ItemDataRole.UserRole)))

    def _open_plugin(self, plugin_id: str) -> None:
        if self.services.main_window is not None:
            self.services.main_window.open_plugin(plugin_id)
