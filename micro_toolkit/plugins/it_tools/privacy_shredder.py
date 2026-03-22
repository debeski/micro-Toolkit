from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin


def secure_shred_task(context, file_path: str, passes: int):
    size = os.path.getsize(file_path)
    context.log(
        f"Starting {passes}-pass shred on '{os.path.basename(file_path)}' ({size} bytes)..."
    )

    with open(file_path, "ba+", buffering=0) as handle:
        for current_pass in range(passes):
            handle.seek(0)
            handle.write(os.urandom(size))
            context.progress((current_pass + 1) / float(passes))

    directory = os.path.dirname(file_path)
    random_name = os.urandom(12).hex()
    random_path = os.path.join(directory, random_name)
    os.rename(file_path, random_path)
    os.remove(random_path)
    context.log("File shredded and deleted successfully.")
    return {
        "file_name": os.path.basename(file_path),
        "passes": passes,
    }


class PrivacyShredderPlugin(QtPlugin):
    plugin_id = "shredder"
    name = "Privacy Data Shredder"
    description = "Overwrite a file with random bytes, rename it, and delete it after explicit confirmation."
    category = "IT Toolkit"

    def create_widget(self, services) -> QWidget:
        return PrivacyShredderPage(services, self.plugin_id)


class PrivacyShredderPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Privacy Data Shredder")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #8a1f11;")
        layout.addWidget(title)

        description = QLabel(
            "This permanently destroys a file by overwriting it with random bytes before deletion. Use it carefully."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #6a382f;")
        layout.addWidget(description)

        file_row = QHBoxLayout()
        file_row.setSpacing(10)
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Select a file to shred...")
        file_row.addWidget(self.file_input, 1)
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_file)
        file_row.addWidget(browse_button)
        layout.addLayout(file_row)

        passes_card = QFrame()
        passes_card.setStyleSheet(
            "QFrame { background: #fff7f2; border: 1px solid #efd3c9; border-radius: 14px; }"
        )
        passes_layout = QVBoxLayout(passes_card)
        passes_layout.setContentsMargins(16, 14, 16, 14)
        passes_layout.setSpacing(8)

        passes_title = QLabel("Overwrite Passes")
        passes_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #6a2218;")
        passes_layout.addWidget(passes_title)

        slider_row = QHBoxLayout()
        slider_row.setSpacing(10)
        self.passes_slider = QSlider(Qt.Orientation.Horizontal)
        self.passes_slider.setRange(1, 35)
        self.passes_slider.setValue(3)
        self.passes_slider.valueChanged.connect(self._sync_passes_label)
        slider_row.addWidget(self.passes_slider, 1)

        self.passes_value_label = QLabel("3")
        self.passes_value_label.setFixedWidth(30)
        slider_row.addWidget(self.passes_value_label)
        passes_layout.addLayout(slider_row)

        note = QLabel("Higher pass counts increase runtime substantially.")
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 12px; color: #7c5c57;")
        passes_layout.addWidget(note)
        layout.addWidget(passes_card)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Shred File")
        self.run_button.setStyleSheet(
            "QPushButton { background: #b63f26; color: white; border-radius: 12px; padding: 10px 14px; font-weight: 700; }"
            "QPushButton:hover { background: #9e341e; }"
            "QPushButton:disabled { background: #d79a8b; }"
        )
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.progress, 1)
        layout.addLayout(controls)

        summary_card = QFrame()
        summary_card.setStyleSheet(
            "QFrame { background: #fff7f2; border: 1px solid #efd3c9; border-radius: 14px; }"
        )
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel("Choose a file to shred.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #6a382f;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Shred activity will appear here.")
        layout.addWidget(self.output, 1)

    def _sync_passes_label(self, value: int) -> None:
        self.passes_value_label.setText(str(value))

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File To Shred",
            str(self.services.default_output_path()),
            "All Files (*)",
        )
        if file_path:
            self.file_input.setText(file_path)

    def _run(self) -> None:
        file_path = self.file_input.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "Missing Input", "Choose a valid file to shred.")
            return

        answer = QMessageBox.warning(
            self,
            "Critical Warning",
            "This will permanently overwrite and delete the selected file. Recovery should be considered impossible.\n\nDo you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.run_button.setEnabled(False)
        self.progress.setValue(0)
        self.output.setPlainText("")
        self.summary_label.setText("Shredding file...")

        passes = int(self.passes_slider.value())
        self.services.run_task(
            lambda context: secure_shred_task(context, file_path, passes),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            on_progress=self._handle_progress,
        )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self.file_input.clear()
        self.summary_label.setText(
            f"Shredded {result['file_name']} using {result['passes']} overwrite passes."
        )
        self.output.setPlainText(
            f"File shredded successfully.\nFile: {result['file_name']}\nPasses: {result['passes']}"
        )
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            f"Shredded {result['file_name']} with {result['passes']} passes",
        )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown shredder error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Privacy shredder failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
