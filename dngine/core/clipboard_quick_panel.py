from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dngine.core.clipboard_store import ClipboardStore


def _preview(text: str, length: int = 72) -> str:
    normalized = " ".join((text or "").split())
    return normalized if len(normalized) <= length else normalized[: length - 3] + "..."


class ClipboardQuickPanel(QWidget):
    def __init__(self, services, *, open_full_callback=None, before_restore_callback=None):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.services = services
        self.store = ClipboardStore(self.services.database_path)
        self.clipboard = QGuiApplication.clipboard()
        self.open_full_callback = open_full_callback
        self.before_restore_callback = before_restore_callback
        self.setObjectName("ClipboardQuickPanel")
        self.resize(520, 420)
        self._build_ui()
        self._refresh_entries()
        self.refresh_ui()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _tr(self, key: str, default: str) -> str:
        translator = getattr(self.services, "i18n", None)
        if translator is None:
            return default
        return translator.tr(key, default)

    def _build_ui(self) -> None:
        palette = self.services.theme_manager.current_palette()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 700;")
        header.addWidget(self.title_label, 1)
        self.open_full_button = QPushButton()
        self.open_full_button.clicked.connect(self._open_full)
        header.addWidget(self.open_full_button, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header)

        self.search_input = QLineEdit()
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
        self.preview.setMaximumHeight(140)
        shell_layout.addWidget(self.preview)
        layout.addWidget(shell, 1)

        self.hint_label = QLabel()
        self.hint_label.setStyleSheet(f"font-size: 12px; color: {palette.text_muted};")
        layout.addWidget(self.hint_label)

    def refresh_ui(self) -> None:
        palette = self.services.theme_manager.current_palette()
        self.setWindowTitle(self._tr("clipboard.quick.window_title", "Clipboard Quick Panel"))
        self.title_label.setText(self._tr("clipboard.quick.title", "Clipboard Quick History"))
        self.search_input.setPlaceholderText(self._tr("clipboard.quick.search", "Filter recent clipboard items..."))
        self.preview.setPlaceholderText(self._tr("clipboard.quick.preview.placeholder", "Select an item to preview it here."))
        self.hint_label.setText(self._tr("clipboard.quick.hint", "Enter or double-click to copy. Esc hides the panel."))
        self.hint_label.setStyleSheet(f"font-size: 12px; color: {palette.text_muted};")
        self.open_full_button.setVisible(callable(self.open_full_callback))
        self.open_full_button.setText(self._tr("clipboard.quick.open_full", "Open Clip Snip"))

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
            return
        self.refresh_ui()
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
        if entry.content_type == "files" and entry.file_paths:
            self.preview.setPlainText("\n".join(entry.file_paths))
            return
        if entry.content_type == "image":
            self.preview.setPlainText(self._tr("clipboard.quick.preview.image", "Image entry. Press Enter or double-click to restore it to the clipboard."))
            return
        self.preview.setPlainText(entry.content)

    def _copy_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if callable(self.before_restore_callback):
            self.before_restore_callback()
        if self.store.restore_entry_to_clipboard(entry, self.clipboard):
            self.services.log(self._tr("clipboard.quick.log.restored", "Copied clipboard history item from quick panel."))
        self.hide()

    def _open_full(self) -> None:
        if not callable(self.open_full_callback):
            return
        self.open_full_callback()
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

    def eventFilter(self, watched, event) -> bool:
        if not self.isVisible():
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.MouseButtonPress:
            global_pos = None
            if hasattr(event, "globalPosition"):
                try:
                    global_pos = event.globalPosition().toPoint()
                except Exception:
                    global_pos = None
            elif hasattr(event, "globalPos"):
                try:
                    global_pos = event.globalPos()
                except Exception:
                    global_pos = None
            if global_pos is not None and not self.rect().contains(self.mapFromGlobal(global_pos)):
                self.hide()
        return super().eventFilter(watched, event)

    def _move_near_cursor(self) -> None:
        cursor_pos = QCursor.pos()
        target = QPoint(cursor_pos.x() - int(self.width() / 2), cursor_pos.y() - int(self.height() / 2))
        self.move(target)


class ClipboardQuickPanelController(QObject):
    def __init__(self, services, *, before_restore_callback=None):
        super().__init__()
        self.services = services
        self.before_restore_callback = before_restore_callback
        self._panel: ClipboardQuickPanel | None = None

    def toggle(self) -> None:
        panel = self._panel or self._create_panel()
        panel.toggle()

    def _create_panel(self) -> ClipboardQuickPanel:
        self._panel = ClipboardQuickPanel(
            self.services,
            open_full_callback=self._open_full_clipboard,
            before_restore_callback=self.before_restore_callback,
        )
        return self._panel

    def _open_full_clipboard(self) -> None:
        window = getattr(self.services, "main_window", None)
        if window is None:
            return
        restore = getattr(window, "restore_from_tray", None)
        if callable(restore):
            restore()
        window.open_plugin("clip_snip")
