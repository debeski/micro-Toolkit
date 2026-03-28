from __future__ import annotations

import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.icon_registry import icon_from_name
from micro_toolkit.core.page_style import apply_page_chrome, apply_semantic_class, muted_text_style, section_title_style
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr


class DevLabPlugin(QtPlugin):
    plugin_id = "dev_lab"
    name = "Dev Lab"
    description = "Developer inspection tools for exploring live Qt widgets, layout structure, and styles."
    category = ""
    standalone = True
    allow_name_override = False
    allow_icon_override = False
    preferred_icon = "inspect"

    def create_widget(self, services) -> QWidget:
        return DevLabPage(services, self.plugin_id)


class DevLabPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self.summary_label: QLabel | None = None
        self.status_label: QLabel | None = None
        self.path_list: QListWidget | None = None
        self.details_view: QPlainTextEdit | None = None
        self.inspect_button: QPushButton | None = None
        self.copy_button: QPushButton | None = None
        self._copy_feedback_timer: QTimer | None = None
        self.text_unlock_checkbox: QCheckBox | None = None
        self._last_snapshot: dict[str, object] = {}
        self._build_ui()
        self._apply_texts()
        self._refresh_state()
        self.services.ui_inspector.snapshot_changed.connect(self._handle_snapshot_changed)
        self.services.ui_inspector.inspect_mode_changed.connect(self._handle_inspect_mode_changed)
        self.services.ui_inspector.text_unlock_changed.connect(self._handle_text_unlock_changed)
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._apply_styles)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        outer.addWidget(self.description_label)

        control_card = QFrame()
        self.control_card = control_card
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(18, 18, 18, 18)
        control_layout.setSpacing(12)

        self.control_title = QLabel()
        control_layout.addWidget(self.control_title)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(10)

        self.text_unlock_checkbox = QCheckBox()
        self.text_unlock_checkbox.toggled.connect(self._toggle_text_unlock)
        button_row.addWidget(
            self.text_unlock_checkbox,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        button_row.addStretch(1)

        self.inspect_button = QPushButton()
        self.inspect_button.clicked.connect(self._toggle_inspecting)
        button_row.addWidget(
            self.inspect_button,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        control_layout.addLayout(button_row)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        control_layout.addWidget(self.status_label)
        outer.addWidget(control_card)

        content_row = QHBoxLayout()
        content_row.setSpacing(14)

        path_card = QFrame()
        self.path_card = path_card
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(18, 18, 18, 18)
        path_layout.setSpacing(10)
        self.path_title = QLabel()
        path_layout.addWidget(self.path_title)
        self.path_list = QListWidget()
        path_layout.addWidget(self.path_list, 1)
        content_row.addWidget(path_card, 1)

        detail_card = QFrame()
        self.detail_card = detail_card
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(18, 18, 18, 18)
        detail_layout.setSpacing(10)
        detail_header = QHBoxLayout()
        detail_header.setContentsMargins(0, 0, 0, 0)
        detail_header.setSpacing(8)
        self.details_title = QLabel()
        detail_header.addWidget(self.details_title)
        detail_header.addStretch(1)
        self.copy_button = QPushButton()
        self.copy_button.clicked.connect(self._copy_snapshot)
        detail_header.addWidget(self.copy_button, 0, Qt.AlignmentFlag.AlignRight)
        detail_layout.addLayout(detail_header)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        detail_layout.addWidget(self.summary_label)
        self.details_view = QPlainTextEdit()
        self.details_view.setReadOnly(True)
        apply_semantic_class(self.details_view, "output_class")
        detail_layout.addWidget(self.details_view, 1)
        content_row.addWidget(detail_card, 2)

        outer.addLayout(content_row, 1)
        self._copy_feedback_timer = QTimer(self)
        self._copy_feedback_timer.setSingleShot(True)
        self._copy_feedback_timer.timeout.connect(self._reset_copy_button_text)
        self._apply_styles()

    def _apply_styles(self, *_args) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.control_card, self.path_card, self.detail_card),
            summary_label=self.summary_label,
            title_size=26,
            title_weight=800,
            description_size=14,
            card_radius=16,
        )
        self.control_title.setStyleSheet(section_title_style(palette, size=18))
        self.path_title.setStyleSheet(section_title_style(palette, size=18))
        self.details_title.setStyleSheet(section_title_style(palette, size=18))
        self.status_label.setStyleSheet(muted_text_style(palette, size=13))
        self._reset_copy_button_text()

    def _apply_texts(self, *_args) -> None:
        self.title_label.setText(self.tr("title", "Dev Lab"))
        self.description_label.setText(
            self.tr(
                "description",
                "Inspect live widgets in the running interface. Start inspect mode, hover the UI, then left-click a widget to capture its structure, palette, and stylesheet details. If you need to move to another page first, use right-click navigation while inspect mode stays active.",
            )
        )
        self.path_title.setText(self.tr("path.title", "Parent Chain"))
        self.details_title.setText(self.tr("details.title", "Widget Details"))
        self.control_title.setText(self.tr("tools.title", "Tools"))
        self._reset_copy_button_text()
        self.text_unlock_checkbox.setText(
            self.tr("text_unlock", "Unlock static text selection across the app")
        )
        self._refresh_state()

    def _refresh_state(self) -> None:
        enabled = self.services.developer_mode_enabled()
        inspecting = self.services.ui_inspector.inspect_mode()
        text_unlock = self.services.ui_inspector.text_unlock_enabled()
        self.inspect_button.setEnabled(enabled)
        self.copy_button.setEnabled(bool(self._last_snapshot))
        self.text_unlock_checkbox.blockSignals(True)
        self.text_unlock_checkbox.setChecked(text_unlock)
        self.text_unlock_checkbox.setEnabled(enabled)
        self.text_unlock_checkbox.blockSignals(False)
        self.inspect_button.setText(
            self.tr("inspect.stop", "Stop inspecting") if inspecting else self.tr("inspect.start", "Start inspecting")
        )
        if not enabled:
            self.status_label.setText(
                self.tr("status.locked", "Developer mode is off. Enable it from Command Center to use Dev Lab.")
            )
        elif inspecting:
            self.status_label.setText(
                self.tr("status.live", "Inspect mode is active. Hover the app, left-click to capture a widget, and use right-click navigation if you need to move to another page first. Press Esc to cancel.")
            )
        elif text_unlock:
            self.status_label.setText(
                self.tr("status.text_unlock", "Inspector text unlock is active. Static app text can now be highlighted and copied where supported.")
            )
        else:
            self.status_label.setText(
                self.tr("status.ready", "Inspector is ready. Start inspect mode to capture a widget.")
            )
        if not self._last_snapshot:
            self.summary_label.setText(self.tr("summary.empty", "No widget selected yet."))
            self.details_view.setPlainText("")
            self.path_list.clear()

    def begin_inspecting(self) -> None:
        if self.services.developer_mode_enabled():
            self.services.ui_inspector.set_inspect_mode(True)

    def _toggle_inspecting(self) -> None:
        if not self.services.developer_mode_enabled():
            return
        self.services.ui_inspector.toggle_inspect_mode()

    def _handle_snapshot_changed(self, payload: dict[str, object]) -> None:
        self._last_snapshot = dict(payload)
        self.copy_button.setEnabled(True)
        class_name = str(payload.get("class_name") or "QWidget")
        object_name = str(payload.get("object_name") or "")
        geometry = str(payload.get("geometry") or "")
        self.summary_label.setText(
            self.tr(
                "summary.value",
                "Selected: {class_name}{object_suffix}\nGeometry: {geometry}",
                class_name=class_name,
                object_suffix=f"  #{object_name}" if object_name else "",
                geometry=geometry,
            )
        )
        self.path_list.clear()
        parent_chain = payload.get("parent_chain") or []
        for item in parent_chain:
            self.path_list.addItem(str(item))
        self.details_view.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
        self._refresh_state()

    def _handle_inspect_mode_changed(self, _enabled: bool) -> None:
        self._refresh_state()

    def _handle_text_unlock_changed(self, _enabled: bool) -> None:
        self._refresh_state()

    def _toggle_text_unlock(self, enabled: bool) -> None:
        if not self.services.developer_mode_enabled():
            return
        self.services.ui_inspector.set_text_unlock_enabled(enabled)

    def _copy_snapshot(self) -> None:
        if not self._last_snapshot:
            return
        QApplication.clipboard().setText(json.dumps(self._last_snapshot, indent=2, ensure_ascii=False))
        check_icon = icon_from_name("check", self)
        if check_icon is not None:
            self.copy_button.setIcon(check_icon)
        self.copy_button.setText(self.tr("copy.done", "Copied"))
        if self._copy_feedback_timer is not None:
            self._copy_feedback_timer.start(1400)

    def _reset_copy_button_text(self) -> None:
        copy_icon = icon_from_name("copy", self)
        self.copy_button.setIcon(copy_icon or self.copy_button.icon())
        self.copy_button.setText(self.tr("copy", "Copy snapshot"))
