from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin


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
        self._build_ui()
        self._reload_workflows()
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
        outer.addWidget(self.description_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.list_label = QLabel()
        left_layout.addWidget(self.list_label)
        self.workflow_list = QListWidget()
        self.workflow_list.currentTextChanged.connect(self._load_selected_workflow)
        left_layout.addWidget(self.workflow_list, 1)

        list_buttons = QHBoxLayout()
        self.reload_button = QPushButton()
        self.reload_button.clicked.connect(self._reload_workflows)
        list_buttons.addWidget(self.reload_button)
        self.delete_button = QPushButton()
        self.delete_button.clicked.connect(self._delete_current_workflow)
        list_buttons.addWidget(self.delete_button)
        left_layout.addLayout(list_buttons)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        self.meta_card = QFrame()
        meta_grid = QGridLayout(self.meta_card)
        meta_grid.setHorizontalSpacing(10)
        meta_grid.setVerticalSpacing(10)

        self.name_label = QLabel()
        meta_grid.addWidget(self.name_label, 0, 0)
        self.name_input = QLineEdit()
        meta_grid.addWidget(self.name_input, 0, 1)

        self.description_meta_label = QLabel()
        meta_grid.addWidget(self.description_meta_label, 1, 0)
        self.description_input = QLineEdit()
        meta_grid.addWidget(self.description_input, 1, 1)
        right_layout.addWidget(self.meta_card)

        self.steps_label = QLabel()
        right_layout.addWidget(self.steps_label)

        self.step_table = QTableWidget(0, 2)
        self.step_table.setAlternatingRowColors(True)
        self.step_table.verticalHeader().setVisible(False)
        self.step_table.horizontalHeader().setStretchLastSection(True)
        right_layout.addWidget(self.step_table, 1)

        step_buttons = QHBoxLayout()
        self.add_step_button = QPushButton()
        self.add_step_button.clicked.connect(self._add_step)
        step_buttons.addWidget(self.add_step_button)
        self.remove_step_button = QPushButton()
        self.remove_step_button.clicked.connect(self._remove_selected_step)
        step_buttons.addWidget(self.remove_step_button)
        step_buttons.addStretch(1)
        self.save_button = QPushButton()
        self.save_button.clicked.connect(self._save_workflow)
        step_buttons.addWidget(self.save_button)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run_workflow)
        step_buttons.addWidget(self.run_button)
        right_layout.addLayout(step_buttons)

        self.reference_label = QLabel()
        right_layout.addWidget(self.reference_label)
        self.command_reference = QPlainTextEdit()
        self.command_reference.setReadOnly(True)
        self.command_reference.setMaximumBlockCount(500)
        right_layout.addWidget(self.command_reference, 1)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

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
            QMessageBox.warning(self, self._pt("warning.title", "Missing name"), self._pt("warning.name", "Enter a workflow name before saving or running it."))
            return
        payload = {
            "name": name,
            "description": self.description_input.text().strip(),
            "steps": self._collect_steps(),
        }
        self.services.workflow_manager.save_workflow(name, payload)
        self._reload_workflows()
        QMessageBox.information(self, self._pt("saved.title", "Workflow saved"), self._pt("saved.body", "The workflow was saved successfully."))

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
            QMessageBox.warning(self, self._pt("warning.title", "Missing name"), self._pt("warning.name", "Enter a workflow name before saving or running it."))
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
            QMessageBox.critical(self, self._pt("run_failed.title", "Workflow failed"), "\n".join(messages))
            return

        messages.append(json.dumps(self.services.serialize_result(result), indent=2, ensure_ascii=False))
        self.command_reference.setPlainText("\n".join(messages))
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
        lines = []
        for spec in self.services.command_registry.list_commands():
            lines.append(f"{spec.command_id}\n  {spec.description}")
        self.command_reference.setPlainText("\n\n".join(lines))

    def _apply_texts(self) -> None:
        self.title_label.setText(self._pt("title", "Workflows"))
        self.description_label.setText(
            self._pt(
                "description",
                "Save reusable automation sequences built from registered app commands. Workflows can open tools, switch language, change theme, and trigger shell actions.",
            )
        )
        self.list_label.setText(self._pt("list", "Saved workflows"))
        self.reload_button.setText(self._pt("reload", "Reload"))
        self.delete_button.setText(self._pt("delete", "Delete"))
        self.name_label.setText(self._pt("name", "Name"))
        self.description_meta_label.setText(self._pt("meta.description", "Description"))
        self.steps_label.setText(self._pt("steps", "Steps"))
        self.step_table.setHorizontalHeaderLabels(
            [
                self._pt("command", "Command"),
                self._pt("arguments", "Arguments JSON"),
            ]
        )
        self.add_step_button.setText(self._pt("add_step", "Add step"))
        self.remove_step_button.setText(self._pt("remove_step", "Remove step"))
        self.save_button.setText(self._pt("save", "Save workflow"))
        self.run_button.setText(self._pt("run", "Run workflow"))
        self.reference_label.setText(self._pt("reference", "Available commands"))
        self._refresh_command_reference()
