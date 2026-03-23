from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.icon_registry import icon_from_name
from micro_toolkit.core.page_style import card_style, muted_text_style, page_title_style, section_title_style
from micro_toolkit.core.plugin_api import QtPlugin


@dataclass(frozen=True)
class WifiProfile:
    ssid: str
    password: str
    security: str
    device: str
    status: str
    notes: str = ""


def _run_command(args: list[str], *, timeout: float = 12.0) -> tuple[bool, str, str]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, "", f"Command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out: {' '.join(args)}"
    except Exception as exc:
        return False, "", str(exc)
    return completed.returncode == 0, completed.stdout.strip(), completed.stderr.strip()


def _split_escaped_colons(line: str, expected_parts: int) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == ":" and len(parts) < expected_parts - 1:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    while len(parts) < expected_parts:
        parts.append("")
    return parts[:expected_parts]


def _first_text(*values: str) -> str:
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def _dedupe_texts(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _maskless_password_hint(password: str, security: str) -> str:
    if password:
        return ""
    lowered = str(security or "").lower()
    if not lowered or lowered in {"open", "none", "--"}:
        return "Open network"
    return "Password unavailable from current backend"


def _linux_connection_value(profile_name: str, field: str) -> str:
    ok, output, _ = _run_command(["nmcli", "-s", "-g", field, "connection", "show", profile_name], timeout=8.0)
    if not ok:
        return ""
    return output.splitlines()[0].strip() if output else ""


def _linux_wifi_payload(context) -> dict[str, object]:
    warnings: list[str] = []
    current_network: dict[str, str] | None = None
    profiles: list[WifiProfile] = []

    if shutil.which("nmcli") is None:
        return {
            "platform": "linux",
            "backend": "nmcli",
            "current": None,
            "profiles": [],
            "warnings": ["NetworkManager CLI (`nmcli`) is not available on this system."],
        }

    context.log("Reading active Linux Wi-Fi connections with nmcli.")
    active_connections: dict[str, dict[str, str]] = {}
    ok, output, error = _run_command(["nmcli", "-t", "-e", "yes", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"])
    if ok:
        for line in output.splitlines():
            if not line.strip():
                continue
            name, connection_type, device = _split_escaped_colons(line, 3)
            if connection_type.strip() not in {"wifi", "802-11-wireless"}:
                continue
            active_connections[name.strip()] = {"device": device.strip()}
    elif error:
        warnings.append(error)

    wifi_scan_by_ssid: dict[str, dict[str, str]] = {}
    ok, output, error = _run_command(
        ["nmcli", "-t", "-e", "yes", "-f", "ACTIVE,SSID,SIGNAL,RATE,SECURITY,DEVICE", "dev", "wifi", "list", "--rescan", "no"]
    )
    if ok:
        for line in output.splitlines():
            if not line.strip():
                continue
            active, ssid, signal, rate, security, device = _split_escaped_colons(line, 6)
            wifi_scan_by_ssid[ssid.strip()] = {
                "signal": signal.strip(),
                "rate": rate.strip(),
                "security": security.strip() or "Open",
                "device": device.strip(),
                "active": active.strip().lower() == "yes",
            }
    elif error:
        warnings.append(error)

    ok, output, error = _run_command(["nmcli", "-t", "-e", "yes", "-f", "NAME,TYPE,DEVICE", "connection", "show"])
    if not ok:
        warnings.append(error or "Unable to read saved Wi-Fi profiles via nmcli.")
        return {
            "platform": "linux",
            "backend": "nmcli",
            "current": current_network,
            "profiles": [],
            "warnings": _dedupe_texts(warnings),
        }

    for line in output.splitlines():
        if not line.strip():
            continue
        profile_name, connection_type, device = _split_escaped_colons(line, 3)
        if connection_type.strip() not in {"wifi", "802-11-wireless"}:
            continue
        profile_name = profile_name.strip()
        scan_details = wifi_scan_by_ssid.get(profile_name, {})
        key_mgmt = _linux_connection_value(profile_name, "802-11-wireless-security.key-mgmt")
        security = _first_text(scan_details.get("security", ""), key_mgmt.replace("-", " ").upper(), "Open")
        password = _first_text(
            _linux_connection_value(profile_name, "802-11-wireless-security.psk"),
            _linux_connection_value(profile_name, "802-1x.password"),
        )
        status = "Saved"
        if profile_name in active_connections:
            status = "Connected"
            current_network = {
                "ssid": profile_name,
                "device": _first_text(active_connections[profile_name].get("device", ""), scan_details.get("device", ""), device.strip(), "--"),
                "signal": scan_details.get("signal", "--") or "--",
                "rate": scan_details.get("rate", "--") or "--",
                "security": security,
                "password": password or "--",
            }
        profiles.append(
            WifiProfile(
                ssid=profile_name,
                password=password,
                security=security,
                device=_first_text(scan_details.get("device", ""), device.strip(), "--"),
                status=status,
                notes=_maskless_password_hint(password, security),
            )
        )

    if current_network is None:
        for ssid, details in wifi_scan_by_ssid.items():
            if details.get("active"):
                current_network = {
                    "ssid": ssid,
                    "device": details.get("device", "--") or "--",
                    "signal": details.get("signal", "--") or "--",
                    "rate": details.get("rate", "--") or "--",
                    "security": details.get("security", "Open") or "Open",
                    "password": "--",
                }
                break

    return {
        "platform": "linux",
        "backend": "nmcli",
        "current": current_network,
        "profiles": [profile.__dict__ for profile in sorted(profiles, key=lambda item: (item.status != "Connected", item.ssid.lower()))],
        "warnings": _dedupe_texts(warnings),
    }


def _xml_find_text(root: ET.Element, tag_name: str) -> str:
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == tag_name:
            return (element.text or "").strip()
    return ""


def _windows_wifi_payload(context) -> dict[str, object]:
    warnings: list[str] = [
        "Windows current-network fields are best-effort and may vary with localized netsh output."
    ]
    profiles: list[WifiProfile] = []
    current_network: dict[str, str] | None = None

    if shutil.which("netsh") is None:
        raise RuntimeError("`netsh` is not available on this Windows system.")

    context.log("Exporting Windows Wi-Fi profiles with clear keys.")
    with tempfile.TemporaryDirectory(prefix="micro_toolkit_wifi_") as temp_dir:
        ok, _, error = _run_command(["netsh", "wlan", "export", "profile", "key=clear", f"folder={temp_dir}"], timeout=20.0)
        if not ok and error:
            warnings.append(error)
        for xml_path in sorted(Path(temp_dir).glob("*.xml")):
            try:
                root = ET.fromstring(xml_path.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            ssid = _first_text(_xml_find_text(root, "name"), xml_path.stem)
            security = _first_text(_xml_find_text(root, "authentication"), "Saved profile")
            password = _xml_find_text(root, "keyMaterial")
            profiles.append(
                WifiProfile(
                    ssid=ssid,
                    password=password,
                    security=security,
                    device="Wi-Fi",
                    status="Saved",
                    notes=_maskless_password_hint(password, security),
                )
            )

    ok, output, error = _run_command(["netsh", "wlan", "show", "interfaces"], timeout=12.0)
    if ok:
        def capture(label: str) -> str:
            match = re.search(rf"^\s*{label}\s*:\s*(.+)$", output, re.MULTILINE)
            return match.group(1).strip() if match else ""

        ssid = capture("SSID")
        if ssid:
            current_network = {
                "ssid": ssid,
                "device": _first_text(capture("Name"), "Wi-Fi"),
                "signal": capture("Signal") or "--",
                "rate": _first_text(capture("Receive rate \\(Mbps\\)"), capture("Transmit rate \\(Mbps\\)"), "--"),
                "security": _first_text(capture("Authentication"), "--"),
                "password": "--",
            }
    elif error:
        warnings.append(error)

    profile_by_ssid = {profile.ssid: profile for profile in profiles}
    if current_network and current_network["ssid"] in profile_by_ssid:
        profile = profile_by_ssid[current_network["ssid"]]
        current_network["password"] = profile.password or "--"
        current_network["security"] = profile.security or current_network["security"]
        profiles = [
            WifiProfile(
                ssid=item.ssid,
                password=item.password,
                security=item.security,
                device=item.device,
                status="Connected" if item.ssid == current_network["ssid"] else item.status,
                notes=item.notes,
            )
            for item in profiles
        ]

    return {
        "platform": "windows",
        "backend": "netsh",
        "current": current_network,
        "profiles": [profile.__dict__ for profile in sorted(profiles, key=lambda item: (item.status != "Connected", item.ssid.lower()))],
        "warnings": _dedupe_texts(warnings),
    }


def _macos_wifi_device() -> str:
    ok, output, _ = _run_command(["networksetup", "-listallhardwareports"], timeout=10.0)
    if not ok:
        return ""
    blocks = output.split("\n\n")
    for block in blocks:
        if "Hardware Port: Wi-Fi" in block or "Hardware Port: AirPort" in block:
            for line in block.splitlines():
                if line.strip().startswith("Device:"):
                    return line.split(":", 1)[1].strip()
    return ""


def _macos_wifi_payload(context) -> dict[str, object]:
    warnings: list[str] = []
    device = _macos_wifi_device()
    if not device:
        raise RuntimeError("Unable to determine the active Wi-Fi interface on macOS.")

    context.log(f"Reading macOS Wi-Fi profiles for {device}.")
    profiles: list[WifiProfile] = []
    current_network: dict[str, str] | None = None

    ok, output, error = _run_command(["networksetup", "-listpreferredwirelessnetworks", device], timeout=12.0)
    if not ok:
        raise RuntimeError(error or "Unable to list preferred wireless networks.")
    ssids = [line.strip() for line in output.splitlines()[1:] if line.strip()]

    ok, output, error = _run_command(["networksetup", "-getairportnetwork", device], timeout=8.0)
    current_ssid = ""
    if ok:
        if ":" in output:
            current_ssid = output.split(":", 1)[1].strip()
    elif error:
        warnings.append(error)

    for ssid in ssids:
        ok, password, error = _run_command(
            ["security", "find-generic-password", "-D", "AirPort network password", "-a", ssid, "-gw"],
            timeout=8.0,
        )
        if not ok and error and "could not be found" not in error.lower():
            warnings.append(f"{ssid}: {error}")
        profiles.append(
            WifiProfile(
                ssid=ssid,
                password=password if ok else "",
                security="Saved profile",
                device=device,
                status="Connected" if ssid == current_ssid else "Saved",
                notes=_maskless_password_hint(password if ok else "", "Saved profile"),
            )
        )

    if current_ssid:
        matched = next((item for item in profiles if item.ssid == current_ssid), None)
        current_network = {
            "ssid": current_ssid,
            "device": device,
            "signal": "--",
            "rate": "--",
            "security": matched.security if matched else "--",
            "password": matched.password if matched and matched.password else "--",
        }

    return {
        "platform": "macos",
        "backend": "networksetup/security",
        "current": current_network,
        "profiles": [profile.__dict__ for profile in sorted(profiles, key=lambda item: (item.status != "Connected", item.ssid.lower()))],
        "warnings": _dedupe_texts(warnings),
    }


def collect_wifi_payload(context) -> dict[str, object]:
    context.progress(0.08)
    platform_key = sys.platform.lower()
    if platform_key.startswith("linux"):
        payload = _linux_wifi_payload(context)
    elif platform_key.startswith("win"):
        payload = _windows_wifi_payload(context)
    elif platform_key == "darwin":
        payload = _macos_wifi_payload(context)
    else:
        raise RuntimeError(f"Unsupported platform for Wi-Fi inspection: {sys.platform}")
    context.progress(1.0)
    return payload


class WifiProfilesPlugin(QtPlugin):
    plugin_id = "wifi_profiles"
    name = "Wi-Fi Profiles"
    description = "Inspect saved Wi-Fi profiles, current network details, and any locally available stored passwords."
    category = "Networks"
    preferred_icon = "network"
    translations = {
        "en": {
            "plugin.name": "Wi-Fi Profiles",
            "plugin.description": "Inspect saved Wi-Fi profiles, current network details, and any locally available stored passwords.",
            "plugin.category": "Networks",
            "title": "Wi-Fi Profiles",
            "subtitle": "Review the current Wi-Fi connection, saved network profiles, and passwords that your platform backend can expose.",
            "refresh": "Refresh profiles",
            "copy_current": "Copy current password",
            "current_heading": "Current network",
            "saved_heading": "Saved Wi-Fi profiles",
            "warnings_heading": "Backend notes",
            "unsupported": "No current Wi-Fi network is connected.",
            "status_ready": "Ready to inspect Wi-Fi profiles.",
            "status_loaded": "Loaded {count} Wi-Fi profile(s) using {backend}.",
            "status_empty": "No Wi-Fi profiles were returned by the current backend.",
            "copy_ok": "Password copied for {ssid}.",
        },
        "ar": {
            "plugin.name": "شبكات واي فاي",
            "plugin.description": "استعرض الشبكات المحفوظة ومعلومات الشبكة الحالية وأي كلمات مرور محلية يمكن للنظام إظهارها.",
            "plugin.category": "الشبكات",
            "title": "شبكات واي فاي",
            "subtitle": "راجع اتصال الواي فاي الحالي والشبكات المحفوظة وكلمات المرور التي يمكن للواجهة الخلفية للنظام إظهارها.",
            "refresh": "تحديث الشبكات",
            "copy_current": "نسخ كلمة مرور الحالية",
            "current_heading": "الشبكة الحالية",
            "saved_heading": "الشبكات المحفوظة",
            "warnings_heading": "ملاحظات الواجهة الخلفية",
            "unsupported": "لا توجد شبكة واي فاي حالية متصلة.",
            "status_ready": "جاهز لفحص شبكات واي فاي.",
            "status_loaded": "تم تحميل {count} شبكة باستخدام {backend}.",
            "status_empty": "لم تُرجع الواجهة الخلفية أي شبكات واي فاي.",
            "copy_ok": "تم نسخ كلمة المرور للشبكة {ssid}.",
        },
    }

    def create_widget(self, services) -> QWidget:
        return WifiProfilesPage(services, self.plugin_id)


class WifiProfilesPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._payload: dict[str, object] = {"profiles": [], "warnings": [], "current": None}
        self._current_password = ""
        self._build_ui()
        self._apply_theme_styles()
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self._refresh()

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(18)

        self.hero_card = QFrame()
        hero_layout = QVBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(20, 20, 20, 20)
        hero_layout.setSpacing(8)

        self.title_label = QLabel(self._pt("title", "Wi-Fi Profiles"))
        hero_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(
            self._pt(
                "subtitle",
                "Review the current Wi-Fi connection, saved network profiles, and passwords that your platform backend can expose.",
            )
        )
        self.subtitle_label.setWordWrap(True)
        hero_layout.addWidget(self.subtitle_label)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.refresh_button = QPushButton(self._pt("refresh", "Refresh profiles"))
        self.refresh_button.clicked.connect(self._refresh)
        controls.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.copy_current_button = QPushButton(self._pt("copy_current", "Copy current password"))
        self.copy_current_button.setEnabled(False)
        self.copy_current_button.clicked.connect(self._copy_current_password)
        controls.addWidget(self.copy_current_button, 0, Qt.AlignmentFlag.AlignLeft)

        controls.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        controls.addWidget(self.progress, 1)
        hero_layout.addLayout(controls)

        self.status_label = QLabel(self._pt("status_ready", "Ready to inspect Wi-Fi profiles."))
        self.status_label.setWordWrap(True)
        hero_layout.addWidget(self.status_label)
        layout.addWidget(self.hero_card)

        info_row = QHBoxLayout()
        info_row.setSpacing(14)

        self.current_card = QFrame()
        current_layout = QVBoxLayout(self.current_card)
        current_layout.setContentsMargins(18, 16, 18, 16)
        current_layout.setSpacing(10)
        self.current_heading = QLabel(self._pt("current_heading", "Current network"))
        current_layout.addWidget(self.current_heading)

        self.current_grid = QGridLayout()
        self.current_grid.setHorizontalSpacing(10)
        self.current_grid.setVerticalSpacing(8)
        current_layout.addLayout(self.current_grid)

        self.current_fields: dict[str, QLabel] = {}
        field_labels = [
            ("ssid", "SSID"),
            ("device", "Device"),
            ("signal", "Signal"),
            ("rate", "Rate"),
            ("security", "Security"),
            ("password", "Password"),
        ]
        for row, (field_key, field_title) in enumerate(field_labels):
            label = QLabel(field_title)
            value = QLabel("--")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            self.current_grid.addWidget(label, row, 0)
            self.current_grid.addWidget(value, row, 1)
            self.current_fields[f"{field_key}_title"] = label
            self.current_fields[field_key] = value
        info_row.addWidget(self.current_card, 1)

        self.warnings_card = QFrame()
        warnings_layout = QVBoxLayout(self.warnings_card)
        warnings_layout.setContentsMargins(18, 16, 18, 16)
        warnings_layout.setSpacing(10)
        self.warnings_heading = QLabel(self._pt("warnings_heading", "Backend notes"))
        warnings_layout.addWidget(self.warnings_heading)
        self.warnings_output = QPlainTextEdit()
        self.warnings_output.setReadOnly(True)
        self.warnings_output.setPlaceholderText("No backend warnings.")
        warnings_layout.addWidget(self.warnings_output, 1)
        info_row.addWidget(self.warnings_card, 1)
        layout.addLayout(info_row)

        self.table_card = QFrame()
        table_layout = QVBoxLayout(self.table_card)
        table_layout.setContentsMargins(18, 16, 18, 16)
        table_layout.setSpacing(10)
        self.table_heading = QLabel(self._pt("saved_heading", "Saved Wi-Fi profiles"))
        table_layout.addWidget(self.table_heading)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["SSID", "Password", "Security", "Device", "Status", "Notes", "Actions"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        table_layout.addWidget(self.table, 1)
        layout.addWidget(self.table_card, 1)

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        for card in (self.hero_card, self.current_card, self.warnings_card, self.table_card):
            card.setStyleSheet(card_style(palette))

        self.title_label.setStyleSheet(page_title_style(palette))
        self.subtitle_label.setStyleSheet(muted_text_style(palette, size=14))
        self.status_label.setStyleSheet(muted_text_style(palette, size=13, weight=600))
        self.current_heading.setStyleSheet(section_title_style(palette))
        self.warnings_heading.setStyleSheet(section_title_style(palette))
        self.table_heading.setStyleSheet(section_title_style(palette))
        for key, label in self.current_fields.items():
            if key.endswith("_title"):
                label.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {palette.text_primary};")
            else:
                label.setStyleSheet(f"font-size: 14px; font-weight: 500; color: {palette.text_muted};")

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()
        self._rebuild_action_cells()

    def _refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        self.copy_current_button.setEnabled(False)
        self.progress.setValue(14)
        self.status_label.setText(self._pt("status_ready", "Ready to inspect Wi-Fi profiles."))
        self.services.run_task(
            collect_wifi_payload,
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._handle_finished,
            on_progress=self._handle_progress,
        )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        self._payload = dict(payload) if isinstance(payload, dict) else {}
        profiles = self._payload.get("profiles") or []
        backend = str(self._payload.get("backend") or sys.platform)
        count = len(profiles) if isinstance(profiles, list) else 0
        if count:
            self.status_label.setText(self._pt("status_loaded", "Loaded {count} Wi-Fi profile(s) using {backend}.", count=count, backend=backend))
            self.services.record_run(self.plugin_id, "SUCCESS", f"Loaded {count} Wi-Fi profile(s) via {backend}")
        else:
            self.status_label.setText(self._pt("status_empty", "No Wi-Fi profiles were returned by the current backend."))
            self.services.record_run(self.plugin_id, "WARNING", f"No Wi-Fi profiles returned via {backend}")
        self._render_current_network()
        self._render_warnings()
        self._render_profiles()

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Wi-Fi inspection failed.") if isinstance(payload, dict) else str(payload)
        self.status_label.setText(message)
        self.warnings_output.setPlainText(message)
        self.table.setRowCount(0)
        self._current_password = ""
        self.copy_current_button.setEnabled(False)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])

    def _handle_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        if self.progress.value() < 100:
            self.progress.setValue(100)

    def _render_current_network(self) -> None:
        current = self._payload.get("current")
        if not isinstance(current, dict):
            for key, label in self.current_fields.items():
                if not key.endswith("_title"):
                    label.setText("--")
            self._current_password = ""
            self.copy_current_button.setEnabled(False)
            self.current_fields["ssid"].setText(self._pt("unsupported", "No current Wi-Fi network is connected."))
            return

        self._current_password = str(current.get("password") or "").strip()
        self.copy_current_button.setEnabled(bool(self._current_password and self._current_password != "--"))
        for field in ("ssid", "device", "signal", "rate", "security", "password"):
            value = str(current.get(field) or "--")
            if field == "password" and not value.strip():
                value = "--"
            self.current_fields[field].setText(value)

    def _render_warnings(self) -> None:
        warnings = self._payload.get("warnings") or []
        if not isinstance(warnings, list):
            warnings = []
        text = "\n".join(f"- {str(item)}" for item in warnings if str(item).strip())
        self.warnings_output.setPlainText(text or "No backend warnings.")

    def _render_profiles(self) -> None:
        payload_profiles = self._payload.get("profiles") or []
        profiles = payload_profiles if isinstance(payload_profiles, list) else []
        self.table.setRowCount(len(profiles))
        for row_index, row in enumerate(profiles):
            item = row if isinstance(row, dict) else {}
            values = [
                str(item.get("ssid") or ""),
                str(item.get("password") or ""),
                str(item.get("security") or ""),
                str(item.get("device") or ""),
                str(item.get("status") or ""),
                str(item.get("notes") or ""),
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 1:
                    cell.setToolTip(value or "No stored password available")
                self.table.setItem(row_index, column, cell)
        self._rebuild_action_cells()
        self.table.resizeRowsToContents()

    def _rebuild_action_cells(self) -> None:
        payload_profiles = self._payload.get("profiles") or []
        profiles = payload_profiles if isinstance(payload_profiles, list) else []
        for row_index, row in enumerate(profiles):
            item = row if isinstance(row, dict) else {}
            password = str(item.get("password") or "")
            ssid = str(item.get("ssid") or "Wi-Fi")
            action_host = QWidget()
            action_layout = QHBoxLayout(action_host)
            action_layout.setContentsMargins(6, 0, 6, 0)
            action_layout.setSpacing(4)
            action_layout.addStretch(1)

            copy_button = QToolButton()
            copy_button.setIcon(icon_from_name("clipboard", self) or copy_button.icon())
            copy_button.setToolTip("Copy password")
            copy_button.setEnabled(bool(password))
            copy_button.clicked.connect(lambda _checked=False, text=password, name=ssid: self._copy_password(text, name))
            action_layout.addWidget(copy_button)
            action_layout.addStretch(1)
            self.table.setCellWidget(row_index, 6, action_host)

    def _copy_password(self, password: str, ssid: str) -> None:
        if not password:
            QMessageBox.information(self, "No Password", "No stored password is available for this profile.")
            return
        QGuiApplication.clipboard().setText(password)
        self.services.log(self._pt("copy_ok", "Password copied for {ssid}.", ssid=ssid))

    def _copy_current_password(self) -> None:
        current = self._payload.get("current")
        ssid = str(current.get("ssid") or "current network") if isinstance(current, dict) else "current network"
        self._copy_password(self._current_password, ssid)
