from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QStyle,
    QStyleOptionTabWidgetFrame,
    QScrollArea,
    )

from micro_toolkit.core.confirm_dialog import confirm_action
from micro_toolkit.core.icon_registry import icon_choices, icon_from_name
from micro_toolkit.core.page_style import card_style, muted_text_style, page_title_style, section_title_style
from micro_toolkit.core.plugin_api import QtPlugin
from micro_toolkit.core.app_config import DEFAULT_CONFIG
from micro_toolkit.core.shell_registry import DASHBOARD_PLUGIN_ID, INSPECTOR_PLUGIN_ID
from micro_toolkit.core.widgets import ScrollSafeComboBox, ScrollSafeSlider, adaptive_columns, adaptive_grid_columns, visible_parent_width, width_breakpoint


QComboBox = ScrollSafeComboBox


class CurrentTabSizeWidget(QTabWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.currentChanged.connect(self._refresh_geometry)

    def sizeHint(self):
        return self._tab_aware_size_hint(minimum=False)

    def minimumSizeHint(self):
        return self._tab_aware_size_hint(minimum=True)

    def _tab_aware_size_hint(self, *, minimum: bool):
        current = self.currentWidget()
        if current is None:
            return super().minimumSizeHint() if minimum else super().sizeHint()

        page_hint = current.minimumSizeHint() if minimum else current.sizeHint()
        tab_bar_hint = self.tabBar().sizeHint()

        option = QStyleOptionTabWidgetFrame()
        self.initStyleOption(option)
        frame_width = self.style().pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth, option, self)
        width = max(page_hint.width(), tab_bar_hint.width()) + (frame_width * 2)
        height = page_hint.height() + tab_bar_hint.height() + (frame_width * 2)
        return QSize(width, height)

    def _refresh_geometry(self, _index: int) -> None:
        self.updateGeometry()
        current = self.currentWidget()
        if current is not None:
            current.updateGeometry()


class ThemeSwatchButton(QToolButton):
    def __init__(self, label: str, color_hex: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._color_hex = color_hex
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIconSize(QSize(22, 22))
        self.setFixedSize(34, 34)
        self.setToolTip(label)
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        pixmap = QPixmap(26, 26)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#ffffff"), 1.4))
        painter.setBrush(QColor(self._color_hex))
        painter.drawEllipse(3, 3, 20, 20)
        painter.end()
        self.setIcon(QIcon(pixmap))


class ChoiceChipButton(QToolButton):
    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setText(label)
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setMinimumHeight(32)


class QuickAccessPreviewTile(QFrame):
    clicked = Signal()

    def __init__(self, label: str, icon: QIcon, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("QuickAccessPreviewTile")
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(112, 96)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setPixmap(icon.pixmap(38, 38))
        layout.addWidget(self.icon_label)
        self.text_label = QLabel(label)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)

    def apply_palette(self, palette) -> None:
        background = palette.accent_soft if self._hovered else "transparent"
        border = palette.accent if self._hovered else "transparent"
        self.setStyleSheet(
            f"""
            QFrame#QuickAccessPreviewTile {{
                background: {background};
                border: 1px solid {border};
                border-radius: 18px;
            }}
            QLabel {{
                background: transparent;
                color: {palette.text_primary};
                font-size: 12px;
                font-weight: 600;
            }}
            """
        )

    def enterEvent(self, event) -> None:
        self._hovered = True
        page = self.parentWidget()
        while page is not None and not hasattr(page, "services"):
            page = page.parentWidget()
        services = getattr(page, "services", None)
        if services is not None:
            self.apply_palette(services.theme_manager.current_palette())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        page = self.parentWidget()
        while page is not None and not hasattr(page, "services"):
            page = page.parentWidget()
        services = getattr(page, "services", None)
        if services is not None:
            self.apply_palette(services.theme_manager.current_palette())
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ClickSlider(ScrollSafeSlider):
    interaction_started = Signal(int)
    interaction_finished = Signal(int)

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None):
        super().__init__(orientation, parent)
        self._mouse_interaction_active = False

    def mouse_interaction_active(self) -> bool:
        return self._mouse_interaction_active

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_interaction_active = True
            self.interaction_started.emit(self.value())
            self._set_value_from_event(event)
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._set_value_from_event(event)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_interaction_active = False
            self.interaction_finished.emit(self.value())

    def _set_value_from_event(self, event) -> None:
        if self.orientation() == Qt.Orientation.Horizontal:
            span = max(1, self.width())
            position = max(0, min(span, int(event.position().x())))
        else:
            span = max(1, self.height())
            position = max(0, min(span, int(event.position().y())))
        value = QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            position,
            span,
            upsideDown=(self.orientation() == Qt.Orientation.Vertical),
        )
        self.setValue(value)


