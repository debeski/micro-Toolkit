from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.clipboard_store import ClipboardStore


def _preview(text: str, length: int = 72) -> str:
    normalized = " ".join((text or "").split())
    return normalized if len(normalized) <= length else normalized[: length - 3] + "..."


class ClipboardQuickPanel(QWidget):
    def __init__(self, services):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.services = services
        self.store = ClipboardStore(self.services.database_path)
        self.clipboard = QGuiApplication.clipboard()
        self.setObjectName("ClipboardQuickPanel")
        self.setWindowTitle("Clipboard Quick Panel")
        self.resize(520, 420)
        self._build_ui()
        self._refresh_entries()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Clipboard Quick History")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter recent clipboard items...")
        self.search_input.textChanged.connect(self._refresh_entries)
        layout.addWidget(self.search_input)

        shell = QFrame()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(8)

        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self._update_preview)
        self.list_widget.itemDoubleClicked.connect(self._copy_selected)
        shell_layout.addWidget(self.list_widget, 1)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select an item to preview it here.")
        self.preview.setMaximumHeight(140)
        shell_layout.addWidget(self.preview)
        layout.addWidget(shell, 1)

        hint = QLabel("Enter or double-click to copy. Esc hides the panel.")
        hint.setStyleSheet("font-size: 12px; color: palette(mid);")
        layout.addWidget(hint)

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
            return
        self._refresh_entries()
        self._move_near_cursor()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _refresh_entries(self) -> None:
        search = self.search_input.text().strip()
        entries = self.store.list_entries(search=search)[:25]
        self.list_widget.clear()
        for entry in entries:
            label = f"[{entry.content_type}] {_preview(entry.content)}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list_widget.addItem(item)
        if entries:
            self.list_widget.setCurrentRow(0)
        else:
            self.preview.clear()

    def _update_preview(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            self.preview.clear()
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        self.preview.setPlainText(entry.content)

    def _copy_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        self.clipboard.setText(entry.content)
        self.services.log("Copied clipboard history item from quick panel.")
        self.hide()

    def keyPressEvent(self, event) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self._copy_selected()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.hide()

    def _move_near_cursor(self) -> None:
        cursor_pos = QCursor.pos()
        target = QPoint(cursor_pos.x() - int(self.width() / 2), cursor_pos.y() - int(self.height() / 2))
        self.move(target)


class ClipboardQuickPanelController(QObject):
    def __init__(self, services):
        super().__init__()
        self.services = services
        self._panel: ClipboardQuickPanel | None = None

    def toggle(self) -> None:
        panel = self._panel or self._create_panel()
        panel.toggle()

    def _create_panel(self) -> ClipboardQuickPanel:
        self._panel = ClipboardQuickPanel(self.services)
        return self._panel
