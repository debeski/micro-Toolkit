from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette, Qt

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
    window_bg: str
    surface_bg: str
    surface_alt_bg: str
    input_bg: str
    border: str
    text_primary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_soft: str
    danger: str
    selection: str
    status_bg: str


LIGHT_PALETTE = ThemePalette(
    mode="light",
    window_bg="#f6f9fd",
    surface_bg="#fbfdff",
    surface_alt_bg="#f8fbff",
    input_bg="#ffffff",
    border="#dde7f3",
    text_primary="#142131",
    text_muted="#687a8c",
    accent="#1f7a8c",
    accent_hover="#186574",
    accent_soft="#dcecf7",
    danger="#b63f26",
    selection="#1f7a8c",
    status_bg="#f8fbff",
)


DARK_PALETTE = ThemePalette(
    mode="dark",
    window_bg="#11161d",
    surface_bg="#171d26",
    surface_alt_bg="#1c2430",
    input_bg="#151c25",
    border="#2b3846",
    text_primary="#edf4fb",
    text_muted="#a5b5c7",
    accent="#3ba7bb",
    accent_hover="#2d91a5",
    accent_soft="#1b3342",
    danger="#d66b57",
    selection="#3ba7bb",
    status_bg="#171d26",
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
        window_bg = base.window_bg
        surface_bg = base.surface_bg
        surface_alt_bg = base.surface_alt_bg
        status_bg = base.status_bg
        if base.mode == "light":
            # Keep the shell light, but let it pick up a faint tint from the selected theme color.
            window_bg = self._mix_hex(base.window_bg, accent, 0.08, darken=103)
            surface_bg = self._mix_hex(base.surface_bg, accent, 0.045, darken=101)
            surface_alt_bg = self._mix_hex(base.surface_alt_bg, accent, 0.06, darken=102)
            status_bg = self._mix_hex(base.status_bg, accent, 0.05, darken=101)
        return ThemePalette(
            mode=base.mode,
            window_bg=window_bg,
            surface_bg=surface_bg,
            surface_alt_bg=surface_alt_bg,
            input_bg=base.input_bg,
            border=base.border,
            text_primary=base.text_primary,
            text_muted=base.text_muted,
            accent=accent,
            accent_hover=accent_hover,
            accent_soft=accent_soft,
            danger=base.danger,
            selection=accent,
            status_bg=status_bg,
        )

    def apply(self, app) -> None:
        self._ensure_font_loaded()
        scale = self._normalized_scale()
        palette = self.current_palette()
        app.setFont(self._build_font(scale))
        app.setPalette(self._build_qpalette(palette))
        if apply_material_stylesheet is not None:
            try:
                app.setStyle("Fusion")
            except Exception:
                pass
        stylesheet = self._build_material_stylesheet(palette, scale)
        app.setStyleSheet(stylesheet)
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
        page_title_size = max(20, round(24 * scale))
        eyebrow_size = max(10, round(11 * scale))
        card_radius = max(0, round(4 * scale))
        input_radius = max(10, round(12 * scale))
        return f"""
        QLabel, QCheckBox, QRadioButton {{
            background: transparent;
        }}
        QMainWindow {{
            background: {palette.window_bg};
        }}
        QFrame#SidebarCard {{
            background: {palette.surface_bg};
            border: none;
            border-right: 1px solid {palette.border};
            border-radius: 0px;
        }}
        QFrame#SidebarHeader, QFrame#UtilityBar {{
            background: {palette.surface_alt_bg};
            border: none;
            border-bottom: 1px solid {palette.border};
            border-radius: 0px;
        }}
        QWidget#UtilitySearchHost, QWidget#UtilityActionsHost {{
            background: transparent;
        }}
        QFrame#HeaderCard {{
            background: {palette.surface_bg};
            border: none;
            border-bottom: 1px solid {palette.border};
            border-radius: 0px;
        }}
        QFrame#PageCard {{
            background: {palette.window_bg};
            border: none;
            border-radius: 0px;
        }}
        QStackedWidget {{
            background: {palette.window_bg};
        }}
        QScrollArea {{
            background: {palette.window_bg};
            border: none;
        }}
        QScrollArea > QWidget > QWidget {{
            background: {palette.window_bg};
        }}
        QFrame#LoadingOverlayCard {{
            background: {palette.surface_bg};
            border: 1px solid {palette.border};
            border-radius: {card_radius}px;
        }}
        QLabel#AppTitle {{
            font-size: {title_size}px;
            font-weight: 700;
            color: {palette.text_primary};
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
            letter-spacing: 0.08em;
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
            padding: 16px 3px 20px 3px;
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
        QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QTableView, QTableWidget {{
            background: {palette.input_bg};
            border: none;
            border-radius: 0px;
            color: {palette.text_primary};
        }}
        QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
        QLineEdit[readOnly="true"], QPlainTextEdit[readOnly="true"], QTextEdit[readOnly="true"] {{
            border: none;
            outline: 0;
        }}
        QLineEdit#ShellSearchInput {{
            min-height: {max(24, round(28 * scale))}px;
            max-height: {max(24, round(28 * scale))}px;
            padding: 0 12px;
            border-radius: 0px;
            background: {palette.surface_alt_bg};
            border: none;
            color: {palette.text_primary};
        }}
        QLineEdit#ShellSearchInput:focus {{
            border: none;
        }}
        QLineEdit#ShellSearchInput:hover,
        QLineEdit#ShellSearchInput:disabled,
        QLineEdit#ShellSearchInput[readOnly="true"] {{
            border: none;
            outline: 0;
        }}
        QLineEdit#TerminalInput {{
            min-height: {max(28, round(34 * scale))}px;
            padding: 0 12px;
            background: {palette.surface_alt_bg};
            color: {palette.text_primary};
            border-top: 1px solid {palette.border};
            border-left: none;
            border-right: none;
            border-bottom: none;
        }}
        QLineEdit#TerminalInput:focus {{
            background: {palette.surface_bg};
            border-top: 1px solid {palette.accent};
        }}
        QLineEdit#TerminalInput:hover {{
            background: {palette.surface_bg};
        }}
        QLineEdit#TerminalInput:disabled,
        QLineEdit#TerminalInput[readOnly="true"] {{
            border-top: 1px solid {palette.border};
        }}
        QTreeWidget::item, QListWidget::item {{
            padding: 10px 12px;
            border-radius: 10px;
            margin: 4px 0px;
        }}
        QTreeWidget::item:hover, QListWidget::item:hover {{
            background: {palette.surface_bg};
        }}
        QTreeWidget::item:selected, QListWidget::item:selected {{
            background: {palette.accent_soft};
            color: {palette.text_primary};
        }}
        QTreeWidget::branch:selected {{
            background: transparent;
        }}
        QTableView QHeaderView, QTableWidget QHeaderView {{
            background: {palette.surface_bg};
            border: none;
        }}
        QTableView QHeaderView::section, QTableWidget QHeaderView::section {{
            padding: 4px 6px;
            border: none;
            border-right: 1px solid {palette.border};
            border-bottom: 1px solid {palette.border};
            background: {palette.surface_bg};
            color: {palette.text_primary};
        }}
        QTableCornerButton::section {{
            background: {palette.surface_bg};
            border: none;
            border-right: 1px solid {palette.border};
            border-bottom: 1px solid {palette.border};
        }}
        QPushButton, QComboBox, QAbstractSpinBox, QTabWidget::pane {{
            background: {palette.surface_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 0px;
        }}
        QTabBar::tab {{
            background: {palette.surface_alt_bg};
            color: {palette.text_muted};
            border: 1px solid {palette.border};
            border-bottom: none;
            padding: 6px 12px;
        }}
        QTabBar::tab:selected {{
            background: {palette.surface_bg};
            color: {palette.text_primary};
        }}
        QSlider::groove:horizontal {{
            height: 6px;
            background: {palette.surface_alt_bg};
            border: 1px solid {palette.border};
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
            background: {palette.surface_bg};
            border: 2px solid {palette.accent};
        }}
        QToolButton#HeaderActionButton {{
            background: {palette.surface_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 0px;
            padding: 6px 12px;
        }}
        QToolButton#HeaderActionButton:hover {{
            border-color: {palette.accent};
        }}
        QToolButton#HeaderActionButton:checked {{
            background: {palette.accent_soft};
            border-color: {palette.accent};
        }}
        QToolButton#SystemToolbarButton, QToolButton#ConsoleToggle, QToolButton#TerminalToggle {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 10px;
            padding: 5px;
            color: {palette.text_primary};
        }}
        QToolButton#SystemToolbarButton:hover, QToolButton#ConsoleToggle:hover, QToolButton#TerminalToggle:hover {{
            border-color: {palette.border};
            background: {palette.surface_bg};
        }}
        QToolButton#SystemToolbarButton:checked, QToolButton#ConsoleToggle:checked, QToolButton#TerminalToggle:checked {{
            background: {palette.accent_soft};
            border: 1px solid {palette.accent};
        }}
        QToolButton:checked {{
            background: {palette.accent_soft};
            border: 1px solid {palette.accent};
            color: {palette.text_primary};
        }}
        QStatusBar {{
            background: {palette.status_bg};
            border-top: 1px solid {palette.border};
            min-height: 20px;
        }}
        QDockWidget::title {{
            background: {palette.surface_alt_bg};
            color: {palette.text_primary};
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid {palette.border};
        }}
        QMainWindow::separator:horizontal {{
            height: 6px;
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(0, 0, 0, {24 if palette.mode == 'dark' else 10}),
                stop:1 rgba(0, 0, 0, 0)
            );
            border: none;
        }}
        QMainWindow::separator:vertical {{
            width: 6px;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(0, 0, 0, {24 if palette.mode == 'dark' else 10}),
                stop:1 rgba(0, 0, 0, 0)
            );
            border: none;
        }}
        """

    def _build_fallback_stylesheet(self, palette: ThemePalette, scale: float) -> str:
        input_radius = max(10, round(12 * scale))
        return f"""
        QWidget {{
            background: {palette.window_bg};
            color: {palette.text_primary};
        }}
        QLineEdit, QPlainTextEdit, QTextEdit, QTreeWidget, QListWidget, QTableView, QTableWidget, QComboBox, QSpinBox, QDoubleSpinBox {{
            background: {palette.input_bg};
            border: none;
            border-radius: {input_radius}px;
        }}
        QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
        QLineEdit[readOnly="true"], QPlainTextEdit[readOnly="true"], QTextEdit[readOnly="true"] {{
            border: none;
            outline: 0;
        }}
        {self._build_overlay_stylesheet(palette, scale)}
        """

    def _build_qpalette(self, palette: ThemePalette) -> QPalette:
        qt_palette = QPalette()
        window = QColor(palette.window_bg)
        surface = QColor(palette.surface_bg)
        surface_alt = QColor(palette.surface_alt_bg)
        input_bg = QColor(palette.input_bg)
        border = QColor(palette.border)
        text = QColor(palette.text_primary)
        muted = QColor(palette.text_muted)
        accent = QColor(palette.accent)
        highlighted = QColor("#0f2b34" if palette.mode == "light" else "#081317")

        qt_palette.setColor(QPalette.ColorRole.Window, window)
        qt_palette.setColor(QPalette.ColorRole.WindowText, text)
        qt_palette.setColor(QPalette.ColorRole.Base, input_bg)
        qt_palette.setColor(QPalette.ColorRole.AlternateBase, surface_alt)
        qt_palette.setColor(QPalette.ColorRole.ToolTipBase, surface)
        qt_palette.setColor(QPalette.ColorRole.ToolTipText, text)
        qt_palette.setColor(QPalette.ColorRole.Text, text)
        qt_palette.setColor(QPalette.ColorRole.Button, surface)
        qt_palette.setColor(QPalette.ColorRole.ButtonText, text)
        qt_palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
        qt_palette.setColor(QPalette.ColorRole.PlaceholderText, muted)
        qt_palette.setColor(QPalette.ColorRole.Highlight, accent)
        qt_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(highlighted))
        qt_palette.setColor(QPalette.ColorRole.Light, surface_alt.lighter(106))
        qt_palette.setColor(QPalette.ColorRole.Midlight, surface_alt)
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
