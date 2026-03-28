from __future__ import annotations

import platform
from datetime import datetime
from pathlib import Path

import psutil
from PySide6.QtCharts import QChart, QChartView, QPieSeries
from PySide6.QtCore import QMargins, QTimer, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin, bind_tr, safe_tr
from micro_toolkit.core.page_style import apply_page_chrome, muted_text_style, page_title_style, section_title_style

def collect_system_audit_payload(*, translate=None) -> dict[str, object]:
    root_disk_path = Path.home().anchor or "/"
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(root_disk_path)

    cpu_freq = psutil.cpu_freq()
    net_io = psutil.net_io_counters()
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    return {
        "system": f"{platform.system()} {platform.release()}",
        "hostname": platform.node(),
        "architecture": platform.machine(),
        "processor": platform.processor() or platform.machine() or safe_tr(translate, "status.unknown", "Unknown"),
        "physical_cpus": psutil.cpu_count(logical=False) or 0,
        "logical_cpus": psutil.cpu_count(logical=True) or 0,
        "cpu_frequency_mhz": round(cpu_freq.current, 0) if cpu_freq is not None else None,
        "memory_total_gb": round(memory.total / (1024**3), 2),
        "memory_available_gb": round(memory.available / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_used_pct": float(disk.percent),
        "python_version": platform.python_version(),
        "booted_at": boot_time.strftime("%Y-%m-%d %H:%M"),
        "uptime_hours": round((datetime.now() - boot_time).total_seconds() / 3600, 1),
        "network_sent_gb": round(net_io.bytes_sent / (1024**3), 2),
        "network_recv_gb": round(net_io.bytes_recv / (1024**3), 2),
        "battery_pct": None if battery is None else float(battery.percent),
        "battery_plugged": None if battery is None else bool(battery.power_plugged),
    }


def gather_system_audit(context, *, translate=None) -> dict[str, object]:
    translate = translate or getattr(context, "translate", None)
    context.log(safe_tr(translate, "log.start", "Collecting system overview details..."))
    context.progress(0.12)
    context.progress(0.42)
    payload = collect_system_audit_payload(translate=translate)
    context.progress(1.0)
    context.log(safe_tr(translate, "log.done", "System overview audit complete."))
    return payload


class SystemAuditPlugin(QtPlugin):
    plugin_id = "sys_audit"
    name = "System Overview"
    description = "Monitor live CPU, memory, and disk activity alongside local hardware and runtime details."
    category = "IT Utilities"
    preferred_icon = "computer"

    def create_widget(self, services) -> QWidget:
        return SystemAuditPage(services, self.metadata().plugin_id)


class MetricDonut(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self._title = title
        self.title_label = QLabel(title)
        self.value_label = QLabel("--")
        self.caption_label = QLabel("")
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setFixedHeight(122)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        layout.addWidget(self.title_label)
        layout.addWidget(self.chart_view, 0, Qt.AlignmentFlag.AlignCenter)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value_label)
        self.caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption_label.setWordWrap(True)
        layout.addWidget(self.caption_label)
        layout.addStretch(1)

    def set_title(self, title: str) -> None:
        self._title = title
        self.title_label.setText(title)

    def set_metric(self, percent: float, *, caption: str, accent: str, remainder: str) -> None:
        percent = max(0.0, min(100.0, float(percent)))
        self.value_label.setText(f"{percent:.0f}%")
        self.caption_label.setText(caption)
        self.chart_view.setChart(self._build_chart(percent, accent, remainder))

    def _build_chart(self, percent: float, accent: str, remainder: str) -> QChart:
        series = QPieSeries()
        series.setHoleSize(0.68)
        used = series.append(self._title, percent)
        free = series.append("Remaining", max(0.0, 100.0 - percent))
        used.setColor(QColor(accent))
        used.setBorderColor(QColor(accent))
        free.setColor(QColor(remainder))
        free.setBorderColor(QColor(remainder))
        used.setLabelVisible(False)
        free.setLabelVisible(False)

        chart = QChart()
        chart.addSeries(series)
        chart.legend().hide()
        chart.setBackgroundVisible(False)
        chart.setMargins(QMargins(0, 0, 0, 0))
        return chart


class SystemAuditPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self._audit_payload: dict[str, object] = {}
        self._audit_running = False
        self._timer = QTimer(self)
        self._timer.setInterval(2500)
        self._timer.timeout.connect(self._refresh_live_metrics)
        psutil.cpu_percent(interval=None)
        self._build_ui()
        self._apply_texts()
        self._apply_theme_styles()
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self.services.i18n.language_changed.connect(self._handle_language_change)
        self._run_audit()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(18)

        self.hero_card = QFrame()
        hero_layout = QVBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(20, 20, 20, 20)
        hero_layout.setSpacing(8)

        self.title_label = QLabel()
        hero_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel()
        self.subtitle_label.setWordWrap(True)
        hero_layout.addWidget(self.subtitle_label)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self._run_audit)
        controls.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.timestamp_label = QLabel("--")
        controls.addWidget(self.timestamp_label, 0, Qt.AlignmentFlag.AlignVCenter)
        controls.addStretch(1)

        hero_layout.addLayout(controls)
        layout.addWidget(self.hero_card)

        self.metric_grid = QGridLayout()
        self.metric_grid.setHorizontalSpacing(14)
        self.metric_grid.setVerticalSpacing(14)
        layout.addLayout(self.metric_grid)

        self.cpu_donut = MetricDonut("")
        self.memory_donut = MetricDonut("")
        self.disk_donut = MetricDonut("")
        self.metric_grid.addWidget(self.cpu_donut, 0, 0)
        self.metric_grid.addWidget(self.memory_donut, 0, 1)
        self.metric_grid.addWidget(self.disk_donut, 0, 2)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self.profile_card = self._make_detail_card("")
        self.runtime_card = self._make_detail_card("")
        self.health_card = self._make_detail_card("")
        cards_row.addWidget(self.profile_card, 1)
        cards_row.addWidget(self.runtime_card, 1)
        cards_row.addWidget(self.health_card, 1)
        layout.addLayout(cards_row)

        self.details_card = QFrame()
        details_layout = QVBoxLayout(self.details_card)
        details_layout.setContentsMargins(18, 16, 18, 16)
        details_layout.setSpacing(10)
        self.details_heading = QLabel()
        details_layout.addWidget(self.details_heading)

        self.details_table = QTableWidget(0, 2)
        self.details_table.setAlternatingRowColors(True)
        self.details_table.verticalHeader().setVisible(False)
        self.details_table.horizontalHeader().setStretchLastSection(True)
        self.details_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.details_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        details_layout.addWidget(self.details_table, 1)
        layout.addWidget(self.details_card, 1)

    def _make_detail_card(self, heading: str) -> QFrame:
        card = QFrame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        title = QLabel(heading)
        body = QLabel("")
        body.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addStretch(1)
        card._title_label = title
        card._body_label = body
        return card

    def _run_audit(self) -> None:
        if self._audit_running:
            return
        self._audit_running = True
        self._timer.stop()
        self.refresh_button.setEnabled(False)
        self.services.log(self.tr("log.refresh", "Refreshing system overview."))
        self.services.run_task(
            lambda context: gather_system_audit(context, translate=self.tr),
            on_result=self._handle_audit_result,
            on_error=self._handle_audit_error,
            on_finished=self._finish_audit_refresh,
            status_text=self.tr("log.refresh", "Refreshing system overview."),
        )

    def _handle_audit_result(self, payload: object) -> None:
        self._audit_payload = dict(payload) if isinstance(payload, dict) else {}
        self._apply_audit_payload()
        self._refresh_live_metrics()
        self.services.record_run(self.plugin_id, "SUCCESS", "Updated system overview")
        self.services.log(self.tr("log.success", "System overview refreshed successfully."))

    def _handle_audit_error(self, payload: object) -> None:
        message = payload.get("message", self.tr("log.failed", "System overview refresh failed.")) if isinstance(payload, dict) else str(payload)
        self.timestamp_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "System overview refresh failed."), "ERROR")

    def _finish_audit_refresh(self) -> None:
        self._audit_running = False
        self.refresh_button.setEnabled(True)
        self._timer.start()

    def _apply_audit_payload(self) -> None:
        data = self._audit_payload
        self._set_detail_card(
            self.profile_card,
            self.tr("card.hardware.title", "Hardware"),
            [
                (self.tr("card.hardware.host", "Host"), data.get("hostname", "--")),
                (self.tr("card.hardware.proc", "Processor"), data.get("processor", "--")),
                (self.tr("card.hardware.arch", "Architecture"), data.get("architecture", "--")),
                (
                    self.tr("card.hardware.cores", "Cores"),
                    self.tr(
                        "card.hardware.cores_val",
                        "{physical} physical / {logical} logical",
                        physical=data.get("physical_cpus", 0),
                        logical=data.get("logical_cpus", 0),
                    ),
                ),
            ],
        )
        self._set_detail_card(
            self.runtime_card,
            self.tr("card.runtime.title", "Runtime"),
            [
                (self.tr("card.runtime.system", "System"), data.get("system", "--")),
                (self.tr("card.runtime.python", "Python"), data.get("python_version", "--")),
                (self.tr("card.runtime.booted", "Booted"), data.get("booted_at", "--")),
                (
                    self.tr("card.runtime.uptime", "Uptime"),
                    self.tr("card.runtime.hours", "{count} hours", count=data.get("uptime_hours", 0)),
                ),
            ],
        )
        battery_pct = data.get("battery_pct")
        battery_text = "--"
        if battery_pct is not None:
            plugged = self._tr_bool(bool(data.get("battery_plugged")))
            battery_text = f"{battery_pct:.0f}% ({plugged})"
        self._set_detail_card(
            self.health_card,
            self.tr("card.health.title", "Health"),
            [
                (self.tr("card.health.mem", "Memory total"), self._fmt_optional(data.get("memory_total_gb"), self.tr("unit.gb", "GB"))),
                (self.tr("card.health.disk", "Disk total"), self._fmt_optional(data.get("disk_total_gb"), self.tr("unit.gb", "GB"))),
                (self.tr("card.health.net", "Network sent"), self._fmt_optional(data.get("network_sent_gb"), self.tr("unit.gb", "GB"))),
                (self.tr("card.health.battery", "Battery"), battery_text),
            ],
        )

        rows = [
            (self.tr("row.hostname", "Hostname"), data.get("hostname", "--")),
            (self.tr("row.os", "Operating system"), data.get("system", "--")),
            (self.tr("row.arch", "Architecture"), data.get("architecture", "--")),
            (self.tr("row.proc", "Processor"), data.get("processor", "--")),
            (self.tr("row.cpu_freq", "CPU frequency"), self._fmt_optional(data.get("cpu_frequency_mhz"), self.tr("unit.mhz", "MHz"))),
            (self.tr("row.phys_cpus", "Physical CPUs"), str(data.get("physical_cpus", "--"))),
            (self.tr("row.log_cpus", "Logical CPUs"), str(data.get("logical_cpus", "--"))),
            (self.tr("row.mem_total", "Memory total"), self._fmt_optional(data.get("memory_total_gb"), self.tr("unit.gb", "GB"))),
            (self.tr("row.mem_avail", "Memory available"), self._fmt_optional(data.get("memory_available_gb"), self.tr("unit.gb", "GB"))),
            (self.tr("row.disk_total", "Disk total"), self._fmt_optional(data.get("disk_total_gb"), self.tr("unit.gb", "GB"))),
            (self.tr("row.disk_free", "Disk free"), self._fmt_optional(data.get("disk_free_gb"), self.tr("unit.gb", "GB"))),
            (self.tr("row.disk_used", "Disk used"), self._fmt_optional(data.get("disk_used_pct"), self.tr("unit.pct", "%"))),
            (self.tr("row.python", "Python"), data.get("python_version", "--")),
            (self.tr("row.booted", "Booted at"), data.get("booted_at", "--")),
            (self.tr("row.uptime", "Uptime"), self.tr("card.runtime.hours", "{count} hours", count=data.get("uptime_hours", 0))),
            (self.tr("row.net_sent", "Network sent"), self._fmt_optional(data.get("network_sent_gb"), self.tr("unit.gb", "GB"))),
            (self.tr("row.net_recv", "Network received"), self._fmt_optional(data.get("network_recv_gb"), self.tr("unit.gb", "GB"))),
        ]
        self.details_table.setRowCount(len(rows))
        self.details_table.setHorizontalHeaderLabels(
            [
                self.tr("table.header.metric", "Metric"),
                self.tr("table.header.value", "Value"),
            ]
        )
        for row, (label, value) in enumerate(rows):
            self.details_table.setItem(row, 0, QTableWidgetItem(label))
            self.details_table.setItem(row, 1, QTableWidgetItem(str(value)))

    def _refresh_live_metrics(self) -> None:
        palette = self.services.theme_manager.current_palette()
        cpu_pct = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(Path.home().anchor or "/")
        self.cpu_donut.set_metric(
            cpu_pct,
            caption=self.tr("cpu.caption", "{count} threads active", count=psutil.cpu_count(logical=True) or 0),
            accent=palette.accent,
            remainder=palette.border,
        )
        self.memory_donut.set_metric(
            memory.percent,
            caption=self.tr("memory.caption", "{count} GB available", count=f"{memory.available / (1024**3):.1f}"),
            accent="#d66b57" if palette.mode == "dark" else "#b63f26",
            remainder=palette.border,
        )
        self.disk_donut.set_metric(
            disk.percent,
            caption=self.tr("disk.caption", "{count} GB free", count=f"{disk.free / (1024**3):.1f}"),
            accent="#7fbc41" if palette.mode == "dark" else "#2f7d4d",
            remainder=palette.border,
        )
        self.timestamp_label.setText(self.tr("timestamp", "Updated {time}", time=datetime.now().strftime("%H:%M:%S")))

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.subtitle_label,
            cards=(
                self.hero_card,
                self.cpu_donut,
                self.memory_donut,
                self.disk_donut,
                self.profile_card,
                self.runtime_card,
                self.health_card,
                self.details_card,
            ),
        )
        self.timestamp_label.setStyleSheet(muted_text_style(palette, weight=600, extra=""))
        self.details_heading.setStyleSheet(section_title_style(palette))

        for donut in (self.cpu_donut, self.memory_donut, self.disk_donut):
            donut.title_label.setStyleSheet(section_title_style(palette, size=16))
            donut.value_label.setStyleSheet(page_title_style(palette, size=26))
            donut.caption_label.setStyleSheet(muted_text_style(palette))

        for card in (self.profile_card, self.runtime_card, self.health_card):
            card._title_label.setStyleSheet(section_title_style(palette))
            card._body_label.setStyleSheet(muted_text_style(palette, extra="line-height: 1.35;"))

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()
        self._refresh_live_metrics()
        if self._audit_payload:
            self._apply_audit_payload()

    def _handle_language_change(self) -> None:
        self._apply_texts()
        if self._audit_payload:
            self._apply_audit_payload()
            self._refresh_live_metrics()

    def _apply_texts(self) -> None:
        self.title_label.setText(self.tr("title", "System Overview"))
        self.subtitle_label.setText(
            self.tr(
                "description",
                "Monitor live resource usage, hardware profile, runtime details, and local system health from one place.",
            )
        )
        self.refresh_button.setText(self.tr("refresh", "Refresh overview"))
        self.cpu_donut.set_title(self.tr("cpu.title", "CPU"))
        self.memory_donut.set_title(self.tr("memory.title", "Memory"))
        self.disk_donut.set_title(self.tr("disk.title", "Disk"))
        self.details_heading.setText(self.tr("table.heading", "System details"))

    @staticmethod
    def _set_detail_card(card: QFrame, title: str, rows: list[tuple[str, object]]) -> None:
        card._title_label.setText(title)
        card._body_label.setText("\n".join(f"{label}: {value}" for label, value in rows))

    @staticmethod
    def _fmt_optional(value: object, suffix: str) -> str:
        if value is None or value == "":
            return "--"
        return f"{value} {suffix}"

    def _tr_bool(self, value: bool) -> str:
        return self.tr("status.plugged", "plugged in") if value else self.tr("status.battery", "battery")
