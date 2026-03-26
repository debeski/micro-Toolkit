from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSortFilterProxyModel, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
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
    QStackedWidget,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.clipboard_store import ClipboardEntry, ClipboardStore
from micro_toolkit.core.plugin_api import QtPlugin
from micro_toolkit.core.page_style import card_style, muted_text_style, page_title_style
from micro_toolkit.core.widgets import ScrollSafeComboBox, adaptive_grid_columns, width_breakpoint


QComboBox = ScrollSafeComboBox


TYPE_LABELS = {
    "ALL": "type.all",
    "text": "type.text",
    "code": "type.code",
    "url": "type.url",
    "file_path": "type.path",
    "table": "type.table",
    "rich_text": "type.rich",
    "image": "type.image",
    "files": "type.files",
}


@dataclass(frozen=True)
class ClipboardRow:
    entry_id: int
    content: str
    preview: str
    content_type: str
    label: str
    category: str
    pinned: bool
    created_at: str
    html_content: str
    image_path: str
    file_paths: list[str]
    metadata: dict


def build_preview(entry: ClipboardEntry, length: int = 88) -> str:
    if entry.content_type == "image":
        width = entry.metadata.get("width")
        height = entry.metadata.get("height")
        if width and height:
            return f"{width} x {height} image"
        return "Captured image"
    if entry.content_type == "files":
        names = [Path(path).name for path in entry.file_paths]
        if not names:
            return "Copied files"
        joined = ", ".join(names[:3])
        if len(names) > 3:
            joined += f" +{len(names) - 3}"
        return joined
    normalized = " ".join((entry.content or "").replace("\t", "    ").split())
    if len(normalized) <= length:
        return normalized
    return normalized[: length - 3] + "..."


class ClipboardTableModel(QAbstractTableModel):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._rows: list[ClipboardRow] = []

    def _pt(self, key: str, default: str) -> str:
        return self.services.plugin_text(self.plugin_id, key, default)

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
        return 6

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return "Pinned" if row.pinned else ""
            if index.column() == 1:
                return TYPE_LABELS.get(row.content_type, row.content_type.title())
            if index.column() == 2:
                return row.label
            if index.column() == 3:
                return row.category
            if index.column() == 4:
                return row.preview
            if index.column() == 5:
                return row.created_at
        if role == Qt.ItemDataRole.UserRole:
            return row
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            headers = [
                self._pt("header.pin", "Pin"),
                self._pt("header.type", "Type"),
                self._pt("header.label", "Label"),
                self._pt("header.category", "Category"),
                self._pt("header.preview", "Preview"),
                self._pt("header.captured", "Captured"),
            ]
            return headers[section]
        return str(section + 1)

    def row_at(self, row_index: int) -> ClipboardRow | None:
        if 0 <= row_index < len(self._rows):
            return self._rows[row_index]
        return None

    def row_for_entry(self, entry_id: int) -> ClipboardRow | None:
        for row in self._rows:
            if row.entry_id == entry_id:
                return row
        return None


