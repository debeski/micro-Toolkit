from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.icon_registry import icon_from_name
from micro_toolkit.core.page_style import card_style, muted_text_style, page_title_style, section_title_style
from micro_toolkit.core.plugin_api import QtPlugin


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="ignore", check=False)
    except Exception:
        return None


def _parse_key_value_lines(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def _split_nmcli_fields(line: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    escape = False
    for char in line:
        if escape:
            current.append(char)
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == ":":
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _linux_wifi_snapshot() -> tuple[dict[str, object] | None, list[dict[str, str]], list[str]]:
    warnings: list[str] = []
    current: dict[str, object] | None = None
    profiles: list[dict[str, str]] = []

    current_scan = _run_command(["nmcli", "-t", "-f", "ACTIVE,SSID,BSSID,CHAN,RATE,SIGNAL,SECURITY", "dev", "wifi", "list"])
    if current_scan is None:
        warnings.append("`nmcli` is not available on this Linux session.")
        return None, [], warnings

    for raw_line in current_scan.stdout.splitlines():
        parts = _split_nmcli_fields(raw_line)
        if len(parts) < 6:
            continue
        if parts[0].lower() not in {"yes", "*"}:
            continue
        current = {
            "ssid": parts[1],
            "bssid": parts[2],
            "channel": parts[3],
            "rate": parts[4],
            "signal": parts[5],
            "security": parts[6] if len(parts) > 6 else "",
        }
        break

    saved = _run_command(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show"])
    if saved is None:
        warnings.append("Unable to query saved NetworkManager connections.")
        return current, [], warnings

    for raw_line in saved.stdout.splitlines():
        parts = _split_nmcli_fields(raw_line)
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        conn_type = parts[1].strip().lower()
        device = parts[2].strip() if len(parts) > 2 else ""
        if conn_type not in {"802-11-wireless", "wifi"} or not name:
            continue
        password = ""
        security = ""
        detail = _run_command(["nmcli", "-s", "-g", "802-11-wireless-security.key-mgmt,802-11-wireless-security.psk,802-1x.password", "connection", "show", name])
        if detail is not None:
            detail_lines = [line.strip() for line in detail.stdout.splitlines() if line.strip()]
            if detail_lines:
                security = detail_lines[0] if len(detail_lines) > 0 else ""
                password = detail_lines[1] if len(detail_lines) > 1 else ""
                if not password and len(detail_lines) > 2:
                    password = detail_lines[2]
        profiles.append(
            {
                "ssid": name,
                "password": password,
                "security": security,
                "device": device,
                "status": "Connected" if current and current.get("ssid") == name else "Saved",
            }
        )

    if profiles and not any(profile.get("password") for profile in profiles):
        warnings.append("Saved Wi-Fi passwords may require additional desktop or root permissions on this Linux session.")
    return current, profiles, warnings


def _windows_wifi_snapshot() -> tuple[dict[str, object] | None, list[dict[str, str]], list[str]]:
    warnings: list[str] = []
    current: dict[str, object] | None = None
    profiles: list[dict[str, str]] = []

    interfaces = _run_command(["netsh", "wlan", "show", "interfaces"])
    if interfaces is not None:
        parsed = _parse_key_value_lines(interfaces.stdout)
        current = {
            "ssid": parsed.get("SSID", ""),
            "bssid": parsed.get("BSSID", ""),
            "signal": parsed.get("Signal", ""),
            "radio": parsed.get("Radio type", ""),
            "security": parsed.get("Authentication", ""),
        }

    saved = _run_command(["netsh", "wlan", "show", "profiles"])
    if saved is None:
        warnings.append("Unable to query saved Wi-Fi profiles with `netsh`.")
        return current, profiles, warnings

    profile_names = re.findall(r"All User Profile\s*:\s*(.+)", saved.stdout)
    total = len(profile_names)
    for index, name in enumerate(profile_names, start=1):
        ssid = name.strip().strip('"')
        detail = _run_command(["netsh", "wlan", "show", "profile", f'name={ssid}', "key=clear"])
        parsed = _parse_key_value_lines(detail.stdout if detail is not None else "")
        profiles.append(
            {
                "ssid": ssid,
                "password": parsed.get("Key Content", ""),
                "security": parsed.get("Authentication", ""),
                "device": "",
                "status": "Connected" if current and current.get("ssid") == ssid else "Saved",
            }
        )
    if total and not profiles:
        warnings.append("No readable Wi-Fi profiles were returned by `netsh`.")
    return current, profiles, warnings


def _macos_wifi_device() -> str:
    result = _run_command(["networksetup", "-listallhardwareports"])
    if result is None:
        return ""
    current_port = ""
    current_device = ""
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("Hardware Port:"):
            current_port = line.split(":", 1)[1].strip()
        elif line.startswith("Device:"):
            current_device = line.split(":", 1)[1].strip()
        elif not line:
            if current_port in {"Wi-Fi", "AirPort"} and current_device:
                return current_device
            current_port = ""
            current_device = ""
    if current_port in {"Wi-Fi", "AirPort"} and current_device:
        return current_device
    return ""


def _macos_wifi_snapshot() -> tuple[dict[str, object] | None, list[dict[str, str]], list[str]]:
    warnings: list[str] = []
    current: dict[str, object] | None = None
    profiles: list[dict[str, str]] = []
    device = _macos_wifi_device()
    if not device:
        warnings.append("Unable to determine the Wi-Fi interface on this macOS session.")
        return None, profiles, warnings

    current_network = _run_command(["networksetup", "-getairportnetwork", device])
    if current_network is not None and ":" in current_network.stdout:
        ssid = current_network.stdout.split(":", 1)[1].strip()
        current = {"ssid": ssid, "device": device, "security": "", "bssid": "", "signal": ""}

    preferred = _run_command(["networksetup", "-listpreferredwirelessnetworks", device])
    if preferred is None:
        warnings.append("Unable to query saved preferred Wi-Fi networks.")
        return current, profiles, warnings

    names = []
    for line in preferred.stdout.splitlines()[1:]:
        ssid = line.strip()
        if ssid:
            names.append(ssid)

    for ssid in names:
        password = ""
        secret = _run_command(["security", "find-generic-password", "-D", "AirPort network password", "-a", ssid, "-gw"])
        if secret is not None and secret.returncode == 0:
            password = secret.stdout.strip()
        profiles.append(
            {
                "ssid": ssid,
                "password": password,
                "security": "",
                "device": device,
                "status": "Connected" if current and current.get("ssid") == ssid else "Saved",
            }
        )
    return current, profiles, warnings


def collect_wifi_snapshot(context) -> dict[str, object]:
    context.log("Collecting Wi-Fi profile details...")
    context.progress(0.15)
    if sys.platform.startswith("win"):
        current, profiles, warnings = _windows_wifi_snapshot()
    elif sys.platform == "darwin":
        current, profiles, warnings = _macos_wifi_snapshot()
    else:
        current, profiles, warnings = _linux_wifi_snapshot()
    context.progress(0.95)
    context.log(f"Collected {len(profiles)} saved Wi-Fi profile(s).")
    context.progress(1.0)
    return {
        "platform": sys.platform,
        "current": current,
        "profiles": profiles,
        "warnings": warnings,
    }


class WifiRevealerPlugin(QtPlugin):
    plugin_id = "wifi_revealer"
    name = "Wi-Fi Password Revealer"
    description = "Inspect the current Wi-Fi connection and list saved Wi-Fi profiles with available passwords."
    category = "IT Toolkit"
    preferred_icon = "network"
    translations = {
        "en": {
            "plugin.name": "Wi-Fi Password Revealer",
            "plugin.description": "Inspect the current Wi-Fi connection and list saved Wi-Fi profiles with available passwords.",
            "ui.title": "Wi-Fi Password Revealer",
            "ui.description": "Review the current Wi-Fi connection, inspect saved networks, and copy any passwords that the active platform backend can read.",
            "ui.refresh": "Refresh Wi-Fi Data",
            "ui.summary.ready": "Load the current Wi-Fi connection and saved profiles.",
            "ui.summary.loading": "Reading Wi-Fi information...",
            "ui.summary.empty": "No saved Wi-Fi profiles were returned on this system.",
            "ui.summary.success": "Loaded {count} saved Wi-Fi profile(s).",
            "ui.current.title": "Current Network",
            "ui.current.none": "No active Wi-Fi connection detected.",
            "ui.saved.title": "Saved Networks",
            "ui.warnings.title": "Warnings and Notes",
            "ui.copy": "Copy Password",
            "ui.copy.none": "The selected profile does not expose a readable password on this session.",
            "ui.copy.done": "Password copied to the system clipboard.",
            "table.ssid": "SSID",
            "table.password": "Password",
            "table.security": "Security",
            "table.device": "Device",
            "table.status": "Status",
            "table.action": "Action",
        },
        "ar": {
            "plugin.name": "كاشف كلمات مرور الواي فاي",
            "plugin.description": "اعرض اتصال الواي فاي الحالي وقائمة الشبكات المحفوظة مع كلمات المرور المتاحة.",
            "ui.title": "كاشف كلمات مرور الواي فاي",
            "ui.description": "اعرض اتصال الواي فاي الحالي، وافحص الشبكات المحفوظة، وانسخ كلمات المرور التي يستطيع النظام قراءتها.",
            "ui.refresh": "تحديث بيانات الواي فاي",
            "ui.summary.ready": "حمّل اتصال الواي فاي الحالي والشبكات المحفوظة.",
            "ui.summary.loading": "جار قراءة معلومات الواي فاي...",
            "ui.summary.empty": "لم يتم العثور على شبكات واي فاي محفوظة قابلة للعرض على هذا النظام.",
            "ui.summary.success": "تم تحميل {count} شبكة واي فاي محفوظة.",
            "ui.current.title": "الشبكة الحالية",
            "ui.current.none": "لم يتم اكتشاف اتصال واي فاي نشط.",
            "ui.saved.title": "الشبكات المحفوظة",
            "ui.warnings.title": "تنبيهات وملاحظات",
            "ui.copy": "نسخ كلمة المرور",
            "ui.copy.none": "الشبكة المحددة لا تعرض كلمة مرور قابلة للقراءة في هذه الجلسة.",
            "ui.copy.done": "تم نسخ كلمة المرور إلى الحافظة.",
            "table.ssid": "اسم الشبكة",
            "table.password": "كلمة المرور",
            "table.security": "الأمان",
            "table.device": "الجهاز",
            "table.status": "الحالة",
            "table.action": "إجراء",
        },
    }

    def create_widget(self, services) -> QWidget:
        return WifiRevealerPage(services, self.plugin_id)


class WifiRevealerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._profiles: list[dict[str, str]] = []
        self._build_ui()
        self._apply_texts()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self._refresh()

    def _t(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        self.title_label = QLabel()
        layout.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self._refresh)
        controls.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.progress, 1)
        layout.addLayout(controls)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(self.summary_card)

        self.current_card = QFrame()
        current_layout = QVBoxLayout(self.current_card)
        current_layout.setContentsMargins(18, 16, 18, 16)
        current_layout.setSpacing(8)
        self.current_heading = QLabel()
        current_layout.addWidget(self.current_heading)
        self.current_body = QLabel()
        self.current_body.setWordWrap(True)
        current_layout.addWidget(self.current_body)
        layout.addWidget(self.current_card)

        self.saved_card = QFrame()
        saved_layout = QVBoxLayout(self.saved_card)
        saved_layout.setContentsMargins(18, 16, 18, 16)
        saved_layout.setSpacing(10)
        self.saved_heading = QLabel()
        saved_layout.addWidget(self.saved_heading)
        self.table = QTableWidget(0, 6)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, self.table.horizontalHeader().ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, self.table.horizontalHeader().ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, self.table.horizontalHeader().ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, self.table.horizontalHeader().ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, self.table.horizontalHeader().ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        saved_layout.addWidget(self.table, 1)
        layout.addWidget(self.saved_card, 1)

        self.warning_card = QFrame()
        warning_layout = QVBoxLayout(self.warning_card)
        warning_layout.setContentsMargins(18, 16, 18, 16)
        warning_layout.setSpacing(10)
        self.warning_heading = QLabel()
        warning_layout.addWidget(self.warning_heading)
        self.warning_output = QPlainTextEdit()
        self.warning_output.setReadOnly(True)
        warning_layout.addWidget(self.warning_output)
        layout.addWidget(self.warning_card)

    def _apply_texts(self) -> None:
        self._apply_theme_styles()
        self.title_label.setText(self._t("ui.title", "Wi-Fi Password Revealer"))
        self.description_label.setText(
            self._t(
                "ui.description",
                "Review the current Wi-Fi connection, inspect saved networks, and copy any passwords that the active platform backend can read.",
            )
        )
        self.refresh_button.setText(self._t("ui.refresh", "Refresh Wi-Fi Data"))
        self.current_heading.setText(self._t("ui.current.title", "Current Network"))
        self.saved_heading.setText(self._t("ui.saved.title", "Saved Networks"))
        self.warning_heading.setText(self._t("ui.warnings.title", "Warnings and Notes"))
        self.table.setHorizontalHeaderLabels(
            [
                self._t("table.ssid", "SSID"),
                self._t("table.password", "Password"),
                self._t("table.security", "Security"),
                self._t("table.device", "Device"),
                self._t("table.status", "Status"),
                self._t("table.action", "Action"),
            ]
        )
        if not self.summary_label.text():
            self.summary_label.setText(self._t("ui.summary.ready", "Load the current Wi-Fi connection and saved profiles."))

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        for frame in (self.summary_card, self.current_card, self.saved_card, self.warning_card):
            frame.setStyleSheet(card_style(palette))
        self.title_label.setStyleSheet(page_title_style(palette, size=26, weight=700))
        self.description_label.setStyleSheet(muted_text_style(palette))
        self.summary_label.setStyleSheet(muted_text_style(palette, size=13))
        self.current_heading.setStyleSheet(section_title_style(palette))
        self.current_body.setStyleSheet(muted_text_style(palette))
        self.saved_heading.setStyleSheet(section_title_style(palette))
        self.warning_heading.setStyleSheet(section_title_style(palette))

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        self.progress.setValue(0)
        self.summary_label.setText(self._t("ui.summary.loading", "Reading Wi-Fi information..."))
        self.warning_output.clear()
        self.table.setRowCount(0)
        self.services.run_task(
            collect_wifi_snapshot,
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_refresh,
            on_progress=self._handle_progress,
        )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._profiles = list(result.get("profiles") or [])
        current = result.get("current")
        warnings = [str(item) for item in (result.get("warnings") or []) if str(item).strip()]

        if current:
            current_lines = []
            for label, key in (
                ("SSID", "ssid"),
                ("BSSID", "bssid"),
                ("Security", "security"),
                ("Signal", "signal"),
                ("Rate", "rate"),
                ("Channel", "channel"),
                ("Device", "device"),
                ("Radio", "radio"),
            ):
                value = str(current.get(key) or "").strip()
                if value:
                    current_lines.append(f"{label}: {value}")
            self.current_body.setText("\n".join(current_lines) if current_lines else self._t("ui.current.none", "No active Wi-Fi connection detected."))
        else:
            self.current_body.setText(self._t("ui.current.none", "No active Wi-Fi connection detected."))

        self.table.setRowCount(len(self._profiles))
        copy_label = self._t("ui.copy", "Copy Password")
        for row_index, profile in enumerate(self._profiles):
            self.table.setItem(row_index, 0, QTableWidgetItem(profile.get("ssid", "")))
            self.table.setItem(row_index, 1, QTableWidgetItem(profile.get("password", "")))
            self.table.setItem(row_index, 2, QTableWidgetItem(profile.get("security", "")))
            self.table.setItem(row_index, 3, QTableWidgetItem(profile.get("device", "")))
            self.table.setItem(row_index, 4, QTableWidgetItem(profile.get("status", "")))
            action_button = QToolButton()
            action_button.setAutoRaise(True)
            action_button.setIcon(icon_from_name("clipboard", self) or self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogContentsView))
            action_button.setToolTip(copy_label)
            action_button.clicked.connect(lambda _checked=False, idx=row_index: self._copy_password(idx))
            self.table.setCellWidget(row_index, 5, action_button)

        if self._profiles:
            self.summary_label.setText(self._t("ui.summary.success", "Loaded {count} saved Wi-Fi profile(s).", count=str(len(self._profiles))))
        else:
            self.summary_label.setText(self._t("ui.summary.empty", "No saved Wi-Fi profiles were returned on this system."))
        self.warning_output.setPlainText("\n".join(warnings) if warnings else "No extra warnings.")
        status = "SUCCESS" if self._profiles or current else "WARNING"
        self.services.record_run(self.plugin_id, status, f"Loaded {len(self._profiles)} Wi-Fi profile(s)")

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown Wi-Fi inspection error") if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.warning_output.setPlainText(message)
        self.current_body.setText(self._t("ui.current.none", "No active Wi-Fi connection detected."))
        self.services.record_run(self.plugin_id, "ERROR", message[:500])

    def _finish_refresh(self) -> None:
        self.refresh_button.setEnabled(True)
        self.progress.setValue(100)

    def _copy_password(self, row_index: int) -> None:
        if not (0 <= row_index < len(self._profiles)):
            return
        password = str(self._profiles[row_index].get("password") or "")
        if not password:
            QMessageBox.information(self, self._t("plugin.name", "Wi-Fi Password Revealer"), self._t("ui.copy.none", "The selected profile does not expose a readable password on this session."))
            return
        QGuiApplication.clipboard().setText(password)
        self.services.log("Copied Wi-Fi password to the system clipboard.")
        QMessageBox.information(self, self._t("plugin.name", "Wi-Fi Password Revealer"), self._t("ui.copy.done", "Password copied to the system clipboard."))
