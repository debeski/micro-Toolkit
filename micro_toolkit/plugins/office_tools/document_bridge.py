from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.app_utils import generate_output_filename, open_file_or_folder
from micro_toolkit.core.command_runtime import HeadlessTaskContext
from micro_toolkit.core.document_converter import convert_docx_to_markdown, convert_markdown_to_docx
from micro_toolkit.core.plugin_api import QtPlugin


def _resolve_output_path(
    source_path: str,
    *,
    output_path: str = "",
    output_dir: str = "",
    operation: str,
    extension: str,
) -> Path:
    if output_path:
        return Path(output_path).expanduser().resolve()

    source = Path(source_path).expanduser().resolve()
    base_dir = Path(output_dir).expanduser().resolve() if output_dir else source.parent
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = generate_output_filename(operation, source.stem, extension)
    return base_dir / filename


def markdown_to_docx_task(context, markdown_path: str, output_path: str, layout_mode: str, font_name: str):
    return convert_markdown_to_docx(
        markdown_path,
        output_path,
        layout_mode=layout_mode,
        font_name=font_name or "Dubai",
        log_cb=context.log,
        progress_cb=context.progress,
    )


def docx_to_markdown_task(context, docx_path: str, output_path: str, extract_images: bool):
    return convert_docx_to_markdown(
        docx_path,
        output_path,
        extract_images=extract_images,
        log_cb=context.log,
        progress_cb=context.progress,
    )


def _run_headless(plugin_id: str, services, *, task_fn):
    try:
        result = task_fn()
    except Exception as exc:
        services.record_run(plugin_id, "ERROR", str(exc)[:500])
        raise
    services.record_run(plugin_id, "SUCCESS", str(result.get("output_path", ""))[:500])
    return result


class DocumentBridgePlugin(QtPlugin):
    plugin_id = "doc_bridge"
    name = "Document Bridge"
    description = "Convert Markdown reports into DOCX files and DOCX documents back into Markdown."
    category = "Office Utilities"
    translations = {
        "en": {
            "plugin.name": "Document Bridge",
            "plugin.description": "Convert Markdown reports into DOCX files and DOCX documents back into Markdown.",
            "plugin.category": "Office Utilities",
        },
        "ar": {
            "plugin.name": "جسر المستندات",
            "plugin.description": "حوّل تقارير Markdown إلى DOCX وأعد تحويل ملفات DOCX إلى Markdown.",
            "plugin.category": "أدوات المكتب",
        },
    }

    def register_commands(self, registry, services) -> None:
        registry.register(
            "tool.doc_bridge.md_to_docx",
            "Markdown To DOCX",
            "Convert a markdown file into a styled DOCX document.",
            lambda markdown_path, output_path="", output_dir="", layout_mode="auto", font_name="Dubai": _run_headless(
                self.plugin_id,
                services,
                task_fn=lambda: markdown_to_docx_task(
                    HeadlessTaskContext(services, command_id="tool.doc_bridge.md_to_docx"),
                    markdown_path,
                    str(
                        _resolve_output_path(
                            markdown_path,
                            output_path=output_path,
                            output_dir=output_dir or str(services.default_output_path()),
                            operation="Markdown_To_DOCX",
                            extension=".docx",
                        )
                    ),
                    layout_mode,
                    font_name,
                ),
            ),
        )
        registry.register(
            "tool.doc_bridge.docx_to_md",
            "DOCX To Markdown",
            "Convert a DOCX document into a markdown file and optionally extract embedded images.",
            lambda docx_path, output_path="", output_dir="", extract_images=True: _run_headless(
                self.plugin_id,
                services,
                task_fn=lambda: docx_to_markdown_task(
                    HeadlessTaskContext(services, command_id="tool.doc_bridge.docx_to_md"),
                    docx_path,
                    str(
                        _resolve_output_path(
                            docx_path,
                            output_path=output_path,
                            output_dir=output_dir or str(services.default_output_path()),
                            operation="DOCX_To_Markdown",
                            extension=".md",
                        )
                    ),
                    bool(extract_images),
                ),
            ),
        )

    def create_widget(self, services) -> QWidget:
        return DocumentBridgePage(services, self.plugin_id)


