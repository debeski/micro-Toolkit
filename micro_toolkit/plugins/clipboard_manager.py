from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSortFilterProxyModel, QTimer
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.clipboard_store import ClipboardEntry, ClipboardStore
from micro_toolkit.core.plugin_api import QtPlugin


TYPE_LABELS = {
    "ALL": "All",
    "text": "Text",
    "code": "Code",
    "url": "URL",
    "file_path": "Path",
    "table": "Table",
    "rich_text": "Rich",
}


@dataclass(frozen=True)
class ClipboardRow:
    entry_id: int
    content: str
    preview: str
    content_type: str
    label: str
    created_at: str


def build_preview(text: str, length: int = 88) -> str:
    normalized = " ".join((text or "").replace("\t", "    ").split())
    if len(normalized) <= length:
        return normalized
    return normalized[: length - 3] + "..."


class ClipboardTableModel(QAbstractTableModel):
    HEADERS = ["Type", "Label", "Preview", "Captured"]

    def __init__(self):
        super().__init__()
        self._rows: list[ClipboardRow] = []

    def set_rows(self, rows: list[ClipboardRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return TYPE_LABELS.get(row.content_type, row.content_type.title())
            if index.column() == 1:
                return row.label
            if index.column() == 2:
                return row.preview
            if index.column() == 3:
                return row.created_at
        if role == Qt.ItemDataRole.UserRole:
            return row
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return str(section + 1)

    def row_at(self, row_index: int) -> ClipboardRow | None:
        if 0 <= row_index < len(self._rows):
            return self._rows[row_index]
        return None


class LabelManagerDialog(QDialog):
    def __init__(self, store: ClipboardStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Manage Labels")
        self.resize(360, 320)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        note = QLabel("Create reusable labels for clipboard items.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.list_box = QPlainTextEdit()
        self.list_box.setReadOnly(True)
        layout.addWidget(self.list_box, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.new_label_input = QLineEdit()
        self.new_label_input.setPlaceholderText("New label name")
        row.addWidget(self.new_label_input, 1)
        add_button = QPushButton("Add")
        add_button.clicked.connect(self._add_label)
        row.addWidget(add_button)
        layout.addLayout(row)

        delete_button = QPushButton("Delete Label")
        delete_button.clicked.connect(self._delete_label)
        layout.addWidget(delete_button, 0, Qt.AlignmentFlag.AlignLeft)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh(self) -> None:
        labels = self.store.list_labels()
        self.list_box.setPlainText("\n".join(labels) if labels else "No labels yet.")

    def _add_label(self) -> None:
        label = self.new_label_input.text().strip()
        if not label:
            return
        self.store.add_label(label)
        self.new_label_input.clear()
        self._refresh()

    def _delete_label(self) -> None:
        labels = self.store.list_labels()
        if not labels:
            return
        label, accepted = QInputDialog.getItem(self, "Delete Label", "Label", labels, 0, False)
        if accepted and label:
            self.store.delete_label(label)
            self._refresh()


class ClipboardManagerPlugin(QtPlugin):
    plugin_id = "clip_manager"
    name = "Clipboard Manager"
    description = "A standalone clipboard workspace with persistent history, labels, filtering, and live capture."
    category = ""
    standalone = True

    def create_widget(self, services) -> QWidget:
        return ClipboardManagerPage(services, self.plugin_id)


class ClipboardManagerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.store = ClipboardStore(self.services.database_path)
        self.clipboard = QGuiApplication.clipboard()
        self.model = ClipboardTableModel()
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._auto_capture_enabled = True
        self._suspend_capture_once = False
        self._last_seen_text = ""
        self._build_ui()
        self._wire_events()
        self._refresh_entries()
        self._bootstrap_existing_clipboard()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        title = QLabel("Clipboard Manager")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        outer.addWidget(title)

        description = QLabel(
            "This clipboard workspace uses native clipboard signals, a persistent SQLite store, label management, and a table/detail layout instead of an ad-hoc row pool."
        )
        description.setWordWrap(True)
        description.setStyleSheet("font-size: 14px; color: #43535c;")
        outer.addWidget(description)

        toolbar_card = QFrame()
        toolbar_card.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }"
        )
        toolbar = QGridLayout(toolbar_card)
        toolbar.setContentsMargins(16, 14, 16, 14)
        toolbar.setHorizontalSpacing(10)
        toolbar.setVerticalSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search clipboard history...")
        toolbar.addWidget(self.search_input, 0, 0, 1, 2)

        self.type_filter = QComboBox()
        for value, label in TYPE_LABELS.items():
            self.type_filter.addItem(label, value)
        toolbar.addWidget(self.type_filter, 0, 2)

        self.label_filter = QComboBox()
        self.label_filter.addItem("All Labels", "")
        toolbar.addWidget(self.label_filter, 0, 3)

        self.auto_capture_checkbox = QCheckBox("Auto capture")
        self.auto_capture_checkbox.setChecked(True)
        toolbar.addWidget(self.auto_capture_checkbox, 1, 0)

        self.capture_button = QPushButton("Capture Current")
        toolbar.addWidget(self.capture_button, 1, 1)

        self.manage_labels_button = QPushButton("Manage Labels")
        toolbar.addWidget(self.manage_labels_button, 1, 2)

        self.clear_history_button = QPushButton("Clear History")
        toolbar.addWidget(self.clear_history_button, 1, 3)

        outer.addWidget(toolbar_card)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        self.table_view = QTableView()
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_view.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        left_layout.addWidget(self.table_view, 1)

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        summary_card = QFrame()
        summary_card.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }"
        )
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel("Select a clipboard item to inspect and act on it.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        right_layout.addWidget(summary_card)

        detail_actions = QHBoxLayout()
        detail_actions.setSpacing(10)
        self.copy_button = QPushButton("Copy Selected")
        detail_actions.addWidget(self.copy_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.label_button = QPushButton("Set Label")
        detail_actions.addWidget(self.label_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.delete_button = QPushButton("Delete Selected")
        detail_actions.addWidget(self.delete_button, 0, Qt.AlignmentFlag.AlignLeft)
        detail_actions.addStretch(1)
        right_layout.addLayout(detail_actions)

        self.detail_view = QPlainTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setPlaceholderText("Clipboard content preview will appear here.")
        right_layout.addWidget(self.detail_view, 1)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

    def _wire_events(self) -> None:
        self.search_input.textChanged.connect(self._refresh_entries)
        self.type_filter.currentIndexChanged.connect(self._refresh_entries)
        self.label_filter.currentIndexChanged.connect(self._refresh_entries)
        self.auto_capture_checkbox.toggled.connect(self._set_auto_capture)
        self.capture_button.clicked.connect(self._capture_current_clipboard)
        self.manage_labels_button.clicked.connect(self._manage_labels)
        self.clear_history_button.clicked.connect(self._clear_history)
        self.copy_button.clicked.connect(self._copy_selected)
        self.label_button.clicked.connect(self._set_label_for_selected)
        self.delete_button.clicked.connect(self._delete_selected)
        self.table_view.selectionModel().selectionChanged.connect(self._update_detail_panel)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)
        self.clipboard.dataChanged.connect(self._handle_clipboard_changed)

    def _bootstrap_existing_clipboard(self) -> None:
        # Capture the current clipboard text once at startup without duplicating future self-copies.
        QTimer.singleShot(0, self._capture_current_clipboard)

    def _set_auto_capture(self, enabled: bool) -> None:
        self._auto_capture_enabled = enabled
        self.services.log("Clipboard auto-capture enabled." if enabled else "Clipboard auto-capture paused.")

    def _selected_row(self) -> ClipboardRow | None:
        selection_model = self.table_view.selectionModel()
        if selection_model is None or not selection_model.hasSelection():
            return None
        proxy_index = selection_model.selectedRows()[0]
        source_index = self.proxy_model.mapToSource(proxy_index)
        return self.model.row_at(source_index.row())

    def _current_filters(self) -> tuple[str, str, str]:
        return (
            self.search_input.text().strip(),
            self.type_filter.currentData(),
            self.label_filter.currentData(),
        )

    def _refresh_entries(self) -> None:
        search, content_type, label = self._current_filters()
        entries = self.store.list_entries(search=search, content_type=content_type, label=label)
        rows = [
            ClipboardRow(
                entry_id=entry.entry_id,
                content=entry.content,
                preview=build_preview(entry.content),
                content_type=entry.content_type,
                label=entry.label,
                created_at=entry.created_at,
            )
            for entry in entries
        ]
        self.model.set_rows(rows)
        self._refresh_label_filter()
        self._update_detail_panel()

    def _refresh_label_filter(self) -> None:
        current_label = self.label_filter.currentData()
        labels = self.store.list_labels()
        self.label_filter.blockSignals(True)
        self.label_filter.clear()
        self.label_filter.addItem("All Labels", "")
        for label in labels:
            self.label_filter.addItem(label, label)
        index = self.label_filter.findData(current_label)
        self.label_filter.setCurrentIndex(index if index >= 0 else 0)
        self.label_filter.blockSignals(False)

    def _handle_clipboard_changed(self) -> None:
        if self._suspend_capture_once:
            self._suspend_capture_once = False
            return
        if self._auto_capture_enabled:
            self._capture_current_clipboard()

    def _capture_current_clipboard(self) -> None:
        mime_data = self.clipboard.mimeData()
        if mime_data is None:
            return
        text = mime_data.text() or ""
        normalized = text.strip()
        if not normalized:
            return
        if normalized == self._last_seen_text:
            return
        inserted = self.store.add_entry(normalized)
        self._last_seen_text = normalized
        if inserted:
            self.services.log("Clipboard entry captured.")
            self._refresh_entries()

    def _update_detail_panel(self) -> None:
        row = self._selected_row()
        if row is None:
            self.summary_label.setText("Select a clipboard item to inspect and act on it.")
            self.detail_view.clear()
            return
        label_text = row.label or "No label"
        type_text = TYPE_LABELS.get(row.content_type, row.content_type.title())
        self.summary_label.setText(
            f"{type_text} item captured at {row.created_at}. Label: {label_text}."
        )
        self.detail_view.setPlainText(row.content)

    def _copy_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._suspend_capture_once = True
        self.clipboard.setText(row.content)
        self._last_seen_text = row.content.strip()
        self.services.log("Clipboard item copied back to the system clipboard.")

    def _set_label_for_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        labels = [""] + self.store.list_labels()
        current_index = labels.index(row.label) if row.label in labels else 0
        label, accepted = QInputDialog.getItem(
            self,
            "Set Label",
            "Choose or clear label",
            labels,
            current_index,
            False,
        )
        if accepted:
            if label:
                self.store.add_label(label)
            self.store.update_label(row.entry_id, label)
            self.services.log("Clipboard label updated.")
            self._refresh_entries()

    def _delete_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self.store.delete_entry(row.entry_id)
        self.services.log("Clipboard entry deleted.")
        self._refresh_entries()

    def _clear_history(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Clear Clipboard History",
            "Delete all saved clipboard entries from the local history database?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.clear_entries()
        self.services.log("Clipboard history cleared.")
        self._refresh_entries()

    def _manage_labels(self) -> None:
        dialog = LabelManagerDialog(self.store, self)
        dialog.exec()
        self._refresh_entries()

    def _show_context_menu(self, position) -> None:
        row = self._selected_row()
        if row is None:
            return
        menu = QMenu(self)
        copy_action = QAction("Copy Selected", self)
        copy_action.triggered.connect(self._copy_selected)
        menu.addAction(copy_action)

        label_action = QAction("Set Label", self)
        label_action.triggered.connect(self._set_label_for_selected)
        menu.addAction(label_action)

        delete_action = QAction("Delete Selected", self)
        delete_action.triggered.connect(self._delete_selected)
        menu.addAction(delete_action)

        menu.exec(self.table_view.viewport().mapToGlobal(position))