class IconPickerDialog(QDialog):
    def __init__(self, parent: QWidget, options: list[tuple[str, str, object]], current_value: str = ""):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self._selected_icon = str(current_value or "").strip()
        self._options = options
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setWrapping(True)
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(8)
        self.grid.setIconSize(QSize(22, 22))
        self.grid.setGridSize(QSize(86, 62))
        self.grid.setWordWrap(True)
        self.grid.itemClicked.connect(self._choose_item)
        self.grid.itemDoubleClicked.connect(self._choose_item)
        layout.addWidget(self.grid)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        clear_button = QPushButton("Default")
        clear_button.clicked.connect(self._clear_selection)
        actions.addWidget(clear_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        self.resize(420, 320)

    def _populate(self) -> None:
        default_item = QListWidgetItem("Default")
        default_item.setData(Qt.ItemDataRole.UserRole, "")
        self.grid.addItem(default_item)
        if not self._selected_icon:
            self.grid.setCurrentItem(default_item)

        for icon_id, label, icon in self._options:
            item = QListWidgetItem(icon, label)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setData(Qt.ItemDataRole.UserRole, icon_id)
            self.grid.addItem(item)
            if icon_id == self._selected_icon:
                self.grid.setCurrentItem(item)

    def _choose_item(self, item: QListWidgetItem) -> None:
        self._selected_icon = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        self.accept()

    def _clear_selection(self) -> None:
        self._selected_icon = ""
        self.accept()

    def selected_icon(self) -> str:
        return self._selected_icon


class IconPickerButton(QToolButton):
    def __init__(self, page: "SettingsCenterPage", initial_value: str = ""):
        super().__init__(page)
        self._page = page
        self._selected_icon = str(initial_value or "").strip()
        self.setAutoRaise(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIconSize(QSize(18, 18))
        self.setFixedSize(32, 30)
        self.clicked.connect(self._open_picker)
        self._refresh()

    def _refresh(self) -> None:
        icon = icon_from_name(self._selected_icon, self._page) if self._selected_icon else None
        self.setIcon(icon or icon_from_name("plugin", self._page) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.setToolTip(self._page._pt("plugins.row.icon_picker", "Choose an icon"))

    def _open_picker(self) -> None:
        dialog = IconPickerDialog(self, self._page._icon_options(), self._selected_icon)
        anchor = self.mapToGlobal(self.rect().bottomLeft())
        dialog.move(anchor.x(), anchor.y() + 4)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._selected_icon = dialog.selected_icon()
            self._refresh()

    def selected_icon(self) -> str:
        return self._selected_icon


class SettingsCenterPlugin(QtPlugin):
    plugin_id = "settings_center"
    name = "Settings"
    description = "Application settings for appearance, automation, shortcuts, and plugin management."
    category = ""
    standalone = True
    translations = {
        "en": {
            "plugin.name": "Settings",
            "plugin.description": "Application settings for appearance, automation, shortcuts, and plugin management.",
        },
        "ar": {
            "plugin.name": "الإعدادات",
            "plugin.description": "إعدادات التطبيق للمظهر، والأتمتة، والاختصارات، وإدارة الإضافات.",
        },
    }

    def create_widget(self, services) -> QWidget:
        return SettingsCenterPage(services)


class SettingsCenterPage(QWidget):
    plugin_id = "settings_center"

    def __init__(self, services):
        super().__init__()
        self.services = services
        self.i18n = services.i18n
        self.shortcut_action_ids: list[str] = []
        self.plugin_row_map: dict[str, int] = {}
        self._building_plugin_table = False
        self._editing_plugin_id: str | None = None
        self._editing_snapshot: dict[str, str] = {}
        self._suspend_live_updates = False
        self._density_interaction_start_value: int | None = None
        self._scaling_interaction_start_value: int | None = None
        self._responsive_bucket = ""
        self._quick_access_preview_columns = 0
        self._geometry_refresh_pending = False
        self._responsive_refresh_pending = False
        self._plugins_table_width_sync_pending = False
        self._theme_preview_timer = QTimer(self)
        self._theme_preview_timer.setSingleShot(True)
        self._theme_preview_timer.timeout.connect(self._apply_pending_theme_preview)
        self._language_preview_timer = QTimer(self)
        self._language_preview_timer.setSingleShot(True)
        self._language_preview_timer.timeout.connect(self._apply_pending_language_preview)
        self._density_preview_timer = QTimer(self)
        self._density_preview_timer.setSingleShot(True)
        self._density_preview_timer.timeout.connect(self._apply_pending_density_preview)
        self._scaling_preview_timer = QTimer(self)
        self._scaling_preview_timer.setSingleShot(True)
        self._scaling_preview_timer.timeout.connect(self._apply_pending_scaling_preview)
        self._build_ui()
        self._populate_values()
        self._apply_texts()
        self.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self.services.quick_access_changed.connect(self._render_quick_access_settings)
        self.services.plugin_visuals_changed.connect(lambda _plugin_id: self._render_quick_access_settings())
        self.services.plugin_visuals_changed.connect(lambda _plugin_id: self._populate_startup_page_combo())

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def sizeHint(self):
        return self._page_size_hint(minimum=False)

    def minimumSizeHint(self):
        return self._page_size_hint(minimum=True)

    def _page_size_hint(self, *, minimum: bool):
        title_hint = self.title_label.minimumSizeHint() if minimum else self.title_label.sizeHint()
        description_hint = self.description_label.minimumSizeHint() if minimum else self.description_label.sizeHint()
        tabs_hint = self.tabs.minimumSizeHint() if minimum else self.tabs.sizeHint()
        margins = self.layout().contentsMargins() if self.layout() is not None else self.contentsMargins()
        spacing = self.layout().spacing() if self.layout() is not None else 0
        width = max(title_hint.width(), description_hint.width(), tabs_hint.width()) + margins.left() + margins.right()
        height = (
            margins.top()
            + title_hint.height()
            + spacing
            + description_hint.height()
            + spacing
            + tabs_hint.height()
            + margins.bottom()
        )
        return QSize(width, height)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 26px; font-weight: 700;")
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("font-size: 14px;")
        outer.addWidget(self.description_label)

        self.tabs = CurrentTabSizeWidget()
        self.tabs.currentChanged.connect(self._handle_tab_changed)
        outer.addWidget(self.tabs, 1)

        self.general_tab = QWidget()
        self.quick_access_tab = QWidget()
        self.shortcuts_tab = QWidget()
        self.plugins_tab = QWidget()
        self.tabs.addTab(self.general_tab, "")
        self.tabs.addTab(self.quick_access_tab, "")
        self.tabs.addTab(self.shortcuts_tab, "")
        self.tabs.addTab(self.plugins_tab, "")

        self._build_general_tab()
        self._build_quick_access_tab()
        self._build_shortcuts_tab()
        self._build_plugins_tab()

    def _build_general_tab(self) -> None:
        layout = QVBoxLayout(self.general_tab)
        layout.setContentsMargins(20, 20, 20, 10)
        layout.setSpacing(14)

        self.output_card = QFrame()
        output_layout = QVBoxLayout(self.output_card)
        output_layout.setContentsMargins(18, 16, 18, 16)
        output_layout.setSpacing(10)
        self.output_title = QLabel()
        output_layout.addWidget(self.output_title)
        self.general_note = QLabel()
        self.general_note.setWordWrap(True)
        output_layout.addWidget(self.general_note)
        self.output_label = QLabel()
        self.startup_page_label = QLabel()
        output_form = QFormLayout()
        output_form.setContentsMargins(0, 4, 0, 0)
        output_form.setSpacing(12)

        row = QHBoxLayout()
        self.output_dir_input = QLineEdit()
        row.addWidget(self.output_dir_input, 1)
        self.output_browse_button = QPushButton()
        self.output_browse_button.clicked.connect(self._browse_output_dir)
        row.addWidget(self.output_browse_button)
        output_form.addRow(self.output_label, row)

        self.startup_page_combo = QComboBox()
        output_form.addRow(self.startup_page_label, self.startup_page_combo)
        output_layout.addLayout(output_form)
        layout.addWidget(self.output_card)

        self.appearance_card = QFrame()
        appearance_layout = QVBoxLayout(self.appearance_card)
        appearance_layout.setContentsMargins(18, 16, 18, 16)
        appearance_layout.setSpacing(10)
        self.appearance_title = QLabel()
        appearance_layout.addWidget(self.appearance_title)
        self.appearance_note = QLabel()
        self.appearance_note.setWordWrap(True)
        appearance_layout.addWidget(self.appearance_note)
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        form.setSpacing(12)
        self.theme_label = QLabel()
        self.language_label = QLabel()
        self.density_label = QLabel()
        self.scaling_label = QLabel()

        self.theme_button_group = QButtonGroup(self)
        self.theme_button_group.setExclusive(True)
        self.theme_color_buttons: dict[str, ThemeSwatchButton] = {}
        theme_picker_host = QWidget()
        self.theme_picker_host = theme_picker_host
        theme_picker_layout = QHBoxLayout(theme_picker_host)
        theme_picker_layout.setContentsMargins(0, 0, 0, 0)
        theme_picker_layout.setSpacing(8)
        for color_key, label, preview in self.services.theme_manager.available_theme_colors():
            button = ThemeSwatchButton(label, preview, theme_picker_host)
            button.clicked.connect(self._handle_live_theme_change)
            self.theme_button_group.addButton(button)
            self.theme_color_buttons[color_key] = button
            theme_picker_layout.addWidget(button)
        self.dark_mode_checkbox = QCheckBox()
        self.dark_mode_checkbox.toggled.connect(self._handle_live_theme_change)
        theme_picker_layout.addWidget(self.dark_mode_checkbox)
        theme_picker_layout.addStretch(1)
        form.addRow(self.theme_label, theme_picker_host)

        self.language_button_group = QButtonGroup(self)
        self.language_button_group.setExclusive(True)
        self.language_buttons: dict[str, ChoiceChipButton] = {}
        language_host = QWidget()
        self.language_host = language_host
        language_layout = QHBoxLayout(language_host)
        language_layout.setContentsMargins(0, 0, 0, 0)
        language_layout.setSpacing(8)
        for code, label in self.i18n.available_languages():
            button = ChoiceChipButton(label, language_host)
            button.clicked.connect(self._handle_live_language_change)
            self.language_button_group.addButton(button)
            self.language_buttons[code] = button
            language_layout.addWidget(button)
        language_layout.addStretch(1)
        form.addRow(self.language_label, language_host)

        density_host = QWidget()
        self.density_host = density_host
        density_layout = QHBoxLayout(density_host)
        density_layout.setContentsMargins(0, 0, 0, 0)
        density_layout.setSpacing(10)
        self.density_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.density_slider.setRange(-3, 3)
        self.density_slider.setSingleStep(1)
        self.density_slider.setPageStep(1)
        self.density_slider.setTickInterval(1)
        self.density_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.density_slider.interaction_started.connect(self._remember_density_interaction_start)
        self.density_slider.valueChanged.connect(self._handle_live_density_change)
        self.density_slider.interaction_finished.connect(self._handle_density_released)
        density_layout.addWidget(self.density_slider, 1)
        self.density_value_label = QLabel("0")
        density_layout.addWidget(self.density_value_label)
        form.addRow(self.density_label, density_host)

        scaling_host = QWidget()
        self.scaling_host = scaling_host
        scaling_layout = QHBoxLayout(scaling_host)
        scaling_layout.setContentsMargins(0, 0, 0, 0)
        scaling_layout.setSpacing(10)
        self.scaling_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.scaling_slider.setRange(85, 160)
        self.scaling_slider.setSingleStep(10)
        self.scaling_slider.setPageStep(10)
        self.scaling_slider.setTickInterval(10)
        self.scaling_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.scaling_slider.interaction_started.connect(self._remember_scaling_interaction_start)
        self.scaling_slider.valueChanged.connect(self._handle_live_scaling_change)
        self.scaling_slider.interaction_finished.connect(self._handle_scaling_released)
        scaling_layout.addWidget(self.scaling_slider, 1)
        self.scaling_value_label = QLabel("100%")
        scaling_layout.addWidget(self.scaling_value_label)
        form.addRow(self.scaling_label, scaling_host)
        appearance_layout.addLayout(form)

        layout.addWidget(self.appearance_card)

        self.general_tools_row = QHBoxLayout()
        self.general_tools_row.setContentsMargins(0, 0, 0, 0)
        self.general_tools_row.setSpacing(12)

        self.automation_card = QFrame()
        card_layout = QVBoxLayout(self.automation_card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(8)
        self.behavior_title = QLabel()
        card_layout.addWidget(self.behavior_title)
        self.behavior_note = QLabel()
        self.behavior_note.setWordWrap(True)
        card_layout.addWidget(self.behavior_note)

        self.minimize_to_tray_checkbox = QCheckBox()
        card_layout.addWidget(self.minimize_to_tray_checkbox)
        self.close_to_tray_checkbox = QCheckBox()
        card_layout.addWidget(self.close_to_tray_checkbox)
        self.confirm_on_exit_checkbox = QCheckBox()
        card_layout.addWidget(self.confirm_on_exit_checkbox)
        self.run_on_startup_checkbox = QCheckBox()
        card_layout.addWidget(self.run_on_startup_checkbox)
        self.start_minimized_checkbox = QCheckBox()
        card_layout.addWidget(self.start_minimized_checkbox)
        self.developer_mode_checkbox = QCheckBox()
        card_layout.addWidget(self.developer_mode_checkbox)
        self.autostart_status_label = QLabel()
        self.autostart_status_label.setWordWrap(True)
        card_layout.addWidget(self.autostart_status_label)
        self.general_tools_row.addWidget(self.automation_card, 1)

        self.backup_card = QFrame()
        backup_layout = QVBoxLayout(self.backup_card)
        backup_layout.setContentsMargins(18, 16, 18, 16)
        backup_layout.setSpacing(8)
        self.backup_title = QLabel()
        backup_layout.addWidget(self.backup_title)
        self.backup_note = QLabel()
        self.backup_note.setWordWrap(True)
        backup_layout.addWidget(self.backup_note)
        self.backup_schedule_label = QLabel()
        self.backup_schedule_combo = QComboBox()
        self.backup_schedule_combo.addItem("Daily", "daily")
        self.backup_schedule_combo.addItem("Weekly", "weekly")
        self.backup_schedule_combo.addItem("Monthly", "monthly")
        self.backup_schedule_combo.currentIndexChanged.connect(self._refresh_backup_status)
        backup_schedule_row = QHBoxLayout()
        backup_schedule_row.setContentsMargins(0, 0, 0, 0)
        backup_schedule_row.setSpacing(8)
        backup_schedule_row.addWidget(self.backup_schedule_label)
        backup_schedule_row.addWidget(self.backup_schedule_combo, 1)
        backup_layout.addLayout(backup_schedule_row)
        self.backup_status_label = QLabel()
        self.backup_status_label.setWordWrap(True)
        backup_layout.addWidget(self.backup_status_label)
        backup_actions = QHBoxLayout()
        backup_actions.setContentsMargins(0, 0, 0, 0)
        backup_actions.setSpacing(8)
        self.create_backup_button = QPushButton()
        self.create_backup_button.clicked.connect(self._create_backup_now)
        backup_actions.addWidget(self.create_backup_button)
        self.restore_backup_button = QPushButton()
        self.restore_backup_button.clicked.connect(self._restore_backup_from_file)
        backup_actions.addWidget(self.restore_backup_button)
        backup_actions.addStretch(1)
        backup_layout.addLayout(backup_actions)
        self.general_tools_row.addWidget(self.backup_card, 1)

        layout.addLayout(self.general_tools_row)

        self.general_actions = QHBoxLayout()
        self.general_actions.addStretch(1)
        self.general_reset_button = QPushButton()
        self.general_reset_button.clicked.connect(self._reset_general_defaults)
        self.general_actions.addWidget(self.general_reset_button)
        self.general_save_button = QPushButton()
        self.general_save_button.clicked.connect(self._save_general_settings)
        self.general_actions.addWidget(self.general_save_button)
        layout.addLayout(self.general_actions)

    def _build_quick_access_tab(self) -> None:
        layout = QVBoxLayout(self.quick_access_tab)
        layout.setContentsMargins(20, 20, 20, 10)
        layout.setSpacing(14)

        self.quick_access_tab_note = QLabel()
        self.quick_access_tab_note.setWordWrap(True)
        layout.addWidget(self.quick_access_tab_note)

        self.quick_access_card = QFrame()
        quick_layout = QVBoxLayout(self.quick_access_card)
        quick_layout.setContentsMargins(18, 18, 18, 18)
        quick_layout.setSpacing(12)

        self.quick_access_title = QLabel()
        quick_layout.addWidget(self.quick_access_title)
        self.quick_access_note = QLabel()
        self.quick_access_note.setWordWrap(True)
        quick_layout.addWidget(self.quick_access_note)

        self.quick_access_preview_frame = QFrame()
        self.quick_access_preview_frame.setObjectName("QuickAccessPreview")
        self.quick_access_preview_layout = QGridLayout(self.quick_access_preview_frame)
        self.quick_access_preview_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_access_preview_layout.setHorizontalSpacing(10)
        self.quick_access_preview_layout.setVerticalSpacing(10)
        quick_layout.addWidget(self.quick_access_preview_frame)

        self.quick_add_row = QHBoxLayout()
        self.quick_add_row.setContentsMargins(0, 0, 0, 0)
        self.quick_add_row.setSpacing(8)
        self.quick_access_combo = QComboBox()
        self.quick_add_row.addWidget(self.quick_access_combo, 1)
        self.quick_access_add_button = QPushButton()
        self.quick_access_add_button.clicked.connect(self._add_selected_quick_access_plugin)
        self.quick_add_row.addWidget(self.quick_access_add_button)
        quick_layout.addLayout(self.quick_add_row)

        self.quick_manage_row = QHBoxLayout()
        self.quick_manage_row.setContentsMargins(0, 0, 0, 0)
        self.quick_manage_row.setSpacing(8)
        self.quick_access_list = QListWidget()
        self.quick_access_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.quick_access_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.quick_access_list.setMaximumHeight(230)
        self.quick_access_list.itemSelectionChanged.connect(self._sync_quick_access_buttons)
        self.quick_access_list.model().rowsMoved.connect(self._persist_quick_access_from_settings_list)
        self.quick_manage_row.addWidget(self.quick_access_list, 1)

        self.quick_actions_host = QWidget()
        self.quick_actions_layout = QGridLayout(self.quick_actions_host)
        self.quick_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_actions_layout.setHorizontalSpacing(6)
        self.quick_actions_layout.setVerticalSpacing(6)
        self.quick_access_move_up_button = QPushButton()
        self.quick_access_move_up_button.clicked.connect(lambda: self._move_selected_quick_access(-1))
        self.quick_access_move_down_button = QPushButton()
        self.quick_access_move_down_button.clicked.connect(lambda: self._move_selected_quick_access(1))
        self.quick_access_open_button = QPushButton()
        self.quick_access_open_button.clicked.connect(self._open_selected_quick_access_plugin)
        self.quick_access_remove_button = QPushButton()
        self.quick_access_remove_button.clicked.connect(self._remove_selected_quick_access_plugin)
        self._quick_action_buttons = [
            self.quick_access_move_up_button,
            self.quick_access_move_down_button,
            self.quick_access_open_button,
            self.quick_access_remove_button,
        ]
        self.quick_manage_row.addWidget(self.quick_actions_host)
        quick_layout.addLayout(self.quick_manage_row)

        layout.addWidget(self.quick_access_card, 1)

    def _build_shortcuts_tab(self) -> None:
        layout = QVBoxLayout(self.shortcuts_tab)
        layout.setContentsMargins(20, 20, 20, 10)
        layout.setSpacing(14)

        self.shortcut_note = QLabel()
        self.shortcut_note.setWordWrap(True)
        layout.addWidget(self.shortcut_note)

        self.shortcut_status_label = QLabel()
        self.shortcut_status_label.setWordWrap(True)
        layout.addWidget(self.shortcut_status_label)

        self.shortcut_actions = QHBoxLayout()
        self.start_helper_button = QPushButton()
        self.start_helper_button.clicked.connect(self._start_hotkey_helper)
        self.shortcut_actions.addWidget(self.start_helper_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.stop_helper_button = QPushButton()
        self.stop_helper_button.clicked.connect(self._stop_hotkey_helper)
        self.shortcut_actions.addWidget(self.stop_helper_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.shortcut_actions.addStretch(1)
        layout.addLayout(self.shortcut_actions)

        self.shortcut_table = QTableWidget(0, 3)
        self.shortcut_table.setAlternatingRowColors(True)
        self.shortcut_table.verticalHeader().setVisible(False)
        self.shortcut_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.shortcut_table, 1)

        self.shortcuts_footer_actions = QHBoxLayout()
        self.shortcuts_footer_actions.addStretch(1)
        self.shortcuts_reset_button = QPushButton()
        self.shortcuts_reset_button.clicked.connect(self._reset_shortcut_defaults)
        self.shortcuts_footer_actions.addWidget(self.shortcuts_reset_button)
        self.shortcuts_save_button = QPushButton()
        self.shortcuts_save_button.clicked.connect(self._save_shortcuts)
        self.shortcuts_footer_actions.addWidget(self.shortcuts_save_button)
        layout.addLayout(self.shortcuts_footer_actions)

    def _build_plugins_tab(self) -> None:
        layout = QVBoxLayout(self.plugins_tab)
        layout.setContentsMargins(20, 20, 20, 10)
        layout.setSpacing(14)

        self.plugins_note = QLabel()
        self.plugins_note.setWordWrap(True)
        layout.addWidget(self.plugins_note)

        self.plugins_table = QTableWidget(0, 11)
        self.plugins_table.setAlternatingRowColors(True)
        self.plugins_table.verticalHeader().setVisible(False)
        self.plugins_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.plugins_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.plugins_table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.plugins_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.plugins_table.customContextMenuRequested.connect(self._show_plugins_context_menu)
        header = self.plugins_table.horizontalHeader()
        header.setSectionsMovable(False)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(44)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        header.sectionResized.connect(self._schedule_plugins_table_width_sync)
        self.plugins_table.setColumnWidth(0, 88)
        self.plugins_table.setColumnWidth(1, 88)
        self.plugins_table.setColumnWidth(2, 220)
        self.plugins_table.setColumnWidth(3, 140)
        self.plugins_table.setColumnWidth(4, 92)
        self.plugins_table.setColumnWidth(5, 86)
        self.plugins_table.setColumnWidth(6, 82)
        self.plugins_table.setColumnWidth(7, 82)
        self.plugins_table.setColumnWidth(8, 86)
        self.plugins_table.setColumnWidth(9, 140)
        layout.addWidget(self.plugins_table, 1)

        self.plugins_actions_layout = QGridLayout()
        self.plugins_actions_layout.setHorizontalSpacing(8)
        self.plugins_actions_layout.setVerticalSpacing(8)
        self.import_file_button = self._make_action_button("open", self._import_plugin_file)
        self.import_folder_button = self._make_action_button("folder-open", self._import_plugin_folder)
        self.import_backup_button = self._make_action_button("download", self._import_backup)
        self.export_selected_button = self._make_action_button("save", self._export_selected_plugins)
        self.export_all_button = self._make_action_button("database", self._export_all_plugins)
        self.apply_plugin_state_button = self._make_action_button("check", self._apply_plugin_states)
        self.reset_plugins_button = self._make_action_button("repeat", self._reset_plugin_defaults)
        self.refresh_plugins_button = self._make_action_button("sync", self._populate_plugin_table)
        self._plugin_action_buttons = [
            self.import_file_button,
            self.import_folder_button,
            self.import_backup_button,
            self.export_selected_button,
            self.export_all_button,
            self.apply_plugin_state_button,
            self.reset_plugins_button,
            self.refresh_plugins_button,
        ]
        layout.addLayout(self.plugins_actions_layout)
        self._apply_responsive_layout(force=True)

    def _populate_values(self) -> None:
        self._suspend_live_updates = True
        self.output_dir_input.setText(str(self.services.default_output_path()))
        self._sync_theme_picker()
        self._sync_language_picker()
        self.density_slider.setValue(self.services.theme_manager.current_density_scale())
        self.density_value_label.setText(str(self.density_slider.value()))
        scaling_value = int(round(float(self.services.theme_manager.current_ui_scaling()) * 100))
        self.scaling_slider.setValue(max(85, min(160, scaling_value)))
        self.scaling_value_label.setText(f"{self.scaling_slider.value()}%")
        self.minimize_to_tray_checkbox.setChecked(bool(self.services.config.get("minimize_to_tray")))
        self.close_to_tray_checkbox.setChecked(bool(self.services.config.get("close_to_tray")))
        self.confirm_on_exit_checkbox.setChecked(bool(self.services.config.get("confirm_on_exit")))
        self.run_on_startup_checkbox.setChecked(bool(self.services.autostart_manager.is_enabled()))
        self.start_minimized_checkbox.setChecked(bool(self.services.config.get("start_minimized")))
        self.developer_mode_checkbox.setChecked(self.services.developer_mode_enabled())
        self._set_combo_value(self.backup_schedule_combo, self.services.backup_manager.schedule())
        self._populate_startup_page_combo(str(self.services.config.get("default_start_plugin") or DASHBOARD_PLUGIN_ID))
        self._render_quick_access_settings()
        self._populate_shortcuts()
        self._populate_plugin_table()
        self._refresh_autostart_status()
        self._refresh_shortcut_status()
        self._refresh_backup_status()
        self._suspend_live_updates = False
        self._apply_responsive_layout(force=True)

    def _selected_theme_color(self) -> str:
        for color_key, button in self.theme_color_buttons.items():
            if button.isChecked():
                return color_key
        return self.services.theme_manager.current_color_key()

    def _sync_theme_picker(self) -> None:
        current_color = self.services.theme_manager.current_color_key()
        for color_key, button in self.theme_color_buttons.items():
            button.blockSignals(True)
            button.setChecked(color_key == current_color)
            button.blockSignals(False)
        self.dark_mode_checkbox.blockSignals(True)
        self.dark_mode_checkbox.setChecked(self.services.theme_manager.is_dark_mode())
        self.dark_mode_checkbox.blockSignals(False)

    def _sync_language_picker(self) -> None:
        current_language = self.i18n.current_language()
        for code, button in self.language_buttons.items():
            button.blockSignals(True)
            button.setChecked(code == current_language)
            button.blockSignals(False)

    def _handle_live_theme_change(self) -> None:
        if self._suspend_live_updates:
            return
        self._schedule_theme_preview()

    def _handle_live_language_change(self) -> None:
        if self._suspend_live_updates:
            return
        self._schedule_language_preview()

    def _remember_density_interaction_start(self, value: int) -> None:
        self._density_interaction_start_value = int(value)

    def _remember_scaling_interaction_start(self, value: int) -> None:
        self._scaling_interaction_start_value = int(value)

    def _handle_live_density_change(self, value: int) -> None:
        self.density_value_label.setText(str(value))
        if self._suspend_live_updates:
            return
        if self.density_slider.mouse_interaction_active():
            return
        if not self.density_slider.isSliderDown():
            self._schedule_density_preview()

    def _handle_live_scaling_change(self, value: int) -> None:
        self.scaling_value_label.setText(f"{value}%")
        if self._suspend_live_updates:
            return
        if self.scaling_slider.mouse_interaction_active():
            return
        if not self.scaling_slider.isSliderDown():
            self._schedule_scaling_preview()

    def _handle_density_released(self, _value: int) -> None:
        if self._suspend_live_updates:
            return
        start_value = self._density_interaction_start_value
        self._density_interaction_start_value = None
        if start_value is not None and int(self.density_slider.value()) == int(start_value):
            return
        self._schedule_density_preview()

    def _handle_scaling_released(self, _value: int) -> None:
        if self._suspend_live_updates:
            return
        start_value = self._scaling_interaction_start_value
        self._scaling_interaction_start_value = None
        if start_value is not None and int(self.scaling_slider.value()) == int(start_value):
            return
        self._schedule_scaling_preview()

    def _selected_language(self) -> str:
        for code, button in self.language_buttons.items():
            if button.isChecked():
                return code
        return self.i18n.current_language()

    def _render_quick_access_settings(self, preferred_plugin_id: str | None = None) -> None:
        if not hasattr(self, "quick_access_list"):
            return

        while self.quick_access_preview_layout.count():
            item = self.quick_access_preview_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        palette = self.services.theme_manager.current_palette()
        quick_ids = self.services.quick_access_ids()
        preview_columns = self._quick_access_preview_column_count()
        self._quick_access_preview_columns = preview_columns
        preview_count = 0
        if quick_ids:
            for plugin_id in quick_ids:
                spec = self.services.plugin_manager.get_spec(plugin_id)
                if spec is None:
                    continue
                tile = QuickAccessPreviewTile(
                    self.services.plugin_display_name(spec),
                    self._quick_access_preview_icon(spec),
                    self.quick_access_preview_frame,
                )
                tile.setToolTip(spec.localized_description(self.i18n.current_language()))
                tile.clicked.connect(lambda _checked=False, pid=plugin_id: self._open_quick_access_plugin(pid))
                self.quick_access_preview_layout.addWidget(tile, preview_count // preview_columns, preview_count % preview_columns)
                preview_count += 1
        else:
            empty = QLabel(self._pt("quick_access.empty", "No quick access tools selected yet."))
            empty.setStyleSheet(muted_text_style(palette, size=13))
            self.quick_access_preview_layout.addWidget(empty, 0, 0, 1, preview_columns)
        if preview_count:
            for column in range(preview_columns):
                self.quick_access_preview_layout.setColumnStretch(column, 1)
            self.quick_access_preview_layout.setRowStretch((preview_count // preview_columns) + 1, 1)

        current_selection = preferred_plugin_id
        current_item = self.quick_access_list.currentItem()
        if current_selection is None and current_item is not None:
            current_selection = str(current_item.data(Qt.ItemDataRole.UserRole) or "")

        self.quick_access_list.blockSignals(True)
        self.quick_access_list.clear()
        selected_row = -1
        for row_index, plugin_id in enumerate(quick_ids):
            spec = self.services.plugin_manager.get_spec(plugin_id)
            if spec is None:
                continue
            item = QListWidgetItem(self.services.plugin_display_name(spec))
            item.setData(Qt.ItemDataRole.UserRole, plugin_id)
            self.quick_access_list.addItem(item)
            if plugin_id == current_selection:
                selected_row = row_index
        if self.quick_access_list.count():
            self.quick_access_list.setCurrentRow(selected_row if selected_row >= 0 else 0)
        self.quick_access_list.blockSignals(False)

        self.quick_access_combo.blockSignals(True)
        self.quick_access_combo.clear()
        pinned = set(quick_ids)
        for spec in self.services.pinnable_plugin_specs():
            if spec.plugin_id in pinned:
                continue
            self.quick_access_combo.addItem(self.services.plugin_display_name(spec), spec.plugin_id)
        self.quick_access_combo.blockSignals(False)
        self._sync_quick_access_buttons()

    def _quick_access_preview_column_count(self) -> int:
        available_width = min(
            visible_parent_width(self),
            self.quick_access_preview_frame.contentsRect().width()
            or self.quick_access_preview_frame.width()
            or self.quick_access_card.contentsRect().width()
            or self.quick_access_card.width()
            or self.width(),
        )
        spacing = self.quick_access_preview_layout.horizontalSpacing()
        required_for_four = (120 * 4) + (spacing * 3)
        return 4 if available_width >= required_for_four else 2

    def _refresh_quick_access_preview_layout(self) -> None:
        if not hasattr(self, "quick_access_preview_layout"):
            return
        target_columns = self._quick_access_preview_column_count()
        if target_columns == self._quick_access_preview_columns:
            return
        current_item = self.quick_access_list.currentItem() if hasattr(self, "quick_access_list") else None
        preferred_plugin_id = None
        if current_item is not None:
            preferred_plugin_id = str(current_item.data(Qt.ItemDataRole.UserRole) or "")
        self._render_quick_access_settings(preferred_plugin_id)

    def _sync_quick_access_buttons(self) -> None:
        current_row = self.quick_access_list.currentRow()
        count = self.quick_access_list.count()
        has_selection = current_row >= 0
        self.quick_access_add_button.setEnabled(self.quick_access_combo.count() > 0)
        self.quick_access_move_up_button.setEnabled(has_selection and current_row > 0)
        self.quick_access_move_down_button.setEnabled(has_selection and current_row >= 0 and current_row < count - 1)
        self.quick_access_open_button.setEnabled(has_selection)
        self.quick_access_remove_button.setEnabled(has_selection)
        self._apply_responsive_layout()

    def _persist_quick_access_from_settings_list(self, *_args) -> None:
        plugin_ids: list[str] = []
        selected_plugin_id = ""
        current_item = self.quick_access_list.currentItem()
        if current_item is not None:
            selected_plugin_id = str(current_item.data(Qt.ItemDataRole.UserRole) or "")
        for row in range(self.quick_access_list.count()):
            item = self.quick_access_list.item(row)
            if item is not None:
                plugin_ids.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
        self.services.set_quick_access_ids(plugin_ids)
        self._render_quick_access_settings(selected_plugin_id)

    def _add_selected_quick_access_plugin(self) -> None:
        plugin_id = str(self.quick_access_combo.currentData() or "").strip()
        if not plugin_id:
            return
        updated = self.services.quick_access_ids() + [plugin_id]
        self.services.set_quick_access_ids(updated)
        self._render_quick_access_settings(plugin_id)

    def _remove_selected_quick_access_plugin(self) -> None:
        item = self.quick_access_list.currentItem()
        if item is None:
            return
        plugin_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not plugin_id:
            return
        updated = [value for value in self.services.quick_access_ids() if value != plugin_id]
        self.services.set_quick_access_ids(updated)
        self._render_quick_access_settings()

    def _move_selected_quick_access(self, step: int) -> None:
        item = self.quick_access_list.currentItem()
        if item is None:
            return
        plugin_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        plugin_ids = self.services.quick_access_ids()
        if plugin_id not in plugin_ids:
            return
        current_index = plugin_ids.index(plugin_id)
        target_index = current_index + int(step)
        if target_index < 0 or target_index >= len(plugin_ids):
            return
        plugin_ids[current_index], plugin_ids[target_index] = plugin_ids[target_index], plugin_ids[current_index]
        self.services.set_quick_access_ids(plugin_ids)
        self._render_quick_access_settings(plugin_id)

    def _open_selected_quick_access_plugin(self) -> None:
        item = self.quick_access_list.currentItem()
        if item is None:
            return
        self._open_quick_access_plugin(str(item.data(Qt.ItemDataRole.UserRole) or ""))

    def _open_quick_access_plugin(self, plugin_id: str) -> None:
        if plugin_id and self.services.main_window is not None:
            self.services.main_window.open_plugin(plugin_id)

    def _quick_access_preview_icon(self, spec) -> QIcon:
        main_window = self.services.main_window
        icon_getter = getattr(main_window, "_plugin_icon", None)
        if callable(icon_getter):
            try:
                return icon_getter(spec)
            except Exception:
                pass
        override = self._sanitized_plugin_icon_override(spec)
        if override:
            icon = icon_from_name(override, self)
            if icon is not None:
                return icon
        preferred = icon_from_name(str(spec.preferred_icon or ""), self)
        if preferred is not None:
            return preferred
        fallback = icon_from_name("desktop", self) or icon_from_name("tools", self)
        if fallback is not None:
            return fallback
        return self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon)

    def _schedule_theme_preview(self) -> None:
        self._theme_preview_timer.start(120)

    def _schedule_language_preview(self) -> None:
        self._language_preview_timer.start(120)

    def _schedule_density_preview(self) -> None:
        self._density_preview_timer.start(1000)

    def _schedule_scaling_preview(self) -> None:
        self._scaling_preview_timer.start(1000)

    def _apply_pending_theme_preview(self) -> None:
        self.services.set_theme_selection(self._selected_theme_color(), self.dark_mode_checkbox.isChecked())

    def _apply_pending_language_preview(self) -> None:
        self.services.set_language(self._selected_language())

    def _apply_pending_density_preview(self) -> None:
        self.services.set_density_scale(int(self.density_slider.value()))

    def _apply_pending_scaling_preview(self) -> None:
        self.services.set_ui_scaling(self.scaling_slider.value() / 100.0)

    def _populate_shortcuts(self) -> None:
        bindings = self.services.shortcut_manager.list_bindings()
        self.shortcut_action_ids = [binding.action_id for binding in bindings]
        self.shortcut_table.setRowCount(len(bindings))
        self.shortcut_table.setHorizontalHeaderLabels(
            [
                self._pt("shortcuts.action", "Action"),
                self._pt("shortcuts.sequence", "Shortcut"),
                self._pt("shortcuts.scope", "Scope"),
            ]
        )
        scope_options = self.services.shortcut_manager.available_scopes()
        for row_index, binding in enumerate(bindings):
            title = self._pt(f"shortcut.action.{binding.action_id}", binding.title)
            title_item = QTableWidgetItem(title)
            title_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.shortcut_table.setItem(row_index, 0, title_item)
            self.shortcut_table.setItem(row_index, 1, QTableWidgetItem(binding.sequence or binding.default_sequence))

            combo = QComboBox()
            for scope_id, label in scope_options:
                combo.addItem(self._pt(f"shortcut.scope.{scope_id}", label), scope_id)
            self._set_combo_value(combo, binding.scope)
            self.shortcut_table.setCellWidget(row_index, 2, combo)
        self._refresh_shortcut_status()

    def _populate_plugin_table(self) -> None:
        self._building_plugin_table = True
        try:
            specs = self.services.manageable_plugin_specs(include_disabled=True)
            self.plugin_row_map = {}
            self.plugins_table.setRowCount(len(specs))
            self.plugins_table.setHorizontalHeaderLabels(
                [
                    "",
                    self._pt("plugins.icon", "Icon"),
                    self._pt("plugins.name", "Plugin"),
                    self._pt("plugins.category", "Category"),
                    self._pt("plugins.source", "Source"),
                    self._pt("plugins.trusted", "Trusted"),
                    self._pt("plugins.enabled", "Enabled"),
                    self._pt("plugins.hidden", "Hidden"),
                    self._pt("plugins.risk", "Risk"),
                    self._pt("plugins.status", "Status"),
                    self._pt("plugins.file", "File"),
                ]
            )
            language = self.services.i18n.current_language()
            for row_index, spec in enumerate(specs):
                self.plugin_row_map[spec.plugin_id] = row_index

                self.plugins_table.setCellWidget(row_index, 0, self._row_action_widget(spec, selected=False))
                self.plugins_table.removeCellWidget(row_index, 1)

                icon_item = QTableWidgetItem(self._icon_display_text(spec))
                icon_item.setIcon(self._icon_display_icon(spec) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
                icon_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 1, icon_item)

                name_item = QTableWidgetItem(self.services.plugin_display_name(spec))
                name_item.setData(Qt.ItemDataRole.UserRole, spec.plugin_id)
                name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 2, name_item)

                category_item = QTableWidgetItem(spec.localized_category(language) or self._pt("plugins.standalone", "Standalone"))
                category_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 3, category_item)

                source_item = QTableWidgetItem(self._pt(f"plugins.source.{spec.source_type.lower()}", spec.source_type.title()))
                source_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 4, source_item)

                trusted_item = QTableWidgetItem()
                trusted_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                if spec.source_type != "builtin":
                    trusted_item.setFlags(trusted_flags)
                else:
                    trusted_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                trusted_item.setCheckState(Qt.CheckState.Checked if spec.trusted else Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 5, trusted_item)

                enabled_item = QTableWidgetItem()
                enabled_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                hidden_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                enabled_item.setFlags(enabled_flags)
                enabled_item.setCheckState(Qt.CheckState.Checked if spec.enabled else Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 6, enabled_item)

                hidden_item = QTableWidgetItem()
                hidden_item.setFlags(hidden_flags)
                hidden_item.setCheckState(Qt.CheckState.Checked if spec.hidden else Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 7, hidden_item)

                risk_item = QTableWidgetItem(self._pt(f"plugins.risk.{spec.risk_level.lower()}", spec.risk_level.title()))
                risk_item.setToolTip(self._plugin_review_details(spec))
                risk_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self._style_risk_item(risk_item, spec.risk_level)
                self.plugins_table.setItem(row_index, 8, risk_item)

                status_text = self._plugin_status_text(spec)
                status_item = QTableWidgetItem(status_text)
                status_item.setToolTip(self._plugin_review_details(spec))
                status_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self._style_risk_item(status_item, spec.risk_level)
                self.plugins_table.setItem(row_index, 9, status_item)

                file_item = QTableWidgetItem(spec.file_path.name)
                file_item.setToolTip(str(spec.file_path))
                file_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 10, file_item)
        finally:
            self._building_plugin_table = False
        self.plugins_table.resizeColumnToContents(0)
        self.plugins_table.resizeColumnToContents(1)
        self._schedule_plugins_table_width_sync()

    def _make_action_button(self, icon_name: str, handler) -> QToolButton:
        button = QToolButton()
        button.setAutoRaise(False)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIcon(icon_from_name(icon_name, self) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        button.setIconSize(QSize(16, 16))
        button.setMinimumHeight(36)
        button.clicked.connect(handler)
        return button

    def _row_action_widget(self, spec, *, selected: bool) -> QWidget:
        container = QWidget()
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)

        export_check = QCheckBox()
        export_check.setStyleSheet("background: transparent;")
        export_check.setChecked(selected)
        export_check.setToolTip(self._pt("plugins.export", "Select for export"))
        layout.addWidget(export_check)
        return container

    def _sanitized_plugin_icon_override(self, spec) -> str:
        override = str(self.services.plugin_icon_override(spec) or "").strip()
        if not override:
            return ""
        if Path(override).exists():
            return override
        return override if icon_from_name(override, self) is not None else ""

    def _confirm_risky(self, title: str, body: str) -> bool:
        return confirm_action(
            self,
            title=title,
            body=body,
            confirm_text=self._pt("confirm.continue", "Continue"),
            cancel_text=self._pt("confirm.cancel", "Cancel"),
        )

    def _begin_row_edit(self, plugin_id: str) -> None:
        if self._editing_plugin_id and self._editing_plugin_id != plugin_id:
            self._cancel_row_edit(self._editing_plugin_id, repopulate=False)
        self._editing_plugin_id = plugin_id
        self._editing_snapshot = dict(self.services.plugin_override(plugin_id))
        self._set_row_editing(plugin_id, True)

    def _save_row_edit(self, plugin_id: str) -> None:
        spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
        row = self.plugin_row_map.get(plugin_id)
        if spec is None or row is None:
            return
        name_item = self.plugins_table.item(row, 2)
        name_override = ""
        if spec.allow_name_override and name_item is not None:
            typed_name = name_item.text().strip()
            if typed_name and typed_name != spec.localized_name(self.i18n.current_language()):
                name_override = typed_name

        icon_override = self._editing_snapshot.get("icon", "")
        if spec.allow_icon_override:
            icon_widget = self.plugins_table.cellWidget(row, 1)
            if isinstance(icon_widget, IconPickerButton):
                icon_override = icon_widget.selected_icon()

        self.services.set_plugin_override(plugin_id, display_name=name_override, icon=icon_override)
        self._editing_plugin_id = None
        self._editing_snapshot = {}
        self._populate_plugin_table()

    def _cancel_row_edit(self, plugin_id: str, *, repopulate: bool = True) -> None:
        self._editing_plugin_id = None
        self._editing_snapshot = {}
        if repopulate:
            self._populate_plugin_table()

    def _set_row_editing(self, plugin_id: str, editing: bool) -> None:
        row = self.plugin_row_map.get(plugin_id)
        spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
        if row is None or spec is None:
            return

        selected = self._is_row_selected_for_export(row)
        self.plugins_table.setCellWidget(row, 0, self._row_action_widget(spec, selected=selected))

        name_item = self.plugins_table.item(row, 2)
        if name_item is not None:
            flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            if editing and spec.allow_name_override:
                flags |= Qt.ItemFlag.ItemIsEditable
                if not name_item.text().strip():
                    name_item.setText(spec.localized_name(self.i18n.current_language()))
            name_item.setFlags(flags)

        if editing and spec.allow_icon_override:
            picker = IconPickerButton(self, self._editing_snapshot.get("icon", ""))
            self.plugins_table.setCellWidget(row, 1, picker)
        else:
            self.plugins_table.removeCellWidget(row, 1)
            icon_item = self.plugins_table.item(row, 1)
            if icon_item is not None:
                icon_item.setText(self._icon_display_text(spec))
                icon_item.setIcon(self._icon_display_icon(spec) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.plugins_table.resizeColumnToContents(0)
        self.plugins_table.resizeColumnToContents(1)

    def _is_row_selected_for_export(self, row: int) -> bool:
        widget = self.plugins_table.cellWidget(row, 0)
        if widget is None:
            return False
        checkbox = widget.findChild(QCheckBox)
        return bool(checkbox is not None and checkbox.isChecked())

    def _icon_display_text(self, spec) -> str:
        override = self._sanitized_plugin_icon_override(spec)
        return self._icon_display_name(override)

    def _icon_display_name(self, icon_value: str) -> str:
        if not icon_value:
            return ""
        options = {icon_id: label for icon_id, label, _icon in self._icon_options()}
        return options.get(icon_value, Path(icon_value).name or icon_value)

    def _icon_display_icon(self, spec):
        override = self._sanitized_plugin_icon_override(spec)
        effective = override or str(spec.preferred_icon or "").strip()
        return icon_from_name(effective, self) if effective else icon_from_name("plugin", self)

    def _plugin_spec_for_row(self, row: int):
        if row < 0:
            return None
        name_item = self.plugins_table.item(row, 2)
        if name_item is None:
            return None
        plugin_id = str(name_item.data(Qt.ItemDataRole.UserRole) or "")
        if not plugin_id:
            return None
        return self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)

    def _toggle_plugin_row_check(self, row: int, column: int) -> None:
        item = self.plugins_table.item(row, column)
        if item is None:
            return
        current = item.checkState() == Qt.CheckState.Checked
        item.setCheckState(Qt.CheckState.Unchecked if current else Qt.CheckState.Checked)

    def _show_plugins_context_menu(self, position) -> None:
        index = self.plugins_table.indexAt(position)
        if not index.isValid():
            return
        row = index.row()
        self.plugins_table.selectRow(row)
        spec = self._plugin_spec_for_row(row)
        if spec is None:
            return

        menu = QMenu(self)
        if spec.allow_name_override:
            rename_action = menu.addAction(self._pt("plugins.menu.rename", "Change name..."))
            rename_action.triggered.connect(lambda _checked=False, plugin_id=spec.plugin_id: self._change_plugin_name(plugin_id))
        if spec.allow_icon_override:
            icon_action = menu.addAction(self._pt("plugins.menu.icon", "Change icon..."))
            icon_action.triggered.connect(lambda _checked=False, plugin_id=spec.plugin_id: self._change_plugin_icon(plugin_id))
        reset_visuals = menu.addAction(self._pt("plugins.menu.reset_visuals", "Reset name and icon"))
        reset_visuals.triggered.connect(lambda _checked=False, plugin_id=spec.plugin_id: self._reset_plugin_visuals(plugin_id))

        menu.addSeparator()
        enabled_action = menu.addAction(self._pt("plugins.menu.toggle_enabled", "Toggle enabled"))
        enabled_action.triggered.connect(lambda _checked=False, current_row=row: self._toggle_plugin_row_check(current_row, 6))
        hidden_action = menu.addAction(self._pt("plugins.menu.toggle_hidden", "Toggle hidden"))
        hidden_action.triggered.connect(lambda _checked=False, current_row=row: self._toggle_plugin_row_check(current_row, 7))
        if spec.source_type != "builtin":
            trusted_action = menu.addAction(self._pt("plugins.menu.toggle_trusted", "Toggle trusted"))
            trusted_action.triggered.connect(lambda _checked=False, current_row=row: self._toggle_plugin_row_check(current_row, 5))

        details = self._plugin_review_details(spec)
        if details:
            menu.addSeparator()
            review_action = menu.addAction(self._pt("plugins.menu.review", "Review details"))
            review_action.triggered.connect(
                lambda _checked=False, text=details, title=self.services.plugin_display_name(spec): QMessageBox.information(self, title, text)
            )
        menu.exec(self.plugins_table.viewport().mapToGlobal(position))

    def _change_plugin_name(self, plugin_id: str) -> None:
        spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
        if spec is None:
            return
        current_override = self.services.plugin_override(plugin_id).get("display_name", "")
        current_text = current_override or self.services.plugin_display_name(spec)
        value, accepted = QInputDialog.getText(
            self,
            self._pt("plugins.rename.title", "Change display name"),
            self._pt("plugins.rename.prompt", "Display name"),
            text=current_text,
        )
        if not accepted:
            return
        override = value.strip()
        if override == spec.localized_name(self.i18n.current_language()):
            override = ""
        current_icon = self._sanitized_plugin_icon_override(spec)
        self.services.set_plugin_override(plugin_id, display_name=override, icon=current_icon)
        self._populate_plugin_table()
        self._render_quick_access_settings(plugin_id)

    def _change_plugin_icon(self, plugin_id: str) -> None:
        spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
        if spec is None:
            return
        dialog = IconPickerDialog(self, self._icon_options(), self._sanitized_plugin_icon_override(spec))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        current_name = self.services.plugin_override(plugin_id).get("display_name", "")
        self.services.set_plugin_override(plugin_id, display_name=current_name, icon=dialog.selected_icon())
        self._populate_plugin_table()
        self._render_quick_access_settings(plugin_id)

    def _reset_plugin_visuals(self, plugin_id: str) -> None:
        self.services.set_plugin_override(plugin_id, display_name="", icon="")
        self._populate_plugin_table()
        self._render_quick_access_settings(plugin_id)

    def _browse_output_dir(self) -> None:
        current = self.output_dir_input.text().strip() or str(self.services.default_output_path())
        selected = QFileDialog.getExistingDirectory(self, self._pt("output.browse", "Choose output folder"), current)
        if selected:
            self.output_dir_input.setText(selected)

    def _startup_page_specs(self):
        specs = []
        for spec in self.services.plugin_manager.sidebar_plugins():
            if spec.plugin_id == INSPECTOR_PLUGIN_ID:
                continue
            specs.append(spec)
        return specs

    def _populate_startup_page_combo(self, preferred_plugin_id: str | None = None) -> None:
        if not hasattr(self, "startup_page_combo"):
            return
        selected_plugin_id = preferred_plugin_id
        if selected_plugin_id is None:
            selected_plugin_id = str(self.startup_page_combo.currentData() or self.services.config.get("default_start_plugin") or DASHBOARD_PLUGIN_ID)

        self.startup_page_combo.blockSignals(True)
        self.startup_page_combo.clear()
        for spec in self._startup_page_specs():
            self.startup_page_combo.addItem(self.services.plugin_display_name(spec), spec.plugin_id)
        self.startup_page_combo.blockSignals(False)
        self._set_combo_value(self.startup_page_combo, selected_plugin_id)

    def _save_general_settings(self) -> None:
        window = self.services.main_window
        if window is not None:
            window.begin_loading(self._pt("loading.saving", "Saving settings..."))
        try:
            output_dir = Path(self.output_dir_input.text().strip() or self.services.output_root)
            output_dir.mkdir(parents=True, exist_ok=True)
            self._theme_preview_timer.stop()
            self._language_preview_timer.stop()
            self._density_preview_timer.stop()
            self._scaling_preview_timer.stop()

            self.services.config.update_many(
                {
                    "material_theme": self.services.theme_manager.current_theme(),
                    "material_color": self.services.theme_manager.current_color_key(),
                    "material_dark": self.services.theme_manager.is_dark_mode(),
                    "appearance_mode": self.services.theme_manager.current_mode(),
                    "density_scale": self.services.theme_manager.current_density_scale(),
                    "ui_scaling": self.services.theme_manager.current_ui_scaling(),
                    "language": self.services.i18n.current_language(),
                    "backup_schedule": self.backup_schedule_combo.currentData() or "monthly",
                    "default_output_path": str(output_dir),
                    "default_start_plugin": str(self.startup_page_combo.currentData() or DASHBOARD_PLUGIN_ID),
                    "minimize_to_tray": self.minimize_to_tray_checkbox.isChecked(),
                    "close_to_tray": self.close_to_tray_checkbox.isChecked(),
                    "confirm_on_exit": self.confirm_on_exit_checkbox.isChecked(),
                    "run_on_startup": self.run_on_startup_checkbox.isChecked(),
                    "start_minimized": self.start_minimized_checkbox.isChecked(),
                }
            )
            if self.services.developer_mode_enabled() != self.developer_mode_checkbox.isChecked() or bool(self.services.config.get("developer_mode")) != self.developer_mode_checkbox.isChecked():
                self.services.set_developer_mode(self.developer_mode_checkbox.isChecked())

            self.services.autostart_manager.set_enabled(
                self.run_on_startup_checkbox.isChecked(),
                start_minimized=self.start_minimized_checkbox.isChecked(),
            )
            self.services.tray_manager.sync_visibility()
            self._refresh_autostart_status()
            self._refresh_backup_status()
        finally:
            if window is not None:
                window.end_loading()
        QMessageBox.information(self, self._pt("saved.title", "Settings saved"), self._pt("saved.body", "Your application settings were updated."))

    def _reset_general_defaults(self) -> None:
        if not self._confirm_risky(
            self._pt("confirm.reset_general.title", "Reset general settings?"),
            self._pt("confirm.reset_general.body", "This will reset appearance, language preview, tray behavior, startup behavior, and backup settings in this tab back to their defaults."),
        ):
            return
        defaults = DEFAULT_CONFIG
        self._suspend_live_updates = True
        self.output_dir_input.setText(str(self.services.output_root))
        target_color = str(defaults.get("material_color") or "pink")
        for color_key, button in self.theme_color_buttons.items():
            button.setChecked(color_key == target_color)
        self.dark_mode_checkbox.setChecked(bool(defaults.get("material_dark")))
        target_language = str(defaults.get("language") or "en")
        for code, button in self.language_buttons.items():
            button.setChecked(code == target_language)
        self.density_slider.setValue(int(defaults.get("density_scale") or 0))
        self.scaling_slider.setValue(int(round(float(defaults.get("ui_scaling") or 1.0) * 100)))
        self.minimize_to_tray_checkbox.setChecked(bool(defaults.get("minimize_to_tray")))
        self.close_to_tray_checkbox.setChecked(bool(defaults.get("close_to_tray")))
        self.confirm_on_exit_checkbox.setChecked(bool(defaults.get("confirm_on_exit")))
        self.run_on_startup_checkbox.setChecked(bool(defaults.get("run_on_startup")))
        self.start_minimized_checkbox.setChecked(bool(defaults.get("start_minimized")))
        self.developer_mode_checkbox.setChecked(bool(defaults.get("developer_mode")))
        self._set_combo_value(self.backup_schedule_combo, defaults.get("backup_schedule", "monthly"))
        self._populate_startup_page_combo(str(defaults.get("default_start_plugin") or DASHBOARD_PLUGIN_ID))
        self._suspend_live_updates = False
        self.density_value_label.setText(str(self.density_slider.value()))
        self.scaling_value_label.setText(f"{self.scaling_slider.value()}%")
        self._apply_pending_language_preview()
        self._apply_pending_theme_preview()
        self._apply_pending_density_preview()
        self._apply_pending_scaling_preview()

    def _save_shortcuts(self) -> None:
        window = self.services.main_window
        if window is not None:
            window.begin_loading(self._pt("loading.saving_shortcuts", "Saving shortcuts..."))
        try:
            shortcut_updates: dict[str, dict[str, str]] = {}
            for row_index, action_id in enumerate(self.shortcut_action_ids):
                sequence_item = self.shortcut_table.item(row_index, 1)
                combo = self.shortcut_table.cellWidget(row_index, 2)
                shortcut_updates[action_id] = {
                    "sequence": sequence_item.text().strip() if sequence_item is not None else "",
                    "scope": combo.currentData() if combo is not None else "application",
                }
            self.services.shortcut_manager.update_bindings(shortcut_updates)
            self._refresh_shortcut_status()
        finally:
            if window is not None:
                window.end_loading()
        QMessageBox.information(self, self._pt("shortcuts.saved.title", "Shortcuts saved"), self._pt("shortcuts.saved.body", "Shortcut changes were saved."))

    def _reset_shortcut_defaults(self) -> None:
        if not self._confirm_risky(
            self._pt("confirm.reset_shortcuts.title", "Reset shortcuts?"),
            self._pt("confirm.reset_shortcuts.body", "This will replace the current shortcut edits in this tab with the default shortcut bindings."),
        ):
            return
        bindings = self.services.shortcut_manager.list_bindings()
        scope_options = self.services.shortcut_manager.available_scopes()
        for row_index, binding in enumerate(bindings):
            self.shortcut_table.setItem(row_index, 1, QTableWidgetItem(binding.default_sequence))
            combo = self.shortcut_table.cellWidget(row_index, 2)
            if isinstance(combo, QComboBox):
                combo.clear()
                for scope_id, label in scope_options:
                    combo.addItem(label, scope_id)
                self._set_combo_value(combo, binding.default_scope)

    def _reset_plugin_defaults(self) -> None:
        if not self._confirm_risky(
            self._pt("confirm.reset_plugins.title", "Reset plugin defaults?"),
            self._pt("confirm.reset_plugins.body", "This will reset plugin overrides and plugin state entries back to their defaults. A safety backup will be attempted first."),
        ):
            return
        if not self._create_safety_backup("plugin_reset"):
            return
        self.services.config.set("plugin_overrides", {})
        specs = self.services.manageable_plugin_specs(include_disabled=True)
        for spec in specs:
            self.services.plugin_state_manager.reset(spec.plugin_id)
            if spec.source_type == "custom":
                self.services.plugin_state_manager.set_enabled(spec.plugin_id, False)
                self.services.plugin_state_manager.set_hidden(spec.plugin_id, False)
                self.services.plugin_state_manager.set_trusted(spec.plugin_id, False)
                self.services.plugin_state_manager.set_scan_report(
                    spec.plugin_id,
                    {
                        "risk_level": spec.risk_level,
                        "summary": spec.risk_summary,
                    },
                )
        self.services.reload_plugins()
        QMessageBox.information(self, self._pt("plugins.reset.title", "Plugins reset"), self._pt("plugins.reset.body", "Plugin overrides and states were reset to their defaults."))

    def _create_backup_now(self) -> None:
        window = self.services.main_window
        if window is not None:
            window.begin_loading(self._pt("loading.backup", "Creating encrypted backup..."))
        try:
            backup_path = self.services.create_backup(reason="manual")
        except Exception as exc:
            if window is not None:
                window.end_loading()
            QMessageBox.critical(self, self._pt("backup.failed.title", "Backup failed"), str(exc))
            return
        if window is not None:
            window.end_loading()
        self._refresh_backup_status()
        QMessageBox.information(self, self._pt("backup.created.title", "Backup created"), self._pt("backup.created.body", "Encrypted backup written to {path}", path=str(backup_path)))

    def _restore_backup_from_file(self) -> None:
        start_dir = self.services.backup_manager.backups_root
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._pt("backup.restore_dialog", "Restore encrypted backup"),
            str(start_dir),
            "Micro Toolkit Backup (*.mtkbak)",
        )
        if not file_path:
            return
        confirmed = confirm_action(
            self,
            title=self._pt("backup.restore_confirm.title", "Restore backup"),
            body=self._pt("backup.restore_confirm.body", "This will overwrite app data and may replace bundled files. Continue?"),
            confirm_text=self._pt("backup.restore", "Restore backup"),
            cancel_text=self._pt("confirm.cancel", "Cancel"),
        )
        if not confirmed:
            return
        window = self.services.main_window
        if window is not None:
            window.begin_loading(self._pt("loading.restore", "Restoring backup..."))
        try:
            self.services.restore_backup(Path(file_path))
        except Exception as exc:
            if window is not None:
                window.end_loading()
            QMessageBox.critical(self, self._pt("backup.failed.title", "Backup failed"), str(exc))
            return
        if window is not None:
            window.end_loading()
        self._refresh_backup_status()
        QMessageBox.information(self, self._pt("backup.restored.title", "Backup restored"), self._pt("backup.restored.body", "The backup was restored. Restart Micro Toolkit to ensure every file is reloaded cleanly."))

    def _create_safety_backup(self, reason: str) -> bool:
        try:
            self.services.create_backup(reason=reason)
            self._refresh_backup_status()
            return True
        except Exception as exc:
            return confirm_action(
                self,
                title=self._pt("backup.safety_failed.title", "Backup unavailable"),
                body=self._pt("backup.safety_failed.body", "A safety backup could not be created before this reset:\n\n{error}\n\nContinue anyway?", error=str(exc)),
                confirm_text=self._pt("confirm.continue", "Continue"),
                cancel_text=self._pt("confirm.cancel", "Cancel"),
            )

    def _refresh_backup_status(self) -> None:
        backups = self.services.backup_manager.list_backups()
        latest_raw = backups[0]["modified_at"] if backups else ""
        
        if latest_raw:
            # Wrap date in RTL marker if we are in an RTL layout to prevent flip issues with hyphens/colons
            latest = f"\u200f{latest_raw}" if self.services.i18n.is_rtl() else latest_raw
        else:
            latest = self._pt("backup.none", "No backups yet")
            
        schedule_key = str(self.backup_schedule_combo.currentData() or self.services.backup_manager.schedule()).lower()
        schedule_text = self._pt(f"backup.schedule.{schedule_key}", schedule_key.title())
        
        self.backup_status_label.setText(
            self._pt(
                "backup.status",
                "Schedule: {schedule}. Last backup: {latest}.",
                schedule=schedule_text,
                latest=latest,
            )
        )

    def _refresh_shortcut_status(self) -> None:
        shortcut_manager = self.services.shortcut_manager
        helper_manager = self.services.hotkey_helper_manager
        if shortcut_manager.direct_global_hotkeys_supported():
            self.shortcut_status_label.setText(
                self._pt(
                    "shortcuts.status.available",
                    "Global shortcut registration is available in this session.",
                )
            )
            self.start_helper_button.setVisible(False)
            self.stop_helper_button.setVisible(False)
            return

        if helper_manager.is_active():
            self.shortcut_status_label.setText(
                self._pt(
                    "shortcuts.status.helper_active",
                    "The elevated hotkey helper is active for this session. Global shortcuts will be routed through the helper process.",
                )
            )
            self.start_helper_button.setVisible(False)
            self.stop_helper_button.setVisible(True)
            self.stop_helper_button.setText(self._pt("shortcuts.stop_helper", "Stop Hotkey Helper"))
            return

        reason = helper_manager.helper_reason() or self._pt(
            "shortcuts.status.unavailable",
            "Global shortcuts are unavailable in this session.",
        )
        if helper_manager.can_request_helper():
            self.shortcut_status_label.setText(
                self._pt(
                    "shortcuts.status.helper_available",
                    "Global shortcuts are currently unavailable. {reason} Start the hotkey helper if you want global capture without elevating the main app.",
                    reason=reason,
                )
            )
            self.start_helper_button.setVisible(True)
            self.start_helper_button.setText(self._pt("shortcuts.start_helper", "Start Hotkey Helper"))
            self.stop_helper_button.setVisible(False)
            return

        self.shortcut_status_label.setText(
            self._pt(
                "shortcuts.status.no_helper",
                "Global shortcuts are currently unavailable. {reason}",
                reason=reason,
            )
        )
        self.start_helper_button.setVisible(False)
        self.stop_helper_button.setVisible(False)

    def _start_hotkey_helper(self) -> None:
        try:
            result = self.services.command_registry.execute("app.start_hotkey_helper")
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._pt("shortcuts.helper_failed.title", "Helper unavailable"),
                str(exc),
            )
            return
        QMessageBox.information(
            self,
            self._pt("shortcuts.helper_started.title", "Helper started"),
            str(result.get("message", self._pt("shortcuts.helper_started.body", "The hotkey helper is now active for this session."))),
        )
        self._refresh_shortcut_status()

    def _stop_hotkey_helper(self) -> None:
        self.services.command_registry.execute("app.stop_hotkey_helper")
        self._refresh_shortcut_status()

    def _icon_options(self) -> list[tuple[str, str, object]]:
        rows: list[tuple[str, str, object]] = []
        for icon_id, fallback_label, icon in icon_choices(self):
            label = self._pt(f"plugins.icon.{icon_id.replace('-', '_')}", fallback_label)
            rows.append((icon_id, label, icon))
        return rows

    def _plugin_status_text(self, spec) -> str:
        if spec.quarantined:
            return self._pt("plugins.status.quarantined", "Quarantined")
        if spec.source_type == "custom" and not spec.trusted:
            return self._pt("plugins.status.review", "Pending Review")
        if not spec.enabled:
            return self._pt("plugins.status.disabled", "Disabled")
        if spec.last_error:
            return self._pt("plugins.status.error", "Error Recorded")
        return self._pt("plugins.status.ready", "Ready")

    def _plugin_review_details(self, spec) -> str:
        details: list[str] = []
        if spec.risk_summary:
            details.append(spec.risk_summary)
        if spec.last_error:
            details.append(self._pt("plugins.error_detail", "Last error: {error}", error=spec.last_error))
        if spec.failure_count:
            details.append(
                self._pt(
                    "plugins.failure_detail",
                    "Failure count: {count}",
                    count=str(spec.failure_count),
                )
            )
        return "\n".join(details)

    def _style_risk_item(self, item: QTableWidgetItem, risk_level: str) -> None:
        normalized = (risk_level or "low").lower()
        if normalized in {"high", "critical"}:
            item.setForeground(QColor("#c62828"))
        elif normalized == "medium":
            item.setForeground(QColor("#b26a00"))
        else:
            item.setForeground(QColor("#1b5e20"))

    def _apply_plugin_states(self) -> None:
        if not self._confirm_risky(
            self._pt("confirm.apply_plugins.title", "Apply plugin changes?"),
            self._pt("confirm.apply_plugins.body", "This will apply trust, enable, and hidden-state changes for the listed plugins."),
        ):
            return
        specs = self.services.manageable_plugin_specs(include_disabled=True)
        pending_risk_review: list[str] = []
        forced_block: list[str] = []
        updates: list[tuple[str, str, bool, bool, bool, bool]] = []
        language = self.services.i18n.current_language()
        for spec in specs:
            row_index = self.plugin_row_map.get(spec.plugin_id)
            if row_index is None:
                continue
            trusted_item = self.plugins_table.item(row_index, 5)
            enabled_item = self.plugins_table.item(row_index, 6)
            hidden_item = self.plugins_table.item(row_index, 7)
            trusted = trusted_item.checkState() == Qt.CheckState.Checked if trusted_item is not None else spec.trusted
            enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item is not None else True
            hidden = hidden_item.checkState() == Qt.CheckState.Checked if hidden_item is not None else False
            if spec.source_type == "builtin":
                trusted = True
            if spec.source_type == "custom" and spec.risk_level == "critical":
                trusted = False
                enabled = False
                forced_block.append(spec.localized_name(language))
            elif spec.source_type == "custom" and trusted and not spec.trusted and spec.risk_level in {"medium", "high"}:
                pending_risk_review.append(spec.localized_name(language))
            if spec.source_type == "custom" and not trusted:
                enabled = False
            updates.append((spec.plugin_id, spec.source_type, trusted, enabled, hidden, spec.risk_level == "critical"))

        if pending_risk_review:
            confirmed = confirm_action(
                self,
                title=self._pt("plugins.review_prompt.title", "Trust custom plugins?"),
                body=self._pt(
                    "plugins.review_prompt.body",
                    "The following custom plugins contain medium or high risk markers from the static safety scan:\n\n{plugins}\n\nTrusting them will allow the app to import and run their code. Only continue if you trust the author and reviewed the plugin contents.",
                    plugins="\n".join(f"- {name}" for name in pending_risk_review),
                ),
                confirm_text=self._pt("plugins.review_prompt.confirm", "Trust and apply"),
                cancel_text=self._pt("confirm.cancel", "Cancel"),
            )
            if not confirmed:
                for index, (plugin_id, source_type, trusted, enabled, hidden, force_quarantine) in enumerate(updates):
                    if source_type == "custom" and trusted:
                        updates[index] = (plugin_id, source_type, False, False, hidden, force_quarantine)

        for plugin_id, source_type, trusted, enabled, hidden, force_quarantine in updates:
            if force_quarantine:
                self.services.plugin_state_manager.quarantine(
                    plugin_id,
                    self._pt(
                        "plugins.blocked.reason",
                        "The static safety scan detected critical-risk patterns. This plugin remains quarantined until removed or replaced.",
                    ),
                )
                self.services.plugin_state_manager.set_hidden(plugin_id, hidden)
                continue
            self.services.plugin_state_manager.set_trusted(plugin_id, trusted)
            self.services.plugin_state_manager.set_enabled(plugin_id, enabled)
            self.services.plugin_state_manager.set_hidden(plugin_id, hidden)

        if forced_block:
            QMessageBox.warning(
                self,
                self._pt("plugins.blocked.title", "Plugins blocked"),
                self._pt(
                    "plugins.blocked.body",
                    "These custom plugins remain blocked because the static scan detected critical-risk patterns:\n\n{plugins}",
                    plugins="\n".join(f"- {name}" for name in forced_block),
                ),
            )
        QMessageBox.information(
            self,
            self._pt("plugins.applied.title", "Plugin settings updated"),
            self._pt("plugins.applied.body", "Plugin trust, visibility, and enabled state were updated."),
        )
        self.services.reload_plugins()

    def _import_plugin_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._pt("plugins.import_file", "Import plugin file"),
            str(Path.home()),
            "Python Files (*.py)",
        )
        if not file_path:
            return
        try:
            plugin_ids = self.services.plugin_package_manager.import_plugin_file(Path(file_path))
        except Exception as exc:
            QMessageBox.critical(self, self._pt("plugins.import_failed.title", "Import failed"), str(exc))
            return
        QMessageBox.information(
            self,
            self._pt("plugins.imported.title", "Plugin imported"),
            self._pt("plugins.imported.body", "Imported plugins: {plugins}. They were added disabled and untrusted pending review.", plugins=", ".join(plugin_ids)),
        )
        self.services.reload_plugins()

    def _import_plugin_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(self, self._pt("plugins.import_folder", "Import plugin folder"), str(Path.home()))
        if not folder_path:
            return
        try:
            plugin_ids = self.services.plugin_package_manager.import_plugin_folder(Path(folder_path))
        except Exception as exc:
            QMessageBox.critical(self, self._pt("plugins.import_failed.title", "Import failed"), str(exc))
            return
        QMessageBox.information(
            self,
            self._pt("plugins.imported.title", "Plugin imported"),
            self._pt("plugins.imported.body", "Imported plugins: {plugins}. They were added disabled and untrusted pending review.", plugins=", ".join(plugin_ids)),
        )
        self.services.reload_plugins()

    def _import_backup(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._pt("plugins.import_backup", "Import plugin backup"),
            str(Path.home()),
            "Plugin Backup (*.zip)",
        )
        if not file_path:
            return
        try:
            plugin_ids = self.services.plugin_package_manager.import_backup(Path(file_path))
        except Exception as exc:
            QMessageBox.critical(self, self._pt("plugins.import_failed.title", "Import failed"), str(exc))
            return
        QMessageBox.information(
            self,
            self._pt("plugins.imported.title", "Plugin imported"),
            self._pt("plugins.imported.body", "Imported plugins: {plugins}. They were added disabled and untrusted pending review.", plugins=", ".join(plugin_ids)),
        )
        self.services.reload_plugins()

    def _export_selected_plugins(self) -> None:
        specs = self._selected_export_specs()
        if not specs:
            QMessageBox.warning(self, self._pt("plugins.export_failed.title", "Nothing selected"), self._pt("plugins.export_failed.body", "Select at least one plugin to export."))
            return
        self._export_specs(specs)

    def _export_all_plugins(self) -> None:
        specs = self.services.manageable_plugin_specs(include_disabled=True)
        self._export_specs(specs)

    def _export_specs(self, specs) -> None:
        suggested = Path.home() / "micro_toolkit_plugins_backup.zip"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self._pt("plugins.export_dialog", "Export plugin backup"),
            str(suggested),
            "Plugin Backup (*.zip)",
        )
        if not file_path:
            return
        destination = Path(file_path)
        if destination.suffix.lower() != ".zip":
            destination = destination.with_suffix(".zip")
        try:
            exported = self.services.plugin_package_manager.export_plugins(specs, destination)
        except Exception as exc:
            QMessageBox.critical(self, self._pt("plugins.export_failed.title", "Export failed"), str(exc))
            return
        QMessageBox.information(
            self,
            self._pt("plugins.exported.title", "Plugins exported"),
            self._pt("plugins.exported.body", "Plugin backup written to {path}", path=str(exported)),
        )

    def _selected_export_specs(self):
        specs_by_id = {
            spec.plugin_id: spec
            for spec in self.services.manageable_plugin_specs(include_disabled=True)
        }
        selected = []
        for row_index in range(self.plugins_table.rowCount()):
            name_item = self.plugins_table.item(row_index, 2)
            if name_item is None:
                continue
            if not self._is_row_selected_for_export(row_index):
                continue
            plugin_id = name_item.data(Qt.ItemDataRole.UserRole)
            spec = specs_by_id.get(plugin_id)
            if spec is not None:
                selected.append(spec)
        return selected

    def _refresh_autostart_status(self) -> None:
        enabled = self.services.autostart_manager.is_enabled()
        key = "startup.enabled" if enabled else "startup.disabled"
        self.autostart_status_label.setText(self._pt(key, "Autostart is disabled."))

    def _apply_texts(self) -> None:
        palette = self.services.theme_manager.current_palette()
        self._apply_theme_styles()
        self.title_label.setText(self._pt("title", "Settings"))
        self.description_label.setText(
            self._pt(
                "description",
                "Control appearance, language, startup behavior, tray behavior, shortcuts, and plugin management from one place.",
            )
        )
        self.description_label.setStyleSheet(f"font-size: 14px; color: {palette.text_muted};")
        self.tabs.setTabText(0, self._pt("tab.general", "General"))
        self.tabs.setTabText(1, self._pt("tab.quick_access", "Quick Access"))
        self.tabs.setTabText(2, self._pt("tab.shortcuts", "Shortcuts"))
        self.tabs.setTabText(3, self._pt("tab.plugins", "Plugins"))

        self.output_label.setText(self._pt("output.label", "Default output folder"))
        self.startup_page_label.setText(self._pt("output.startup_page", "Default startup page"))
        self.output_browse_button.setText(self._pt("output.browse_button", "Browse"))
        self.output_title.setText(self._pt("general.output.title", "Workspace"))
        self.general_note.setText(self._pt("output.note", "Tools export into this folder by default, and the app can open straight to your preferred page on launch."))
        self._populate_startup_page_combo()

        self.appearance_title.setText(self._pt("general.appearance.title", "Appearance"))
        self.theme_label.setText(self._pt("theme.label", "Theme"))
        color_labels = {
            "pink": self._pt("theme.color.pink", "Pink"),
            "blue": self._pt("theme.color.blue", "Blue"),
            "orange": self._pt("theme.color.orange", "Orange"),
            "green": self._pt("theme.color.green", "Green"),
            "red": self._pt("theme.color.red", "Red"),
        }
        for color_key, button in self.theme_color_buttons.items():
            button.setToolTip(color_labels.get(color_key, color_key.title()))
        self.dark_mode_checkbox.setText(self._pt("theme.dark_mode", "Dark mode"))
        self.language_label.setText(self._pt("language.label", "Language"))
        self.density_label.setText(self._pt("density.label", "Density"))
        self.scaling_label.setText(self._pt("scaling.label", "UI scaling"))
        for code, button in self.language_buttons.items():
            for language_code, label in self.i18n.available_languages():
                if code == language_code:
                    button.setText(label)
                    break
        self.appearance_note.setText(
            self._pt("appearance.note", "Appearance and language preview live in the app, but they are only written to the config when you click Save settings.")
        )

        self.behavior_title.setText(self._pt("general.behavior.title", "Behavior"))
        self.behavior_note.setText(
            self._pt(
                "general.behavior.note",
                "Tray handling, startup behavior, exit confirmation, and developer mode live together here so the app shell is easier to reason about.",
            )
        )
        self.minimize_to_tray_checkbox.setText(self._pt("tray.minimize", "Minimize to system tray"))
        self.close_to_tray_checkbox.setText(self._pt("tray.close", "Close to system tray"))
        self.confirm_on_exit_checkbox.setText(self._pt("exit.confirm", "Always ask on exit"))
        self.run_on_startup_checkbox.setText(self._pt("startup.run", "Start on system login"))
        self.start_minimized_checkbox.setText(self._pt("startup.minimized", "Start minimized"))
        self.developer_mode_checkbox.setText(self._pt("developer.mode", "Developer mode"))
        self.backup_title.setText(self._pt("general.backup.title", "Backups"))
        self.backup_note.setText(
            self._pt(
                "general.backup.note",
                "Keep an encrypted safety trail of your workspace state, then restore from here when you need to roll back quickly.",
            )
        )
        self.backup_schedule_label.setText(self._pt("backup.schedule", "Backup intensity"))
        for index in range(self.backup_schedule_combo.count()):
            value = str(self.backup_schedule_combo.itemData(index) or "")
            text = {
                "daily": self._pt("backup.schedule.daily", "Daily"),
                "weekly": self._pt("backup.schedule.weekly", "Weekly"),
                "monthly": self._pt("backup.schedule.monthly", "Monthly"),
            }.get(value, value.title())
            self.backup_schedule_combo.setItemText(index, text)
        self.create_backup_button.setText(self._pt("backup.create", "Create backup"))
        self.restore_backup_button.setText(self._pt("backup.restore", "Restore backup"))
        self.quick_access_tab_note.setText(
            self._pt(
                "quick_access.tab_note",
                "Build a desktop-style quick launch strip for your most-used tools. Add tools, reorder them, and test the launcher here.",
            )
        )
        self.quick_access_title.setText(self._pt("quick_access.title", "Quick access"))
        self.quick_access_note.setText(
            self._pt(
                "quick_access.note",
                "These icons mirror the dashboard launcher. Drag the list to reorder, or use the move buttons for precise placement.",
            )
        )
        self.quick_access_add_button.setText(self._pt("quick_access.add", "Add"))
        self.quick_access_move_up_button.setText(self._pt("quick_access.move_up", "Move up"))
        self.quick_access_move_down_button.setText(self._pt("quick_access.move_down", "Move down"))
        self.quick_access_open_button.setText(self._pt("quick_access.open", "Open"))
        self.quick_access_remove_button.setText(self._pt("quick_access.remove", "Remove"))

        self.shortcut_note.setText(
            self._pt(
                "shortcuts.note",
                "Application shortcuts are always available while the app is focused. Global shortcuts are optional and may depend on desktop permissions.",
            )
        )
        self.plugins_note.setText(
            self._pt(
                "plugins.note",
                "Manage built-in and custom plugins here. Use the checkboxes for trust, enabled, and hidden state, then right-click a row for name, icon, and review actions.",
            )
        )
        self.import_file_button.setText(self._pt("plugins.import_file_button", "Import File"))
        self.import_folder_button.setText(self._pt("plugins.import_folder_button", "Import Folder"))
        self.import_backup_button.setText(self._pt("plugins.import_backup_button", "Import Backup"))
        self.export_selected_button.setText(self._pt("plugins.export_selected", "Export Selected"))
        self.export_all_button.setText(self._pt("plugins.export_all", "Export All"))
        self.apply_plugin_state_button.setText(self._pt("plugins.apply", "Apply Plugin Changes"))
        self.reset_plugins_button.setText(self._pt("plugins.reset", "Reset plugin defaults"))
        self.refresh_plugins_button.setText(self._pt("plugins.refresh", "Refresh"))
        self.import_file_button.setToolTip(self.import_file_button.text())
        self.import_folder_button.setToolTip(self.import_folder_button.text())
        self.import_backup_button.setToolTip(self.import_backup_button.text())
        self.export_selected_button.setToolTip(self.export_selected_button.text())
        self.export_all_button.setToolTip(self.export_all_button.text())
        self.apply_plugin_state_button.setToolTip(self.apply_plugin_state_button.text())
        self.reset_plugins_button.setToolTip(self.reset_plugins_button.text())
        self.refresh_plugins_button.setToolTip(self.refresh_plugins_button.text())

        self.general_reset_button.setText(self._pt("reset", "Reset defaults"))
        self.general_save_button.setText(self._pt("save", "Save settings"))
        self.shortcuts_reset_button.setText(self._pt("shortcuts.reset", "Reset shortcuts"))
        self.shortcuts_save_button.setText(self._pt("shortcuts.save", "Save shortcuts"))
        self._populate_shortcuts()
        self._populate_plugin_table()
        self._refresh_autostart_status()
        self._refresh_backup_status()
        self._render_quick_access_settings()
        self._apply_responsive_layout(force=True)

    def _set_combo_value(self, combo: QComboBox, value) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _handle_tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is self.plugins_tab:
            self._populate_plugin_table()
        self._schedule_responsive_refresh()
        self._schedule_page_geometry_refresh()
        window = self.services.main_window
        if window is not None and getattr(window, "current_plugin_id", None) == self.plugin_id:
            sync = getattr(window, "_sync_system_toolbar_selection", None)
            if callable(sync):
                sync(self.plugin_id)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()
        self._schedule_responsive_refresh()
        self._schedule_page_geometry_refresh()

    def _refresh_page_geometry(self) -> None:
        self._geometry_refresh_pending = False
        self.tabs.updateGeometry()
        self.updateGeometry()
        target_height = self.sizeHint().height()
        self.setMinimumHeight(target_height)
        self.setMaximumHeight(target_height)
        if self.height() != target_height:
            self.resize(self.width(), target_height)
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                widget = parent.widget()
                if widget is not None:
                    widget.updateGeometry()
                parent.updateGeometry()
                break
            parent = parent.parentWidget()

    def _schedule_page_geometry_refresh(self) -> None:
        if self._geometry_refresh_pending:
            return
        self._geometry_refresh_pending = True
        QTimer.singleShot(0, self._refresh_page_geometry)

    def _schedule_responsive_refresh(self) -> None:
        if self._responsive_refresh_pending:
            return
        self._responsive_refresh_pending = True
        QTimer.singleShot(0, self._run_responsive_refresh)

    def _run_responsive_refresh(self) -> None:
        self._responsive_refresh_pending = False
        self._apply_responsive_layout()

    def _plugins_table_content_width(self) -> int:
        header = self.plugins_table.horizontalHeader()
        width = (self.plugins_table.frameWidth() * 2) + self.plugins_table.verticalHeader().width()
        for column in range(self.plugins_table.columnCount()):
            width += header.sectionSize(column)
        if self.plugins_table.verticalScrollBar().isVisible():
            width += self.plugins_table.verticalScrollBar().sizeHint().width()
        return width + 2

    def _schedule_plugins_table_width_sync(self, *_args) -> None:
        if self._plugins_table_width_sync_pending:
            return
        self._plugins_table_width_sync_pending = True
        QTimer.singleShot(0, self._sync_plugins_table_width)

    def _sync_plugins_table_width(self) -> None:
        self._plugins_table_width_sync_pending = False
        if not hasattr(self, "plugins_table"):
            return
        required_width = self._plugins_table_content_width()
        if self.plugins_table.minimumWidth() != required_width:
            self.plugins_table.setMinimumWidth(required_width)
        self.plugins_table.updateGeometry()
        self.plugins_tab.updateGeometry()
        self.tabs.updateGeometry()
        self.updateGeometry()

    def _apply_responsive_layout(self, *, force: bool = False) -> None:
        bucket = width_breakpoint(self.width(), compact_max=760, medium_max=1180)
        structure_changed = force or bucket != self._responsive_bucket
        self._responsive_bucket = bucket
        compact = bucket == "compact"

        if structure_changed:
            self.general_tools_row.setDirection(
                QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            )
            self.quick_add_row.setDirection(
                QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            )
            self.quick_manage_row.setDirection(
                QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            )
            self.shortcut_actions.setDirection(
                QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            )

        while self.quick_actions_layout.count():
            item = self.quick_actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self.quick_actions_host)
        quick_columns = adaptive_grid_columns(
            min(
                visible_parent_width(self),
                self.quick_actions_host.contentsRect().width()
                or self.quick_actions_host.width()
                or self.quick_access_card.contentsRect().width()
                or self.quick_access_card.width(),
            ),
            item_widths=[button.sizeHint().width() for button in self._quick_action_buttons],
            spacing=self.quick_actions_layout.horizontalSpacing(),
            min_columns=2,
        )
        for index, button in enumerate(self._quick_action_buttons):
            self.quick_actions_layout.addWidget(button, index // quick_columns, index % quick_columns)
        for column in range(quick_columns):
            self.quick_actions_layout.setColumnStretch(column, 1)

        while self.plugins_actions_layout.count():
            item = self.plugins_actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self.plugins_tab)
        available_width = min(
            visible_parent_width(self),
            self.plugins_tab.contentsRect().width() or self.plugins_tab.width() or self.width(),
        )
        plugin_button_widths = [button.sizeHint().width() for button in self._plugin_action_buttons]
        plugin_spacing = self.plugins_actions_layout.horizontalSpacing()
        required_for_single_row = sum(plugin_button_widths) + (plugin_spacing * max(0, len(plugin_button_widths) - 1))
        plugin_columns = len(plugin_button_widths) if available_width >= required_for_single_row else 4
        for index, button in enumerate(self._plugin_action_buttons):
            self.plugins_actions_layout.addWidget(button, index // plugin_columns, index % plugin_columns)
        for column in range(plugin_columns):
            self.plugins_actions_layout.setColumnStretch(column, 1)
        self._refresh_quick_access_preview_layout()

    def current_section_id(self) -> str:
        current = self.tabs.currentWidget()
        if current is self.plugins_tab:
            return "plugins"
        if current is self.quick_access_tab:
            return "quick_access"
        if current is self.shortcuts_tab:
            return "shortcuts"
        return "general"

    def open_plugins_tab(self) -> None:
        self.tabs.setCurrentWidget(self.plugins_tab)
        self._populate_plugin_table()

    def open_general_tab(self) -> None:
        self.tabs.setCurrentWidget(self.general_tab)

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()
        self._sync_theme_picker()
        if self.tabs.currentWidget() is self.plugins_tab:
            self._populate_plugin_table()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        self.setStyleSheet(f"background: {palette.window_bg};")
        for widget in (
            self.general_tab,
            self.quick_access_tab,
            self.shortcuts_tab,
            self.plugins_tab,
            self.theme_picker_host,
            self.language_host,
            self.density_host,
            self.scaling_host,
        ):
            widget.setStyleSheet("background: transparent;")
        self.tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                background: {palette.window_bg};
                border: none;
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
            """
        )
        self.title_label.setStyleSheet(page_title_style(palette, size=26, weight=700))
        self.description_label.setStyleSheet(muted_text_style(palette))
        for frame in (
            self.output_card,
            self.appearance_card,
            self.automation_card,
            self.backup_card,
            self.quick_access_card,
        ):
            frame.setStyleSheet(card_style(palette))
        for label in (
            self.general_note,
            self.appearance_note,
            self.autostart_status_label,
            self.quick_access_tab_note,
            self.quick_access_note,
            self.shortcut_note,
            self.shortcut_status_label,
            self.plugins_note,
            self.behavior_note,
            self.backup_note,
        ):
            label.setStyleSheet(muted_text_style(palette))
        for label in (
            self.output_title,
            self.appearance_title,
            self.behavior_title,
            self.backup_title,
        ):
            label.setStyleSheet(section_title_style(palette, size=18))
        self.quick_access_title.setStyleSheet(section_title_style(palette, size=18))
        self.quick_access_preview_frame.setStyleSheet(
            f"""
            QFrame#QuickAccessPreview {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {palette.surface_alt_bg},
                    stop:1 {palette.surface_bg});
                border: 1px solid {palette.border};
                border-radius: 16px;
            }}
            """
        )
        self.quick_access_list.setStyleSheet(
            f"""
            QListWidget {{
                background: {palette.input_bg};
                border: 1px solid {palette.border};
                border-radius: 12px;
                color: {palette.text_primary};
            }}
            QListWidget::item {{
                padding: 8px 10px;
                margin: 0;
            }}
            QListWidget::item:selected {{
                background: {palette.accent_soft};
                color: {palette.text_primary};
            }}
            """
        )
        self.quick_access_combo.setStyleSheet(
            f"""
            QComboBox {{
                background: {palette.input_bg};
                color: {palette.text_primary};
                border: 1px solid {palette.border};
                border-radius: 12px;
                padding: 6px 10px;
            }}
            """
        )
        for tile in self.quick_access_preview_frame.findChildren(QuickAccessPreviewTile):
            tile.apply_palette(palette)
        plugin_action_buttons = (
            self.import_file_button,
            self.import_folder_button,
            self.import_backup_button,
            self.export_selected_button,
            self.export_all_button,
            self.apply_plugin_state_button,
            self.reset_plugins_button,
            self.refresh_plugins_button,
        )
        for button in plugin_action_buttons:
            button.setStyleSheet(
                f"""
                QToolButton {{
                    background: {palette.surface_bg};
                    color: {palette.text_primary};
                    border: 1px solid {palette.border};
                    border-radius: 12px;
                    padding: 5px 8px;
                    font-size: 12px;
                    font-weight: 600;
                }}
                QToolButton:hover {{
                    border-color: {palette.accent};
                    background: {palette.accent_soft};
                }}
                """
            )
        for button in self.theme_color_buttons.values():
            button.setStyleSheet(
                f"""
                QToolButton {{
                    border: 1px solid {palette.border};
                    border-radius: 14px;
                    padding: 6px 8px;
                    background: {palette.surface_alt_bg};
                    color: {palette.text_primary};
                    font-weight: 600;
                }}
                QToolButton:checked {{
                    border: 2px solid {palette.accent};
                    background: {palette.accent_soft};
                }}
                """
            )
        for button in self.language_buttons.values():
            button.setStyleSheet(
                f"""
                QToolButton {{
                    border: 1px solid {palette.border};
                    border-radius: 14px;
                    padding: 6px 14px;
                    background: {palette.surface_alt_bg};
                    color: {palette.text_primary};
                    font-weight: 600;
                }}
                QToolButton:hover {{
                    border-color: {palette.accent};
                }}
                QToolButton:checked {{
                    border: 1px solid {palette.accent};
                    background: {palette.accent_soft};
                    color: {palette.text_primary};
                }}
                """
            )
        self.dark_mode_checkbox.setStyleSheet(
            f"""
            QCheckBox {{
                color: {palette.text_primary};
                spacing: 8px;
                font-weight: 600;
            }}
            QCheckBox::indicator {{
                width: 40px;
                height: 22px;
                border-radius: 11px;
                border: 1px solid {palette.border};
                background: {palette.surface_alt_bg};
            }}
            QCheckBox::indicator:checked {{
                border-color: {palette.accent};
                background: {palette.accent};
            }}
            """
        )
        for slider in (self.density_slider, self.scaling_slider):
            slider.setStyleSheet(
                f"""
                QSlider::groove:horizontal {{
                    height: 6px;
                    border-radius: 3px;
                    background: {palette.border};
                }}
                QSlider::sub-page:horizontal {{
                    border-radius: 3px;
                    background: {palette.accent};
                }}
                QSlider::handle:horizontal {{
                    width: 18px;
                    margin: -6px 0;
                    border-radius: 9px;
                    background: {palette.surface_bg};
                    border: 2px solid {palette.accent};
                }}
                """
            )