class DocumentBridgePage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._latest_output_path: str | None = None
        self._build_ui()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self._apply_texts()
        self._sync_mode_state()

    def _t(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(self.description_label)

        mode_card = QFrame()
        mode_card.setStyleSheet("QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }")
        mode_layout = QFormLayout(mode_card)
        mode_layout.setContentsMargins(16, 14, 16, 14)
        mode_layout.setSpacing(10)

        self.mode_label = QLabel()
        self.mode_combo = QComboBox()
        self.mode_combo.currentIndexChanged.connect(self._sync_mode_state)
        mode_layout.addRow(self.mode_label, self.mode_combo)
        layout.addWidget(mode_card)

        self.source_label = QLabel()
        source_row = QHBoxLayout()
        source_row.setSpacing(10)
        self.source_input = QLineEdit()
        source_row.addWidget(self.source_input, 1)
        self.source_button = QPushButton()
        self.source_button.clicked.connect(self._browse_source)
        source_row.addWidget(self.source_button)
        layout.addWidget(self.source_label)
        layout.addLayout(source_row)

        self.output_label = QLabel()
        output_row = QHBoxLayout()
        output_row.setSpacing(10)
        self.output_input = QLineEdit()
        output_row.addWidget(self.output_input, 1)
        self.output_button = QPushButton()
        self.output_button.clicked.connect(self._browse_output)
        output_row.addWidget(self.output_button)
        layout.addWidget(self.output_label)
        layout.addLayout(output_row)

        self.options_stack = QStackedWidget()
        layout.addWidget(self.options_stack)

        self.md_options = QFrame()
        self.md_options.setStyleSheet("QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }")
        md_form = QFormLayout(self.md_options)
        md_form.setContentsMargins(16, 14, 16, 14)
        md_form.setSpacing(10)

        self.layout_mode_label = QLabel()
        self.layout_mode_combo = QComboBox()
        md_form.addRow(self.layout_mode_label, self.layout_mode_combo)

        self.font_name_label = QLabel()
        self.font_name_input = QLineEdit("Dubai")
        md_form.addRow(self.font_name_label, self.font_name_input)
        self.options_stack.addWidget(self.md_options)

        self.docx_options = QFrame()
        self.docx_options.setStyleSheet("QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }")
        docx_layout = QVBoxLayout(self.docx_options)
        docx_layout.setContentsMargins(16, 14, 16, 14)
        docx_layout.setSpacing(10)
        self.extract_images_checkbox = QCheckBox()
        self.extract_images_checkbox.setChecked(True)
        docx_layout.addWidget(self.extract_images_checkbox)
        docx_layout.addStretch(1)
        self.options_stack.addWidget(self.docx_options)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_output_button = QPushButton()
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self._open_output)
        controls.addWidget(self.open_output_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.progress, 1)
        layout.addLayout(controls)

        summary_card = QFrame()
        summary_card.setStyleSheet("QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.output_log = QPlainTextEdit()
        self.output_log.setReadOnly(True)
        layout.addWidget(self.output_log, 1)

    def _current_mode(self) -> str:
        return self.mode_combo.currentData() or "md_to_docx"

    def _refresh_combo(self, combo: QComboBox, items: list[tuple[str, str]], current_value: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        for label, value in items:
            combo.addItem(label, value)
        index = combo.findData(current_value)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _apply_texts(self, *_args) -> None:
        self.title_label.setText(self._t("ui.title", "Document Bridge"))
        self.description_label.setText(
            self._t(
                "ui.description",
                "Convert Markdown reports to DOCX and convert DOCX documents back to Markdown without leaving the toolkit.",
            )
        )
        self.mode_label.setText(self._t("ui.mode.label", "Mode"))
        self.source_label.setText(self._t("ui.source.label", "Source File"))
        self.output_label.setText(self._t("ui.output.label", "Output File"))
        self.source_button.setText(self._t("ui.source.browse", "Browse"))
        self.output_button.setText(self._t("ui.output.browse", "Save As"))
        self.layout_mode_label.setText(self._t("ui.layout.label", "Layout Direction"))
        self.font_name_label.setText(self._t("ui.font.label", "Preferred Font"))
        self.extract_images_checkbox.setText(self._t("ui.extract_images", "Extract embedded images into a sibling media folder"))
        self.run_button.setText(self._t("ui.run", "Convert"))
        self.open_output_button.setText(self._t("ui.open_result", "Open Result"))
        self.output_log.setPlaceholderText(self._t("ui.log.placeholder", "Conversion details will appear here."))

        self._refresh_combo(
            self.mode_combo,
            [
                (self._t("ui.mode.md_to_docx", "Markdown -> DOCX"), "md_to_docx"),
                (self._t("ui.mode.docx_to_md", "DOCX -> Markdown"), "docx_to_md"),
            ],
            self._current_mode(),
        )
        current_layout = self.layout_mode_combo.currentData() or "auto"
        self._refresh_combo(
            self.layout_mode_combo,
            [
                (self._t("ui.layout.auto", "Auto Detect"), "auto"),
                (self._t("ui.layout.ltr", "Force LTR"), "ltr"),
                (self._t("ui.layout.rtl", "Force RTL"), "rtl"),
            ],
            current_layout,
        )
        self._sync_mode_state()

    def _sync_mode_state(self, *_args) -> None:
        mode = self._current_mode()
        is_md_mode = mode == "md_to_docx"
        self.options_stack.setCurrentIndex(0 if is_md_mode else 1)
        self.summary_label.setText(
            self._t(
                "ui.summary.ready.md_to_docx" if is_md_mode else "ui.summary.ready.docx_to_md",
                "Choose a file to begin conversion.",
            )
        )
        self.source_input.setPlaceholderText(
            self._t(
                "ui.source.placeholder.md_to_docx" if is_md_mode else "ui.source.placeholder.docx_to_md",
                "Choose a source document...",
            )
        )
        self.output_input.setPlaceholderText(
            self._t(
                "ui.output.placeholder.md_to_docx" if is_md_mode else "ui.output.placeholder.docx_to_md",
                "Choose where to save the converted file...",
            )
        )

    def _suggest_output_path(self, source_path: str) -> str:
        source = Path(source_path).expanduser()
        if not source.name:
            return ""
        default_dir = self.services.default_output_path()
        if self._current_mode() == "md_to_docx":
            name = generate_output_filename("Markdown_To_DOCX", source.stem, ".docx")
        else:
            name = generate_output_filename("DOCX_To_Markdown", source.stem, ".md")
        return str(default_dir / name)

    def _browse_source(self) -> None:
        if self._current_mode() == "md_to_docx":
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                self._t("ui.dialog.source.md_to_docx", "Select Markdown File"),
                str(self.services.default_output_path()),
                "Markdown Files (*.md *.markdown *.txt);;All Files (*)",
            )
        else:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                self._t("ui.dialog.source.docx_to_md", "Select DOCX File"),
                str(self.services.default_output_path()),
                "Word Documents (*.docx);;All Files (*)",
            )
        if not file_path:
            return
        self.source_input.setText(file_path)
        self.output_input.setText(self._suggest_output_path(file_path))

    def _browse_output(self) -> None:
        suggested = self.output_input.text().strip() or self._suggest_output_path(self.source_input.text().strip())
        if self._current_mode() == "md_to_docx":
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                self._t("ui.dialog.output.md_to_docx", "Save DOCX File"),
                suggested,
                "Word Documents (*.docx)",
            )
        else:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                self._t("ui.dialog.output.docx_to_md", "Save Markdown File"),
                suggested,
                "Markdown Files (*.md)",
            )
        if file_path:
            self.output_input.setText(file_path)

    def _run(self) -> None:
        source_path = self.source_input.text().strip()
        if not source_path:
            QMessageBox.warning(self, self._t("ui.missing.title", "Missing Input"), self._t("ui.missing.source", "Choose a source file first."))
            return

        output_path = self.output_input.text().strip() or self._suggest_output_path(source_path)
        if not output_path:
            QMessageBox.warning(self, self._t("ui.missing.title", "Missing Input"), self._t("ui.missing.output", "Choose an output file path."))
            return

        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)
        self.progress.setValue(0)
        self.output_log.setPlainText("")
        self.summary_label.setText(self._t("ui.summary.running", "Converting document..."))

        if self._current_mode() == "md_to_docx":
            self.services.run_task(
                lambda context: markdown_to_docx_task(
                    context,
                    source_path,
                    output_path,
                    self.layout_mode_combo.currentData() or "auto",
                    self.font_name_input.text().strip() or "Dubai",
                ),
                on_result=self._handle_result,
                on_error=self._handle_error,
                on_finished=self._finish_run,
                on_progress=self._handle_progress,
            )
        else:
            self.services.run_task(
                lambda context: docx_to_markdown_task(
                    context,
                    source_path,
                    output_path,
                    self.extract_images_checkbox.isChecked(),
                ),
                on_result=self._handle_result,
                on_error=self._handle_error,
                on_finished=self._finish_run,
                on_progress=self._handle_progress,
            )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_output_path = result.get("output_path")
        self.output_log.setPlainText("\n".join(f"{key}: {value}" for key, value in result.items() if value not in ("", None)))

        if self._current_mode() == "md_to_docx":
            self.summary_label.setText(
                self._t(
                    "ui.summary.success.md_to_docx",
                    "Created DOCX output with {headings} headings, {tables} tables, and {images} images.",
                    headings=result.get("headings", 0),
                    tables=result.get("tables", 0),
                    images=result.get("images", 0),
                )
            )
        else:
            self.summary_label.setText(
                self._t(
                    "ui.summary.success.docx_to_md",
                    "Created Markdown output with {headings} headings, {tables} tables, and {images} extracted images.",
                    headings=result.get("headings", 0),
                    tables=result.get("tables", 0),
                    images=result.get("images", 0),
                )
            )

        self.open_output_button.setEnabled(bool(self._latest_output_path))
        self.services.record_run(self.plugin_id, "SUCCESS", str(self._latest_output_path or "")[:500])

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown conversion error") if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.output_log.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Document Bridge failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_output(self) -> None:
        if not self._latest_output_path:
            return
        if not open_file_or_folder(self._latest_output_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_output_path))
