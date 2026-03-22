from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, Qt


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
    window_bg="#f4efe6",
    surface_bg="#fffaf3",
    surface_alt_bg="#fffdf9",
    input_bg="#fffdf9",
    border="#e0d5c6",
    text_primary="#18242c",
    text_muted="#56646b",
    accent="#1f7a8c",
    accent_hover="#186574",
    accent_soft="#d9edf0",
    danger="#b63f26",
    selection="#1f7a8c",
    status_bg="#fffaf3",
)


DARK_PALETTE = ThemePalette(
    mode="dark",
    window_bg="#151b20",
    surface_bg="#1d262d",
    surface_alt_bg="#222e36",
    input_bg="#1c252c",
    border="#31414c",
    text_primary="#edf3f6",
    text_muted="#a8bbc5",
    accent="#3ba7bb",
    accent_hover="#2d91a5",
    accent_soft="#173944",
    danger="#d66b57",
    selection="#3ba7bb",
    status_bg="#1d262d",
)


class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self, config, assets_root):
        super().__init__()
        self.config = config
        self.assets_root = assets_root
        self._font_family = "DejaVu Sans"
        self._loaded_font_family = None

    def available_modes(self) -> list[tuple[str, str]]:
        return [
            ("system", "System"),
            ("light", "Light"),
            ("dark", "Dark"),
        ]

    def current_mode(self) -> str:
        value = str(self.config.get("appearance_mode") or "system").strip().lower()
        if value not in {"system", "light", "dark"}:
            value = "system"
        return value

    def set_mode(self, mode: str) -> None:
        normalized = (mode or "system").strip().lower()
        if normalized not in {"system", "light", "dark"}:
            normalized = "system"
        self.config.set("appearance_mode", normalized)
        self.theme_changed.emit(normalized)

    def current_palette(self) -> ThemePalette:
        configured_mode = self.current_mode()
        if configured_mode == "system":
            actual_mode = self._system_mode()
        else:
            actual_mode = configured_mode
        return DARK_PALETTE if actual_mode == "dark" else LIGHT_PALETTE

    def apply(self, app) -> None:
        self._ensure_font_loaded(app)
        scale = self._normalized_scale()
        base_font = QFont(self._loaded_font_family or self._font_family, max(10, round(11 * scale)))
        app.setFont(base_font)
        app.setStyleSheet(self._build_stylesheet(self.current_palette(), scale))
        self.theme_changed.emit(self.current_mode())

    def refresh_system_mode(self, app) -> None:
        if self.current_mode() == "system":
            self.apply(app)

    def _system_mode(self) -> str:
        style_hints = QGuiApplication.styleHints()
        try:
            color_scheme = style_hints.colorScheme()
        except Exception:
            return "light"
        return "dark" if color_scheme == Qt.ColorScheme.Dark else "light"

    def _ensure_font_loaded(self, app) -> None:
        font_path = self.assets_root / "fonts" / "DejaVuSans-Bold.ttf"
        regular_path = self.assets_root / "fonts" / "DejaVuSans.ttf"
        for candidate in (regular_path, font_path):
            if not candidate.exists():
                continue
            font_id = QFontDatabase.addApplicationFont(str(candidate))
            if font_id == -1:
                continue
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                self._loaded_font_family = families[0]
                return
        self._loaded_font_family = self._font_family

    def _normalized_scale(self) -> float:
        try:
            scale = float(self.config.get("ui_scaling") or 1.0)
        except Exception:
            return 1.0
        return min(1.6, max(0.85, scale))

    def _build_stylesheet(self, palette: ThemePalette, scale: float) -> str:
        title_size = max(24, round(26 * scale))
        page_title_size = max(20, round(24 * scale))
        eyebrow_size = max(10, round(11 * scale))
        body_size = max(12, round(13 * scale))
        card_radius = max(14, round(18 * scale))
        input_radius = max(10, round(12 * scale))
        return f"""
        QWidget {{
            background: {palette.window_bg};
            color: {palette.text_primary};
            font-family: "{self._loaded_font_family or self._font_family}";
            font-size: {body_size}px;
        }}
        QMainWindow {{
            background: {palette.window_bg};
        }}
        QFrame#SidebarCard, QFrame#HeaderCard, QFrame#PageCard {{
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
        QLabel#SectionEyebrow {{
            color: {palette.accent};
            font-size: {eyebrow_size}px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        QLineEdit, QPlainTextEdit, QTextEdit, QTreeWidget, QListWidget, QTableView, QTableWidget, QComboBox, QSpinBox, QDoubleSpinBox {{
            background: {palette.input_bg};
            border: 1px solid {palette.border};
            border-radius: {input_radius}px;
            padding: 8px;
            selection-background-color: {palette.selection};
            selection-color: {"#0f2b34" if palette.mode == "light" else "#081317"};
        }}
        QHeaderView::section {{
            background: {palette.surface_alt_bg};
            color: {palette.text_primary};
            border: none;
            border-bottom: 1px solid {palette.border};
            padding: 8px;
            font-weight: 700;
        }}
        QTreeWidget, QListWidget, QTableView, QTableWidget {{
            alternate-background-color: {palette.surface_alt_bg};
            gridline-color: {palette.border};
        }}
        QTreeWidget::item, QListWidget::item {{
            padding: 8px 6px;
            border-radius: 8px;
        }}
        QTreeWidget::item:selected, QListWidget::item:selected {{
            background: {palette.accent_soft};
            color: {palette.text_primary};
        }}
        QPushButton {{
            background: {palette.accent};
            color: white;
            border: none;
            border-radius: {input_radius}px;
            padding: 10px 14px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background: {palette.accent_hover};
        }}
        QPushButton:disabled {{
            background: {palette.border};
            color: {palette.text_muted};
        }}
        QCheckBox, QRadioButton {{
            color: {palette.text_primary};
            spacing: 8px;
        }}
        QTabWidget::pane {{
            border: 1px solid {palette.border};
            border-radius: {input_radius}px;
            background: {palette.surface_bg};
            margin-top: 8px;
        }}
        QTabBar::tab {{
            background: {palette.surface_alt_bg};
            color: {palette.text_muted};
            padding: 8px 14px;
            border-top-left-radius: {input_radius}px;
            border-top-right-radius: {input_radius}px;
            margin-right: 4px;
        }}
        QTabBar::tab:selected {{
            background: {palette.surface_bg};
            color: {palette.text_primary};
            font-weight: 700;
        }}
        QProgressBar {{
            background: {palette.surface_alt_bg};
            border: none;
            border-radius: 8px;
            text-align: center;
            color: {palette.text_primary};
        }}
        QProgressBar::chunk {{
            background: {palette.accent};
            border-radius: 8px;
        }}
        QStatusBar {{
            background: {palette.status_bg};
            border-top: 1px solid {palette.border};
        }}
        QDockWidget::title {{
            background: {palette.surface_alt_bg};
            color: {palette.text_primary};
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid {palette.border};
        }}
        QMenu {{
            background: {palette.surface_bg};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            padding: 6px;
        }}
        QMenu::item:selected {{
            background: {palette.accent_soft};
        }}
        """
