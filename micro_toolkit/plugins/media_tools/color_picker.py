from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.icon_registry import icon_from_name
from micro_toolkit.core.page_style import apply_page_chrome, apply_semantic_class, section_title_style
from micro_toolkit.core.plugin_api import QtPlugin, bind_tr


@dataclass(frozen=True)
class ColorSnapshot:
    hex_value: str
    rgb_value: str
    hsl_value: str


@dataclass(frozen=True)
class ScreenCapture:
    geometry: QRect
    pixmap: QPixmap


class ScreenColorPickerOverlay(QWidget):
    color_picked = Signal(QColor)
    canceled = Signal()

    def __init__(self, geometry: QRect, captures: list[ScreenCapture]):
        super().__init__(None)
        self._geometry = QRect(geometry)
        self._captures = list(captures)
        self._cursor_pos = QPoint(0, 0)
        self._hover_color = QColor()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.BypassWindowManagerHint, False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(self._geometry)
        self._update_hover(QCursor.pos())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.activateWindow()
        self.raise_()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.canceled.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._update_hover(event.globalPosition().toPoint())
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.color_picked.emit(self._hover_color)
            event.accept()
            return
        if event.button() in {Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton}:
            self.canceled.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for capture in self._captures:
            target_rect = QRect(capture.geometry)
            target_rect.moveTopLeft(capture.geometry.topLeft() - self._geometry.topLeft())
            painter.drawPixmap(target_rect, capture.pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 18))

        if not self._cursor_pos.isNull():
            cross_pen = QPen(QColor("#ffffff"), 1)
            painter.setPen(cross_pen)
            painter.drawLine(self._cursor_pos.x(), 0, self._cursor_pos.x(), self.height())
            painter.drawLine(0, self._cursor_pos.y(), self.width(), self._cursor_pos.y())
            painter.fillRect(self._cursor_pos.x() - 6, self._cursor_pos.y() - 6, 12, 12, self._hover_color)
            painter.setPen(QPen(QColor(0, 0, 0, 160), 2))
            painter.drawRect(self._cursor_pos.x() - 6, self._cursor_pos.y() - 6, 12, 12)
            self._paint_info_chip(painter)
        painter.end()

    def _paint_info_chip(self, painter: QPainter) -> None:
        hex_text = self._hover_color.name().upper() if self._hover_color.isValid() else "#000000"
        chip_rect = QRect(self._cursor_pos.x() + 18, self._cursor_pos.y() + 18, 124, 34)
        if chip_rect.right() > self.width() - 8:
            chip_rect.moveLeft(self._cursor_pos.x() - chip_rect.width() - 18)
        if chip_rect.bottom() > self.height() - 8:
            chip_rect.moveTop(self._cursor_pos.y() - chip_rect.height() - 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(18, 24, 31, 232))
        painter.drawRoundedRect(chip_rect, 10, 10)
        swatch_rect = QRect(chip_rect.left() + 8, chip_rect.top() + 8, 18, 18)
        painter.setBrush(self._hover_color)
        painter.drawRoundedRect(swatch_rect, 4, 4)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(chip_rect.adjusted(34, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, hex_text)

    def _update_hover(self, global_pos: QPoint) -> None:
        self._cursor_pos = self.mapFromGlobal(global_pos)
        self._hover_color = self._sample_color(self._cursor_pos)
        self.update()

    def _sample_color(self, local_pos: QPoint) -> QColor:
        global_pos = local_pos + self._geometry.topLeft()
        for capture in self._captures:
            if not capture.geometry.contains(global_pos):
                continue
            if capture.pixmap.isNull():
                break
            image = capture.pixmap.toImage()
            local_screen_pos = global_pos - capture.geometry.topLeft()
            dpr = max(1.0, float(capture.pixmap.devicePixelRatio()))
            x = max(0, min(image.width() - 1, int(local_screen_pos.x() * dpr)))
            y = max(0, min(image.height() - 1, int(local_screen_pos.y() * dpr)))
            return image.pixelColor(x, y)
        return QColor("#000000")


class ScreenColorPickerSession(QObject):
    color_picked = Signal(QColor)
    canceled = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._overlay: ScreenColorPickerOverlay | None = None

    def start(self) -> bool:
        screens = QGuiApplication.screens()
        if not screens:
            return False
        self._close_all()
        geometry = self._virtual_geometry(screens)
        captures = self._capture_screens(screens)
        if geometry.isNull() or not captures:
            return False
        overlay = ScreenColorPickerOverlay(geometry, captures)
        overlay.color_picked.connect(self._handle_color_picked)
        overlay.canceled.connect(self._handle_canceled)
        self._overlay = overlay
        overlay.show()
        return True

    def _handle_color_picked(self, color: QColor) -> None:
        self._close_all()
        self.color_picked.emit(color)

    def _handle_canceled(self) -> None:
        self._close_all()
        self.canceled.emit()

    def _close_all(self) -> None:
        if self._overlay is not None:
            try:
                self._overlay.close()
            except Exception:
                pass
            self._overlay.deleteLater()
            self._overlay = None

    def _virtual_geometry(self, screens) -> QRect:
        geometry = QRect()
        for screen in screens:
            geometry = geometry.united(screen.geometry())
        return geometry

    def _capture_screens(self, screens) -> list[ScreenCapture]:
        captures: list[ScreenCapture] = []
        for screen in screens:
            shot = screen.grabWindow(0)
            if shot.isNull():
                continue
            captures.append(ScreenCapture(screen.geometry(), shot))
        return captures


class ColorPickerPlugin(QtPlugin):
    plugin_id = "color_picker"
    name = "Color Picker"
    description = "Pick a color from anywhere on the screen and inspect its preview, RGB, HEX, and HSL values."
    category = "Media Utilities"
    preferred_icon = "palette"

    def create_widget(self, services) -> QWidget:
        return ColorPickerPage(services, self.plugin_id)


class ColorPickerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self._picker_session = ScreenColorPickerSession(self)
        self._picker_session.color_picked.connect(self._handle_color_picked)
        self._picker_session.canceled.connect(self._handle_pick_canceled)
        self._build_ui()
        self._apply_texts()
        self._apply_styles()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._apply_styles)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        outer.addWidget(self.description_label)

        hero_card = QFrame()
        self.hero_card = hero_card
        hero_layout = QHBoxLayout(hero_card)
        hero_layout.setContentsMargins(20, 20, 20, 20)
        hero_layout.setSpacing(16)

        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("ColorPreviewFrame")
        self.preview_frame.setFixedSize(128, 128)
        hero_layout.addWidget(self.preview_frame, 0, Qt.AlignmentFlag.AlignTop)

        hero_side = QVBoxLayout()
        hero_side.setSpacing(10)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        hero_side.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.pick_button = QPushButton()
        self.pick_button.clicked.connect(self._start_pick)
        button_row.addWidget(self.pick_button)
        self.copy_hex_button = QToolButton()
        apply_semantic_class(self.copy_hex_button, "inline_icon_button_class")
        self.copy_hex_button.setAutoRaise(True)
        self.copy_hex_button.setIconSize(QSize(16, 16))
        self.copy_hex_button.setFixedSize(28, 28)
        self.copy_hex_button.clicked.connect(lambda: self._copy_value(self.hex_value.text()))
        button_row.addWidget(self.copy_hex_button)
        button_row.addStretch(1)
        hero_side.addLayout(button_row)
        hero_side.addStretch(1)
        hero_layout.addLayout(hero_side, 1)
        outer.addWidget(hero_card)

        values_card = QFrame()
        self.values_card = values_card
        values_layout = QGridLayout(values_card)
        values_layout.setContentsMargins(20, 20, 20, 20)
        values_layout.setHorizontalSpacing(14)
        values_layout.setVerticalSpacing(12)

        self.hex_label = QLabel()
        self.hex_value = QLineEdit()
        self.hex_value.setReadOnly(True)
        values_layout.addWidget(self.hex_label, 0, 0)
        values_layout.addWidget(self.hex_value, 0, 1)

        self.rgb_label = QLabel()
        self.rgb_value = QLineEdit()
        self.rgb_value.setReadOnly(True)
        values_layout.addWidget(self.rgb_label, 1, 0)
        values_layout.addWidget(self.rgb_value, 1, 1)

        self.hsl_label = QLabel()
        self.hsl_value = QLineEdit()
        self.hsl_value.setReadOnly(True)
        values_layout.addWidget(self.hsl_label, 2, 0)
        values_layout.addWidget(self.hsl_value, 2, 1)
        outer.addWidget(values_card)

        self._set_color(QColor("#D85A8F"))

    def _apply_texts(self) -> None:
        self.title_label.setText(self.tr("title", "Color Picker"))
        self.description_label.setText(
            self.tr(
                "description",
                "Pick a color from anywhere on the screen, then inspect its preview, RGB, HEX, and HSL values.",
            )
        )
        self.status_label.setText(self.tr("status.ready", "Ready to sample a color from the screen."))
        self.pick_button.setText(self.tr("pick", "Pick from screen"))
        self.copy_hex_button.setToolTip(self.tr("copy.hex", "Copy HEX"))
        self.copy_hex_button.setIcon(icon_from_name("copy", self) or QIcon())
        self.hex_label.setText(self.tr("field.hex", "HEX"))
        self.rgb_label.setText(self.tr("field.rgb", "RGB"))
        self.hsl_label.setText(self.tr("field.hsl", "HSL"))

    def _apply_styles(self, *_args) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.hero_card, self.values_card),
            summary_label=self.status_label,
            title_size=26,
            title_weight=800,
            description_size=14,
            card_radius=16,
        )
        self.hex_label.setStyleSheet(section_title_style(palette, size=14, weight=700))
        self.rgb_label.setStyleSheet(section_title_style(palette, size=14, weight=700))
        self.hsl_label.setStyleSheet(section_title_style(palette, size=14, weight=700))
        self.copy_hex_button.setIcon(icon_from_name("copy", self) or QIcon())

    def _start_pick(self) -> None:
        if not self._picker_session.start():
            QMessageBox.warning(
                self,
                self.tr("warning.title", "Screen capture unavailable"),
                self.tr("warning.body", "The screen picker could not start on this session."),
            )
            return
        self.status_label.setText(self.tr("status.live", "Pick mode is active. Click any pixel on screen, or press Esc to cancel."))

    def _handle_color_picked(self, color: QColor) -> None:
        self._set_color(color)
        self.status_label.setText(self.tr("status.picked", "Color captured successfully."))

    def _handle_pick_canceled(self) -> None:
        self.status_label.setText(self.tr("status.canceled", "Pick mode canceled."))

    def _set_color(self, color: QColor) -> None:
        snapshot = self._snapshot_for(color)
        self.preview_frame.setStyleSheet(
            f"background: {snapshot.hex_value}; border: none; border-radius: 18px;"
        )
        self.hex_value.setText(snapshot.hex_value)
        self.rgb_value.setText(snapshot.rgb_value)
        self.hsl_value.setText(snapshot.hsl_value)

    def _snapshot_for(self, color: QColor) -> ColorSnapshot:
        hex_value = color.name().upper()
        rgb_value = f"rgb({color.red()}, {color.green()}, {color.blue()})"
        hue = color.hslHue()
        sat = round(color.hslSaturationF() * 100)
        light = round(color.lightnessF() * 100)
        hue_text = "0" if hue < 0 else str(hue)
        hsl_value = f"hsl({hue_text}, {sat}%, {light}%)"
        return ColorSnapshot(hex_value=hex_value, rgb_value=rgb_value, hsl_value=hsl_value)

    def _copy_value(self, value: str) -> None:
        QApplication.clipboard().setText(str(value or ""))
