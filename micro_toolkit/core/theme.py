from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QCursor, QFont, QFontDatabase, QGuiApplication, QPalette, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QPlainTextEdit,
    QRadioButton,
    QSlider,
    QStyle,
    QStyleOptionButton,
    QTabBar,
    QTextEdit,
    QToolButton,
    QWidget,
)

try:
    from qt_material import apply_stylesheet as apply_material_stylesheet
    from qt_material import build_stylesheet as build_material_stylesheet
    from qt_material import list_themes as list_material_themes
except Exception:  # pragma: no cover - optional dependency
    apply_material_stylesheet = None
    build_material_stylesheet = None
    list_material_themes = None


@dataclass(frozen=True)
class ThemePalette:
    mode: str
    base_bg: str
    component_bg: str
    card_bg: str
    element_bg: str
    border: str
    text_primary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_soft: str
    danger: str
    selection: str

    @property
    def window_bg(self) -> str:
        return self.base_bg

    @property
    def surface_bg(self) -> str:
        return self.card_bg

    @property
    def surface_alt_bg(self) -> str:
        return self.component_bg

    @property
    def input_bg(self) -> str:
        return self.element_bg

    @property
    def status_bg(self) -> str:
        return self.base_bg


LIGHT_PALETTE = ThemePalette(
    mode="light",
    base_bg="#f8fbff",
    component_bg="#fbfdff",
    card_bg="#ffffff",
    element_bg="#ffffff",
    border="#dde7f3",
    text_primary="#142131",
    text_muted="#687a8c",
    accent="#1f7a8c",
    accent_hover="#186574",
    accent_soft="#dcecf7",
    danger="#b63f26",
    selection="#1f7a8c",
)


DARK_PALETTE = ThemePalette(
    mode="dark",
    base_bg="#1b2330",
    component_bg="#202938",
    card_bg="#263142",
    element_bg="#2d394b",
    border="#35475b",
    text_primary="#edf4fb",
    text_muted="#a5b5c7",
    accent="#3ba7bb",
    accent_hover="#2d91a5",
    accent_soft="#1b3342",
    danger="#d66b57",
    selection="#3ba7bb",
)


MATERIAL_COLOR_OPTIONS = (
    ("pink", "Pink", "light_pink_500.xml", "dark_pink.xml", "#d85a8f"),
    ("blue", "Blue", "light_blue_500.xml", "dark_blue.xml", "#4a90e2"),
    ("orange", "Orange", "light_orange.xml", "dark_amber.xml", "#f39c32"),
    ("green", "Green", "light_lightgreen_500.xml", "dark_lightgreen.xml", "#7cb342"),
    ("red", "Red", "light_red_500.xml", "dark_red.xml", "#e35d5b"),
)

MATERIAL_COLOR_MAP = {
    key: {
        "label": label,
        "light": light_theme,
        "dark": dark_theme,
        "preview": preview,
    }
    for key, label, light_theme, dark_theme, preview in MATERIAL_COLOR_OPTIONS
}

DEFAULT_MATERIAL_THEME = "light_pink_500.xml"


class _InteractiveCursorFilter(QObject):
    @staticmethod
    def _has_busy_override() -> bool:
        try:
            app = QApplication.instance()
            if app is None:
                return False
            cursor = QApplication.overrideCursor()
        except Exception:
            return False
        if cursor is None:
            return False
        return cursor.shape() in {Qt.CursorShape.WaitCursor, Qt.CursorShape.BusyCursor}

    def _interactive_widget(self, obj) -> QWidget | None:
        if not isinstance(obj, QWidget):
            return None
        if obj.property("_micro_no_pointer"):
            return None
        if obj.property("_micro_sidebar_pointer"):
            return obj
        if isinstance(obj, (QAbstractButton, QComboBox, QAbstractSpinBox, QSlider, QTabBar, QToolButton)):
            return obj
        return None

    @staticmethod
    def _event_pos(widget: QWidget, event) -> object | None:
        position = getattr(event, "position", None)
        if callable(position):
            try:
                return position().toPoint()
            except Exception:
                pass
        pos = getattr(event, "pos", None)
        if callable(pos):
            try:
                return pos()
            except Exception:
                pass
        if widget.underMouse():
            try:
                return widget.mapFromGlobal(QCursor.pos())
            except Exception:
                return None
        return None

    def _checkbox_hit_rect(self, widget: QWidget) -> object | None:
        if not isinstance(widget, (QCheckBox, QRadioButton)):
            return None
        option = QStyleOptionButton()
        widget.initStyleOption(option)
        if isinstance(widget, QCheckBox):
            indicator = widget.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, widget)
            spacing = widget.style().pixelMetric(QStyle.PixelMetric.PM_CheckBoxLabelSpacing, option, widget)
        else:
            indicator = widget.style().subElementRect(QStyle.SubElement.SE_RadioButtonIndicator, option, widget)
            spacing = widget.style().pixelMetric(QStyle.PixelMetric.PM_RadioButtonLabelSpacing, option, widget)
        text = widget.text()
        if not text:
            return indicator
        text_width = max(0, widget.fontMetrics().horizontalAdvance(text))
        text_height = max(indicator.height(), widget.fontMetrics().height())
        spacing = max(0, int(spacing))
        rtl = widget.layoutDirection() == Qt.LayoutDirection.RightToLeft
        if rtl:
            text_left = max(0, indicator.left() - spacing - text_width)
        else:
            text_left = min(widget.width() - text_width, indicator.right() + spacing + 1)
        text_top = max(0, int(round((widget.height() - text_height) / 2)))
        text_rect = QRect(text_left, text_top, text_width, text_height)
        return indicator.united(text_rect)

    def _sidebar_hit(self, widget: QWidget, event) -> bool:
        if not widget.property("_micro_sidebar_pointer"):
            return False
        pos = self._event_pos(widget, event)
        if pos is None:
            return False
        parent = widget.parent()
        if not isinstance(parent, QAbstractItemView):
            return False
        index = parent.indexAt(pos)
        return index.isValid()

    def _should_point(self, widget: QWidget, event) -> bool:
        if not widget.isEnabled():
            return False
        if widget.property("_micro_sidebar_pointer"):
            return self._sidebar_hit(widget, event)
        if isinstance(widget, (QCheckBox, QRadioButton)):
            pos = self._event_pos(widget, event)
            hit_rect = self._checkbox_hit_rect(widget)
            if pos is None or hit_rect is None:
                return False
            return hit_rect.contains(pos)
        return True

    def _sync_cursor(self, widget: QWidget, event=None) -> None:
        widget.setMouseTracking(True)
        widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if self._has_busy_override():
            widget.unsetCursor()
            return
        if self._should_point(widget, event):
            widget.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            widget.unsetCursor()

    def eventFilter(self, obj, event) -> bool:
        widget = self._interactive_widget(obj)
        if widget is None:
            return False
        if event.type() in {
            QEvent.Type.Enter,
            QEvent.Type.HoverEnter,
            QEvent.Type.HoverMove,
            QEvent.Type.MouseMove,
            QEvent.Type.EnabledChange,
            QEvent.Type.Show,
            QEvent.Type.Polish,
        }:
            self._sync_cursor(widget, event)
        elif event.type() in {QEvent.Type.Leave, QEvent.Type.Hide}:
            widget.unsetCursor()
        return False

    def refresh_existing(self, app) -> None:
        widgets = getattr(app, "allWidgets", None)
        if not callable(widgets):
            return
        for widget in widgets():
            interactive = self._interactive_widget(widget)
            if interactive is not None:
                self._sync_cursor(interactive)


