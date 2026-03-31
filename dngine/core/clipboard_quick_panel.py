from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, QPoint, QTimer, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
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


def _preview(text: str, length: int = 56) -> str:
    normalized = " ".join((text or "").split())
    return normalized if len(normalized) <= length else normalized[: length - 3] + "..."


class ClipboardQuickPanel(QWidget):
    def __init__(self, services, *, open_full_callback=None, before_restore_callback=None):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.services = services
        self.store = ClipboardStore(self.services.database_path)
        self.clipboard = QGuiApplication.clipboard()
        self.open_full_callback = open_full_callback
        self.before_restore_callback = before_restore_callback
        self._drag_offset: QPoint | None = None
        self._manual_position: QPoint | None = None
        self._auto_hide_guard_active = False
        self._auto_hide_guard_timer = QTimer(self)
        self._auto_hide_guard_timer.setSingleShot(True)
        self._auto_hide_guard_timer.timeout.connect(self._clear_auto_hide_guard)
        self.setObjectName("ClipboardQuickPanel")
        self.resize(430, 330)
        self._build_ui()
        self._refresh_entries()
        self.refresh_ui()
        self.services.clip_monitor_manager.status_changed.connect(self._handle_store_changed)
        self.services.i18n.language_changed.connect(self._handle_language_changed)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
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
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        header.addWidget(self.title_label, 1)
        self.open_full_button = QPushButton()
        self.open_full_button.clicked.connect(self._open_full)
        header.addWidget(self.open_full_button, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header)

        self.search_input = QLineEdit()
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._refresh_entries)
        layout.addWidget(self.search_input)

        shell = QFrame()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(4)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(False)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setSpacing(0)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_widget.itemSelectionChanged.connect(self._update_preview)
        self.list_widget.itemDoubleClicked.connect(self._copy_selected)
        shell_layout.addWidget(self.list_widget, 1)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(88)
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
        self.setStyleSheet(
            f"""
            QWidget#ClipboardQuickPanel {{
                background: {palette.card_bg};
                border: 1px solid {palette.border};
                border-radius: 14px;
            }}
            QWidget#ClipboardQuickPanel QLineEdit,
            QWidget#ClipboardQuickPanel QListWidget,
            QWidget#ClipboardQuickPanel QPlainTextEdit {{
                background: {palette.element_bg};
                border: 1px solid {palette.border};
                border-radius: 9px;
                color: {palette.text_primary};
                font-size: 12px;
            }}
            QWidget#ClipboardQuickPanel QListWidget::item {{
                padding: 2px 6px;
                margin: 0px;
                min-height: 0px;
                border-radius: 6px;
            }}
            QWidget#ClipboardQuickPanel QListWidget::item:selected {{
                background: {palette.accent_soft};
                color: {palette.text_primary};
            }}
            QWidget#ClipboardQuickPanel QPushButton {{
                padding: 3px 8px;
                font-size: 12px;
            }}
            """
        )

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
            return
        self.show_panel()

    def show_panel(self) -> None:
        self.refresh_ui()
        self._refresh_entries()
        self._move_to_anchor()
        self._arm_auto_hide_guard()
        self.show()
        QTimer.singleShot(0, self._finalize_show)

    def _refresh_entries(self) -> None:
        search = self.search_input.text().strip()
        entries = self.store.list_entries(search=search)[:25]
        current_item = self.list_widget.currentItem()
        current_entry = current_item.data(Qt.ItemDataRole.UserRole) if current_item is not None else None
        current_entry_id = getattr(current_entry, "entry_id", None)
        self.list_widget.clear()
        selected_row = 0
        for entry in entries:
            label = f"[{entry.content_type}] {_preview(entry.content)}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list_widget.addItem(item)
            if current_entry_id == entry.entry_id:
                selected_row = self.list_widget.count() - 1
        if entries:
            self.list_widget.setCurrentRow(selected_row)
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

    def _handle_store_changed(self) -> None:
        if self.isVisible():
            self._refresh_entries()

    def _handle_language_changed(self, _language: str) -> None:
        self.refresh_ui()
        if self.isVisible():
            self._refresh_entries()

    def _handle_theme_change(self, _mode: str) -> None:
        self.refresh_ui()

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
        self._hide_if_allowed()

    def hideEvent(self, event) -> None:
        self._clear_auto_hide_guard()
        super().hideEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_allowed(event.position().toPoint()):
            global_pos = event.globalPosition().toPoint()
            self._drag_offset = global_pos - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            target = global_pos - self._drag_offset
            clamped = self._clamp_to_screen(target, reference_point=global_pos)
            self.move(clamped)
            self._manual_position = QPoint(clamped)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if not self.isVisible():
            return super().eventFilter(watched, event)
        if event.type() in {QEvent.Type.ApplicationDeactivate, QEvent.Type.WindowDeactivate}:
            self._hide_if_allowed()
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
                self._hide_if_allowed()
        return super().eventFilter(watched, event)

    def _finalize_show(self) -> None:
        if not self.isVisible():
            return
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.search_input.selectAll()

    def _arm_auto_hide_guard(self) -> None:
        self._clear_auto_hide_guard()
        if sys.platform != "darwin":
            return
        self._auto_hide_guard_active = True
        self._auto_hide_guard_timer.start(180)

    def _clear_auto_hide_guard(self) -> None:
        self._auto_hide_guard_active = False
        self._auto_hide_guard_timer.stop()

    def _hide_if_allowed(self) -> None:
        if self._auto_hide_guard_active:
            return
        self.hide()

    def _drag_allowed(self, point: QPoint) -> bool:
        child = self.childAt(point)
        return not isinstance(child, (QLineEdit, QListWidget, QPlainTextEdit, QPushButton))

    def _move_to_anchor(self) -> None:
        if self._manual_position is not None:
            self.move(self._clamp_to_screen(self._manual_position))
            return
        self.move(self._anchored_position())

    def _anchored_position(self) -> QPoint:
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return QPoint(0, 0)
        available = screen.availableGeometry()
        geometry = screen.geometry()
        gap = 6
        width = self.width()
        height = self.height()
        left_gap = available.left() - geometry.left()
        top_gap = available.top() - geometry.top()
        right_gap = geometry.right() - available.right()
        bottom_gap = geometry.bottom() - available.bottom()
        reserved = {
            "left": left_gap,
            "top": top_gap,
            "right": right_gap,
            "bottom": bottom_gap,
        }
        edge, edge_gap = max(reserved.items(), key=lambda item: item[1])

        if edge_gap > 0:
            if edge == "bottom":
                target = QPoint(cursor_pos.x() - int(width / 2), available.bottom() - height - gap + 1)
            elif edge == "top":
                target = QPoint(cursor_pos.x() - int(width / 2), available.top() + gap)
            elif edge == "left":
                target = QPoint(available.left() + gap, cursor_pos.y() - int(height / 2))
            else:
                target = QPoint(available.right() - width - gap + 1, cursor_pos.y() - int(height / 2))
            return self._clamp_to_screen(target, reference_point=cursor_pos)

        fallback = QPoint(cursor_pos.x() - int(width / 2), cursor_pos.y() + gap)
        if cursor_pos.y() + gap + height > available.bottom() and cursor_pos.y() - gap - height >= available.top():
            fallback.setY(cursor_pos.y() - height - gap)
        return self._clamp_to_screen(fallback, reference_point=cursor_pos)

    def _clamp_to_screen(self, target: QPoint, *, reference_point: QPoint | None = None) -> QPoint:
        screen = None
        if reference_point is not None:
            screen = QGuiApplication.screenAt(reference_point)
        if screen is None:
            center = QPoint(target.x() + int(self.width() / 2), target.y() + int(self.height() / 2))
            screen = QGuiApplication.screenAt(center)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return target
        available = screen.availableGeometry()
        gap = 6
        left = available.left() + gap
        right = available.right() - self.width() - gap + 1
        top = available.top() + gap
        bottom = available.bottom() - self.height() - gap + 1
        return QPoint(
            max(left, min(target.x(), right)),
            max(top, min(target.y(), bottom)),
        )


class ClipboardQuickPanelController(QObject):
    def __init__(self, services, *, before_restore_callback=None):
        super().__init__()
        self.services = services
        self.before_restore_callback = before_restore_callback
        self._panel: ClipboardQuickPanel | None = None

    def toggle(self) -> None:
        panel = self._panel or self._create_panel()
        panel.toggle()

    def show(self) -> None:
        panel = self._panel or self._create_panel()
        panel.show_panel()

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