class NameManagerDialog(QDialog):
    def __init__(self, title: str, note: str, placeholder: str, values_getter, add_callback, delete_callback, parent=None, pt=None):
        super().__init__(parent)
        self._pt = pt or (lambda k, d, **kw: d.format(**kw) if kw else d)
        self._values_getter = values_getter
        self._add_callback = add_callback
        self._delete_callback = delete_callback
        self.setWindowTitle(title)
        self.resize(360, 320)
        self._placeholder = placeholder
        self._note = note
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        note = QLabel(self._note)
        note.setWordWrap(True)
        layout.addWidget(note)

        self.list_box = QPlainTextEdit()
        self.list_box.setReadOnly(True)
        layout.addWidget(self.list_box, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.new_input = QLineEdit()
        self.new_input.setPlaceholderText(self._placeholder)
        row.addWidget(self.new_input, 1)
        add_button = QPushButton(self._pt("dialog.button.add", "Add"))
        add_button.clicked.connect(self._add_value)
        row.addWidget(add_button)
        layout.addLayout(row)

        delete_button = QPushButton(self._pt("dialog.button.delete", "Delete"))
        delete_button.clicked.connect(self._delete_value)
        layout.addWidget(delete_button, 0, Qt.AlignmentFlag.AlignLeft)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh(self) -> None:
        values = self._values_getter()
        self.list_box.setPlainText("\n".join(values) if values else self._pt("dialog.empty.items", "No items yet."))

    def _add_value(self) -> None:
        value = self.new_input.text().strip()
        if not value:
            return
        self._add_callback(value)
        self.new_input.clear()
        self._refresh()

    def _delete_value(self) -> None:
        values = self._values_getter()
        if not values:
            return
        value, accepted = QInputDialog.getItem(self, self._pt("dialog.delete.title", "Delete"), self._pt("dialog.delete.prompt", "Value"), values, 0, False)
        if accepted and value:
            self._delete_callback(value)
            self._refresh()


class ClipboardManagerPlugin(QtPlugin):
    plugin_id = "clip_manager"
    name = "Clipboard Manager"
    description = "A clipboard workspace with persistent history, pinned snippets, categories, and multi-format capture."
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
        self.model = ClipboardTableModel(self.services, self.plugin_id)
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._auto_capture_enabled = True
        self._suspend_capture_once = False
        self._responsive_bucket = ""
        self._responsive_refresh_pending = False
        self._build_ui()
        self._wire_events()
        self._refresh_entries()
        self._bootstrap_existing_clipboard()
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel(self._pt("title", "Clipboard Manager"))
        outer.addWidget(self.title_label)

        self.description_label = QLabel(
            self._pt("description", "Capture plain text, rich text, copied files, and images. Pin important snippets, organize them into categories, and restore the original format back to the clipboard.")
        )
        self.description_label.setWordWrap(True)
        outer.addWidget(self.description_label)

        self.toolbar_card = QFrame()
        self.toolbar_layout = QGridLayout(self.toolbar_card)
        self.toolbar_layout.setContentsMargins(16, 14, 16, 14)
        self.toolbar_layout.setHorizontalSpacing(10)
        self.toolbar_layout.setVerticalSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self._pt("search.placeholder", "Search clipboard history..."))
        self.toolbar_layout.addWidget(self.search_input, 0, 0, 1, 2)

        self.type_filter = QComboBox()
        for value, label_key in TYPE_LABELS.items():
            self.type_filter.addItem(self._pt(label_key, label_key.split('.')[-1].title()), value)
        self.toolbar_layout.addWidget(self.type_filter, 0, 2)

        self.label_filter = QComboBox()
        self.label_filter.addItem(self._pt("filter.labels.all", "All Labels"), "")
        self.toolbar_layout.addWidget(self.label_filter, 0, 3)

        self.category_filter = QComboBox()
        self.category_filter.addItem(self._pt("filter.categories.all", "All Categories"), "")
        self.toolbar_layout.addWidget(self.category_filter, 0, 4)

        self.pinned_only_checkbox = QCheckBox(self._pt("checkbox.pinned_only", "Pinned only"))
        self.toolbar_layout.addWidget(self.pinned_only_checkbox, 1, 0)

        self.auto_capture_checkbox = QCheckBox(self._pt("checkbox.auto_capture", "Auto capture"))
        self.auto_capture_checkbox.setChecked(True)
        self.toolbar_layout.addWidget(self.auto_capture_checkbox, 1, 1)

        self.action_host = QWidget()
        self.action_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.action_host.setStyleSheet("background: transparent;")
        self.action_host_layout = QGridLayout(self.action_host)
        self.action_host_layout.setContentsMargins(0, 0, 0, 0)
        self.action_host_layout.setHorizontalSpacing(8)
        self.action_host_layout.setVerticalSpacing(8)

        self.capture_button = QPushButton(self._pt("button.capture", "Capture Current"))
        self.manage_labels_button = QPushButton(self._pt("button.manage_labels", "Manage Labels"))
        self.manage_categories_button = QPushButton(self._pt("button.manage_categories", "Manage Categories"))
        self.clear_history_button = QPushButton(self._pt("button.clear_history", "Clear History"))
        self._action_buttons = [
            self.capture_button,
            self.manage_labels_button,
            self.manage_categories_button,
            self.clear_history_button,
        ]
        for button in self._action_buttons:
            button.setMinimumWidth(150)
        self.toolbar_layout.addWidget(self.action_host, 1, 2, 2, 3)
        self._relayout_action_buttons()

        outer.addWidget(self.toolbar_card)

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(self.content_splitter, 1)

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
        self.table_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_view.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_view.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table_view.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        left_layout.addWidget(self.table_view, 1)

        self.content_splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel(self._pt("summary.empty", "Select a clipboard item to inspect and act on it."))
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        right_layout.addWidget(self.summary_card)

        self.preview_stack = QStackedWidget()
        right_layout.addWidget(self.preview_stack, 1)

        self.text_preview = QTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setPlaceholderText(self._pt("preview.text.placeholder", "Clipboard content preview will appear here."))
        self.preview_stack.addWidget(self.text_preview)

        self.image_preview = QLabel(self._pt("preview.image.placeholder", "Image preview will appear here."))
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumHeight(220)
        self.image_preview.setWordWrap(True)
        self.preview_stack.addWidget(self.image_preview)

        self.metadata_view = QPlainTextEdit()
        self.metadata_view.setReadOnly(True)
        self.metadata_view.setPlaceholderText(self._pt("preview.metadata.placeholder", "Clipboard metadata will appear here."))
        self.metadata_view.setMaximumHeight(170)
        right_layout.addWidget(self.metadata_view)

        self.content_splitter.addWidget(right_panel)
        self.content_splitter.setStretchFactor(0, 3)
        self.content_splitter.setStretchFactor(1, 2)
        self._apply_theme_styles()
        self._apply_responsive_layout(force=True)

    def _wire_events(self) -> None:
        self.search_input.textChanged.connect(self._refresh_entries)
        self.type_filter.currentIndexChanged.connect(self._refresh_entries)
        self.label_filter.currentIndexChanged.connect(self._refresh_entries)
        self.category_filter.currentIndexChanged.connect(self._refresh_entries)
        self.pinned_only_checkbox.toggled.connect(self._refresh_entries)
        self.auto_capture_checkbox.toggled.connect(self._set_auto_capture)
        self.capture_button.clicked.connect(self._capture_current_clipboard)
        self.manage_labels_button.clicked.connect(self._manage_labels)
        self.manage_categories_button.clicked.connect(self._manage_categories)
        self.clear_history_button.clicked.connect(self._clear_history)
        self.table_view.selectionModel().selectionChanged.connect(self._update_detail_panel)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)
        self.clipboard.dataChanged.connect(self._handle_clipboard_changed)

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        self.title_label.setStyleSheet(page_title_style(palette, size=26, weight=700))
        self.description_label.setStyleSheet(muted_text_style(palette))
        self.summary_label.setStyleSheet(muted_text_style(palette, size=13))
        for frame in (self.toolbar_card, self.summary_card):
            frame.setStyleSheet(card_style(palette))

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()
        self._update_detail_panel()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()
        self._schedule_responsive_refresh()

    def _apply_responsive_layout(self, *, force: bool = False) -> None:
        bucket = width_breakpoint(self.width(), compact_max=700, medium_max=1160)
        compact = bucket == "compact"
        structure_changed = force or bucket != self._responsive_bucket
        self._responsive_bucket = bucket

        if structure_changed:
            self.content_splitter.setOrientation(Qt.Orientation.Horizontal)

            while self.toolbar_layout.count():
                item = self.toolbar_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(self.toolbar_card)

            if compact:
                self.toolbar_layout.addWidget(self.search_input, 0, 0, 1, 5)
                self.toolbar_layout.addWidget(self.type_filter, 1, 0, 1, 2)
                self.toolbar_layout.addWidget(self.label_filter, 1, 2, 1, 3)
                self.toolbar_layout.addWidget(self.category_filter, 2, 0, 1, 3)
                self.toolbar_layout.addWidget(self.pinned_only_checkbox, 2, 3)
                self.toolbar_layout.addWidget(self.auto_capture_checkbox, 2, 4)
                self.toolbar_layout.addWidget(self.action_host, 3, 0, 1, 5)
            else:
                self.toolbar_layout.addWidget(self.search_input, 0, 0, 1, 2)
                self.toolbar_layout.addWidget(self.type_filter, 0, 2)
                self.toolbar_layout.addWidget(self.label_filter, 0, 3)
                self.toolbar_layout.addWidget(self.category_filter, 0, 4)
                self.toolbar_layout.addWidget(self.pinned_only_checkbox, 1, 0)
                self.toolbar_layout.addWidget(self.auto_capture_checkbox, 1, 1)
                self.toolbar_layout.addWidget(self.action_host, 2, 0, 1, 5)
        self._relayout_action_buttons()

    def _relayout_action_buttons(self) -> None:
        if not hasattr(self, "action_host_layout"):
            return
        while self.action_host_layout.count():
            item = self.action_host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self.action_host)

        available_width = self.action_host.contentsRect().width() or self.action_host.width() or self.toolbar_card.contentsRect().width()
        columns = adaptive_grid_columns(
            available_width,
            item_widths=[button.sizeHint().width() for button in self._action_buttons],
            spacing=self.action_host_layout.horizontalSpacing(),
            min_columns=2,
        )
        for index, button in enumerate(self._action_buttons):
            row = index // columns
            column = index % columns
            self.action_host_layout.addWidget(button, row, column)
        for column in range(columns):
            self.action_host_layout.setColumnStretch(column, 1)

    def _schedule_responsive_refresh(self) -> None:
        if self._responsive_refresh_pending:
            return
        self._responsive_refresh_pending = True
        QTimer.singleShot(0, self._run_responsive_refresh)

    def _run_responsive_refresh(self) -> None:
        self._responsive_refresh_pending = False
        self._apply_responsive_layout()

    def _bootstrap_existing_clipboard(self) -> None:
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

    def _current_filters(self) -> tuple[str, str, str, str, bool]:
        return (
            self.search_input.text().strip(),
            self.type_filter.currentData(),
            self.label_filter.currentData(),
            self.category_filter.currentData(),
            self.pinned_only_checkbox.isChecked(),
        )

    def _refresh_entries(self) -> None:
        search, content_type, label, category, pinned_only = self._current_filters()
        entries = self.store.list_entries(
            search=search,
            content_type=content_type,
            label=label,
            category=category,
            pinned_only=pinned_only,
        )
        rows = [
            ClipboardRow(
                entry_id=entry.entry_id,
                content=entry.content,
                preview=build_preview(entry),
                content_type=entry.content_type,
                label=entry.label,
                category=entry.category,
                pinned=entry.pinned,
                created_at=entry.created_at,
                html_content=entry.html_content,
                image_path=entry.image_path,
                file_paths=entry.file_paths,
                metadata=entry.metadata,
            )
            for entry in entries
        ]
        self.model.set_rows(rows)
        self._refresh_label_filter()
        self._refresh_category_filter()
        self._update_detail_panel()

    def _refresh_label_filter(self) -> None:
        current_label = self.label_filter.currentData()
        labels = self.store.list_labels()
        self.label_filter.blockSignals(True)
        self.label_filter.clear()
        self.label_filter.addItem(self._pt("filter.labels.all", "All Labels"), "")
        for label in labels:
            self.label_filter.addItem(label, label)
        index = self.label_filter.findData(current_label)
        self.label_filter.setCurrentIndex(index if index >= 0 else 0)
        self.label_filter.blockSignals(False)

    def _refresh_category_filter(self) -> None:
        current_category = self.category_filter.currentData()
        categories = self.store.list_categories()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem(self._pt("filter.categories.all", "All Categories"), "")
        for category in categories:
            self.category_filter.addItem(category, category)
        index = self.category_filter.findData(current_category)
        self.category_filter.setCurrentIndex(index if index >= 0 else 0)
        self.category_filter.blockSignals(False)

    def _handle_clipboard_changed(self) -> None:
        if self._suspend_capture_once:
            self._suspend_capture_once = False
            return
        if self._auto_capture_enabled:
            self._capture_current_clipboard()

    def _capture_current_clipboard(self) -> None:
        inserted = self.store.add_mime_entry(self.clipboard.mimeData())
        if inserted:
            self.services.log(self._pt("log.captured", "Clipboard entry captured."))
            self._refresh_entries()

    def _update_detail_panel(self) -> None:
        row = self._selected_row()
        if row is None:
            self.summary_label.setText(self._pt("summary.empty", "Select a clipboard item to inspect and act on it."))
            self.text_preview.clear()
            self.image_preview.clear()
            self.image_preview.setText(self._pt("preview.image.placeholder", "Image preview will appear here."))
            self.metadata_view.clear()
            self.preview_stack.setCurrentWidget(self.text_preview)
            return

        label_text = row.label or self._pt("summary.no_label", "No label")
        category_text = row.category or self._pt("summary.uncategorized", "Uncategorized")
        pin_text = self._pt("summary.pinned", "Pinned") if row.pinned else self._pt("summary.history", "History")
        type_text = TYPE_LABELS.get(row.content_type, row.content_type.title())
        if type_text.startswith("type."):
            type_text = self._pt(type_text, type_text.split('.')[-1].title())

        self.summary_label.setText(
            self._pt(
                "summary.item",
                "{pin_text} {type_text} item captured at {created_at}. Label: {label}. Category: {category}.",
                pin_text=pin_text,
                type_text=type_text.lower(),
                created_at=row.created_at,
                label=label_text,
                category=category_text,
            )
        )

        if row.content_type == "image" and row.image_path and Path(row.image_path).exists():
            pixmap = QPixmap(row.image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    420,
                    280,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.image_preview.setPixmap(scaled)
                self.image_preview.setText("")
                self.preview_stack.setCurrentWidget(self.image_preview)
            else:
                self.image_preview.setPixmap(QPixmap())
                self.image_preview.setText(self._pt("preview.image.unavailable", "Image preview unavailable."))
                self.preview_stack.setCurrentWidget(self.image_preview)
        elif row.html_content:
            self.text_preview.setHtml(row.html_content)
            self.preview_stack.setCurrentWidget(self.text_preview)
        elif row.content_type == "files":
            file_lines = row.file_paths or ([row.content] if row.content else [])
            self.text_preview.setPlainText("\n".join(file_lines))
            self.preview_stack.setCurrentWidget(self.text_preview)
        else:
            self.text_preview.setPlainText(row.content)
            self.preview_stack.setCurrentWidget(self.text_preview)

        yes_no = self._pt("meta.yes", "Yes") if row.pinned else self._pt("meta.no", "No")
        metadata_lines = [
            f"{self._pt('meta.type', 'Type')}: {type_text}",
            f"{self._pt('meta.pinned', 'Pinned')}: {yes_no}",
            f"{self._pt('meta.label', 'Label')}: {label_text}",
            f"{self._pt('meta.category', 'Category')}: {category_text}",
        ]
        if row.file_paths:
            metadata_lines.append(f"{self._pt('meta.files', 'Files')}: {len(row.file_paths)}")
        if row.metadata:
            metadata_lines.append("")
            metadata_lines.append(json.dumps(row.metadata, indent=2, ensure_ascii=False))
        self.metadata_view.setPlainText("\n".join(metadata_lines))

    def _copy_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._copy_entry(row.entry_id)

    def _copy_entry(self, entry_id: int) -> None:
        entry = self.store.get_entry(entry_id)
        if entry is None:
            return
        self._suspend_capture_once = True
        if self.store.restore_entry_to_clipboard(entry, self.clipboard):
            self.services.log(self._pt("log.restored", "Clipboard item restored to the system clipboard."))
        else:
            self._suspend_capture_once = False

    def _toggle_pin_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._toggle_pin(row.entry_id)

    def _toggle_pin(self, entry_id: int) -> None:
        row = self.model.row_for_entry(entry_id)
        if row is None:
            return
        self.store.update_pinned(entry_id, not row.pinned)
        self.services.log(self._pt("log.pin_updated", "Clipboard pin state updated."))
        self._refresh_entries()

    def _set_label_for_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._set_label_for_entry(row.entry_id)

    def _set_label_for_entry(self, entry_id: int) -> None:
        row = self.model.row_for_entry(entry_id)
        if row is None:
            return
        labels = [""] + self.store.list_labels()
        current_index = labels.index(row.label) if row.label in labels else 0
        label, accepted = QInputDialog.getItem(
            self,
            self._pt("dialog.label.title", "Set Label"),
            self._pt("dialog.label.prompt", "Choose or clear label"),
            labels,
            current_index,
            True,
        )
        if accepted:
            if label:
                self.store.add_label(label)
            self.store.update_label(row.entry_id, label)
            self.services.log(self._pt("log.label_updated", "Clipboard label updated."))
            self._refresh_entries()

    def _set_category_for_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._set_category_for_entry(row.entry_id)

    def _set_category_for_entry(self, entry_id: int) -> None:
        row = self.model.row_for_entry(entry_id)
        if row is None:
            return
        categories = [""] + self.store.list_categories()
        current_index = categories.index(row.category) if row.category in categories else 0
        category, accepted = QInputDialog.getItem(
            self,
            self._pt("dialog.category.title", "Set Category"),
            self._pt("dialog.category.prompt", "Choose or clear category"),
            categories,
            current_index,
            True,
        )
        if accepted:
            if category:
                self.store.add_category(category)
            self.store.update_category(row.entry_id, category)
            self.services.log(self._pt("log.category_updated", "Clipboard category updated."))
            self._refresh_entries()

    def _delete_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._delete_entry(row.entry_id)

    def _delete_entry(self, entry_id: int) -> None:
        row = self.model.row_for_entry(entry_id)
        if row is None:
            return
        self.store.delete_entry(row.entry_id)
        self.services.log(self._pt("log.deleted", "Clipboard entry deleted."))
        self._refresh_entries()

    def _clear_history(self) -> None:
        answer = QMessageBox.warning(
            self,
            self._pt("dialog.clear.title", "Clear Clipboard History"),
            self._pt("dialog.clear.prompt", "Delete all non-pinned clipboard entries from the local history database?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.clear_entries(preserve_pinned=True)
        self.services.log(self._pt("log.cleared", "Clipboard history cleared. Pinned entries were preserved."))
        self._refresh_entries()

    def _manage_labels(self) -> None:
        dialog = NameManagerDialog(
            self._pt("button.manage_labels", "Manage Labels"),
            self._pt("manager.labels.note", "Create reusable labels for clipboard items."),
            self._pt("manager.labels.placeholder", "New label name"),
            self.store.list_labels,
            self.store.add_label,
            self.store.delete_label,
            self,
            pt=self._pt,
        )
        dialog.exec()
        self._refresh_entries()

    def _manage_categories(self) -> None:
        dialog = NameManagerDialog(
            self._pt("button.manage_categories", "Manage Categories"),
            self._pt("manager.categories.note", "Create reusable categories for pinned snippets and saved clipboard entries."),
            self._pt("manager.categories.placeholder", "New category name"),
            self.store.list_categories,
            self.store.add_category,
            self.store.delete_category,
            self,
            pt=self._pt,
        )
        dialog.exec()
        self._refresh_entries()

    def _show_context_menu(self, position) -> None:
        row = self._selected_row()
        if row is None:
            return
        menu = QMenu(self)
        copy_action = QAction(self._pt("menu.copy", "Copy Selected"), self)
        copy_action.triggered.connect(self._copy_selected)
        menu.addAction(copy_action)

        pin_action = QAction(self._pt("menu.unpin", "Unpin Selected") if row.pinned else self._pt("menu.pin", "Pin Selected"), self)
        pin_action.triggered.connect(self._toggle_pin_selected)
        menu.addAction(pin_action)

        label_action = QAction(self._pt("menu.set_label", "Set Label"), self)
        label_action.triggered.connect(self._set_label_for_selected)
        menu.addAction(label_action)

        category_action = QAction(self._pt("menu.set_category", "Set Category"), self)
        category_action.triggered.connect(self._set_category_for_selected)
        menu.addAction(category_action)

        delete_action = QAction(self._pt("menu.delete", "Delete Selected"), self)
        delete_action.triggered.connect(self._delete_selected)
        menu.addAction(delete_action)

        menu.exec(self.table_view.viewport().mapToGlobal(position))
