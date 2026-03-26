from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QPieSeries, QValueAxis
from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.icon_registry import icon_from_name
from micro_toolkit.core.page_style import (
    body_text_style,
    card_style,
    muted_text_style,
    section_title_style,
    tinted_card_style,
)
from micro_toolkit.core.plugin_api import QtPlugin
from micro_toolkit.core.widgets import width_breakpoint


def _mix_hex(first: str, second: str, ratio: float) -> str:
    first_color = QColor(first)
    second_color = QColor(second)
    if not first_color.isValid() or not second_color.isValid():
        return first
    ratio = max(0.0, min(1.0, float(ratio)))
    red = round((first_color.red() * (1.0 - ratio)) + (second_color.red() * ratio))
    green = round((first_color.green() * (1.0 - ratio)) + (second_color.green() * ratio))
    blue = round((first_color.blue() * (1.0 - ratio)) + (second_color.blue() * ratio))
    return QColor(red, green, blue).name()


class WelcomeOverviewPlugin(QtPlugin):
    plugin_id = "welcome_overview"
    name = "Dashboard"
    description = "A live dashboard for toolkit activity, health signals, and useful next actions."
    category = "General"
    translations = {
        "en": {
            "plugin.name": "Dashboard",
            "plugin.description": "A live dashboard for toolkit activity, health signals, and useful next actions.",
        },
        "ar": {
            "plugin.name": "لوحة التحكم",
            "plugin.description": "لوحة حية لنشاط الأدوات وإشارات الحالة والإجراءات المفيدة التالية.",
        },
    }

    def create_widget(self, services) -> QWidget:
        return DashboardPage(services, self.plugin_id)


class DashboardPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.hero_card: QFrame | None = None
        self.hero_stats_grid = None
        self.hero_side_panel: QFrame | None = None
        self.workspace_card: QFrame | None = None
        self.activity_card: QFrame | None = None
        self.top_tools_card: QFrame | None = None
        self.status_card: QFrame | None = None
        self.hero_eyebrow: QLabel | None = None
        self.hero_title: QLabel | None = None
        self.hero_body: QLabel | None = None
        self.workspace_title: QLabel | None = None
        self.workspace_note: QLabel | None = None
        self.workspace_stack: QVBoxLayout | None = None
        self.activity_title: QLabel | None = None
        self.activity_stack: QVBoxLayout | None = None
        self.top_tools_chart = QChartView()
        self.status_chart = QChartView()
        self._responsive_bucket = ""
        self._workspace_action_buttons: list[QPushButton] = []
        self._build_ui()
        self._refresh()
        self.services.i18n.language_changed.connect(self._refresh)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _plugin_name(self, plugin_id: str, fallback: str) -> str:
        spec = self.services.plugin_manager.get_spec(plugin_id)
        if spec is not None:
            return self.services.plugin_display_name(spec)
        return fallback

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(18)

        self.hero_card = QFrame()
        self.hero_card.setObjectName("DashboardWelcomeCard")
        self.hero_layout = QHBoxLayout(self.hero_card)
        self.hero_layout.setContentsMargins(26, 24, 26, 24)
        self.hero_layout.setSpacing(20)

        hero_left = QVBoxLayout()
        hero_left.setSpacing(10)
        self.hero_eyebrow = QLabel()
        self.hero_title = QLabel()
        self.hero_title.setWordWrap(True)
        self.hero_body = QLabel()
        self.hero_body.setWordWrap(True)
        hero_left.addWidget(self.hero_eyebrow)
        hero_left.addWidget(self.hero_title)
        hero_left.addWidget(self.hero_body)

        self.hero_stats_grid = QGridLayout()
        self.hero_stats_grid.setContentsMargins(0, 8, 0, 0)
        self.hero_stats_grid.setHorizontalSpacing(12)
        self.hero_stats_grid.setVerticalSpacing(12)
        hero_left.addLayout(self.hero_stats_grid)
        self.hero_layout.addLayout(hero_left, 1)
        outer.addWidget(self.hero_card)

        self.operational_row = QHBoxLayout()
        self.operational_row.setSpacing(14)

        self.workspace_card = QFrame()
        workspace_layout = QVBoxLayout(self.workspace_card)
        workspace_layout.setContentsMargins(20, 20, 20, 20)
        workspace_layout.setSpacing(14)

        self.workspace_title = QLabel()
        workspace_layout.addWidget(self.workspace_title)
        self.workspace_note = QLabel()
        self.workspace_note.setWordWrap(True)
        workspace_layout.addWidget(self.workspace_note)

        workspace_stack_host = QFrame()
        self.workspace_stack = QVBoxLayout(workspace_stack_host)
        self.workspace_stack.setContentsMargins(0, 0, 0, 0)
        self.workspace_stack.setSpacing(10)
        workspace_layout.addWidget(workspace_stack_host, 1)

        self.workspace_actions = QGridLayout()
        self.workspace_actions.setContentsMargins(0, 4, 0, 0)
        self.workspace_actions.setHorizontalSpacing(8)
        self.workspace_actions.setVerticalSpacing(8)
        self._workspace_action_buttons = [
            self._make_dashboard_action_button(
                self._plugin_name("clip_manager", "Clipboard"),
                "clipboard",
                lambda: self._open_plugin("clip_manager"),
            ),
            self._make_dashboard_action_button(
                self._plugin_name("workflow_studio", "Workflows"),
                "workflow",
                lambda: self._open_plugin("workflow_studio"),
            ),
            self._make_dashboard_action_button(
                self._plugin_name("settings_center", "Settings"),
                "settings",
                self._open_settings,
            ),
            self._make_dashboard_action_button(
                self._pt("workspace.action.plugins", "Plugins"),
                "inspect",
                self._open_plugins,
            ),
        ]
        workspace_layout.addLayout(self.workspace_actions)
        self.operational_row.addWidget(self.workspace_card, 3)

        self.activity_card = QFrame()
        activity_layout = QVBoxLayout(self.activity_card)
        activity_layout.setContentsMargins(20, 20, 20, 20)
        activity_layout.setSpacing(14)
        self.activity_title = QLabel()
        activity_layout.addWidget(self.activity_title)
        activity_stack_host = QFrame()
        self.activity_stack = QVBoxLayout(activity_stack_host)
        self.activity_stack.setContentsMargins(0, 0, 0, 0)
        self.activity_stack.setSpacing(12)
        activity_layout.addWidget(activity_stack_host, 1)
        self.operational_row.addWidget(self.activity_card, 3)
        outer.addLayout(self.operational_row, 1)

        self.analytics_row = QHBoxLayout()
        self.analytics_row.setSpacing(14)

        self.top_tools_card = QFrame()
        top_tools_layout = QVBoxLayout(self.top_tools_card)
        top_tools_layout.setContentsMargins(18, 16, 18, 16)
        top_tools_layout.setSpacing(10)
        self.top_tools_title = QLabel()
        top_tools_layout.addWidget(self.top_tools_title)
        self.top_tools_chart.setRenderHint(QPainter.RenderHint.Antialiasing)
        top_tools_layout.addWidget(self.top_tools_chart)
        self.analytics_row.addWidget(self.top_tools_card, 2)

        self.status_card = QFrame()
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(18, 16, 18, 16)
        status_layout.setSpacing(10)
        self.status_title = QLabel()
        status_layout.addWidget(self.status_title)
        self.status_chart.setRenderHint(QPainter.RenderHint.Antialiasing)
        status_layout.addWidget(self.status_chart)
        self.analytics_row.addWidget(self.status_card, 1)

        outer.addLayout(self.analytics_row, 1)
        self._apply_responsive_layout(force=True)

    def _refresh(self) -> None:
        greeting, date_text = self._welcome_texts()
        self.hero_eyebrow.setText(self._pt("hero.eyebrow", "Welcome back"))
        self.hero_title.setText(greeting)
        self.hero_body.setText(date_text)
        self.workspace_title.setText(self._pt("workspace.title", "Workspace pulse"))
        self.workspace_note.setText(
            self._pt(
                "workspace.note",
                "A quick read on backups, shortcuts, workflows, and your output desk so you can decide what needs attention next.",
            )
        )
        self.activity_title.setText(self._pt("activity.title", "Recent activity"))
        self.top_tools_title.setText(self._pt("chart.top_tools", "Most used tools"))
        self.status_title.setText(self._pt("chart.status", "Run outcomes"))
        self._render_hero_stats()
        self._render_charts()
        self._render_workspace_pulse()
        self._render_recent_activity()
        self._apply_card_styles()
        self._apply_responsive_layout()

    def _handle_theme_change(self, _mode: str) -> None:
        self._refresh()

    def _apply_card_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        for frame in (
            self.hero_card,
            self.hero_side_panel,
            self.workspace_card,
            self.activity_card,
            self.top_tools_card,
            self.status_card,
        ):
            if frame is not None:
                frame.setStyleSheet(card_style(palette, radius=16))
        self.hero_card.setStyleSheet(self._hero_card_style())
        if self.hero_side_panel is not None:
            self.hero_side_panel.setStyleSheet(
                card_style(palette, radius=16)
                + f"QFrame#DashboardHeroPanel {{ background: {palette.surface_bg}; }}"
            )
        eyebrow_color, title_color, body_color = self._hero_text_colors()
        self.hero_eyebrow.setStyleSheet(
            f"color: {eyebrow_color}; font-size: 12px; font-weight: 700; text-transform: uppercase;"
        )
        self.hero_title.setStyleSheet(f"color: {title_color}; font-size: 34px; font-weight: 800;")
        self.hero_body.setStyleSheet(f"color: {body_color}; font-size: 15px; font-weight: 500;")
        if self.workspace_note is not None:
            self.workspace_note.setStyleSheet(muted_text_style(palette, size=13))
        if self.workspace_card is not None:
            for button in self.workspace_card.findChildren(QPushButton, "DashboardActionButton"):
                button.setStyleSheet(
                    f"""
                    QPushButton#DashboardActionButton {{
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 {palette.surface_bg},
                            stop:1 {palette.surface_alt_bg});
                        color: {palette.text_primary};
                        border: 1px solid {palette.border};
                        border-radius: 14px;
                        padding: 10px 12px;
                        font-size: 13px;
                        font-weight: 700;
                        text-align: left;
                    }}
                    QPushButton#DashboardActionButton:hover {{
                        border-color: {palette.accent};
                        background: {palette.accent_soft};
                    }}
                    """
                )
            for button in self.workspace_card.findChildren(QPushButton, "DashboardInlineButton"):
                button.setStyleSheet(
                    f"""
                    QPushButton#DashboardInlineButton {{
                        background: transparent;
                        color: {palette.accent};
                        border: 1px solid {palette.border};
                        border-radius: 999px;
                        padding: 6px 10px;
                        font-size: 12px;
                        font-weight: 700;
                    }}
                    QPushButton#DashboardInlineButton:hover {{
                        background: {palette.accent_soft};
                        border-color: {palette.accent};
                    }}
                    """
                )
        for label in (self.workspace_title, self.activity_title, self.top_tools_title, self.status_title):
            label.setStyleSheet(section_title_style(palette, size=20))

    def _welcome_texts(self) -> tuple[str, str]:
        now = datetime.now()
        hour = now.hour
        if hour < 12:
            greeting = self._pt("hero.greeting.morning", "Good morning")
        elif hour < 18:
            greeting = self._pt("hero.greeting.afternoon", "Good afternoon")
        else:
            greeting = self._pt("hero.greeting.evening", "Good evening")
        
        locale = QLocale(self.services.i18n.current_language())
        date_text = self._ensure_western_numerals(locale.toString(now, QLocale.FormatType.LongFormat))
        return greeting, date_text

    def _hero_text_colors(self) -> tuple[str, str, str]:
        palette = self.services.theme_manager.current_palette()
        if palette.mode == "dark":
            return ("rgba(255, 255, 255, 0.82)", "#ffffff", "rgba(255, 255, 255, 0.90)")
        return ("rgba(20, 33, 49, 0.70)", "#142131", "rgba(20, 33, 49, 0.84)")

    def _render_hero_stats(self) -> None:
        while self.hero_stats_grid.count():
            item = self.hero_stats_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        summary = self.services.session_manager.get_summary(days=7)
        top_tools = summary.get("top_tools", [])
        top_tool_name = self._pt("hero.none", "No activity yet")
        if top_tools:
            top_tool_id = str(top_tools[0].get("tool_id", "")).strip()
            spec = self.services.plugin_manager.get_spec(top_tool_id)
            if spec is not None:
                top_tool_name = self.services.plugin_display_name(spec)
            elif top_tool_id:
                top_tool_name = top_tool_id
        available_plugins = len(self.services.manageable_plugin_specs())
        output_path = self.services.default_output_path()
        output_name = output_path.name or str(output_path)
        shortcut_count = len(self.services.shortcut_manager.list_bindings())
        workflow_count = len(self.services.workflow_manager.list_workflows())
        success_count = int((summary.get("status_counts") or {}).get("success", 0))
        stats = [
            (self._pt("hero.stat.available", "Available Plugins"), str(available_plugins)),
            (self._pt("hero.stat.output", "Output desk"), output_name),
            (self._pt("hero.stat.shortcuts", "Shortcuts"), str(shortcut_count)),
            (self._pt("hero.stat.workflows", "Workflows"), str(workflow_count)),
            (self._pt("hero.stat.success", "Successful runs"), str(success_count)),
            (self._pt("hero.stat.most_used", "Most used tool"), top_tool_name),
        ]
        palette = self.services.theme_manager.current_palette()
        stat_bg = "rgba(255, 255, 255, 0.10)" if palette.mode == "dark" else "rgba(255, 255, 255, 0.42)"
        stat_value_color = "#ffffff" if palette.mode == "dark" else palette.text_primary
        stat_label_color = "rgba(255, 255, 255, 0.76)" if palette.mode == "dark" else "rgba(20, 33, 49, 0.64)"
        columns = {"wide": 3, "medium": 2, "compact": 1}.get(self._responsive_bucket or "wide", 3)
        for index, (label, value) in enumerate(stats):
            card = QFrame()
            card.setStyleSheet(
                f"background: {stat_bg};"
                "border: none;"
                "border-radius: 12px;"
            )
            layout = QVBoxLayout(card)
            layout.setContentsMargins(14, 9, 14, 9)
            layout.setSpacing(4)
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setStyleSheet(
                f"color: {stat_value_color}; font-size: {'13px' if index == 5 else '15px'}; font-weight: 700;"
            )
            text_label = QLabel(label)
            text_label.setStyleSheet(f"color: {stat_label_color}; font-size: 11px; font-weight: 600;")
            layout.addWidget(value_label)
            layout.addWidget(text_label)
            self.hero_stats_grid.addWidget(card, index // columns, index % columns)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self, *, force: bool = False) -> None:
        bucket = width_breakpoint(self.width(), compact_max=620, medium_max=1120)
        if not force and bucket == self._responsive_bucket:
            if self.hero_stats_grid.count():
                self._render_hero_stats()
            return
        self._responsive_bucket = bucket
        compact = bucket == "compact"

        self.operational_row.setDirection(
            QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        )
        self.analytics_row.setDirection(
            QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        )
        while self.workspace_actions.count():
            item = self.workspace_actions.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self.workspace_card)
        columns = 1 if compact else 2
        for index, button in enumerate(self._workspace_action_buttons):
            self.workspace_actions.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.workspace_actions.setColumnStretch(column, 1)
        if self.hero_stats_grid.count():
            self._render_hero_stats()

    def _render_charts(self) -> None:
        summary = self.services.session_manager.get_summary(days=7)
        self.top_tools_chart.setChart(self._build_top_tools_chart(summary.get("top_tools", [])))
        self.status_chart.setChart(self._build_status_chart(summary.get("status_counts", {})))

    def _build_top_tools_chart(self, rows) -> QChart:
        palette = self.services.theme_manager.current_palette()
        chart = QChart()
        chart.legend().hide()
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.setMargins(type(chart.margins())(0, 0, 0, 0))

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
        bar_set.setColor(QColor(palette.accent))
        bar_set.append(values)
        series.append(bar_set)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsColor(QColor(palette.text_muted))
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%d")
        axis_y.setRange(0, max(values + [1]))
        axis_y.setLabelsColor(QColor(palette.text_muted))
        grid_pen = axis_y.gridLinePen()
        grid_pen.setColor(QColor(palette.border))
        axis_y.setGridLinePen(grid_pen)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        return chart

    def _build_status_chart(self, status_counts) -> QChart:
        palette = self.services.theme_manager.current_palette()
        chart = QChart()
        chart.setBackgroundVisible(False)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        chart.legend().setColor(QColor(palette.text_muted))

        series = QPieSeries()
        if not status_counts:
            slice_obj = series.append(self._pt("chart.none", "No data yet"), 1)
            slice_obj.setColor(QColor(palette.accent_soft))
        else:
            status_colors = {
                "success": QColor("#4caf7a"),
                "warning": QColor("#f0b84a"),
                "error": QColor(palette.danger),
                "failed": QColor(palette.danger),
            }
            for status, count in status_counts.items():
                status_text = self._pt(f"activity.status.{str(status).lower()}", str(status).title())
                slice_obj = series.append(status_text, int(count))
                slice_obj.setColor(status_colors.get(str(status).lower(), QColor(palette.accent)))
        chart.addSeries(series)
        return chart

    def _render_workspace_pulse(self) -> None:
        while self.workspace_stack.count():
            item = self.workspace_stack.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        output_path = self.services.default_output_path()
        output_count = self._safe_dir_item_count(output_path)
        output_meta = self._pt(
            "workspace.output.meta",
            "{count} item(s) are currently sitting in the default export folder.",
            count=str(output_count),
        )
        self.workspace_stack.addWidget(
            self._build_workspace_row(
                self._pt("workspace.output.title", "Output desk"),
                str(output_path),
                output_meta,
                self._pt("workspace.output.action", "Settings"),
                self._open_settings,
            )
        )

        last_backup = self.services.backup_manager.last_backup_at()
        backup_due = self.services.backup_manager.backup_due()
        backup_value = self._pt("workspace.backup.value.due", "Backup due") if backup_due else self._pt("workspace.backup.value.ready", "On schedule")
        
        schedule_key = self.services.backup_manager.schedule().lower()
        # Using settings_center prefix for backup schedules to reuse translations if possible, 
        # but welcome plugin has its own _pt which uses welcome.ar.json. 
        # I'll add backup.schedule.* to welcome.ar.json as well for consistency.
        schedule_text = self._pt(f"backup.schedule.{schedule_key}", schedule_key.title())

        if last_backup:
            backup_meta = self._pt(
                "workspace.backup.meta.last",
                "{schedule} cadence. Last backup: {timestamp}.",
                schedule=schedule_text,
                timestamp=self._format_iso_timestamp(last_backup),
            )
        else:
            backup_meta = self._pt(
                "workspace.backup.meta.none",
                "{schedule} cadence. No encrypted backup has been created yet.",
                schedule=schedule_text,
            )
        self.workspace_stack.addWidget(
            self._build_workspace_row(
                self._pt("workspace.backup.title", "Backups"),
                backup_value,
                backup_meta,
                self._pt("workspace.backup.action", "Create backup"),
                self._create_dashboard_backup,
            )
        )

        workflow_count = len(self.services.workflow_manager.list_workflows())
        workflow_meta = (
            self._pt("workspace.workflows.meta.none", "You do not have any saved workflows yet.")
            if workflow_count == 0
            else self._pt("workspace.workflows.meta.some", "Automation sequences are ready for repeat jobs and handoffs.")
        )
        self.workspace_stack.addWidget(
            self._build_workspace_row(
                self._pt("workspace.workflows.title", "Automation"),
                self._pt("workspace.workflows.value", "{count} workflow(s)", count=str(workflow_count)),
                workflow_meta,
                self._pt("workspace.workflows.action", "Open workflows"),
                lambda: self._open_plugin("workflow_studio"),
            )
        )

        global_bindings = self.services.shortcut_manager.global_binding_sequences()
        helper_active = self.services.hotkey_helper_manager.is_active()
        shortcut_value = (
            self._pt("workspace.shortcuts.value.active", "Helper active")
            if helper_active
            else self._pt("workspace.shortcuts.value.local", "App focused")
        )
        shortcut_meta = self._pt(
            "workspace.shortcuts.meta",
            "{count} global binding(s) configured. Use Shortcuts to adjust helper access.",
            count=str(len(global_bindings)),
        )
        self.workspace_stack.addWidget(
            self._build_workspace_row(
                self._pt("workspace.shortcuts.title", "Shortcuts"),
                shortcut_value,
                shortcut_meta,
                self._pt("workspace.shortcuts.action", "Settings"),
                self._open_settings,
            )
        )
        self.workspace_stack.addStretch(1)
        self._apply_card_styles()

    def _render_recent_activity(self) -> None:
        while self.activity_stack.count():
            item = self.activity_stack.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        palette = self.services.theme_manager.current_palette()
        history = self.services.session_manager.get_history(limit=5)
        if not history:
            empty_text = self._pt("activity.none", "No tool activity has been logged yet.")
            empty = QLabel(empty_text)
            empty.setWordWrap(True)
            empty.setStyleSheet(muted_text_style(palette, size=14))
            self.activity_stack.addWidget(empty)
            self.activity_stack.addStretch(1)
            return

        for _id, tool_id, status, timestamp, details in history:
            spec = self.services.plugin_manager.get_spec(str(tool_id))
            title = self.services.plugin_display_name(spec) if spec is not None else str(tool_id)
            entry = QFrame()
            entry.setStyleSheet(card_style(palette, radius=14))
            layout = QVBoxLayout(entry)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(6)

            top = QHBoxLayout()
            label = QLabel(title)
            label.setStyleSheet(section_title_style(palette, size=17))
            top.addWidget(label)
            top.addStretch(1)
            
            status_text = self._pt(f"activity.status.{str(status).lower()}", str(status).title())
            status_label = QLabel(status_text)
            status_label.setStyleSheet(self._status_badge_style(str(status)))
            top.addWidget(status_label)
            layout.addLayout(top)

            when = QLabel(self._format_timestamp(timestamp))
            when.setStyleSheet(muted_text_style(palette, size=12))
            layout.addWidget(when)

            if details:
                detail_label = QLabel(str(details))
                detail_label.setWordWrap(True)
                detail_label.setStyleSheet(muted_text_style(palette, size=13))
                layout.addWidget(detail_label)
            self.activity_stack.addWidget(entry)
        self.activity_stack.addStretch(1)

    def _status_badge_style(self, status: str) -> str:
        palette = self.services.theme_manager.current_palette()
        status_lower = status.lower()
        if status_lower == "success":
            background = "#d9f2e2" if palette.mode == "light" else "#1f4732"
            foreground = "#23633f" if palette.mode == "light" else "#9ee0b2"
        elif status_lower in {"failed", "error"}:
            background = "#f9dfdb" if palette.mode == "light" else "#4e2522"
            foreground = palette.danger
        else:
            background = palette.accent_soft
            foreground = palette.accent
        return (
            "padding: 4px 10px; border-radius: 999px; "
            f"background: {background}; color: {foreground}; font-size: 12px; font-weight: 700;"
        )

    def _open_plugin(self, plugin_id: str) -> None:
        if self.services.main_window is not None:
            self.services.main_window.open_plugin(plugin_id)

    def _make_dashboard_action_button(self, text: str, icon_name: str, handler) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("DashboardActionButton")
        icon = icon_from_name(icon_name, self)
        if icon is not None:
            button.setIcon(icon)
        button.clicked.connect(handler)
        return button

    def _build_workspace_row(self, title: str, value: str, meta: str, action_text: str, action_handler) -> QFrame:
        palette = self.services.theme_manager.current_palette()
        row = QFrame()
        row.setStyleSheet(tinted_card_style(palette, background=palette.surface_alt_bg, radius=14))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        text_column = QVBoxLayout()
        text_column.setSpacing(4)
        title_label = QLabel(title)
        title_label.setStyleSheet(section_title_style(palette, size=16))
        value_label = QLabel(value)
        value_label.setWordWrap(True)
        value_label.setStyleSheet(body_text_style(palette, size=14))
        meta_label = QLabel(meta)
        meta_label.setWordWrap(True)
        meta_label.setStyleSheet(muted_text_style(palette, size=12))
        text_column.addWidget(title_label)
        text_column.addWidget(value_label)
        text_column.addWidget(meta_label)
        layout.addLayout(text_column, 1)

        action_button = QPushButton(action_text)
        action_button.setObjectName("DashboardInlineButton")
        action_button.clicked.connect(action_handler)
        layout.addWidget(action_button, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _format_timestamp(self, timestamp) -> str:
        try:
            dt = datetime.fromtimestamp(float(timestamp))
            return self._ensure_western_numerals(QLocale(self.services.i18n.current_language()).toString(dt, QLocale.FormatType.ShortFormat))
        except Exception:
            return str(timestamp)
    
    def _format_iso_timestamp(self, timestamp: str) -> str:
        try:
            dt = datetime.fromisoformat(timestamp)
            return self._ensure_western_numerals(QLocale(self.services.i18n.current_language()).toString(dt, QLocale.FormatType.ShortFormat))
        except Exception:
            return timestamp

    def _ensure_western_numerals(self, text: str) -> str:
        eastern_numerals = "٠١٢٣٤٥٦٧٨٩"
        western_numerals = "0123456789"
        trans = str.maketrans(eastern_numerals, western_numerals)
        return text.translate(trans)

    def _safe_dir_item_count(self, path: Path) -> int:
        try:
            return sum(1 for _ in path.iterdir())
        except Exception:
            return 0

    def _create_dashboard_backup(self) -> None:
        try:
            backup_path = self.services.create_backup(reason="dashboard")
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._pt("workspace.backup.failed.title", "Backup failed"),
                str(exc),
            )
            return
        QMessageBox.information(
            self,
            self._pt("workspace.backup.done.title", "Backup created"),
            self._pt("workspace.backup.done.body", "Created encrypted backup at:\n{path}", path=str(backup_path)),
        )
        self._refresh()

    def _open_settings(self) -> None:
        main_window = self.services.main_window
        if main_window is not None:
            main_window.open_settings_center()

    def _open_plugins(self) -> None:
        main_window = self.services.main_window
        if main_window is not None:
            main_window.open_plugin_manager()

    def _hero_card_style(self) -> str:
        palette = self.services.theme_manager.current_palette()
        if palette.mode == "dark":
            start = _mix_hex(palette.surface_bg, palette.accent, 0.32)
            middle = _mix_hex(palette.surface_alt_bg, palette.accent, 0.52)
            end = _mix_hex(palette.accent, "#ffffff", 0.12)
        else:
            start = _mix_hex(palette.surface_bg, palette.accent_soft, 0.62)
            middle = _mix_hex(palette.surface_alt_bg, palette.accent, 0.2)
            end = _mix_hex(palette.accent_soft, palette.accent, 0.42)
        gradient = (
            "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {start}, stop:0.56 {middle}, stop:1 {end})"
        )
        return (
            "QFrame#DashboardWelcomeCard {"
            f"background: {gradient};"
            f"border: 1px solid {_mix_hex(palette.border, palette.accent, 0.28)};"
            "border-radius: 16px;"
            "}"
        )
