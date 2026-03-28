from __future__ import annotations

import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.page_style import apply_page_chrome
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr, safe_tr

def merge_pdfs_task(context, file_paths: list[str], output_dir: str, *, translate=None):
    try:
        import PyPDF2
    except ImportError as exc:
        raise RuntimeError(safe_tr(translate, "error.pypdf2", "PyPDF2 is required to merge PDFs.")) from exc

    merger = PyPDF2.PdfMerger()
    total = len(file_paths)
    for index, file_path in enumerate(file_paths, start=1):
        context.progress(index / float(total))
        merger.append(file_path)
        context.log(safe_tr(translate, "log.added", "Added {file}", file=os.path.basename(file_path)))

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "Merged_Document_Output.pdf")
    merger.write(output_path)
    merger.close()
    context.progress(1.0)
    context.log(safe_tr(translate, "log.saved", "Merged PDF written to {path}", path=output_path))
    return {
        "output_path": output_path,
        "file_count": len(file_paths),
    }


class PDFSuitePlugin(QtPlugin):
    plugin_id = "pdf_suite"
    name = "PDF Core Engine"
    description = "Merge multiple PDF files into one output document."
    category = "Office Utilities"

    def create_widget(self, services) -> QWidget:
        return PDFSuitePage(services, self.plugin_id)


class PDFSuitePage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self.pdf_files: list[str] = []
        self._latest_output_path = None
        self._build_ui()
        self._apply_texts()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        self.title_label = QLabel()
        layout.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)
        self.add_button = QPushButton()
        self.add_button.clicked.connect(self._add_files)
        buttons_row.addWidget(self.add_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self._clear_files)
        buttons_row.addWidget(self.clear_button, 0, Qt.AlignmentFlag.AlignLeft)
        buttons_row.addStretch(1)
        layout.addLayout(buttons_row)

        self.file_list = QListWidget()
        layout.addWidget(self.file_list, 1)

        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        self.output_dir_label = QLabel(str(self.services.default_output_path()))
        self.output_dir_label.setWordWrap(True)
        out_row.addWidget(self.output_dir_label, 1)
        self.browse_output_button = QPushButton()
        self.browse_output_button.clicked.connect(self._choose_output_dir)
        out_row.addWidget(self.browse_output_button)
        layout.addLayout(out_row)
        self.output_dir = str(self.services.default_output_path())

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_output_button = QPushButton()
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self._open_output)
        controls.addWidget(self.open_output_button, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addLayout(controls)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(self.summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)

    def _apply_texts(self) -> None:
        self.title_label.setText(self.tr("title", "PDF Core Engine"))
        self.description_label.setText(
            self.tr(
                "description",
                "Attach multiple PDF files in order, choose an output folder, and merge them into a single document.",
            )
        )
        self.add_button.setText(self.tr("add", "Add PDFs"))
        self.clear_button.setText(self.tr("clear", "Clear List"))
        self.browse_output_button.setText(self.tr("output_folder", "Output Folder"))
        self.run_button.setText(self.tr("run", "Merge PDFs"))
        self.open_output_button.setText(self.tr("open_output", "Open Output"))
        self.summary_label.setText(self.tr("summary.ready", "Add PDF files to begin."))
        self.output.setPlaceholderText(self.tr("summary.placeholder", "PDF merge summary will appear here."))
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.summary_card,),
            summary_label=self.summary_label,
        )

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self.tr("dialog.select_pdfs", "Select PDF Files"),
            str(self.services.default_output_path()),
            self.tr("dialog.pdf_filter", "PDF Documents (*.pdf)"),
        )
        if files:
            self.pdf_files.extend(files)
            self._render_file_list()

    def _clear_files(self) -> None:
        self.pdf_files = []
        self._render_file_list()

    def _render_file_list(self) -> None:
        self.file_list.clear()
        for file_path in self.pdf_files:
            self.file_list.addItem(os.path.basename(file_path))

    def _choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("dialog.select_output", "Select Output Folder"),
            self.output_dir,
        )
        if folder:
            self.output_dir = folder
            self.output_dir_label.setText(folder)

    def _run(self) -> None:
        if not self.pdf_files:
            QMessageBox.warning(
                self,
                self.tr("error.missing_input.title", "Missing Input"),
                self.tr("error.missing_files", "Add at least one PDF file."),
            )
            return

        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)
        self.output.setPlainText("")
        self.summary_label.setText(self.tr("summary.running", "Merging PDFs..."))

        self.services.run_task(
            lambda context: merge_pdfs_task(context, list(self.pdf_files), self.output_dir, translate=self.tr),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_output_path = result["output_path"]
        self.summary_label.setText(
            self.tr(
                "summary.done",
                "Merged {file_count} PDF files into {path}.",
                file_count=result["file_count"],
                path=result["output_path"],
            )
        )
        self.output.setPlainText(
            self.tr(
                "output.done",
                "PDF merge complete.\nFiles merged: {file_count}\nOutput: {path}",
                file_count=result["file_count"],
                path=result["output_path"],
            )
        )
        self.open_output_button.setEnabled(True)
        self.services.record_run(self.plugin_id, "SUCCESS", self.tr("run.success", "Merged {count} PDFs", count=result["file_count"]))

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self.tr("error.unknown", "Unknown PDF suite error")) if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "PDF suite failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_output(self) -> None:
        if self._latest_output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_output_path))
