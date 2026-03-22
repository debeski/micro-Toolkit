from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin


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
        self._build_ui()
        self._populate_values()
        self._apply_texts()
        self.i18n.language_changed.connect(self._apply_texts)

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
        self.description_label.setStyleSheet("font-size: 14px; color: palette(mid);")
        outer.addWidget(self.description_label)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)

        self.general_tab = QWidget()
        self.appearance_tab = QWidget()
        self.automation_tab = QWidget()
        self.shortcuts_tab = QWidget()
        self.plugins_tab = QWidget()
        self.tabs.addTab(self.general_tab, "")
        self.tabs.addTab(self.appearance_tab, "")
        self.tabs.addTab(self.automation_tab, "")
        self.tabs.addTab(self.shortcuts_tab, "")
        self.tabs.addTab(self.plugins_tab, "")

        self._build_general_tab()
        self._build_appearance_tab()
        self._build_automation_tab()
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
        layout.addStretch(1)

    def _build_appearance_tab(self) -> None:
        layout = QVBoxLayout(self.appearance_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

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
        layout.addStretch(1)

    def _build_automation_tab(self) -> None:
        layout = QVBoxLayout(self.automation_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

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

        self.plugins_table = QTableWidget(0, 7)
        self.plugins_table.setAlternatingRowColors(True)
        self.plugins_table.verticalHeader().setVisible(False)
        self.plugins_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.plugins_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.plugins_table, 1)

        row_one = QHBoxLayout()
        self.import_file_button = QPushButton()
        self.import_file_button.clicked.connect(self._import_plugin_file)
        row_one.addWidget(self.import_file_button)
        self.import_folder_button = QPushButton()
        self.import_folder_button.clicked.connect(self._import_plugin_folder)
        row_one.addWidget(self.import_folder_button)
        self.import_backup_button = QPushButton()
        self.import_backup_button.clicked.connect(self._import_backup)
        row_one.addWidget(self.import_backup_button)
        row_one.addStretch(1)
        layout.addLayout(row_one)

        row_two = QHBoxLayout()
        self.export_selected_button = QPushButton()
        self.export_selected_button.clicked.connect(self._export_selected_plugins)
        row_two.addWidget(self.export_selected_button)
        self.export_all_button = QPushButton()
        self.export_all_button.clicked.connect(self._export_all_plugins)
        row_two.addWidget(self.export_all_button)
        self.apply_plugin_state_button = QPushButton()
        self.apply_plugin_state_button.clicked.connect(self._apply_plugin_states)
        row_two.addWidget(self.apply_plugin_state_button)
        self.refresh_plugins_button = QPushButton()
        self.refresh_plugins_button.clicked.connect(self._populate_plugin_table)
        row_two.addWidget(self.refresh_plugins_button)
        row_two.addStretch(1)
        layout.addLayout(row_two)

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
            specs = self.services.plugin_manager.discover_plugins(include_disabled=True)
            self.plugin_row_map = {}
            self.plugins_table.setRowCount(len(specs))
            self.plugins_table.setHorizontalHeaderLabels(
                [
                    self._pt("plugins.export", "Export"),
                    self._pt("plugins.name", "Plugin"),
                    self._pt("plugins.category", "Category"),
                    self._pt("plugins.source", "Source"),
                    self._pt("plugins.enabled", "Enabled"),
                    self._pt("plugins.hidden", "Hidden"),
                    self._pt("plugins.path", "Path"),
                ]
            )
            language = self.services.i18n.current_language()
            for row_index, spec in enumerate(specs):
                self.plugin_row_map[spec.plugin_id] = row_index

                export_item = QTableWidgetItem()
                export_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                export_item.setCheckState(Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 0, export_item)

                name_item = QTableWidgetItem(spec.localized_name(language))
                name_item.setData(Qt.ItemDataRole.UserRole, spec.plugin_id)
                name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 1, name_item)

                category_item = QTableWidgetItem(spec.localized_category(language) or self._pt("plugins.standalone", "Standalone"))
                category_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 2, category_item)

                source_item = QTableWidgetItem(spec.source_type.title())
                source_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 3, source_item)

                enabled_item = QTableWidgetItem()
                enabled_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                hidden_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                if spec.plugin_id != "settings_center":
                    enabled_item.setFlags(enabled_flags)
                else:
                    enabled_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                enabled_item.setCheckState(Qt.CheckState.Checked if spec.enabled else Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 4, enabled_item)

                hidden_item = QTableWidgetItem()
                if spec.plugin_id != "settings_center":
                    hidden_item.setFlags(hidden_flags)
                else:
                    hidden_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                hidden_item.setCheckState(Qt.CheckState.Checked if spec.hidden else Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 5, hidden_item)

                path_item = QTableWidgetItem(str(spec.file_path))
                path_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 6, path_item)
        finally:
            self._building_plugin_table = False

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
                    "The privileged hotkey helper is active for this session. Global shortcuts will be routed through the helper process.",
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

    def _apply_plugin_states(self) -> None:
        specs = self.services.plugin_manager.discover_plugins(include_disabled=True)
        for spec in specs:
            row_index = self.plugin_row_map.get(spec.plugin_id)
            if row_index is None:
                continue
            enabled_item = self.plugins_table.item(row_index, 4)
            hidden_item = self.plugins_table.item(row_index, 5)
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item is not None else True
            hidden = hidden_item.checkState() == Qt.CheckState.Checked if hidden_item is not None else False
            if spec.plugin_id == "settings_center":
                enabled = True
                hidden = False
            self.services.plugin_state_manager.set_enabled(spec.plugin_id, enabled)
            self.services.plugin_state_manager.set_hidden(spec.plugin_id, hidden)
        QMessageBox.information(
            self,
            self._pt("plugins.applied.title", "Plugin settings updated"),
            self._pt("plugins.applied.body", "Plugin visibility and enabled state were updated."),
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
            self._pt("plugins.imported.body", "Imported plugins: {plugins}", plugins=", ".join(plugin_ids)),
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
            self._pt("plugins.imported.body", "Imported plugins: {plugins}", plugins=", ".join(plugin_ids)),
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
            self._pt("plugins.imported.body", "Imported plugins: {plugins}", plugins=", ".join(plugin_ids)),
        )
        self.services.reload_plugins()

    def _export_selected_plugins(self) -> None:
        specs = self._selected_export_specs()
        if not specs:
            QMessageBox.warning(self, self._pt("plugins.export_failed.title", "Nothing selected"), self._pt("plugins.export_failed.body", "Select at least one plugin to export."))
            return
        self._export_specs(specs)

    def _export_all_plugins(self) -> None:
        specs = self.services.plugin_manager.discover_plugins(include_disabled=True)
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
            for spec in self.services.plugin_manager.discover_plugins(include_disabled=True)
        }
        selected = []
        for row_index in range(self.plugins_table.rowCount()):
            export_item = self.plugins_table.item(row_index, 0)
            name_item = self.plugins_table.item(row_index, 1)
            if export_item is None or name_item is None:
                continue
            if export_item.checkState() != Qt.CheckState.Checked:
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
        self.title_label.setText(self._pt("title", "Settings"))
        self.description_label.setText(
            self._pt(
                "description",
                "Control appearance, language, startup behavior, tray behavior, shortcuts, and plugin management from one place.",
            )
        )
        self.tabs.setTabText(0, self._pt("tab.general", "General"))
        self.tabs.setTabText(1, self._pt("tab.appearance", "Appearance"))
        self.tabs.setTabText(2, self._pt("tab.automation", "Automation"))
        self.tabs.setTabText(3, self._pt("tab.shortcuts", "Shortcuts"))
        self.tabs.setTabText(4, self._pt("tab.plugins", "Plugins"))

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
                "Manage built-in and custom plugins here. Import standalone plugin files, plugin folders, or backup archives. Export selected plugins or the full set into a reusable backup zip.",
            )
        )
        self.import_file_button.setText(self._pt("plugins.import_file_button", "Import File"))
        self.import_folder_button.setText(self._pt("plugins.import_folder_button", "Import Folder"))
        self.import_backup_button.setText(self._pt("plugins.import_backup_button", "Import Backup"))
        self.export_selected_button.setText(self._pt("plugins.export_selected", "Export Selected"))
        self.export_all_button.setText(self._pt("plugins.export_all", "Export All"))
        self.apply_plugin_state_button.setText(self._pt("plugins.apply", "Apply Plugin Changes"))
        self.refresh_plugins_button.setText(self._pt("plugins.refresh", "Refresh"))

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