class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self, config, assets_root):
        super().__init__()
        self.config = config
        self.assets_root = Path(assets_root)
        self._font_family = "Amiri"
        self._loaded_font_families: list[str] = []
        self._fonts_initialized = False
        self._color_key = "pink"
        self._dark_mode = False
        self._density_scale = 0
        self._ui_scale = 1.0
        self._cursor_filter = _InteractiveCursorFilter(self)
        self._cursor_filter_installed = False
        self.load_from_config()

    def available_theme_colors(self) -> list[tuple[str, str, str]]:
        return [(key, data["label"], data["preview"]) for key, data in MATERIAL_COLOR_MAP.items()]

    def available_themes(self) -> list[tuple[str, str]]:
        return [(key, data["label"]) for key, data in MATERIAL_COLOR_MAP.items()]

    def available_modes(self) -> list[tuple[str, str]]:
        return self.available_themes()

    def available_density_scales(self) -> list[int]:
        return list(range(-3, 4))

    def current_theme(self) -> str:
        return self._theme_name_for(self.current_color_key(), self.is_dark_mode())

    def current_color_key(self) -> str:
        return self._color_key

    def is_dark_mode(self) -> bool:
        return self._dark_mode

    def current_mode(self) -> str:
        return "dark" if self.is_dark_mode() else "light"

    def current_density_scale(self) -> int:
        return self._density_scale

    def set_theme(self, theme_name: str) -> str:
        normalized = self._normalized_theme_name(theme_name)
        self._color_key = self._color_key_from_theme_name(normalized)
        self._dark_mode = "dark" in normalized.lower()
        self.theme_changed.emit(self.current_mode())
        return normalized

    def set_color(self, color_key: str) -> str:
        normalized_key = str(color_key or "").strip().lower()
        if normalized_key not in MATERIAL_COLOR_MAP:
            normalized_key = "pink"
        return self.set_theme(self._theme_name_for(normalized_key, self.is_dark_mode()))

    def theme_name_for(self, color_key: str, dark: bool) -> str:
        return self._theme_name_for(str(color_key or "").strip().lower(), bool(dark))

    def set_mode(self, mode: str) -> None:
        self.set_theme(mode)

    def set_dark_mode(self, enabled: bool) -> str:
        return self.set_theme(self._theme_name_for(self.current_color_key(), bool(enabled)))

    def set_density_scale(self, density: int) -> int:
        normalized = max(-3, min(3, int(density)))
        self._density_scale = normalized
        self.theme_changed.emit(self.current_mode())
        return normalized

    def set_ui_scaling(self, scale: float) -> float:
        self._ui_scale = min(1.6, max(0.85, float(scale)))
        self.theme_changed.emit(self.current_mode())
        return self._ui_scale

    def current_ui_scaling(self) -> float:
        return self._ui_scale

    def save_to_config(self) -> None:
        theme_name = self.current_theme()
        self.config.update_many(
            {
                "material_theme": theme_name,
                "material_color": self._color_key,
                "material_dark": self._dark_mode,
                "appearance_mode": "dark" if self._dark_mode else "light",
                "density_scale": self._density_scale,
                "ui_scaling": self._ui_scale,
            }
        )

    def load_from_config(self) -> None:
        configured_color = str(self.config.get("material_color") or "").strip().lower()
        configured_theme = str(self.config.get("material_theme") or "").strip()
        if configured_color in MATERIAL_COLOR_MAP:
            self._color_key = configured_color
        elif configured_theme:
            self._color_key = self._color_key_from_theme_name(configured_theme)
        else:
            self._color_key = "pink"

        stored_dark = self.config.get("material_dark")
        if isinstance(stored_dark, bool):
            self._dark_mode = stored_dark
        elif configured_theme:
            self._dark_mode = "dark" in configured_theme.lower()
        else:
            legacy_mode = str(self.config.get("appearance_mode") or "").strip().lower()
            self._dark_mode = legacy_mode == "dark"

        try:
            self._density_scale = max(-3, min(3, int(self.config.get("density_scale") or 0)))
        except Exception:
            self._density_scale = 0
        try:
            self._ui_scale = min(1.6, max(0.85, float(self.config.get("ui_scaling") or 1.0)))
        except Exception:
            self._ui_scale = 1.0

    def current_palette(self) -> ThemePalette:
        base = DARK_PALETTE if self.current_mode() == "dark" else LIGHT_PALETTE
        accent, accent_hover, accent_soft = self._accent_triplet(self.current_color_key(), dark=self.is_dark_mode())
        base_bg = base.base_bg
        component_bg = base.component_bg
        card_bg = base.card_bg
        element_bg = base.element_bg
        border = base.border
        if base.mode == "light":
            base_bg = self._mix_hex(base.base_bg, accent, 0.05)
            component_bg = self._mix_hex(base.component_bg, accent, 0.03)
            card_bg = self._mix_hex(component_bg, "#ffffff", 0.2)
            element_bg = self._mix_hex(card_bg, "#ffffff", 0.34)
            border = self._mix_hex(base.border, accent, 0.06)
        else:
            base_bg = self._mix_hex(base.base_bg, accent, 0.06)
            component_bg = self._mix_hex(base.component_bg, accent, 0.04)
            card_bg = self._mix_hex(base.card_bg, accent, 0.03)
            element_bg = self._mix_hex(base.element_bg, accent, 0.02)
            border = self._mix_hex(base.border, accent, 0.04)
        return ThemePalette(
            mode=base.mode,
            base_bg=base_bg,
            component_bg=component_bg,
            card_bg=card_bg,
            element_bg=element_bg,
            border=border,
            text_primary=base.text_primary,
            text_muted=base.text_muted,
            accent=accent,
            accent_hover=accent_hover,
            accent_soft=accent_soft,
            danger=base.danger,
            selection=accent,
        )

    def refresh_interactive_cursors(self, app=None) -> None:
        target_app = app or QApplication.instance()
        if target_app is None:
            return
        self._cursor_filter.refresh_existing(target_app)

    def _console_surface_bg(self, palette: ThemePalette) -> str:
        return (
            self._mix_hex(palette.component_bg, palette.base_bg, 0.52)
            if palette.mode == "dark"
            else self._mix_hex(palette.component_bg, palette.accent, 0.08, darken=108)
        )

    def _log_surface_bg(self, palette: ThemePalette) -> str:
        return (
            self._mix_hex(palette.component_bg, palette.base_bg, 0.34)
            if palette.mode == "dark"
            else self._mix_hex(palette.component_bg, palette.accent, 0.04, darken=104)
        )

    def _semantic_selection_bg(self, background: str, palette: ThemePalette) -> str:
        return self._mix_hex(background, palette.accent, 0.08 if palette.mode == "dark" else 0.05)

    @staticmethod
    def _semantic_surface_role(widget: QWidget) -> str | None:
        if not isinstance(widget, (QPlainTextEdit, QTextEdit)):
            return None
        object_name = widget.objectName()
        semantic = str(widget.property("micro_class") or "").strip()
        if object_name == "ShellLogOutput" or semantic == "log_class":
            return "log"
        if object_name == "TerminalOutputView" or semantic == "console_class":
            return "console"
        return None

    def sync_semantic_surface(self, widget: QWidget | None) -> None:
        if not isinstance(widget, (QPlainTextEdit, QTextEdit)):
            return
        role = self._semantic_surface_role(widget)
        if role is None:
            return
        palette = self.current_palette()
        if role == "console":
            background = self._console_surface_bg(palette)
        else:
            background = self._log_surface_bg(palette)
        selection = self._semantic_selection_bg(background, palette)
        text = palette.text_primary
        viewport = widget.viewport()
        for target in (widget, viewport):
            if not isinstance(target, QWidget):
                continue
            target.setAutoFillBackground(True)
            target_palette = target.palette()
            target_palette.setColor(QPalette.ColorRole.Base, QColor(background))
            target_palette.setColor(QPalette.ColorRole.Window, QColor(background))
            target_palette.setColor(QPalette.ColorRole.Text, QColor(text))
            target_palette.setColor(QPalette.ColorRole.WindowText, QColor(text))
            target_palette.setColor(QPalette.ColorRole.Highlight, QColor(selection))
            target.setPalette(target_palette)
        viewport.setStyleSheet(f"background-color: {background}; border: none;")
        viewport.update()
        widget.update()

    def sync_semantic_surfaces(self, root) -> None:
        widgets = getattr(root, "allWidgets", None)
        if callable(widgets):
            for widget in widgets():
                self.sync_semantic_surface(widget)
            return
        if not isinstance(root, QWidget):
            return
        self.sync_semantic_surface(root)
        for widget in root.findChildren(QWidget):
            self.sync_semantic_surface(widget)

    def apply(self, app) -> None:
        self._ensure_font_loaded()
        scale = self._normalized_scale()
        palette = self.current_palette()
        app.setFont(self._build_font(scale))
        app.setPalette(self._build_qpalette(palette))
        if not self._cursor_filter_installed:
            app.installEventFilter(self._cursor_filter)
            self._cursor_filter_installed = True
        self._cursor_filter.refresh_existing(app)
        if apply_material_stylesheet is not None:
            try:
                app.setStyle("Fusion")
            except Exception:
                pass
        stylesheet = self._build_material_stylesheet(palette, scale)
        app.setStyleSheet(stylesheet)
        self.sync_semantic_surfaces(app)
        self.theme_changed.emit(palette.mode)

    def refresh_system_mode(self, app) -> None:
        self.apply(app)

    def _build_font(self, scale: float) -> QFont:
        base_font = QFont()
        if self._loaded_font_families:
            try:
                base_font.setFamilies(self._loaded_font_families)
            except Exception:
                base_font.setFamily(self._loaded_font_families[0])
        else:
            base_font.setFamily(self._font_family)
        base_font.setPointSize(max(10, round(11 * scale)))
        return base_font

    def _ensure_font_loaded(self) -> None:
        if self._fonts_initialized and self._loaded_font_families:
            return
        preferred: list[str] = []
        font_candidates = [
            self.assets_root / "fonts" / "Amiri.ttf",
            self.assets_root / "fonts" / "DejaVuSans.ttf",
            self.assets_root / "fonts" / "DejaVuSans-Bold.ttf",
        ]
        for candidate in font_candidates:
            if not candidate.exists():
                continue
            font_id = QFontDatabase.addApplicationFont(str(candidate))
            if font_id == -1:
                continue
            for family in QFontDatabase.applicationFontFamilies(font_id):
                if family and family not in preferred:
                    preferred.append(family)
        for family in ["Amiri", "DejaVu Sans", "Noto Sans Arabic", "Sans Serif"]:
            if family not in preferred:
                preferred.append(family)
        self._loaded_font_families = preferred
        self._fonts_initialized = True

    def _normalized_scale(self) -> float:
        return self._ui_scale

    def _normalized_theme_name(self, theme_name: str) -> str:
        value = str(theme_name or "").strip()
        if not value:
            return DEFAULT_MATERIAL_THEME
        lowered_value = value.lower()
        if lowered_value in MATERIAL_COLOR_MAP:
            return self._theme_name_for(lowered_value, self.is_dark_mode())
        actual_names = list_material_themes() if callable(list_material_themes) else []
        lowered = {name.lower(): name for name in actual_names}
        if value in actual_names:
            return value
        if lowered_value in lowered:
            return lowered[lowered_value]
        if value.lower() == "dark":
            return self._theme_name_for(self.current_color_key(), True)
        if value.lower() == "light":
            return self._theme_name_for(self.current_color_key(), False)
        if value.lower() == "system":
            return self._theme_name_for(self.current_color_key(), False)
        return DEFAULT_MATERIAL_THEME

    def _pretty_theme_name(self, theme_name: str) -> str:
        stem = Path(theme_name).stem.replace("_", " ").replace("-", " ").strip()
        return " ".join(word.capitalize() for word in stem.split()) or theme_name

    def _theme_name_for(self, color_key: str, dark: bool) -> str:
        mapping = MATERIAL_COLOR_MAP.get(color_key, MATERIAL_COLOR_MAP["pink"])
        return mapping["dark" if dark else "light"]

    def _color_key_from_theme_name(self, theme_name: str) -> str:
        lowered = str(theme_name or "").lower()
        for key, mapping in MATERIAL_COLOR_MAP.items():
            if lowered in {mapping["light"].lower(), mapping["dark"].lower()}:
                return key
        for key in MATERIAL_COLOR_MAP:
            if key in lowered:
                return key
        return "pink"

    def _accent_triplet(self, color_key: str, *, dark: bool) -> tuple[str, str, str]:
        light_map = {
            "pink": ("#d85a8f", "#be467a", "#f7d7e4"),
            "blue": ("#4a90e2", "#3a78c4", "#d9e9fb"),
            "orange": ("#f39c32", "#db8618", "#fde8c8"),
            "green": ("#7cb342", "#689c31", "#e3f0cf"),
            "red": ("#e35d5b", "#cb4b48", "#f8d8d7"),
        }
        dark_map = {
            "pink": ("#ff77aa", "#f06292", "#452635"),
            "blue": ("#5ea4ff", "#3f88e6", "#203347"),
            "orange": ("#ffb347", "#ef9b28", "#46331c"),
            "green": ("#9ccc65", "#8bc34a", "#283823"),
            "red": ("#ef6c6c", "#e35d5b", "#472526"),
        }
        mapping = dark_map if dark else light_map
        return mapping.get(color_key, mapping["pink"])

    def _mix_hex(self, base_hex: str, tint_hex: str, amount: float, *, darken: int = 100) -> str:
        base = QColor(base_hex)
        tint = QColor(tint_hex)
        weight = max(0.0, min(1.0, float(amount)))
        red = round((base.red() * (1.0 - weight)) + (tint.red() * weight))
        green = round((base.green() * (1.0 - weight)) + (tint.green() * weight))
        blue = round((base.blue() * (1.0 - weight)) + (tint.blue() * weight))
        mixed = QColor(red, green, blue)
        if darken != 100:
            mixed = mixed.darker(max(100, int(darken)))
        return mixed.name()

    def _material_parent_path(self) -> Path:
        runtime = self.config.config_path.parent / "runtime" / "qt_material"
        runtime.mkdir(parents=True, exist_ok=True)
        return runtime

    def _build_material_stylesheet(self, palette: ThemePalette, scale: float) -> str:
        if build_material_stylesheet is not None:
            stylesheet = build_material_stylesheet(
                theme=self.current_theme(),
                invert_secondary=self.current_mode() == "light",
                extra=self._material_extra(palette),
                parent=str(self._material_parent_path()),
            )
            if stylesheet:
                return stylesheet + "\n" + self._build_overlay_stylesheet(palette, scale)
        return self._build_fallback_stylesheet(palette, scale)

    def _material_extra(self, palette: ThemePalette) -> dict[str, str]:
        return {
            "font_family": self._loaded_font_families[0] if self._loaded_font_families else self._font_family,
            "density_scale": str(self.current_density_scale()),
            "danger": palette.danger,
            "warning": "#d48f12" if palette.mode == "light" else "#f0b84a",
            "success": "#2f7d4d" if palette.mode == "light" else "#6dbb7f",
        }

    def _build_overlay_stylesheet(self, palette: ThemePalette, scale: float) -> str:
        title_size = max(24, round(26 * scale))
        app_title_size = max(17, round(19 * scale))
        page_title_size = max(17, round(20 * scale))
        eyebrow_size = max(10, round(10 * scale))
        card_radius = max(0, round(4 * scale))
        control_radius = max(10, round(12 * scale))
        surface_radius = max(12, round(14 * scale))
        utility_button_size = max(28, round(30 * scale))
        status_toggle_width = max(24, round(24 * scale))
        status_toggle_height = max(18, round(18 * scale))
        console_bg = (
            self._mix_hex(palette.component_bg, palette.base_bg, 0.52)
            if palette.mode == "dark"
            else self._mix_hex(palette.component_bg, palette.accent, 0.08, darken=108)
        )
        terminal_input_bg = self._mix_hex(console_bg, palette.element_bg, 0.14 if palette.mode == "dark" else 0.18)
        log_bg = (
            self._mix_hex(palette.component_bg, palette.base_bg, 0.34)
            if palette.mode == "dark"
            else self._mix_hex(palette.component_bg, palette.accent, 0.04, darken=104)
        )
        hero_bg = self._mix_hex(palette.card_bg, palette.accent, 0.12 if palette.mode == "dark" else 0.08)
        preview_bg = palette.card_bg
        chart_bg = palette.card_bg
        disabled_bg = self._mix_hex(palette.element_bg, palette.base_bg, 0.22 if palette.mode == "dark" else 0.18)
        button_hover_bg = self._mix_hex(
            palette.element_bg,
            palette.accent_soft,
            0.6 if palette.mode == "dark" else 0.42,
        )
        button_pressed_bg = self._mix_hex(
            palette.element_bg,
            palette.accent_soft,
            0.38 if palette.mode == "dark" else 0.22,
        )
        card_border = self._mix_hex(palette.border, palette.card_bg, 0.08)
        return f"""
        QLabel, QCheckBox, QRadioButton {{
            background: transparent;
            color: {palette.text_primary};
        }}
        QMainWindow {{
            background: {palette.base_bg};
        }}
        QFrame#SidebarCard {{
            background: {palette.component_bg};
            border: none;
            border-right: 1px solid {palette.border};
            border-radius: 0px;
        }}
        QFrame#SidebarHeader {{
            background: {palette.base_bg};
            border: none;
            border-bottom: 1px solid {palette.border};
            border-radius: 0px;
        }}
        QFrame#UtilityBar {{
            background: {palette.base_bg};
            border: none;
            border-bottom: 1px solid {palette.border};
            border-radius: 0px;
        }}
        QWidget#UtilitySearchHost, QWidget#UtilityActionsHost {{
            background: transparent;
        }}
        QFrame#HeaderCard {{
            background: {palette.component_bg};
            border: none;
            border-bottom: 1px solid {palette.border};
            border-radius: 0px;
        }}
        QFrame#PageCard {{
            background: {palette.base_bg};
            border: none;
            border-radius: 0px;
        }}
        QStackedWidget {{
            background: {palette.base_bg};
        }}
        QScrollArea {{
            background: {palette.base_bg};
            border: none;
        }}
        QScrollArea > QWidget > QWidget {{
            background: {palette.base_bg};
        }}
        QFrame#LoadingOverlayCard {{
            background: {palette.component_bg};
            border: 1px solid {palette.border};
            border-radius: {card_radius}px;
        }}
        QLabel#AppTitle {{
            font-size: {app_title_size}px;
            font-weight: 700;
            color: {palette.text_primary};
            letter-spacing: 0.005em;
        }}
        QLabel#PageTitle {{
            font-size: {page_title_size}px;
            font-weight: 700;
            color: {palette.text_primary};
        }}
        QLabel#PageDescription, QLabel#PlaceholderBody {{
            color: {palette.text_muted};
        }}
        QLabel#PlaceholderTitle {{
            font-size: {page_title_size}px;
            font-weight: 700;
            color: {palette.text_primary};
        }}
        QLabel#SectionEyebrow {{
            color: {palette.accent};
            font-size: {eyebrow_size}px;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }}
        QLabel#LoadingOverlayLabel {{
            color: {palette.text_primary};
            font-size: {max(12, round(13 * scale))}px;
            font-weight: 600;
        }}
        QLabel#ConfirmDialogTitle {{
            color: {palette.text_primary};
            font-size: {max(18, round(20 * scale))}px;
            font-weight: 700;
        }}
        QLabel#ConfirmDialogBody {{
            color: {palette.text_muted};
            font-size: {max(12, round(13 * scale))}px;
        }}
        QTreeWidget {{
            padding: 10px 2px 12px 2px;
            border: none;
            background: transparent;
            border-radius: 0px;
            outline: 0;
        }}
        QTreeView::branch {{
            background: transparent;
            border-image: none;
            image: none;
        }}
        QTreeView::branch:has-siblings,
        QTreeView::branch:has-children,
        QTreeView::branch:adjoins-item,
        QTreeView::branch:closed,
        QTreeView::branch:open,
        QTreeView::branch:end,
        QTreeView::branch:only-one {{
            border-image: none;
            image: none;
        }}
        QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QAbstractSpinBox {{
            background: {palette.element_bg};
            background-color: {palette.element_bg};
            border: none;
            border-radius: 0px;
            color: {palette.text_primary};
        }}
        QListWidget, QTableView, QTableWidget {{
            background: {palette.card_bg};
            background-color: {palette.card_bg};
            border: 1px solid {card_border};
            border-radius: {surface_radius}px;
            color: {palette.text_primary};
        }}
        QLineEdit, QPlainTextEdit, QTextEdit {{
            background: {palette.element_bg};
            background-color: {palette.element_bg};
            border: none;
            border-bottom: 2px solid {palette.border};
            padding: 5px 2px 4px 2px;
        }}
        QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover {{
            background: {palette.element_bg};
            background-color: {palette.element_bg};
            border-bottom: 2px solid {palette.accent};
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
            background: {palette.element_bg};
            background-color: {palette.element_bg};
            border-bottom: 3px solid {palette.accent_hover};
        }}
        QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled,
        QLineEdit[readOnly="true"] {{
            background: {disabled_bg};
            background-color: {disabled_bg};
            border-bottom: 2px solid {palette.border};
            outline: 0;
        }}
        QPlainTextEdit[readOnly="true"], QTextEdit[readOnly="true"] {{
            background: {palette.card_bg};
            background-color: {palette.card_bg};
            border: 1px solid {card_border};
            border-radius: {surface_radius}px;
            padding: 8px 10px;
            outline: 0;
        }}
        QPlainTextEdit[readOnly="true"]:hover, QTextEdit[readOnly="true"]:hover,
        QPlainTextEdit[readOnly="true"]:focus, QTextEdit[readOnly="true"]:focus {{
            background: {palette.card_bg};
            background-color: {palette.card_bg};
            border: 1px solid {card_border};
        }}
        QLineEdit#ShellSearchInput {{
            padding: 0 2px 2px 2px;
        }}
        QLineEdit#ShellSearchInput:disabled,
        QLineEdit#ShellSearchInput[readOnly="true"] {{
            outline: 0;
        }}
        QComboBox, QSpinBox, QDoubleSpinBox, QAbstractSpinBox {{
            background: {palette.element_bg};
            background-color: {palette.element_bg};
            border: none;
            border-bottom: 2px solid {palette.border};
            border-radius: 0px;
            padding: 4px 2px 4px 2px;
        }}
        QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QAbstractSpinBox:hover {{
            background: {palette.element_bg};
            background-color: {palette.element_bg};
            border-bottom: 2px solid {palette.accent};
        }}
        QComboBox:focus, QComboBox:on, QSpinBox:focus, QDoubleSpinBox:focus, QAbstractSpinBox:focus {{
            background: {palette.element_bg};
            background-color: {palette.element_bg};
            border-bottom: 3px solid {palette.accent_hover};
        }}
        QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QAbstractSpinBox:disabled {{
            background: {disabled_bg};
            background-color: {disabled_bg};
            border-bottom: 2px solid {palette.border};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 22px;
            border: none;
            background: transparent;
        }}
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
            width: 16px;
            border: none;
            background: transparent;
        }}
        QTreeWidget::item, QListWidget::item {{
            padding: 7px 10px;
            border-radius: 10px;
            margin: 2px 0px;
        }}
        QTreeWidget::item:hover, QListWidget::item:hover {{
            background: {palette.card_bg};
        }}
        QTreeWidget::item:selected, QListWidget::item:selected {{
            background: {palette.accent_soft};
            color: {palette.text_primary};
        }}
        QTreeWidget::branch:selected {{
            background: transparent;
        }}
        QTableView QHeaderView, QTableWidget QHeaderView {{
            background: {palette.card_bg};
            border: none;
        }}
        QTableView QHeaderView::section, QTableWidget QHeaderView::section {{
            padding: 4px 6px;
            border: none;
            border-right: 1px solid {card_border};
            border-bottom: 1px solid {card_border};
            background: {palette.card_bg};
            color: {palette.text_primary};
        }}
        QTableCornerButton::section {{
            background: {palette.card_bg};
            border: none;
            border-right: 1px solid {card_border};
            border-bottom: 1px solid {card_border};
        }}
        QTabWidget::pane {{
            background: transparent;
            border: none;
        }}
        QPushButton {{
            background: {palette.element_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: {control_radius}px;
        }}
        QPushButton:hover {{
            border-color: {palette.accent};
            background: {button_hover_bg};
        }}
        QPushButton:pressed {{
            border-color: {palette.accent_hover};
            background: {button_pressed_bg};
        }}
        QPushButton:disabled {{
            background: {disabled_bg};
            color: {palette.text_muted};
            border-color: {palette.border};
        }}
        QToolButton[autoRaise="false"] {{
            background: {palette.element_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: {control_radius}px;
        }}
        QToolButton[autoRaise="false"]:hover {{
            border-color: {palette.accent};
            background: {button_hover_bg};
        }}
        QToolButton[autoRaise="false"]:pressed {{
            border-color: {palette.accent_hover};
            background: {button_pressed_bg};
        }}
        QToolButton[autoRaise="false"]:disabled {{
            background: {disabled_bg};
            color: {palette.text_muted};
            border-color: {palette.border};
        }}
        QPushButton[micro_class="button_class"],
        QToolButton[micro_class="button_class"] {{
            min-height: {max(34, round(36 * scale))}px;
            padding: 5px 10px;
            font-weight: 600;
        }}
        QToolButton[micro_class="chip_button_class"],
        QPushButton[micro_class="chip_button_class"] {{
            background: {palette.element_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 14px;
            padding: 6px 12px;
            font-weight: 600;
        }}
        QToolButton[micro_class="chip_button_class"]:hover,
        QPushButton[micro_class="chip_button_class"]:hover {{
            border-color: {palette.accent};
            background: {button_hover_bg};
        }}
        QToolButton[micro_class="chip_button_class"]:checked,
        QPushButton[micro_class="chip_button_class"]:checked {{
            border-color: {palette.accent};
            background: {palette.accent_soft};
        }}
        QToolButton[micro_class="swatch_button_class"] {{
            background: {palette.element_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 14px;
            padding: 0px;
        }}
        QToolButton[micro_class="swatch_button_class"]:hover {{
            border-color: {palette.accent};
            background: {button_hover_bg};
        }}
        QToolButton[micro_class="swatch_button_class"]:checked {{
            border: 2px solid {palette.accent};
            background: {palette.accent_soft};
        }}
        QToolButton[micro_class="toggle_class"] {{
            background: {palette.element_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 14px;
            padding: 6px 14px;
            font-weight: 600;
        }}
        QToolButton[micro_class="toggle_class"]:hover {{
            border-color: {palette.accent};
            background: {button_hover_bg};
        }}
        QToolButton[micro_class="toggle_class"]:checked {{
            border-color: {palette.accent};
            background: {palette.accent};
            color: {"#ffffff" if palette.mode == "light" else palette.text_primary};
        }}
        QPushButton[micro_class="hero_button_class"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {palette.card_bg},
                stop:1 {palette.component_bg});
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 14px;
            padding: 10px 12px;
            font-size: 13px;
            font-weight: 700;
            text-align: left;
        }}
        QPushButton[micro_class="hero_button_class"]:hover {{
            border-color: {palette.accent};
            background: {palette.accent_soft};
        }}
        QPushButton[micro_class="inline_button_class"] {{
            background: transparent;
            color: {palette.accent};
            border: 1px solid {palette.border};
            border-radius: 999px;
            padding: 6px 10px;
            font-size: 12px;
            font-weight: 700;
        }}
        QPushButton[micro_class="inline_button_class"]:hover {{
            background: {palette.accent_soft};
            border-color: {palette.accent};
        }}
        QToolButton[autoRaise="true"] {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 10px;
            padding: 0px;
            min-width: 0px;
            min-height: 0px;
        }}
        QToolButton[autoRaise="true"]:hover {{
            border-color: {palette.accent};
            background: {palette.accent_soft};
        }}
        QToolButton[autoRaise="true"]:pressed {{
            border-color: {palette.accent_hover};
            background: {palette.card_bg};
        }}
        QToolButton[autoRaise="true"]:disabled {{
            background: transparent;
            border-color: transparent;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 6px;
            border: 1px solid {palette.border};
            background: {palette.element_bg};
        }}
        QCheckBox::indicator:hover {{
            border-color: {palette.accent};
            background: {palette.accent_soft};
        }}
        QCheckBox::indicator:checked {{
            border-color: {palette.accent};
            background: {palette.accent};
        }}
        QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 9px;
            border: 1px solid {palette.border};
            background: {palette.element_bg};
        }}
        QRadioButton::indicator:hover {{
            border-color: {palette.accent};
            background: {palette.accent_soft};
        }}
        QRadioButton::indicator:checked {{
            border-color: {palette.accent};
            background: {palette.accent};
        }}
        QTabBar::tab {{
            background: {palette.component_bg};
            color: {palette.text_muted};
            border: 1px solid {palette.border};
            border-bottom: none;
            padding: 6px 12px;
        }}
        QTabBar::tab:selected {{
            background: {palette.card_bg};
            color: {palette.text_primary};
        }}
        QSlider::groove:horizontal {{
            height: 6px;
            background: {palette.card_bg};
            border: 1px solid {palette.border};
            border-radius: 3px;
        }}
        QSlider {{
            background: {palette.card_bg};
        }}
        QSlider::add-page:horizontal {{
            background: {palette.card_bg};
            border-radius: 3px;
        }}
        QSlider::sub-page:horizontal {{
            background: {palette.accent};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            width: 18px;
            margin: -6px 0;
            border-radius: 9px;
            background: {palette.element_bg};
            border: 2px solid {palette.accent};
        }}
        QToolButton#HeaderActionButton {{
            background: {palette.element_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 10px;
            padding: 4px;
        }}
        QToolButton#HeaderActionButton:hover {{
            border-color: {palette.accent};
        }}
        QToolButton#HeaderActionButton:checked {{
            background: {palette.accent_soft};
            border-color: {palette.accent};
        }}
        QToolButton#SystemToolbarButton {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 10px;
            padding: 0px;
            width: {utility_button_size}px;
            height: {utility_button_size}px;
            min-width: {utility_button_size}px;
            min-height: {utility_button_size}px;
            max-width: {utility_button_size}px;
            max-height: {utility_button_size}px;
            margin: 0px;
            color: {palette.text_primary};
        }}
        QToolButton#SystemToolbarButton:hover {{
            border-color: {palette.border};
            background: {palette.element_bg};
        }}
        QToolButton#SystemToolbarButton:checked {{
            background: {palette.accent_soft};
            border: 1px solid {palette.accent};
        }}
        QToolButton#ConsoleToggle, QToolButton#TerminalToggle {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 0px;
            padding: 0px;
            width: {status_toggle_width}px;
            height: {status_toggle_height}px;
            min-width: {status_toggle_width}px;
            min-height: {status_toggle_height}px;
            max-width: {status_toggle_width}px;
            max-height: {status_toggle_height}px;
            margin: 0px;
            color: {palette.text_primary};
        }}
        QToolButton#ConsoleToggle:hover, QToolButton#TerminalToggle:hover {{
            border-color: {palette.border};
            background: {palette.element_bg};
        }}
        QToolButton#ConsoleToggle:checked, QToolButton#TerminalToggle:checked {{
            border-color: {palette.accent};
            background: {palette.accent_soft};
        }}
        QToolButton#InlineIconButton,
        QToolButton[micro_class="inline_icon_button_class"] {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 10px;
            padding: 0px;
            width: 28px;
            height: 28px;
            min-width: 28px;
            min-height: 28px;
            max-width: 28px;
            max-height: 28px;
            margin: 0px;
            color: {palette.text_primary};
        }}
        QToolButton#InlineIconButton:hover,
        QToolButton[micro_class="inline_icon_button_class"]:hover {{
            border-color: {palette.accent};
            background: {palette.accent_soft};
        }}
        QToolButton#InlineIconButton:pressed,
        QToolButton[micro_class="inline_icon_button_class"]:pressed {{
            border-color: {palette.accent_hover};
            background: {palette.card_bg};
        }}
        QToolButton#InlineIconButton:disabled,
        QToolButton[micro_class="inline_icon_button_class"]:disabled {{
            background: transparent;
            border-color: transparent;
            color: {palette.text_muted};
        }}
        QToolButton:checked {{
            background: {palette.accent_soft};
            border: 1px solid {palette.accent};
            color: {palette.text_primary};
        }}
        QProgressBar {{
            background: {palette.component_bg};
            border: 1px solid {palette.border};
            border-radius: 4px;
            min-height: 8px;
            max-height: 8px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background: {palette.accent};
            border-radius: 4px;
        }}
        QProgressBar#ShellTaskProgressBar {{
            min-width: 132px;
            max-width: 132px;
        }}
        QStatusBar {{
            background: {palette.base_bg};
            border-top: 1px solid {palette.border};
            min-height: 20px;
        }}
        QDockWidget#ActivityDock,
        QDockWidget#ActivityDock > QWidget {{
            background: {palette.component_bg};
            border: none;
        }}
        QDockWidget#ActivityDock::title {{
            background: {palette.component_bg};
            color: {palette.text_primary};
            padding: 8px 12px;
            text-align: left;
            border-top: 1px solid {palette.border};
            border-bottom: 1px solid {palette.border};
        }}
        QMainWindow::separator:horizontal {{
            height: 1px;
            background: {palette.border};
            border: none;
        }}
        QMainWindow::separator:vertical {{
            width: 1px;
            background: {palette.border};
            border: none;
        }}
        QToolTip {{
            background: {palette.component_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 10px;
            padding: 6px 8px;
        }}
        QWidget[micro_class="hero_card_class"],
        QFrame[micro_class="hero_card_class"] {{
            background: {hero_bg};
            border: none;
            border-radius: 18px;
        }}
        QWidget[micro_class="transparent_class"],
        QFrame[micro_class="transparent_class"],
        QCheckBox[micro_class="transparent_class"],
        QStackedWidget[micro_class="transparent_class"] {{
            background: transparent;
            border: none;
        }}
        QWidget[micro_class="preview_class"],
        QFrame[micro_class="preview_class"],
        QLabel[micro_class="preview_class"],
        QWidget[micro_class="chart_class"],
        QFrame[micro_class="chart_class"],
        QChartView[micro_class="chart_class"] {{
            background: {preview_bg};
            border: 1px solid {card_border};
            border-radius: {surface_radius}px;
        }}
        QPlainTextEdit[micro_class="output_class"],
        QTextEdit[micro_class="output_class"] {{
            background: {palette.card_bg};
            border: 1px solid {card_border};
            border-radius: {surface_radius}px;
            padding: 8px 10px;
        }}
        QLineEdit[micro_class="console_class"] {{
            background: {terminal_input_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: {surface_radius}px;
            padding: 8px 10px;
        }}
        QLineEdit[micro_class="console_class"]:hover {{
            border-color: {palette.accent};
        }}
        QLineEdit[micro_class="console_class"]:focus {{
            border-color: {palette.accent_hover};
        }}
        QLineEdit#TerminalInput,
        QLineEdit#TerminalInput:hover,
        QLineEdit#TerminalInput:focus {{
            background: {terminal_input_bg};
            border-radius: 0px;
        }}
        QPlainTextEdit[micro_class="console_class"],
        QTextEdit[micro_class="console_class"] {{
            background: {console_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 0px;
            padding: 8px 10px;
            selection-background-color: {self._mix_hex(console_bg, palette.accent, 0.08 if palette.mode == "dark" else 0.05)};
        }}
        QPlainTextEdit[micro_class="console_class"]:hover,
        QTextEdit[micro_class="console_class"]:hover,
        QPlainTextEdit[micro_class="console_class"]:focus,
        QTextEdit[micro_class="console_class"]:focus {{
            border-color: {palette.border};
        }}
        QPlainTextEdit#TerminalOutputView,
        QTextEdit#TerminalOutputView {{
            background: {console_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 0px;
            padding: 8px 10px;
            selection-background-color: {self._mix_hex(console_bg, palette.accent, 0.08 if palette.mode == "dark" else 0.05)};
        }}
        QPlainTextEdit#TerminalOutputView:hover,
        QTextEdit#TerminalOutputView:hover,
        QPlainTextEdit#TerminalOutputView:focus,
        QTextEdit#TerminalOutputView:focus {{
            background: {console_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 0px;
        }}
        QPlainTextEdit[micro_class="log_class"],
        QTextEdit[micro_class="log_class"] {{
            background: {log_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 0px;
            padding: 8px 10px;
            selection-background-color: {self._mix_hex(log_bg, palette.accent, 0.08 if palette.mode == "dark" else 0.05)};
        }}
        QPlainTextEdit[micro_class="log_class"]:hover,
        QTextEdit[micro_class="log_class"]:hover,
        QPlainTextEdit[micro_class="log_class"]:focus,
        QTextEdit[micro_class="log_class"]:focus {{
            border-color: {palette.border};
        }}
        QPlainTextEdit#ShellLogOutput,
        QTextEdit#ShellLogOutput {{
            background: {log_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 0px;
            padding: 8px 10px;
            selection-background-color: {self._mix_hex(log_bg, palette.accent, 0.08 if palette.mode == "dark" else 0.05)};
        }}
        QPlainTextEdit#ShellLogOutput:hover,
        QTextEdit#ShellLogOutput:hover,
        QPlainTextEdit#ShellLogOutput:focus,
        QTextEdit#ShellLogOutput:focus {{
            background: {log_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 0px;
        }}
        QLabel[micro_class="field_title_class"] {{
            color: {palette.text_primary};
            font-size: 13px;
            font-weight: 700;
        }}
        QLabel[micro_class="field_value_class"] {{
            color: {palette.text_muted};
            font-size: 14px;
            font-weight: 500;
        }}
        QLabel[micro_class="status_text_class"] {{
            color: {palette.text_muted};
            font-size: 13px;
            font-weight: 600;
        }}
        """

    def _build_fallback_stylesheet(self, palette: ThemePalette, scale: float) -> str:
        return f"""
        QWidget {{
            color: {palette.text_primary};
        }}
        {self._build_overlay_stylesheet(palette, scale)}
        """

    def _build_qpalette(self, palette: ThemePalette) -> QPalette:
        qt_palette = QPalette()
        window = QColor(palette.base_bg)
        component = QColor(palette.component_bg)
        card = QColor(palette.card_bg)
        input_bg = QColor(palette.element_bg)
        border = QColor(palette.border)
        text = QColor(palette.text_primary)
        muted = QColor(palette.text_muted)
        accent = QColor(palette.accent)
        highlighted = QColor("#0f2b34" if palette.mode == "light" else "#081317")

        qt_palette.setColor(QPalette.ColorRole.Window, window)
        qt_palette.setColor(QPalette.ColorRole.WindowText, text)
        qt_palette.setColor(QPalette.ColorRole.Base, input_bg)
        qt_palette.setColor(QPalette.ColorRole.AlternateBase, card)
        qt_palette.setColor(QPalette.ColorRole.ToolTipBase, component)
        qt_palette.setColor(QPalette.ColorRole.ToolTipText, text)
        qt_palette.setColor(QPalette.ColorRole.Text, text)
        qt_palette.setColor(QPalette.ColorRole.Button, input_bg)
        qt_palette.setColor(QPalette.ColorRole.ButtonText, text)
        qt_palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
        qt_palette.setColor(QPalette.ColorRole.PlaceholderText, muted)
        qt_palette.setColor(QPalette.ColorRole.Highlight, accent)
        qt_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(highlighted))
        qt_palette.setColor(QPalette.ColorRole.Light, card.lighter(106))
        qt_palette.setColor(QPalette.ColorRole.Midlight, card)
        qt_palette.setColor(QPalette.ColorRole.Mid, border)
        qt_palette.setColor(QPalette.ColorRole.Dark, border.darker(120))
        qt_palette.setColor(QPalette.ColorRole.Shadow, QColor("#10161a" if palette.mode == "dark" else "#90847a"))
        qt_palette.setColor(QPalette.ColorRole.Link, accent)
        qt_palette.setColor(QPalette.ColorRole.LinkVisited, accent.darker(110))
        qt_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, muted)
        qt_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, muted)
        qt_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, muted)
        qt_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, border)
        qt_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, text)
        return qt_palette
