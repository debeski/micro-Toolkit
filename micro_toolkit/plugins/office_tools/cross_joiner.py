from __future__ import annotations

import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
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
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin


def cross_join_task(context, file_a: str, col_a: str, file_b: str, col_b: str, output_dir: str):
    import pandas as pd

    context.log("Loading dataset A...")
    dataframe_a = pd.read_excel(file_a)
    context.log("Loading dataset B...")
    dataframe_b = pd.read_excel(file_b)
    context.progress(0.3)

    if col_a not in dataframe_a.columns or col_b not in dataframe_b.columns:
        raise ValueError(f"Columns '{col_a}' or '{col_b}' were not found in the selected workbooks.")

    context.log("Computing matches and deltas...")
    merged = pd.merge(dataframe_a, dataframe_b, left_on=col_a, right_on=col_b, how="inner")
    context.progress(0.55)
    delta_a = dataframe_a[~dataframe_a[col_a].isin(dataframe_b[col_b])]
    context.progress(0.75)
    delta_b = dataframe_b[~dataframe_b[col_b].isin(dataframe_a[col_a])]
    context.progress(0.9)

    os.makedirs(output_dir, exist_ok=True)
    outputs = []
    if not merged.empty:
        path = os.path.join(output_dir, "CrossMatched_Results.xlsx")
        merged.to_excel(path, index=False)
        outputs.append(("Matches", path, len(merged)))
    if not delta_a.empty:
        path = os.path.join(output_dir, "DeltaMissing_In_B.xlsx")
        delta_a.to_excel(path, index=False)
        outputs.append(("Only In A", path, len(delta_a)))
    if not delta_b.empty:
        path = os.path.join(output_dir, "DeltaMissing_In_A.xlsx")
        delta_b.to_excel(path, index=False)
        outputs.append(("Only In B", path, len(delta_b)))

    if not outputs:
        raise ValueError("No join outputs were generated.")

    context.progress(1.0)
    context.log(f"Cross join complete with {len(outputs)} output files.")
    return {
        "outputs": outputs,
        "file_a": os.path.basename(file_a),
        "file_b": os.path.basename(file_b),
    }


class CrossJoinerPlugin(QtPlugin):
    plugin_id = "cross_joiner"
    name = "Data Cross Joiner"
    description = "Compare two Excel datasets, export matches and deltas, and open the generated result files."
    category = "Office Utilities"

    def create_widget(self, services) -> QWidget:
        return CrossJoinerPage(services, self.plugin_id)


class CrossJoinerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._result_buttons = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Data Cross Joiner")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(title)

        description = QLabel(
            "Load two workbooks, choose the match columns, and export joined rows plus dataset deltas."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(description)

        self.file_a_input, self.col_a_input = self._add_dataset_row(layout, "Dataset A")
        self.file_b_input, self.col_b_input = self._add_dataset_row(layout, "Dataset B")

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton("Run Cross Join")
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

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
        self.summary_label = QLabel("Choose two workbooks and their match columns.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.results_host = QFrame()
        self.results_layout = QVBoxLayout(self.results_host)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(10)
        layout.addWidget(self.results_host)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Cross join summary will appear here.")
        layout.addWidget(self.output, 1)

    def _add_dataset_row(self, parent_layout, label_text: str):
        row = QHBoxLayout()
        row.setSpacing(10)

        label = QLabel(label_text)
        label.setFixedWidth(90)
        row.addWidget(label)

        file_input = QLineEdit()
        file_input.setPlaceholderText(f"{label_text} workbook...")
        row.addWidget(file_input, 1)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(lambda: self._browse_file(file_input))
        row.addWidget(browse_button)

        col_input = QLineEdit()
        col_input.setPlaceholderText("Match column")
        col_input.setFixedWidth(180)
        row.addWidget(col_input)

        parent_layout.addLayout(row)
        return file_input, col_input

    def _browse_file(self, target_input: QLineEdit) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Workbook",
            str(self.services.default_output_path()),
            "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)",
        )
        if file_path:
            target_input.setText(file_path)

    def _clear_result_buttons(self) -> None:
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _run(self) -> None:
        file_a = self.file_a_input.text().strip()
        col_a = self.col_a_input.text().strip()
        file_b = self.file_b_input.text().strip()
        col_b = self.col_b_input.text().strip()
        if not all([file_a, col_a, file_b, col_b]):
            QMessageBox.warning(self, "Missing Input", "Choose both workbooks and both match columns.")
            return

        self.run_button.setEnabled(False)
        self.progress.setValue(0)
        self.output.setPlainText("")
        self._clear_result_buttons()
        self.summary_label.setText("Running cross join...")

        self.services.run_task(
            lambda context: cross_join_task(
                context,
                file_a,
                col_a,
                file_b,
                col_b,
                str(self.services.default_output_path()),
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
        lines = [f"Compared {result['file_a']} against {result['file_b']}."]
        for label, path, row_count in result["outputs"]:
            lines.append(f"{label}: {row_count} rows -> {path}")
            button = QPushButton(f"Open {label}")
            button.clicked.connect(lambda _checked=False, file_path=path: QDesktopServices.openUrl(QUrl.fromLocalFile(file_path)))
            self.results_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)

        self.output.setPlainText("\n".join(lines))
        self.summary_label.setText(f"Generated {len(result['outputs'])} result file(s).")
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            f"Joined {result['file_a']} and {result['file_b']}",
        )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown cross join error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log("Cross join failed.", "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
