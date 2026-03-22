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
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin


def merge_pdfs_task(context, file_paths: list[str], output_dir: str):
    try:
        import PyPDF2
    except ImportError as exc:
        raise RuntimeError("PyPDF2 is required to merge PDFs.") from exc

    merger = PyPDF2.PdfMerger()
    total = len(file_paths)
    for index, file_path in enumerate(file_paths, start=1):
        context.progress(index / float(total))
        merger.append(file_path)
        context.log(f"Added {os.path.basename(file_path)}")

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "Merged_Document_Output.pdf")
    merger.write(output_path)
    merger.close()
    context.progress(1.0)
    context.log(f"Merged PDF written to {output_path}")
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
        self.pdf_files: list[str] = []
        self._latest_output_path = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("PDF Core Engine")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            "Attach multiple PDF files in order, choose an output folder, and merge them into a single document."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)
        add_button = QPushButton("Add PDFs")
        add_button.clicked.connect(self._add_files)
        buttons_row.addWidget(add_button, 0, Qt.AlignmentFlag.AlignLeft)
        clear_button = QPushButton("Clear List")
        clear_button.clicked.connect(self._clear_files)
        buttons_row.addWidget(clear_button, 0, Qt.AlignmentFlag.AlignLeft)
        buttons_row.addStretch(1)
        layout.addLayout(buttons_row)

        self.file_list = QListWidget()
        layout.addWidget(self.file_list, 1)

        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        self.output_dir_label = QLabel(str(self.services.default_output_path()))
        self.output_dir_label.setWordWrap(True)
        out_row.addWidget(self.output_dir_label, 1)
        browse_out_button = QPushButton("Output Folder")
        browse_out_button.clicked.connect(self._choose_output_dir)
        out_row.addWidget(browse_out_button)
        layout.addLayout(out_row)
        self.output_dir = str(self.services.default_output_path())

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Merge PDFs")
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_output_button = QPushButton("Open Output")
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self._open_output)
        controls.addWidget(self.open_output_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.progress, 1)
        layout.addLayout(controls)

        summary_card = QFrame()
        summary_card.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }"
        )
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel("Add PDF files to begin.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("PDF merge summary will appear here.")
        layout.addWidget(self.output, 1)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select PDF Files",
            str(self.services.default_output_path()),
            "PDF Documents (*.pdf)",
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
            "Select Output Folder",
            self.output_dir,
        )
        if folder:
            self.output_dir = folder
            self.output_dir_label.setText(folder)

    def _run(self) -> None:
        if not self.pdf_files:
            QMessageBox.warning(self, "Missing Input", "Add at least one PDF file.")
            return

        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)
        self.progress.setValue(0)
        self.output.setPlainText("")
        self.summary_label.setText("Merging PDFs...")

        self.services.run_task(
            lambda context: merge_pdfs_task(context, list(self.pdf_files), self.output_dir),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            on_progress=self._handle_progress,
        )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_output_path = result["output_path"]
        self.summary_label.setText(
            f"Merged {result['file_count']} PDF files into {result['output_path']}."
        )
        self.output.setPlainText(
            f"PDF merge complete.\nFiles merged: {result['file_count']}\nOutput: {result['output_path']}"
        )
        self.open_output_button.setEnabled(True)
        self.services.record_run(self.plugin_id, "SUCCESS", f"Merged {result['file_count']} PDFs")

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown PDF suite error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("PDF suite failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_output(self) -> None:
        if self._latest_output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_output_path))
