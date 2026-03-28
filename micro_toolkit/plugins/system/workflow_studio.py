from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin, bind_tr
from micro_toolkit.core.page_style import apply_page_chrome, apply_semantic_class, section_title_style
from micro_toolkit.core.widgets import ScrollSafeComboBox, width_breakpoint


QComboBox = ScrollSafeComboBox


class WorkflowStudioPlugin(QtPlugin):
    plugin_id = "workflow_studio"
    name = "Workflows"
    description = "Build saved command workflows for app actions and reusable automation sequences."
    category = ""
    standalone = True
    translations = {
        "en": {
            "plugin.name": "Workflows",
            "plugin.description": "Build saved command workflows for app actions and reusable automation sequences.",
        },
        "ar": {
            "plugin.name": "سلاسل العمل",
            "plugin.description": "أنشئ سلاسل عمل محفوظة لأوامر التطبيق وتسلسلات الأتمتة القابلة لإعادة الاستخدام.",
        },
    }

    def create_widget(self, services) -> QWidget:
        return WorkflowStudioPage(services)


class WorkflowStudioPage(QWidget):
    plugin_id = "workflow_studio"

    def __init__(self, services):
        super().__init__()
        self.services = services
        self.i18n = services.i18n
        self.tr = bind_tr(services, self.plugin_id)
        self._responsive_bucket = ""
        self._build_ui()
        self._reload_workflows()
        self._apply_texts()
        self.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        outer.addWidget(self.description_label)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(self.splitter, 1)

        self.left_panel = QWidget()
        apply_semantic_class(self.left_panel, "transparent_class")
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.list_card = QFrame()
        list_card_layout = QVBoxLayout(self.list_card)
        list_card_layout.setContentsMargins(18, 16, 18, 16)
        list_card_layout.setSpacing(10)

        self.list_label = QLabel()
        list_card_layout.addWidget(self.list_label)
        self.workflow_list = QListWidget()
        self.workflow_list.currentTextChanged.connect(self._load_selected_workflow)
        list_card_layout.addWidget(self.workflow_list, 1)

        self.list_buttons = QHBoxLayout()
        self.reload_button = QPushButton()
        self.reload_button.clicked.connect(self._reload_workflows)
        self.list_buttons.addWidget(self.reload_button)
        self.delete_button = QPushButton()
        self.delete_button.clicked.connect(self._delete_current_workflow)
        self.list_buttons.addWidget(self.delete_button)
        list_card_layout.addLayout(self.list_buttons)
        left_layout.addWidget(self.list_card, 1)
        self.splitter.addWidget(self.left_panel)

        self.right_panel = QWidget()
        apply_semantic_class(self.right_panel, "transparent_class")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)

        self.info_card = QFrame()
        info_layout = QVBoxLayout(self.info_card)
        info_layout.setContentsMargins(18, 16, 18, 16)
        info_layout.setSpacing(12)

        self.info_label = QLabel()
        info_layout.addWidget(self.info_label)

        self.meta_host = QWidget()
        apply_semantic_class(self.meta_host, "transparent_class")
        self.meta_grid = QGridLayout(self.meta_host)
        self.meta_grid.setContentsMargins(0, 0, 0, 0)
        self.meta_grid.setHorizontalSpacing(10)
        self.meta_grid.setVerticalSpacing(10)

        self.name_label = QLabel()
        self.meta_grid.addWidget(self.name_label, 0, 0)
        self.name_input = QLineEdit()
        self.meta_grid.addWidget(self.name_input, 0, 1)

        self.description_meta_label = QLabel()
        self.meta_grid.addWidget(self.description_meta_label, 1, 0)
        self.description_input = QLineEdit()
        self.meta_grid.addWidget(self.description_input, 1, 1)
        info_layout.addWidget(self.meta_host)
        right_layout.addWidget(self.info_card)

        self.steps_card = QFrame()
        steps_layout = QVBoxLayout(self.steps_card)
        steps_layout.setContentsMargins(18, 16, 18, 16)
        steps_layout.setSpacing(12)

        self.steps_label = QLabel()
        steps_layout.addWidget(self.steps_label)
        self.step_table = QTableWidget(0, 2)
        self.step_table.setAlternatingRowColors(True)
        self.step_table.verticalHeader().setVisible(False)
        self.step_table.horizontalHeader().setStretchLastSection(True)
        self.step_table.setMinimumHeight(220)
        self.step_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        steps_layout.addWidget(self.step_table, 1)

        self.step_buttons = QHBoxLayout()
        self.add_step_button = QPushButton()
        self.add_step_button.clicked.connect(self._add_step)
        self.step_buttons.addWidget(self.add_step_button)
        self.remove_step_button = QPushButton()
        self.remove_step_button.clicked.connect(self._remove_selected_step)
        self.step_buttons.addWidget(self.remove_step_button)
        self.step_buttons.addStretch(1)
        self.save_button = QPushButton()
        self.save_button.clicked.connect(self._save_workflow)
        self.step_buttons.addWidget(self.save_button)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run_workflow)
        self.step_buttons.addWidget(self.run_button)
        steps_layout.addLayout(self.step_buttons)
        right_layout.addWidget(self.steps_card, 1)

        self.commands_card = QFrame()
        commands_layout = QVBoxLayout(self.commands_card)
        commands_layout.setContentsMargins(18, 16, 18, 16)
        commands_layout.setSpacing(12)
        self.reference_label = QLabel()
        commands_layout.addWidget(self.reference_label)
        self.reference_card = QFrame()
        reference_layout = QVBoxLayout(self.reference_card)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        reference_layout.setSpacing(10)
        self.command_reference_table = QTableWidget(0, 3)
        self.command_reference_table.setAlternatingRowColors(True)
        self.command_reference_table.verticalHeader().setVisible(False)
        self.command_reference_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.command_reference_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.command_reference_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.command_reference_table.horizontalHeader().setStretchLastSection(True)
        self.command_reference_table.setColumnWidth(0, 190)
        self.command_reference_table.setColumnWidth(1, 220)
        self.command_reference_table.setMinimumHeight(180)
        reference_layout.addWidget(self.command_reference_table, 1)

        self.run_output_label = QLabel()
        reference_layout.addWidget(self.run_output_label)
        self.command_output = QPlainTextEdit()
        self.command_output.setReadOnly(True)
        self.command_output.setMaximumBlockCount(500)
        self.command_output.setMinimumHeight(120)
        apply_semantic_class(self.command_output, "console_class")
        reference_layout.addWidget(self.command_output, 1)
        commands_layout.addWidget(self.reference_card, 1)

        right_layout.addWidget(self.commands_card, 1)
        right_layout.setStretch(0, 0)
        right_layout.setStretch(1, 2)
        right_layout.setStretch(2, 2)

        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self._apply_responsive_layout(force=True)

    def _reload_workflows(self) -> None:
        self.services.ensure_plugin_commands_registered()
        current = self.workflow_list.currentItem().text() if self.workflow_list.currentItem() else ""
        self.workflow_list.clear()
        for name in self.services.workflow_manager.list_workflows():
            self.workflow_list.addItem(name)
        if current:
            matches = self.workflow_list.findItems(current, Qt.MatchFlag.MatchExactly)
            if matches:
                self.workflow_list.setCurrentItem(matches[0])
        self._refresh_command_reference()

    def _load_selected_workflow(self, name: str) -> None:
        if not name:
            return
        payload = self.services.workflow_manager.load_workflow(name)
        self.name_input.setText(payload.get("name", name))
        self.description_input.setText(payload.get("description", ""))
        steps = payload.get("steps", [])
        self.step_table.setRowCount(0)
        for step in steps:
            self._add_step(step.get("command"), step.get("args", {}))

    def _add_step(self, command_id: str | None = None, args: dict | None = None) -> None:
        self.services.ensure_plugin_commands_registered()
        row = self.step_table.rowCount()
        self.step_table.insertRow(row)

        combo = QComboBox()
        for spec in self.services.command_registry.list_commands():
            combo.addItem(f"{spec.command_id} - {spec.title}", spec.command_id)
        self.step_table.setCellWidget(row, 0, combo)
        if command_id:
            for index in range(combo.count()):
                if combo.itemData(index) == command_id:
                    combo.setCurrentIndex(index)
                    break

        args_text = json.dumps(args or {}, ensure_ascii=False)
        self.step_table.setItem(row, 1, QTableWidgetItem(args_text))

    def _remove_selected_step(self) -> None:
        row = self.step_table.currentRow()
        if row >= 0:
            self.step_table.removeRow(row)

    def _save_workflow(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, self.tr("warning.title", "Missing name"), self.tr("warning.name", "Enter a workflow name before saving or running it."))
            return
        payload = {
            "name": name,
            "description": self.description_input.text().strip(),
            "steps": self._collect_steps(),
        }
        self.services.workflow_manager.save_workflow(name, payload)
        self._reload_workflows()
        QMessageBox.information(self, self.tr("saved.title", "Workflow saved"), self.tr("saved.body", "The workflow was saved successfully."))

    def _delete_current_workflow(self) -> None:
        item = self.workflow_list.currentItem()
        if item is None:
            return
        name = item.text()
        self.services.workflow_manager.delete_workflow(name)
        self._reload_workflows()

    def _run_workflow(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, self.tr("warning.title", "Missing name"), self.tr("warning.name", "Enter a workflow name before saving or running it."))
            return
        payload = {
            "name": name,
            "description": self.description_input.text().strip(),
            "steps": self._collect_steps(),
        }
        self.services.workflow_manager.save_workflow(name, payload)
        messages: list[str] = []

        def log_line(message: str) -> None:
            messages.append(message)

        try:
            self.services.ensure_plugin_commands_registered()
            result = self.services.workflow_manager.run_workflow(
                name,
                self.services.command_registry,
                log_cb=log_line,
            )
        except Exception as exc:
            messages.append(str(exc))
            self.command_output.setPlainText("\n".join(messages))
            QMessageBox.critical(self, self.tr("run_failed.title", "Workflow failed"), "\n".join(messages))
            return

        messages.append(json.dumps(self.services.serialize_result(result), indent=2, ensure_ascii=False))
        self.command_output.setPlainText("\n".join(messages))
        self.services.record_run("workflow_studio", "SUCCESS", f"Ran workflow {name}")

    def _collect_steps(self) -> list[dict]:
        steps = []
        for row in range(self.step_table.rowCount()):
            combo = self.step_table.cellWidget(row, 0)
            item = self.step_table.item(row, 1)
            command_id = combo.currentData() if combo is not None else ""
            args_text = item.text().strip() if item is not None else "{}"
            try:
                args = json.loads(args_text or "{}")
            except Exception as exc:
                raise ValueError(f"Row {row + 1} has invalid JSON arguments: {exc}") from exc
            if not isinstance(args, dict):
                raise ValueError(f"Row {row + 1} arguments must be a JSON object.")
            steps.append({"command": command_id, "args": args})
        return steps

    def _refresh_command_reference(self) -> None:
        self.services.ensure_plugin_commands_registered()
        commands = self.services.command_registry.list_commands()
        self.command_reference_table.setRowCount(len(commands))
        for row_index, spec in enumerate(commands):
            self.command_reference_table.setItem(row_index, 0, QTableWidgetItem(spec.command_id))
            self.command_reference_table.setItem(row_index, 1, QTableWidgetItem(spec.title))
            self.command_reference_table.setItem(row_index, 2, QTableWidgetItem(spec.description))
        self.command_reference_table.resizeRowsToContents()

    def _apply_texts(self) -> None:
        self._apply_theme_styles()
        self.title_label.setText(self.tr("title", "Workflows"))
        self.description_label.setText(
            self.tr(
                "description",
                "Save reusable automation sequences built from registered app commands. Workflows can open tools, switch language, change theme, and trigger shell actions.",
            )
        )
        self.list_label.setText(self.tr("list", "Saved workflows"))
        self.reload_button.setText(self.tr("reload", "Reload"))
        self.delete_button.setText(self.tr("delete", "Delete"))
        self.info_label.setText(self.tr("details", "Workflow details"))
        self.name_label.setText(self.tr("name", "Name"))
        self.description_meta_label.setText(self.tr("meta.description", "Description"))
        self.steps_label.setText(self.tr("steps", "Steps"))
        self.step_table.setHorizontalHeaderLabels(
            [
                self.tr("command", "Command"),
                self.tr("arguments", "Arguments JSON"),
            ]
        )
        self.add_step_button.setText(self.tr("add_step", "Add step"))
        self.remove_step_button.setText(self.tr("remove_step", "Remove step"))
        self.save_button.setText(self.tr("save", "Save workflow"))
        self.run_button.setText(self.tr("run", "Run workflow"))
        self.reference_label.setText(self.tr("reference", "Available commands"))
        self.run_output_label.setText(self.tr("run_output", "Run output"))
        self.command_reference_table.setHorizontalHeaderLabels(
            [
                self.tr("reference.command_id", "Command ID"),
                self.tr("reference.title", "Title"),
                self.tr("reference.description", "Description"),
            ]
        )
        self._refresh_command_reference()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.list_card, self.info_card, self.steps_card, self.commands_card),
            title_size=26,
            title_weight=700,
        )
        apply_semantic_class(self.reference_card, "transparent_class")
        self.command_output.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.list_label.setStyleSheet(section_title_style(palette))
        self.info_label.setStyleSheet(section_title_style(palette))
        self.name_label.setStyleSheet(section_title_style(palette, size=14))
        self.description_meta_label.setStyleSheet(section_title_style(palette, size=14))
        self.steps_label.setStyleSheet(section_title_style(palette))
        self.reference_label.setStyleSheet(section_title_style(palette))
        self.run_output_label.setStyleSheet(section_title_style(palette, size=15))

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self, *, force: bool = False) -> None:
        bucket = width_breakpoint(self.width(), compact_max=700, medium_max=1200)
        if not force and bucket == self._responsive_bucket:
            return
        self._responsive_bucket = bucket
        compact = bucket == "compact"

        self.splitter.setOrientation(Qt.Orientation.Vertical if compact else Qt.Orientation.Horizontal)
        self.list_buttons.setDirection(QBoxLayout.Direction.LeftToRight)
        if compact:
            self.meta_grid.addWidget(self.name_label, 0, 0)
            self.meta_grid.addWidget(self.name_input, 1, 0)
            self.meta_grid.addWidget(self.description_meta_label, 2, 0)
            self.meta_grid.addWidget(self.description_input, 3, 0)
        else:
            self.meta_grid.addWidget(self.name_label, 0, 0)
            self.meta_grid.addWidget(self.name_input, 0, 1)
            self.meta_grid.addWidget(self.description_meta_label, 1, 0)
            self.meta_grid.addWidget(self.description_input, 1, 1)
