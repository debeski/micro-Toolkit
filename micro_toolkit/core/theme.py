from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette, Qt

try:
    from qt_material import apply_stylesheet as apply_material_stylesheet
except Exception:  # pragma: no cover - optional dependency
    apply_material_stylesheet = None


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
        self._font_family = "Dubai"
        self._loaded_font_families: list[str] = []

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
        palette = self.current_palette()
        base_font = QFont()
        if self._loaded_font_families:
            try:
                base_font.setFamilies(self._loaded_font_families)
            except Exception:
                base_font.setFamily(self._loaded_font_families[0])
        else:
            base_font.setFamily(self._font_family)
        base_font.setPointSize(max(10, round(11 * scale)))
        app.setFont(base_font)
        if apply_material_stylesheet is not None:
            self._apply_material_theme(app, palette, scale)
        else:
            app.setPalette(self._build_qpalette(palette))
            app.setStyleSheet(self._build_legacy_stylesheet(palette, scale))
        self.theme_changed.emit(palette.mode)

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
        preferred: list[str] = []
        font_candidates = [
            self.assets_root / "fonts" / "dubai-VF.ttf",
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
        fallback_families = ["Dubai", "DejaVu Sans", "Noto Sans Arabic", "Sans Serif"]
        for family in fallback_families:
            if family not in preferred:
                preferred.append(family)
        self._loaded_font_families = preferred

    def _normalized_scale(self) -> float:
        try:
            scale = float(self.config.get("ui_scaling") or 1.0)
        except Exception:
            return 1.0
        return min(1.6, max(0.85, scale))

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

    def _apply_material_theme(self, app, palette: ThemePalette, scale: float) -> None:
        density = self._material_density_scale(scale)
        resource_parent = self.config.config_path.parent / "runtime" / "qt_material"
        resource_parent.mkdir(parents=True, exist_ok=True)
        extra = {
            "font_family": self._loaded_font_families[0] if self._loaded_font_families else self._font_family,
            "danger": palette.danger,
            "warning": "#d48f12" if palette.mode == "light" else "#f0b84a",
            "success": "#2f7d4d" if palette.mode == "light" else "#6dbb7f",
            "density_scale": str(density),
        }
        apply_material_stylesheet(
            app,
            theme=self._material_theme_name(palette),
            invert_secondary=palette.mode == "light",
            extra=extra,
            parent=str(resource_parent),
        )
        app.setPalette(self._build_qpalette(palette))
        app.setStyleSheet(app.styleSheet() + "\n" + self._build_material_overlay_stylesheet(palette, scale))

    def _material_theme_name(self, palette: ThemePalette) -> str:
        return "dark_teal.xml" if palette.mode == "dark" else "light_teal.xml"

    def _material_density_scale(self, scale: float) -> int:
        if scale <= 0.95:
            return -2
        if scale < 1.05:
            return -1
        if scale <= 1.2:
            return 0
        if scale <= 1.4:
            return 1
        return 2

    def _build_material_overlay_stylesheet(self, palette: ThemePalette, scale: float) -> str:
        title_size = max(24, round(26 * scale))
        page_title_size = max(20, round(24 * scale))
        eyebrow_size = max(10, round(11 * scale))
        body_size = max(12, round(13 * scale))
        card_radius = max(14, round(18 * scale))
        input_radius = max(10, round(12 * scale))
        return f"""
        QWidget {{
            font-size: {body_size}px;
        }}
        QLabel, QCheckBox, QRadioButton {{
            background: transparent;
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
        QTreeWidget {{
            padding: 8px;
            border-radius: {input_radius}px;
        }}
        QTreeWidget::item, QListWidget::item {{
            padding: 9px 10px;
            border-radius: 12px;
            margin: 3px 0px;
        }}
        QTreeWidget::item:selected, QListWidget::item:selected {{
            background: {palette.accent_soft};
            color: {palette.text_primary};
        }}
        QTreeWidget::branch:selected {{
            background: transparent;
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
        """

    def _build_legacy_stylesheet(self, palette: ThemePalette, scale: float) -> str:
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
            font-family: "{self._loaded_font_families[0] if self._loaded_font_families else self._font_family}";
            font-size: {body_size}px;
        }}
        QLabel, QCheckBox, QRadioButton {{
            background: transparent;
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
        QTreeWidget {{
            padding: 10px;
        }}
        QTreeWidget::item, QListWidget::item {{
            padding: 10px 10px;
            border-radius: 12px;
            margin: 3px 0px;
        }}
        QTreeWidget::item:selected, QListWidget::item:selected {{
            background: {palette.accent_soft};
            color: {palette.text_primary};
        }}
        QTreeWidget::branch:selected {{
            background: transparent;
        }}
        QToolButton {{
            background: transparent;
            color: {palette.text_primary};
            border: 1px solid transparent;
            border-radius: {input_radius}px;
            padding: 8px 10px;
            font-weight: 600;
        }}
        QToolButton:hover {{
            background: {palette.surface_alt_bg};
            border-color: {palette.border};
        }}
        QToolButton:checked {{
            background: {palette.accent_soft};
            border-color: {palette.accent};
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
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            background: {palette.input_bg};
            border: 1px solid {palette.border};
        }}
        QCheckBox::indicator {{
            border-radius: 4px;
        }}
        QRadioButton::indicator {{
            border-radius: 9px;
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border-color: {palette.accent};
            background: {palette.surface_alt_bg};
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background: {palette.accent};
            border-color: {palette.accent};
        }}
        QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
            background: {palette.surface_alt_bg};
            border-color: {palette.border};
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
            min-height: 20px;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 12px;
            margin: 8px 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {palette.border};
            min-height: 36px;
            border-radius: 6px;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 12px;
            margin: 0px 8px;
        }}
        QScrollBar::handle:horizontal {{
            background: {palette.border};
            min-width: 36px;
            border-radius: 6px;
        }}
        QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
            background: transparent;
            border: none;
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
