from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from micro_toolkit.core.icon_registry import icon_choices, icon_from_name
from micro_toolkit.core.page_style import card_style, muted_text_style, page_title_style
from micro_toolkit.core.plugin_api import QtPlugin


class IconPickerDialog(QDialog):
    def __init__(self, parent: QWidget, options: list[tuple[str, str, object]], current_value: str = ""):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self._selected_icon = str(current_value or "").strip()
        self._options = options
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setWrapping(True)
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(8)
        self.grid.setIconSize(QSize(22, 22))
        self.grid.setGridSize(QSize(86, 62))
        self.grid.setWordWrap(True)
        self.grid.itemClicked.connect(self._choose_item)
        self.grid.itemDoubleClicked.connect(self._choose_item)
        layout.addWidget(self.grid)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        clear_button = QPushButton("Default")
        clear_button.clicked.connect(self._clear_selection)
        actions.addWidget(clear_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        self.resize(420, 320)

    def _populate(self) -> None:
        default_item = QListWidgetItem("Default")
        default_item.setData(Qt.ItemDataRole.UserRole, "")
        self.grid.addItem(default_item)
        if not self._selected_icon:
            self.grid.setCurrentItem(default_item)

        for icon_id, label, icon in self._options:
            item = QListWidgetItem(icon, label)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setData(Qt.ItemDataRole.UserRole, icon_id)
            self.grid.addItem(item)
            if icon_id == self._selected_icon:
                self.grid.setCurrentItem(item)

    def _choose_item(self, item: QListWidgetItem) -> None:
        self._selected_icon = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        self.accept()

    def _clear_selection(self) -> None:
        self._selected_icon = ""
        self.accept()

    def selected_icon(self) -> str:
        return self._selected_icon


class IconPickerButton(QToolButton):
    def __init__(self, page: "SettingsCenterPage", initial_value: str = ""):
        super().__init__(page)
        self._page = page
        self._selected_icon = str(initial_value or "").strip()
        self.setAutoRaise(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIconSize(QSize(18, 18))
        self.setFixedSize(32, 30)
        self.clicked.connect(self._open_picker)
        self._refresh()

    def _refresh(self) -> None:
        icon = icon_from_name(self._selected_icon, self._page) if self._selected_icon else None
        self.setIcon(icon or icon_from_name("plugin", self._page) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.setToolTip(self._page._pt("plugins.row.icon_picker", "Choose an icon"))

    def _open_picker(self) -> None:
        dialog = IconPickerDialog(self, self._page._icon_options(), self._selected_icon)
        anchor = self.mapToGlobal(self.rect().bottomLeft())
        dialog.move(anchor.x(), anchor.y() + 4)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._selected_icon = dialog.selected_icon()
            self._refresh()

    def selected_icon(self) -> str:
        return self._selected_icon


class SettingsCenterPlugin(QtPlugin):
    plugin_id = "settings_center"
    name = "Settings"
    description = "Application settings for appearance, automation, shortcuts, and plugin management."
    category = ""
    standalone = True
    translations = {
        "en": {
            "plugin.name": "Settings",
            "plugin.description": "Application settings for appearance, automation, shortcuts, and plugin management.",
        },
        "ar": {
            "plugin.name": "الإعدادات",
            "plugin.description": "إعدادات التطبيق للمظهر، والأتمتة، والاختصارات، وإدارة الإضافات.",
        },
    }

    def create_widget(self, services) -> QWidget:
        return SettingsCenterPage(services)


class SettingsCenterPage(QWidget):
    plugin_id = "settings_center"

    def __init__(self, services):
        super().__init__()
        self.services = services
        self.i18n = services.i18n
        self.shortcut_action_ids: list[str] = []
        self.plugin_row_map: dict[str, int] = {}
        self._building_plugin_table = False
        self._editing_plugin_id: str | None = None
        self._editing_snapshot: dict[str, str] = {}
        self._build_ui()
        self._populate_values()
        self._apply_texts()
        self.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 26px; font-weight: 700;")
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("font-size: 14px;")
        outer.addWidget(self.description_label)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)

        self.general_tab = QWidget()
        self.shortcuts_tab = QWidget()
        self.plugins_tab = QWidget()
        self.tabs.addTab(self.general_tab, "")
        self.tabs.addTab(self.shortcuts_tab, "")
        self.tabs.addTab(self.plugins_tab, "")

        self._build_general_tab()
        self._build_shortcuts_tab()
        self._build_plugins_tab()

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.reset_button = QPushButton()
        self.reset_button.clicked.connect(self._populate_values)
        actions.addWidget(self.reset_button)
        self.save_button = QPushButton()
        self.save_button.clicked.connect(self._save_settings)
        actions.addWidget(self.save_button)
        outer.addLayout(actions)

    def _build_general_tab(self) -> None:
        layout = QVBoxLayout(self.general_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self.output_card = QFrame()
        output_layout = QFormLayout(self.output_card)
        output_layout.setSpacing(12)
        self.output_label = QLabel()

        row = QHBoxLayout()
        self.output_dir_input = QLineEdit()
        row.addWidget(self.output_dir_input, 1)
        self.output_browse_button = QPushButton()
        self.output_browse_button.clicked.connect(self._browse_output_dir)
        row.addWidget(self.output_browse_button)
        output_layout.addRow(self.output_label, row)
        layout.addWidget(self.output_card)

        self.general_note = QLabel()
        self.general_note.setWordWrap(True)
        layout.addWidget(self.general_note)

        self.appearance_card = QFrame()
        form = QFormLayout(self.appearance_card)
        form.setSpacing(12)
        self.theme_label = QLabel()
        self.language_label = QLabel()
        self.scaling_label = QLabel()

        self.theme_combo = QComboBox()
        for mode, label in self.services.theme_manager.available_modes():
            self.theme_combo.addItem(label, mode)
        form.addRow(self.theme_label, self.theme_combo)

        self.language_combo = QComboBox()
        for code, label in self.i18n.available_languages():
            self.language_combo.addItem(label, code)
        form.addRow(self.language_label, self.language_combo)

        self.scaling_spin = QDoubleSpinBox()
        self.scaling_spin.setRange(0.85, 1.6)
        self.scaling_spin.setSingleStep(0.05)
        self.scaling_spin.setDecimals(2)
        form.addRow(self.scaling_label, self.scaling_spin)

        layout.addWidget(self.appearance_card)
        self.appearance_note = QLabel()
        self.appearance_note.setWordWrap(True)
        layout.addWidget(self.appearance_note)

        self.automation_card = QFrame()
        card_layout = QVBoxLayout(self.automation_card)
        card_layout.setSpacing(10)

        self.minimize_to_tray_checkbox = QCheckBox()
        card_layout.addWidget(self.minimize_to_tray_checkbox)
        self.close_to_tray_checkbox = QCheckBox()
        card_layout.addWidget(self.close_to_tray_checkbox)
        self.run_on_startup_checkbox = QCheckBox()
        card_layout.addWidget(self.run_on_startup_checkbox)
        self.start_minimized_checkbox = QCheckBox()
        card_layout.addWidget(self.start_minimized_checkbox)

        layout.addWidget(self.automation_card)

        self.autostart_status_label = QLabel()
        self.autostart_status_label.setWordWrap(True)
        layout.addWidget(self.autostart_status_label)
        layout.addStretch(1)

    def _build_shortcuts_tab(self) -> None:
        layout = QVBoxLayout(self.shortcuts_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self.shortcut_note = QLabel()
        self.shortcut_note.setWordWrap(True)
        layout.addWidget(self.shortcut_note)

        self.shortcut_status_label = QLabel()
        self.shortcut_status_label.setWordWrap(True)
        layout.addWidget(self.shortcut_status_label)

        shortcut_actions = QHBoxLayout()
        self.start_helper_button = QPushButton()
        self.start_helper_button.clicked.connect(self._start_hotkey_helper)
        shortcut_actions.addWidget(self.start_helper_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.stop_helper_button = QPushButton()
        self.stop_helper_button.clicked.connect(self._stop_hotkey_helper)
        shortcut_actions.addWidget(self.stop_helper_button, 0, Qt.AlignmentFlag.AlignLeft)
        shortcut_actions.addStretch(1)
        layout.addLayout(shortcut_actions)

        self.shortcut_table = QTableWidget(0, 3)
        self.shortcut_table.setAlternatingRowColors(True)
        self.shortcut_table.verticalHeader().setVisible(False)
        self.shortcut_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.shortcut_table, 1)

    def _build_plugins_tab(self) -> None:
        layout = QVBoxLayout(self.plugins_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self.plugins_note = QLabel()
        self.plugins_note.setWordWrap(True)
        layout.addWidget(self.plugins_note)

        self.plugins_table = QTableWidget(0, 11)
        self.plugins_table.setAlternatingRowColors(True)
        self.plugins_table.verticalHeader().setVisible(False)
        self.plugins_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self.plugins_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.plugins_table, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.import_file_button = self._make_action_button("open", self._import_plugin_file)
        actions.addWidget(self.import_file_button)
        self.import_folder_button = self._make_action_button("folder-open", self._import_plugin_folder)
        actions.addWidget(self.import_folder_button)
        self.import_backup_button = self._make_action_button("download", self._import_backup)
        actions.addWidget(self.import_backup_button)
        self.export_selected_button = self._make_action_button("save", self._export_selected_plugins)
        actions.addWidget(self.export_selected_button)
        self.export_all_button = self._make_action_button("database", self._export_all_plugins)
        actions.addWidget(self.export_all_button)
        self.apply_plugin_state_button = self._make_action_button("check", self._apply_plugin_states)
        actions.addWidget(self.apply_plugin_state_button)
        self.refresh_plugins_button = self._make_action_button("sync", self._populate_plugin_table)
        actions.addWidget(self.refresh_plugins_button)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _populate_values(self) -> None:
        self.output_dir_input.setText(str(self.services.default_output_path()))
        self._set_combo_value(self.theme_combo, self.services.theme_manager.current_mode())
        self._set_combo_value(self.language_combo, self.i18n.current_language())
        self.scaling_spin.setValue(float(self.services.config.get("ui_scaling") or 1.0))
        self.minimize_to_tray_checkbox.setChecked(bool(self.services.config.get("minimize_to_tray")))
        self.close_to_tray_checkbox.setChecked(bool(self.services.config.get("close_to_tray")))
        self.run_on_startup_checkbox.setChecked(bool(self.services.autostart_manager.is_enabled()))
        self.start_minimized_checkbox.setChecked(bool(self.services.config.get("start_minimized")))
        self._populate_shortcuts()
        self._populate_plugin_table()
        self._refresh_autostart_status()
        self._refresh_shortcut_status()

    def _populate_shortcuts(self) -> None:
        bindings = self.services.shortcut_manager.list_bindings()
        self.shortcut_action_ids = [binding.action_id for binding in bindings]
        self.shortcut_table.setRowCount(len(bindings))
        self.shortcut_table.setHorizontalHeaderLabels(
            [
                self._pt("shortcuts.action", "Action"),
                self._pt("shortcuts.sequence", "Shortcut"),
                self._pt("shortcuts.scope", "Scope"),
            ]
        )
        scope_options = self.services.shortcut_manager.available_scopes()
        for row_index, binding in enumerate(bindings):
            title_item = QTableWidgetItem(binding.title)
            title_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.shortcut_table.setItem(row_index, 0, title_item)
            self.shortcut_table.setItem(row_index, 1, QTableWidgetItem(binding.sequence or binding.default_sequence))

            combo = QComboBox()
            for scope_id, label in scope_options:
                combo.addItem(label, scope_id)
            self._set_combo_value(combo, binding.scope)
            self.shortcut_table.setCellWidget(row_index, 2, combo)
        self._refresh_shortcut_status()

    def _populate_plugin_table(self) -> None:
        self._building_plugin_table = True
        try:
            specs = self.services.manageable_plugin_specs(include_disabled=True)
            self.plugin_row_map = {}
            self.plugins_table.setRowCount(len(specs))
            self.plugins_table.setHorizontalHeaderLabels(
                [
                    self._pt("plugins.manage", "Select"),
                    self._pt("plugins.icon", "Icon"),
                    self._pt("plugins.name", "Plugin"),
                    self._pt("plugins.category", "Category"),
                    self._pt("plugins.source", "Source"),
                    self._pt("plugins.trusted", "Trusted"),
                    self._pt("plugins.enabled", "Enabled"),
                    self._pt("plugins.hidden", "Hidden"),
                    self._pt("plugins.risk", "Risk"),
                    self._pt("plugins.status", "Status"),
                    self._pt("plugins.path", "Path"),
                ]
            )
            language = self.services.i18n.current_language()
            for row_index, spec in enumerate(specs):
                self.plugin_row_map[spec.plugin_id] = row_index

                self.plugins_table.setCellWidget(row_index, 0, self._row_action_widget(spec, selected=False))
                self.plugins_table.removeCellWidget(row_index, 1)

                icon_item = QTableWidgetItem(self._icon_display_text(spec))
                icon_item.setIcon(self._icon_display_icon(spec) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
                icon_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 1, icon_item)

                name_item = QTableWidgetItem(self.services.plugin_display_name(spec))
                name_item.setData(Qt.ItemDataRole.UserRole, spec.plugin_id)
                name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 2, name_item)

                category_item = QTableWidgetItem(spec.localized_category(language) or self._pt("plugins.standalone", "Standalone"))
                category_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 3, category_item)

                source_item = QTableWidgetItem(spec.source_type.title())
                source_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 4, source_item)

                trusted_item = QTableWidgetItem()
                trusted_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                if spec.source_type != "builtin":
                    trusted_item.setFlags(trusted_flags)
                else:
                    trusted_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                trusted_item.setCheckState(Qt.CheckState.Checked if spec.trusted else Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 5, trusted_item)

                enabled_item = QTableWidgetItem()
                enabled_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                hidden_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                enabled_item.setFlags(enabled_flags)
                enabled_item.setCheckState(Qt.CheckState.Checked if spec.enabled else Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 6, enabled_item)

                hidden_item = QTableWidgetItem()
                hidden_item.setFlags(hidden_flags)
                hidden_item.setCheckState(Qt.CheckState.Checked if spec.hidden else Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 7, hidden_item)

                risk_item = QTableWidgetItem(spec.risk_level.title())
                risk_item.setToolTip(self._plugin_review_details(spec))
                risk_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self._style_risk_item(risk_item, spec.risk_level)
                self.plugins_table.setItem(row_index, 8, risk_item)

                status_text = self._plugin_status_text(spec)
                status_item = QTableWidgetItem(status_text)
                status_item.setToolTip(self._plugin_review_details(spec))
                status_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self._style_risk_item(status_item, spec.risk_level)
                self.plugins_table.setItem(row_index, 9, status_item)

                path_item = QTableWidgetItem(str(spec.file_path))
                path_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 10, path_item)
        finally:
            self._building_plugin_table = False
        self.plugins_table.resizeColumnToContents(0)
        self.plugins_table.resizeColumnToContents(1)

    def _make_action_button(self, icon_name: str, handler) -> QToolButton:
        button = QToolButton()
        button.setAutoRaise(False)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setIcon(icon_from_name(icon_name, self) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(34, 34)
        button.clicked.connect(handler)
        return button

    def _row_action_widget(self, spec, *, selected: bool) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)

        export_check = QCheckBox()
        export_check.setChecked(selected)
        export_check.setToolTip(self._pt("plugins.export", "Select for export"))
        layout.addWidget(export_check)

        if self._editing_plugin_id == spec.plugin_id:
            save_button = QToolButton()
            save_button.setAutoRaise(True)
            save_button.setIcon(icon_from_name("check", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
            save_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            save_button.setToolTip(self._pt("plugins.row.save", "Save row edits"))
            save_button.setIconSize(QSize(16, 16))
            save_button.setFixedSize(24, 24)
            save_button.setStyleSheet("QToolButton { background: #e7f5ec; border: 1px solid #9ad0ab; border-radius: 9px; padding: 2px; }")
            save_button.clicked.connect(lambda _checked=False, pid=spec.plugin_id: self._save_row_edit(pid))
            layout.addWidget(save_button)

            cancel_button = QToolButton()
            cancel_button.setAutoRaise(True)
            cancel_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
            cancel_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            cancel_button.setToolTip(self._pt("plugins.row.cancel", "Cancel row edits"))
            cancel_button.setIconSize(QSize(16, 16))
            cancel_button.setFixedSize(24, 24)
            cancel_button.setStyleSheet("QToolButton { background: #f9ece8; border: 1px solid #d7aba3; border-radius: 9px; padding: 2px; }")
            cancel_button.clicked.connect(lambda _checked=False, pid=spec.plugin_id: self._cancel_row_edit(pid))
            layout.addWidget(cancel_button)
        else:
            edit_button = QToolButton()
            edit_button.setAutoRaise(True)
            edit_button.setIcon(icon_from_name("wrench", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
            edit_button.setIconSize(QSize(15, 15))
            edit_button.setFixedSize(22, 22)
            edit_button.setToolTip(self._pt("plugins.row.edit", "Edit plugin row"))
            edit_button.clicked.connect(lambda _checked=False, pid=spec.plugin_id: self._begin_row_edit(pid))
            layout.addWidget(edit_button)
        return container

    def _begin_row_edit(self, plugin_id: str) -> None:
        if self._editing_plugin_id and self._editing_plugin_id != plugin_id:
            self._cancel_row_edit(self._editing_plugin_id, repopulate=False)
        self._editing_plugin_id = plugin_id
        self._editing_snapshot = dict(self.services.plugin_override(plugin_id))
        self._set_row_editing(plugin_id, True)

    def _save_row_edit(self, plugin_id: str) -> None:
        spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
        row = self.plugin_row_map.get(plugin_id)
        if spec is None or row is None:
            return
        name_item = self.plugins_table.item(row, 2)
        name_override = ""
        if spec.allow_name_override and name_item is not None:
            typed_name = name_item.text().strip()
            if typed_name and typed_name != spec.localized_name(self.i18n.current_language()):
                name_override = typed_name

        icon_override = self._editing_snapshot.get("icon", "")
        if spec.allow_icon_override:
            icon_widget = self.plugins_table.cellWidget(row, 1)
            if isinstance(icon_widget, IconPickerButton):
                icon_override = icon_widget.selected_icon()

        self.services.set_plugin_override(plugin_id, display_name=name_override, icon=icon_override)
        self._editing_plugin_id = None
        self._editing_snapshot = {}
        self._populate_plugin_table()

    def _cancel_row_edit(self, plugin_id: str, *, repopulate: bool = True) -> None:
        self._editing_plugin_id = None
        self._editing_snapshot = {}
        if repopulate:
            self._populate_plugin_table()

    def _set_row_editing(self, plugin_id: str, editing: bool) -> None:
        row = self.plugin_row_map.get(plugin_id)
        spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
        if row is None or spec is None:
            return

        selected = self._is_row_selected_for_export(row)
        self.plugins_table.setCellWidget(row, 0, self._row_action_widget(spec, selected=selected))

        name_item = self.plugins_table.item(row, 2)
        if name_item is not None:
            flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            if editing and spec.allow_name_override:
                flags |= Qt.ItemFlag.ItemIsEditable
                if not name_item.text().strip():
                    name_item.setText(spec.localized_name(self.i18n.current_language()))
            name_item.setFlags(flags)

        if editing and spec.allow_icon_override:
            picker = IconPickerButton(self, self._editing_snapshot.get("icon", ""))
            self.plugins_table.setCellWidget(row, 1, picker)
        else:
            self.plugins_table.removeCellWidget(row, 1)
            icon_item = self.plugins_table.item(row, 1)
            if icon_item is not None:
                icon_item.setText(self._icon_display_text(spec))
                icon_item.setIcon(self._icon_display_icon(spec) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.plugins_table.resizeColumnToContents(0)
        self.plugins_table.resizeColumnToContents(1)

    def _is_row_selected_for_export(self, row: int) -> bool:
        widget = self.plugins_table.cellWidget(row, 0)
        if widget is None:
            return False
        checkbox = widget.findChild(QCheckBox)
        return bool(checkbox is not None and checkbox.isChecked())

    def _icon_display_text(self, spec) -> str:
        override = self.services.plugin_icon_override(spec)
        return self._icon_display_name(override)

    def _icon_display_name(self, icon_value: str) -> str:
        if not icon_value:
            return ""
        options = {icon_id: label for icon_id, label, _icon in self._icon_options()}
        return options.get(icon_value, Path(icon_value).name or icon_value)

    def _icon_display_icon(self, spec):
        override = self.services.plugin_icon_override(spec)
        effective = override or str(spec.preferred_icon or "").strip()
        return icon_from_name(effective, self) if effective else icon_from_name("plugin", self)

    def _browse_output_dir(self) -> None:
        current = self.output_dir_input.text().strip() or str(self.services.default_output_path())
        selected = QFileDialog.getExistingDirectory(self, self._pt("output.browse", "Choose output folder"), current)
        if selected:
            self.output_dir_input.setText(selected)

    def _save_settings(self) -> None:
        output_dir = Path(self.output_dir_input.text().strip() or self.services.output_root)
        output_dir.mkdir(parents=True, exist_ok=True)
        shortcut_updates: dict[str, dict[str, str]] = {}
        for row_index, action_id in enumerate(self.shortcut_action_ids):
            sequence_item = self.shortcut_table.item(row_index, 1)
            combo = self.shortcut_table.cellWidget(row_index, 2)
            shortcut_updates[action_id] = {
                "sequence": sequence_item.text().strip() if sequence_item is not None else "",
                "scope": combo.currentData() if combo is not None else "application",
            }

        self.services.config.update_many(
            {
                "default_output_path": str(output_dir),
                "ui_scaling": float(self.scaling_spin.value()),
                "minimize_to_tray": self.minimize_to_tray_checkbox.isChecked(),
                "close_to_tray": self.close_to_tray_checkbox.isChecked(),
                "run_on_startup": self.run_on_startup_checkbox.isChecked(),
                "start_minimized": self.start_minimized_checkbox.isChecked(),
                "appearance_mode": str(self.theme_combo.currentData() or "system"),
                "language": str(self.language_combo.currentData() or "en"),
            }
        )

        if self.services.application is not None:
            self.services.i18n.apply(self.services.application)
            self.services.theme_manager.apply(self.services.application)
        self.services.autostart_manager.set_enabled(
            self.run_on_startup_checkbox.isChecked(),
            start_minimized=self.start_minimized_checkbox.isChecked(),
        )
        self.services.shortcut_manager.update_bindings(shortcut_updates)
        self.services.tray_manager.sync_visibility()
        self._refresh_autostart_status()
        self._refresh_shortcut_status()
        QMessageBox.information(self, self._pt("saved.title", "Settings saved"), self._pt("saved.body", "Your application settings were updated."))

    def _refresh_shortcut_status(self) -> None:
        shortcut_manager = self.services.shortcut_manager
        helper_manager = self.services.hotkey_helper_manager
        if shortcut_manager.direct_global_hotkeys_supported():
            self.shortcut_status_label.setText(
                self._pt(
                    "shortcuts.status.available",
                    "Global shortcut registration is available in this session.",
                )
            )
            self.start_helper_button.setVisible(False)
            self.stop_helper_button.setVisible(False)
            return

        if helper_manager.is_active():
            self.shortcut_status_label.setText(
                self._pt(
                    "shortcuts.status.helper_active",
                    "The elevated hotkey helper is active for this session. Global shortcuts will be routed through the helper process.",
                )
            )
            self.start_helper_button.setVisible(False)
            self.stop_helper_button.setVisible(True)
            self.stop_helper_button.setText(self._pt("shortcuts.stop_helper", "Stop Hotkey Helper"))
            return

        reason = helper_manager.helper_reason() or self._pt(
            "shortcuts.status.unavailable",
            "Global shortcuts are unavailable in this session.",
        )
        if helper_manager.can_request_helper():
            self.shortcut_status_label.setText(
                self._pt(
                    "shortcuts.status.helper_available",
                    "Global shortcuts are currently unavailable. {reason} Start the hotkey helper if you want global capture without elevating the main app.",
                    reason=reason,
                )
            )
            self.start_helper_button.setVisible(True)
            self.start_helper_button.setText(self._pt("shortcuts.start_helper", "Start Hotkey Helper"))
            self.stop_helper_button.setVisible(False)
            return

        self.shortcut_status_label.setText(
            self._pt(
                "shortcuts.status.no_helper",
                "Global shortcuts are currently unavailable. {reason}",
                reason=reason,
            )
        )
        self.start_helper_button.setVisible(False)
        self.stop_helper_button.setVisible(False)

    def _start_hotkey_helper(self) -> None:
        try:
            result = self.services.command_registry.execute("app.start_hotkey_helper")
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._pt("shortcuts.helper_failed.title", "Helper unavailable"),
                str(exc),
            )
            return
        QMessageBox.information(
            self,
            self._pt("shortcuts.helper_started.title", "Helper started"),
            str(result.get("message", self._pt("shortcuts.helper_started.body", "The hotkey helper is now active for this session."))),
        )
        self._refresh_shortcut_status()

    def _stop_hotkey_helper(self) -> None:
        self.services.command_registry.execute("app.stop_hotkey_helper")
        self._refresh_shortcut_status()

    def _icon_options(self) -> list[tuple[str, str, object]]:
        rows: list[tuple[str, str, object]] = []
        for icon_id, fallback_label, icon in icon_choices(self):
            label = self._pt(f"plugins.icon.{icon_id.replace('-', '_')}", fallback_label)
            rows.append((icon_id, label, icon))
        return rows

    def _plugin_status_text(self, spec) -> str:
        if spec.quarantined:
            return self._pt("plugins.status.quarantined", "Quarantined")
        if spec.source_type == "custom" and not spec.trusted:
            return self._pt("plugins.status.review", "Pending Review")
        if not spec.enabled:
            return self._pt("plugins.status.disabled", "Disabled")
        if spec.last_error:
            return self._pt("plugins.status.error", "Error Recorded")
        return self._pt("plugins.status.ready", "Ready")

    def _plugin_review_details(self, spec) -> str:
        details: list[str] = []
        if spec.risk_summary:
            details.append(spec.risk_summary)
        if spec.last_error:
            details.append(self._pt("plugins.error_detail", "Last error: {error}", error=spec.last_error))
        if spec.failure_count:
            details.append(
                self._pt(
                    "plugins.failure_detail",
                    "Failure count: {count}",
                    count=str(spec.failure_count),
                )
            )
        return "\n".join(details)

    def _style_risk_item(self, item: QTableWidgetItem, risk_level: str) -> None:
        normalized = (risk_level or "low").lower()
        if normalized in {"high", "critical"}:
            item.setForeground(QColor("#c62828"))
        elif normalized == "medium":
            item.setForeground(QColor("#b26a00"))
        else:
            item.setForeground(QColor("#1b5e20"))

    def _apply_plugin_states(self) -> None:
        specs = self.services.manageable_plugin_specs(include_disabled=True)
        pending_risk_review: list[str] = []
        forced_block: list[str] = []
        updates: list[tuple[str, str, bool, bool, bool, bool]] = []
        language = self.services.i18n.current_language()
        for spec in specs:
            row_index = self.plugin_row_map.get(spec.plugin_id)
            if row_index is None:
                continue
            trusted_item = self.plugins_table.item(row_index, 5)
            enabled_item = self.plugins_table.item(row_index, 6)
            hidden_item = self.plugins_table.item(row_index, 7)
            trusted = trusted_item.checkState() == Qt.CheckState.Checked if trusted_item is not None else spec.trusted
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item is not None else True
            hidden = hidden_item.checkState() == Qt.CheckState.Checked if hidden_item is not None else False
            if spec.source_type == "builtin":
                trusted = True
            if spec.source_type == "custom" and spec.risk_level == "critical":
                trusted = False
                enabled = False
                forced_block.append(spec.localized_name(language))
            elif spec.source_type == "custom" and trusted and not spec.trusted and spec.risk_level in {"medium", "high"}:
                pending_risk_review.append(spec.localized_name(language))
            if spec.source_type == "custom" and not trusted:
                enabled = False
            updates.append((spec.plugin_id, spec.source_type, trusted, enabled, hidden, spec.risk_level == "critical"))

        if pending_risk_review:
            response = QMessageBox.question(
                self,
                self._pt("plugins.review_prompt.title", "Trust custom plugins?"),
                self._pt(
                    "plugins.review_prompt.body",
                    "The following custom plugins contain medium or high risk markers from the static safety scan:\n\n{plugins}\n\nTrusting them will allow the app to import and run their code. Only continue if you trust the author and reviewed the plugin contents.",
                    plugins="\n".join(f"- {name}" for name in pending_risk_review),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                for index, (plugin_id, source_type, trusted, enabled, hidden, force_quarantine) in enumerate(updates):
                    if source_type == "custom" and trusted:
                        updates[index] = (plugin_id, source_type, False, False, hidden, force_quarantine)

        for plugin_id, source_type, trusted, enabled, hidden, force_quarantine in updates:
            if force_quarantine:
                self.services.plugin_state_manager.quarantine(
                    plugin_id,
                    self._pt(
                        "plugins.blocked.reason",
                        "The static safety scan detected critical-risk patterns. This plugin remains quarantined until removed or replaced.",
                    ),
                )
                self.services.plugin_state_manager.set_hidden(plugin_id, hidden)
                continue
            self.services.plugin_state_manager.set_trusted(plugin_id, trusted)
            self.services.plugin_state_manager.set_enabled(plugin_id, enabled)
            self.services.plugin_state_manager.set_hidden(plugin_id, hidden)

        if forced_block:
            QMessageBox.warning(
                self,
                self._pt("plugins.blocked.title", "Plugins blocked"),
                self._pt(
                    "plugins.blocked.body",
                    "These custom plugins remain blocked because the static scan detected critical-risk patterns:\n\n{plugins}",
                    plugins="\n".join(f"- {name}" for name in forced_block),
                ),
            )
        QMessageBox.information(
            self,
            self._pt("plugins.applied.title", "Plugin settings updated"),
            self._pt("plugins.applied.body", "Plugin trust, visibility, and enabled state were updated."),
        )
        self.services.reload_plugins()

    def _import_plugin_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._pt("plugins.import_file", "Import plugin file"),
            str(Path.home()),
            "Python Files (*.py)",
        )
        if not file_path:
            return
        try:
            plugin_ids = self.services.plugin_package_manager.import_plugin_file(Path(file_path))
        except Exception as exc:
            QMessageBox.critical(self, self._pt("plugins.import_failed.title", "Import failed"), str(exc))
            return
        QMessageBox.information(
            self,
            self._pt("plugins.imported.title", "Plugin imported"),
            self._pt("plugins.imported.body", "Imported plugins: {plugins}. They were added disabled and untrusted pending review.", plugins=", ".join(plugin_ids)),
        )
        self.services.reload_plugins()

    def _import_plugin_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(self, self._pt("plugins.import_folder", "Import plugin folder"), str(Path.home()))
        if not folder_path:
            return
        try:
            plugin_ids = self.services.plugin_package_manager.import_plugin_folder(Path(folder_path))
        except Exception as exc:
            QMessageBox.critical(self, self._pt("plugins.import_failed.title", "Import failed"), str(exc))
            return
        QMessageBox.information(
            self,
            self._pt("plugins.imported.title", "Plugin imported"),
            self._pt("plugins.imported.body", "Imported plugins: {plugins}. They were added disabled and untrusted pending review.", plugins=", ".join(plugin_ids)),
        )
        self.services.reload_plugins()

    def _import_backup(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._pt("plugins.import_backup", "Import plugin backup"),
            str(Path.home()),
            "Plugin Backup (*.zip)",
        )
        if not file_path:
            return
        try:
            plugin_ids = self.services.plugin_package_manager.import_backup(Path(file_path))
        except Exception as exc:
            QMessageBox.critical(self, self._pt("plugins.import_failed.title", "Import failed"), str(exc))
            return
        QMessageBox.information(
            self,
            self._pt("plugins.imported.title", "Plugin imported"),
            self._pt("plugins.imported.body", "Imported plugins: {plugins}. They were added disabled and untrusted pending review.", plugins=", ".join(plugin_ids)),
        )
        self.services.reload_plugins()

    def _export_selected_plugins(self) -> None:
        specs = self._selected_export_specs()
        if not specs:
            QMessageBox.warning(self, self._pt("plugins.export_failed.title", "Nothing selected"), self._pt("plugins.export_failed.body", "Select at least one plugin to export."))
            return
        self._export_specs(specs)

    def _export_all_plugins(self) -> None:
        specs = self.services.manageable_plugin_specs(include_disabled=True)
        self._export_specs(specs)

    def _export_specs(self, specs) -> None:
        suggested = Path.home() / "micro_toolkit_plugins_backup.zip"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self._pt("plugins.export_dialog", "Export plugin backup"),
            str(suggested),
            "Plugin Backup (*.zip)",
        )
        if not file_path:
            return
        destination = Path(file_path)
        if destination.suffix.lower() != ".zip":
            destination = destination.with_suffix(".zip")
        try:
            exported = self.services.plugin_package_manager.export_plugins(specs, destination)
        except Exception as exc:
            QMessageBox.critical(self, self._pt("plugins.export_failed.title", "Export failed"), str(exc))
            return
        QMessageBox.information(
            self,
            self._pt("plugins.exported.title", "Plugins exported"),
            self._pt("plugins.exported.body", "Plugin backup written to {path}", path=str(exported)),
        )

    def _selected_export_specs(self):
        specs_by_id = {
            spec.plugin_id: spec
            for spec in self.services.manageable_plugin_specs(include_disabled=True)
        }
        selected = []
        for row_index in range(self.plugins_table.rowCount()):
            name_item = self.plugins_table.item(row_index, 2)
            if name_item is None:
                continue
            if not self._is_row_selected_for_export(row_index):
                continue
            plugin_id = name_item.data(Qt.ItemDataRole.UserRole)
            spec = specs_by_id.get(plugin_id)
            if spec is not None:
                selected.append(spec)
        return selected

    def _refresh_autostart_status(self) -> None:
        enabled = self.services.autostart_manager.is_enabled()
        key = "startup.enabled" if enabled else "startup.disabled"
        self.autostart_status_label.setText(self._pt(key, "Autostart is disabled."))

    def _apply_texts(self) -> None:
        palette = self.services.theme_manager.current_palette()
        self._apply_theme_styles()
        self.title_label.setText(self._pt("title", "Settings"))
        self.description_label.setText(
            self._pt(
                "description",
                "Control appearance, language, startup behavior, tray behavior, shortcuts, and plugin management from one place.",
            )
        )
        self.description_label.setStyleSheet(f"font-size: 14px; color: {palette.text_muted};")
        self.tabs.setTabText(0, self._pt("tab.general", "General"))
        self.tabs.setTabText(1, self._pt("tab.shortcuts", "Shortcuts"))
        self.tabs.setTabText(2, self._pt("tab.plugins", "Plugins"))

        self.output_label.setText(self._pt("output.label", "Default output folder"))
        self.output_browse_button.setText(self._pt("output.browse_button", "Browse"))
        self.general_note.setText(self._pt("output.note", "Tools export into this folder by default."))

        self.theme_label.setText(self._pt("theme.label", "Theme"))
        self.language_label.setText(self._pt("language.label", "Language"))
        self.scaling_label.setText(self._pt("scaling.label", "UI scaling"))
        self.appearance_note.setText(self._pt("appearance.note", "Theme and language changes apply immediately."))

        self.minimize_to_tray_checkbox.setText(self._pt("tray.minimize", "Minimize to system tray"))
        self.close_to_tray_checkbox.setText(self._pt("tray.close", "Close to system tray"))
        self.run_on_startup_checkbox.setText(self._pt("startup.run", "Start on system login"))
        self.start_minimized_checkbox.setText(self._pt("startup.minimized", "Start minimized"))

        self.shortcut_note.setText(
            self._pt(
                "shortcuts.note",
                "Application shortcuts are always available while the app is focused. Global shortcuts are optional and may depend on desktop permissions.",
            )
        )
        self.plugins_note.setText(
            self._pt(
                "plugins.note",
                "Manage built-in and custom plugins here. Edit display name and icon inline per row, then trust, enable, hide, import, export, or review plugins from one place.",
            )
        )
        self.import_file_button.setToolTip(self._pt("plugins.import_file_button", "Import File"))
        self.import_folder_button.setToolTip(self._pt("plugins.import_folder_button", "Import Folder"))
        self.import_backup_button.setToolTip(self._pt("plugins.import_backup_button", "Import Backup"))
        self.export_selected_button.setToolTip(self._pt("plugins.export_selected", "Export Selected"))
        self.export_all_button.setToolTip(self._pt("plugins.export_all", "Export All"))
        self.apply_plugin_state_button.setToolTip(self._pt("plugins.apply", "Apply Plugin Changes"))
        self.refresh_plugins_button.setToolTip(self._pt("plugins.refresh", "Refresh"))

        self.reset_button.setText(self._pt("reset", "Reset"))
        self.save_button.setText(self._pt("save", "Save settings"))
        self._populate_shortcuts()
        self._populate_plugin_table()
        self._refresh_autostart_status()

    def _set_combo_value(self, combo: QComboBox, value) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()
        self._populate_plugin_table()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        self.title_label.setStyleSheet(page_title_style(palette, size=26, weight=700))
        self.description_label.setStyleSheet(muted_text_style(palette))
        for frame in (
            self.output_card,
            self.appearance_card,
            self.automation_card,
        ):
            frame.setStyleSheet(card_style(palette))
        for label in (
            self.general_note,
            self.appearance_note,
            self.autostart_status_label,
            self.shortcut_note,
            self.shortcut_status_label,
            self.plugins_note,
        ):
            label.setStyleSheet(muted_text_style(palette))
