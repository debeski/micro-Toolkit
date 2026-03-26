from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
import os
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QProcess, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QIcon, QKeyEvent, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProxyStyle,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTableView,
    QTableWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.confirm_dialog import confirm_action, confirm_action_with_option
from micro_toolkit.core.icon_registry import icon_from_name
from micro_toolkit.core.plugin_manager import PluginSpec
from micro_toolkit.core.services import AppServices
from micro_toolkit.core.shell_registry import (
    DASHBOARD_PLUGIN_ID,
    INSPECTOR_PLUGIN_ID,
    NON_SIDEBAR_PLUGIN_IDS,
    SYSTEM_TOOLBAR_PLUGIN_IDS,
    UNSCROLLED_PLUGIN_IDS,
)
from micro_toolkit.core.table_utils import configure_resizable_table

PLUGIN_ID_ROLE = Qt.ItemDataRole.UserRole + 1
GROUP_KEY_ROLE = Qt.ItemDataRole.UserRole + 2
ITEM_SOURCE_ROLE = Qt.ItemDataRole.UserRole + 3


class BranchlessTreeStyle(QProxyStyle):
    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorBranch:
            return
        super().drawPrimitive(element, option, painter, widget)


class BranchlessTreeWidget(QTreeWidget):
    def drawBranches(self, painter, rect, index) -> None:
        return

    def drawRow(self, painter, option: QStyleOptionViewItem, index) -> None:
        option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasDecoration
        super().drawRow(painter, option, index)


class SidebarItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        depth = 0
        parent = index.parent()
        while parent.isValid():
            depth += 1
            parent = parent.parent()

        left_gutter = 2 + (depth * 6)
        row_rect = opt.rect.adjusted(left_gutter, 4, -3, -4)

        painter.save()
        if opt.state & QStyle.StateFlag.State_Selected:
            bg = opt.palette.color(opt.palette.ColorRole.Highlight)
            bg.setAlpha(34)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(row_rect, 10, 10)
        elif opt.state & QStyle.StateFlag.State_MouseOver:
            bg = opt.palette.color(opt.palette.ColorRole.Highlight)
            bg.setAlpha(14)
            pen = QColor(opt.palette.color(opt.palette.ColorRole.Mid))
            pen.setAlpha(110)
            painter.setPen(QPen(pen, 1))
            painter.setBrush(bg)
            painter.drawRoundedRect(row_rect, 10, 10)
        painter.restore()

        opt.state &= ~QStyle.StateFlag.State_Selected
        opt.state &= ~QStyle.StateFlag.State_MouseOver
        opt.rect = row_rect.adjusted(6, 0, -2, 0)
        super().paint(painter, opt, index)


class SpinnerIndicator(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._advance)
        self.setFixedSize(270, 270)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _advance(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        base = QColor(palette.color(palette.ColorRole.Mid))
        accent = QColor(palette.color(palette.ColorRole.Highlight))
        base.setAlpha(90)
        accent.setAlpha(255)
        rect = self.rect().adjusted(34, 34, -34, -34)
        painter.setPen(QPen(base, 22))
        painter.drawArc(rect, 0, 360 * 16)
        painter.setPen(QPen(accent, 22))
        painter.drawArc(rect, int((-self._angle + 90) * 16), int(-110 * 16))


class StatusElidedLabel(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def setText(self, text: str) -> None:
        self._full_text = str(text or "")
        self._apply_elided_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elided_text()

    def _apply_elided_text(self) -> None:
        metrics = self.fontMetrics()
        width = max(0, self.contentsRect().width())
        rendered = self._full_text if width <= 0 else metrics.elidedText(
            self._full_text,
            Qt.TextElideMode.ElideRight,
            width,
        )
        super().setText(rendered)
        if self._full_text and rendered != self._full_text:
            self.setToolTip(self._full_text)
        else:
            self.setToolTip("")


class LoadingOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spinner = SpinnerIndicator(self)
        layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignCenter)

    def show_message(self, message: str) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self._set_keyboard_grabbed(True)
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.spinner.start()
        self.show()

    def hide_overlay(self) -> None:
        self.spinner.stop()
        self._set_keyboard_grabbed(False)
        self.hide()

    def set_blur_targets(self, _targets: list[QWidget]) -> None:
        # Kept for compatibility with existing calls. The overlay is now self-contained.
        return

    def _set_keyboard_grabbed(self, enabled: bool) -> None:
        app = QApplication.instance()
        if app is None or app.platformName() == "offscreen":
            return
        try:
            if enabled:
                self.grabKeyboard()
            else:
                self.releaseKeyboard()
        except Exception:
            pass

    def mousePressEvent(self, event) -> None:
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        event.accept()

    def wheelEvent(self, event) -> None:
        event.accept()

    def keyPressEvent(self, event) -> None:
        event.accept()

    def keyReleaseEvent(self, event) -> None:
        event.accept()


class TerminalOutputView(QPlainTextEdit):
    def __init__(self, terminal_widget: "EmbeddedTerminalWidget", parent: QWidget | None = None):
        super().__init__(parent)
        self._terminal_widget = terminal_widget

    def keyPressEvent(self, event) -> None:
        if self._forward_to_prompt(event):
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        super().mouseDoubleClickEvent(event)
        self._terminal_widget.focus_prompt(select_all=False)

    def _forward_to_prompt(self, event) -> bool:
        prompt = self._terminal_widget.input
        if not prompt.isEnabled() or prompt.isReadOnly():
            return False

        if event.matches(QKeySequence.StandardKey.Copy):
            return False

        forwarded_key = event.key()
        if forwarded_key in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self._terminal_widget.focus_prompt(select_all=False)
            self._terminal_widget._submit_command()
            return True

        text = event.text()
        if text or forwarded_key in {
            Qt.Key.Key_Backspace,
            Qt.Key.Key_Delete,
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
        }:
            self._terminal_widget.focus_prompt(select_all=False)
            forwarded = QKeyEvent(
                QEvent.Type.KeyPress,
                forwarded_key,
                event.modifiers(),
                text,
                event.isAutoRepeat(),
                event.count(),
            )
            QApplication.sendEvent(prompt, forwarded)
            return True
        return False


class EmbeddedTerminalWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._append_output)
        self.process.finished.connect(self._handle_finished)
        self._start_failed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.output = TerminalOutputView(self)
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        layout.addWidget(self.output, 1)

        self.input = QLineEdit()
        self.input.setObjectName("TerminalInput")
        self.input.setPlaceholderText("Enter command and press Return")
        self.input.returnPressed.connect(self._submit_command)
        layout.addWidget(self.input, 0)

    def _shell_command(self) -> tuple[str, list[str]]:
        if os.name == "nt":
            program = os.environ.get("COMSPEC") or "cmd.exe"
            return program, ["/Q"]
        shell = os.environ.get("SHELL")
        if shell:
            return shell, ["-i"]
        return "bash", ["-i"]

    def _start_shell(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self._start_failed = False
        program, args = self._shell_command()
        self.process.start(program, args)
        if not self.process.waitForStarted(2000):
            self._start_failed = True
            self.output.appendPlainText(f"Failed to start shell: {program}")

    def ensure_started(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._start_shell()

    def _append_output(self) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not data:
            return
        cursor = self.output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(data)
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def _submit_command(self) -> None:
        command = self.input.text().strip()
        if not command:
            return
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.ensure_started()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        line_break = "\r\n" if os.name == "nt" else "\n"
        self.output.appendPlainText(f"> {command}")
        self.process.write((command + line_break).encode("utf-8"))
        self.input.clear()

    def _handle_finished(self) -> None:
        self.output.appendPlainText("\n[Shell exited]")

    def focus_prompt(self, *, select_all: bool = True) -> None:
        self.ensure_started()
        self.input.setFocus()
        if select_all:
            self.input.selectAll()

    def shutdown(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.process.terminate()
        if not self.process.waitForFinished(800):
            self.process.kill()
            self.process.waitForFinished(800)


class MicroToolkitWindow(QMainWindow):
    def __init__(self, services: AppServices, *, initial_plugin_id: str | None = None):
        super().__init__()
        self.services = services
        self.plugin_manager = self.services.plugin_manager
        self.all_specs: list[PluginSpec] = []
        self.plugin_specs: list[PluginSpec] = []
        self.plugin_by_id: dict[str, PluginSpec] = {}
        self.system_toolbar_buttons: dict[str, QToolButton] = {}
        self.page_indices: dict[str, int] = {}
        self.initial_plugin_id = initial_plugin_id
        self.current_plugin_id: str | None = None
        self.current_dock_mode = "activity"
        self._quitting = False
        self._busy_depth = 0
        self._dock_state_timer = QTimer(self)
        self._dock_state_timer.setSingleShot(True)
        self._dock_state_timer.setInterval(220)
        self._dock_state_timer.timeout.connect(self._save_activity_dock_state)

        self.setWindowTitle("Micro Toolkit")
        self.resize(1420, 900)
        self.setMinimumSize(1180, 720)

        self._refresh_specs()
        self._build_ui()
        self._bind_signals()
        self._populate_sidebar()
        self._open_initial_page()
        self._register_shortcuts()
        self._apply_shell_texts()
        self.services.attach_main_window(self)
        self.log_dock.installEventFilter(self)
        QTimer.singleShot(0, self._restore_activity_dock_state)

    def _build_ui(self) -> None:
        central = QWidget(self)
        outer_layout = QHBoxLayout(central)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        self.setCentralWidget(central)

        sidebar_card = QFrame()
        self.sidebar_card = sidebar_card
        sidebar_card.setObjectName("SidebarCard")
        sidebar_card.setFixedWidth(286)
        sidebar_layout = QVBoxLayout(sidebar_card)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        sidebar_header = QFrame()
        sidebar_header.setObjectName("SidebarHeader")
        sidebar_header.setFixedHeight(57)
        brand_row = QHBoxLayout(sidebar_header)
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(0)
        self.app_title_label = QLabel("Micro Toolkit")
        self.app_title_label.setObjectName("AppTitle")
        self.app_title_label.setContentsMargins(20, 0, 20, 0)
        brand_row.addWidget(self.app_title_label, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        brand_row.addStretch(1)
        sidebar_layout.addWidget(sidebar_header)

        self.sidebar_tree = BranchlessTreeWidget()
        self.sidebar_tree.setObjectName("SidebarTree")
        # Avoid wrapping the existing widget-owned style, which can crash during Qt teardown.
        self.sidebar_tree.setStyle(BranchlessTreeStyle())
        self.sidebar_tree.setItemDelegate(SidebarItemDelegate(self.sidebar_tree))
        self.sidebar_tree.setHeaderHidden(True)
        self.sidebar_tree.setRootIsDecorated(False)
        self.sidebar_tree.setIndentation(14)
        self.sidebar_tree.setExpandsOnDoubleClick(False)
        self.sidebar_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sidebar_tree.setUniformRowHeights(True)
        self.sidebar_tree.setAnimated(True)
        sidebar_layout.addWidget(self.sidebar_tree, 1)

        content_shell = QWidget()
        content_layout = QVBoxLayout(content_shell)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        utility_card = QFrame()
        utility_card.setObjectName("UtilityBar")
        utility_card.setFixedHeight(57)
        utility_layout = QHBoxLayout(utility_card)
        utility_layout.setContentsMargins(18, 12, 18, 12)
        utility_layout.setSpacing(14)

        search_host = QWidget()
        search_host.setObjectName("UtilitySearchHost")
        search_host_layout = QVBoxLayout(search_host)
        search_host_layout.setContentsMargins(0, 0, 0, 0)
        search_host_layout.setSpacing(0)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("ShellSearchInput")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(380)
        self.search_input.setMaximumWidth(520)
        self.search_input.setFixedHeight(28)
        search_host.setFixedHeight(28)
        search_host_layout.addWidget(self.search_input, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        utility_layout.addWidget(search_host, 1, Qt.AlignmentFlag.AlignTop)

        self.top_system_tools = QHBoxLayout()
        self.top_system_tools.setContentsMargins(0, 0, 0, 0)
        self.top_system_tools.setSpacing(8)

        for plugin_id, fallback_icon, fallback_label in (
            (DASHBOARD_PLUGIN_ID, QStyle.StandardPixmap.SP_DirHomeIcon, "Dashboard"),
            ("clip_manager", QStyle.StandardPixmap.SP_FileDialogContentsView, "Clipboard"),
            ("workflow_studio", QStyle.StandardPixmap.SP_BrowserReload, "Workflows"),
            ("plugin_manager", QStyle.StandardPixmap.SP_FileIcon, "Plugins"),
            ("about_center", QStyle.StandardPixmap.SP_FileDialogInfoView, "About"),
            ("settings_center", QStyle.StandardPixmap.SP_FileDialogDetailedView, "Settings"),
            (INSPECTOR_PLUGIN_ID, QStyle.StandardPixmap.SP_FileDialogDetailedView, "Inspector"),
        ):
            button = self._make_tool_button(
                icon=self._system_component_icon(plugin_id),
                tooltip=fallback_label,
                handler=lambda _checked=False, pid=plugin_id: self.open_settings_center() if pid == "settings_center" else (self.open_plugin_manager() if pid == "plugin_manager" else (self.open_inspector_center() if pid == INSPECTOR_PLUGIN_ID else self.open_plugin(pid))),
                checkable=True,
            )
            button.setIconSize(QSize(20, 20))
            button.setFixedSize(36, 36)
            button.setObjectName("SystemToolbarButton")
            self.system_toolbar_buttons[plugin_id] = button
            self.top_system_tools.addWidget(button)
            button.setVisible(self._system_toolbar_button_visible(plugin_id))
        self.top_system_tools.addStretch(1)
        system_tools_host = QWidget()
        system_tools_host.setObjectName("UtilityActionsHost")
        system_tools_host.setLayout(self.top_system_tools)
        system_tools_host.setFixedHeight(36)
        utility_layout.addWidget(system_tools_host, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        content_layout.addWidget(utility_card)

        header_card = QFrame()
        header_card.setObjectName("HeaderCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(24, 18, 24, 18)
        header_layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        title_column = QVBoxLayout()
        title_column.setContentsMargins(0, 0, 0, 0)
        title_column.setSpacing(4)

        self.page_context = QLabel()
        self.page_context.setObjectName("SectionEyebrow")
        title_column.addWidget(self.page_context)

        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        title_column.addWidget(self.page_title)
        top_row.addLayout(title_column, 1)

        self.pin_current_button = self._make_tool_button(
            icon=self._named_icon("pin", fallback=QStyle.StandardPixmap.SP_DialogApplyButton),
            tooltip="Pin to quick access",
            handler=self._toggle_current_quick_access,
            checkable=True,
        )
        self.pin_current_button.setObjectName("HeaderActionButton")
        self.pin_current_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.pin_current_button.setAutoRaise(False)
        top_row.addWidget(self.pin_current_button)

        header_layout.addLayout(top_row)

        self.page_description = QLabel()
        self.page_description.setObjectName("PageDescription")
        self.page_description.setWordWrap(True)
        header_layout.addWidget(self.page_description)

        content_layout.addWidget(header_card)

        page_card = QFrame()
        page_card.setObjectName("PageCard")
        page_layout = QVBoxLayout(page_card)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        self.page_stack = QStackedWidget()
        page_layout.addWidget(self.page_stack)
        content_layout.addWidget(page_card, 1)

        outer_layout.addWidget(sidebar_card)
        outer_layout.addWidget(content_shell, 1)

        self.log_dock = QDockWidget(self)
        self.log_dock.setObjectName("ActivityDock")
        self.log_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(800)
        self.log_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.terminal_output = EmbeddedTerminalWidget()
        self.dock_stack = QStackedWidget()
        self.dock_stack.addWidget(self.log_output)
        self.dock_stack.addWidget(self.terminal_output)
        self.log_dock.setWidget(self.dock_stack)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)

        status = QStatusBar()
        self.status_label = StatusElidedLabel()
        status.addWidget(self.status_label, 1)
        self.terminal_button = self._make_tool_button(
            icon=self._named_icon("terminal", fallback=QStyle.StandardPixmap.SP_ComputerIcon),
            tooltip="Show terminal",
            handler=self.toggle_terminal_dock,
            checkable=True,
        )
        self.terminal_button.setObjectName("TerminalToggle")
        self.terminal_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.terminal_button.setIconSize(QSize(18, 18))
        self.terminal_button.setFixedSize(32, 24)
        status.addPermanentWidget(self.terminal_button)
        self.console_button = self._make_tool_button(
            icon=self._named_icon("console", fallback=QStyle.StandardPixmap.SP_FileDialogContentsView),
            tooltip="Show activity console",
            handler=self.toggle_activity_dock,
            checkable=True,
        )
        self.console_button.setObjectName("ConsoleToggle")
        self.console_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.console_button.setIconSize(QSize(22, 22))
        self.console_button.setFixedSize(32, 24)
        status.addPermanentWidget(self.console_button)
        self.setStatusBar(status)
        self.loading_overlay = LoadingOverlay(self)
        self.loading_overlay.set_blur_targets([central, status, self.log_dock])

        placeholder = self._build_placeholder_page()
        self.page_stack.addWidget(placeholder)
        self.page_stack.setCurrentWidget(placeholder)

    def _make_tool_button(self, *, icon, tooltip: str, handler, checkable: bool = False) -> QToolButton:
        button = QToolButton()
        button.setIcon(icon)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setCheckable(checkable)
        button.clicked.connect(handler)
        return button

    def begin_loading(self, message: str = "Loading...") -> None:
        self._busy_depth += 1
        self.loading_overlay.show_message(message)
        QApplication.processEvents()

    def end_loading(self) -> None:
        self._busy_depth = max(0, self._busy_depth - 1)
        if self._busy_depth == 0:
            self.loading_overlay.hide_overlay()

    @contextmanager
    def loading_context(self, message: str = "Loading..."):
        self.begin_loading(message)
        try:
            yield
        finally:
            self.end_loading()

    def _bind_signals(self) -> None:
        self.search_input.textChanged.connect(self._apply_filter)
        self.sidebar_tree.itemSelectionChanged.connect(self._handle_selection_change)
        self.sidebar_tree.itemClicked.connect(self._handle_sidebar_click)
        self.sidebar_tree.itemExpanded.connect(self._handle_sidebar_group_expanded)
        self.sidebar_tree.itemCollapsed.connect(lambda item: self._store_group_state(item, expanded=False))
        self.services.logger.message_logged.connect(self._append_log)
        self.services.logger.status_changed.connect(self.status_label.setText)
        self.services.i18n.language_changed.connect(self._handle_language_change)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self.services.plugin_visuals_changed.connect(self.refresh_plugin_visuals)
        self.log_dock.visibilityChanged.connect(self._sync_console_button)
        self.log_dock.visibilityChanged.connect(lambda _visible: self._schedule_save_activity_dock_state())
        self.log_dock.dockLocationChanged.connect(lambda _area: self._schedule_save_activity_dock_state())
        self.log_dock.topLevelChanged.connect(lambda _floating: self._schedule_save_activity_dock_state())

    def _build_placeholder_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        self.placeholder_eyebrow = QLabel()
        self.placeholder_eyebrow.setObjectName("SectionEyebrow")
        layout.addWidget(self.placeholder_eyebrow)

        self.placeholder_title = QLabel()
        self.placeholder_title.setObjectName("PlaceholderTitle")
        layout.addWidget(self.placeholder_title)

        self.placeholder_body = QLabel()
        self.placeholder_body.setWordWrap(True)
        self.placeholder_body.setObjectName("PlaceholderBody")
        layout.addWidget(self.placeholder_body)
        layout.addStretch(1)
        return page

    def _refresh_specs(self) -> None:
        self.all_specs = self.plugin_manager.discover_plugins(include_disabled=True)
        self.plugin_by_id = {spec.plugin_id: spec for spec in self.all_specs}
        self.plugin_specs = [
            spec
            for spec in self.plugin_manager.sidebar_plugins()
            if spec.plugin_id not in NON_SIDEBAR_PLUGIN_IDS
        ]

    def _group_collapsed_state(self) -> dict[str, bool]:
        raw = self.services.config.get("collapsed_groups") or {}
        return raw if isinstance(raw, dict) else {}

    def _set_group_collapsed_state(self, group_key: str, collapsed: bool) -> None:
        state = dict(self._group_collapsed_state())
        state[group_key] = bool(collapsed)
        self.services.config.set("collapsed_groups", state)

    def _handle_sidebar_group_expanded(self, item: QTreeWidgetItem) -> None:
        if item.parent() is not None:
            self._store_group_state(item, expanded=True)
            return

        root = self.sidebar_tree.invisibleRootItem()
        self.sidebar_tree.blockSignals(True)
        try:
            for index in range(root.childCount()):
                sibling = root.child(index)
                if sibling is item or sibling.childCount() == 0:
                    continue
                sibling.setExpanded(False)
        finally:
            self.sidebar_tree.blockSignals(False)

        for index in range(root.childCount()):
            sibling = root.child(index)
            if sibling.childCount() == 0:
                continue
            self._set_group_collapsed_state(str(sibling.data(0, GROUP_KEY_ROLE) or ""), sibling is not item)

    def _populate_sidebar(self) -> None:
        self.sidebar_tree.clear()
        language = self.services.i18n.current_language()
        collapsed_state = self._group_collapsed_state()
        palette = self.services.theme_manager.current_palette()
        group_font = QFont(self.font())
        group_font.setPointSize(max(9, group_font.pointSize() - 1))
        group_font.setWeight(QFont.Weight.DemiBold)
        group_font.setCapitalization(QFont.Capitalization.AllUppercase)
        item_font = QFont(self.font())
        item_font.setPointSize(max(10, item_font.pointSize()))
        item_brush = QBrush(QColor(palette.text_primary))
        group_brush = QBrush(QColor(palette.text_muted))

        quick_group = QTreeWidgetItem([self.services.i18n.tr("shell.quick_access", "Quick Access")])
        quick_group.setData(0, GROUP_KEY_ROLE, "quick_access")
        quick_group.setFlags(Qt.ItemFlag.ItemIsEnabled)
        quick_group.setExpanded(not collapsed_state.get("quick_access", False))
        quick_group.setIcon(0, self._named_icon("bolt", fallback=QStyle.StandardPixmap.SP_DialogOpenButton))
        quick_group.setFont(0, group_font)
        quick_group.setForeground(0, group_brush)
        quick_group.setSizeHint(0, QSize(0, 54))
        self.sidebar_tree.addTopLevelItem(quick_group)

        quick_specs = [self.plugin_by_id[plugin_id] for plugin_id in self.services.quick_access_ids() if plugin_id in self.plugin_by_id]
        for spec in quick_specs:
            child = QTreeWidgetItem([self.services.plugin_display_name(spec)])
            child.setToolTip(0, spec.localized_description(language))
            child.setData(0, PLUGIN_ID_ROLE, spec.plugin_id)
            child.setData(0, ITEM_SOURCE_ROLE, "quick_access")
            child.setIcon(0, self._plugin_icon(spec))
            child.setFont(0, item_font)
            child.setForeground(0, item_brush)
            child.setSizeHint(0, QSize(0, 40))
            quick_group.addChild(child)

        categories: dict[str, list[PluginSpec]] = defaultdict(list)
        for spec in self.plugin_specs:
            if spec.plugin_id == DASHBOARD_PLUGIN_ID:
                continue
            category_name = spec.localized_category(language).strip() or self.services.i18n.tr("shell.tools", "Tools")
            if category_name.lower() == "general" and spec.plugin_id != DASHBOARD_PLUGIN_ID:
                continue
            categories[category_name].append(spec)

        for category in sorted(categories):
            category_key = f"category::{category}"
            category_item = QTreeWidgetItem([category])
            category_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            category_item.setFirstColumnSpanned(True)
            category_item.setData(0, GROUP_KEY_ROLE, category_key)
            category_item.setExpanded(not collapsed_state.get(category_key, False))
            category_item.setIcon(0, self._group_icon(categories[category]))
            category_item.setFont(0, group_font)
            category_item.setForeground(0, group_brush)
            category_item.setSizeHint(0, QSize(0, 54))
            self.sidebar_tree.addTopLevelItem(category_item)

            for spec in sorted(categories[category], key=lambda item: self.services.plugin_display_name(item).lower()):
                child = QTreeWidgetItem([self.services.plugin_display_name(spec)])
                child.setToolTip(0, spec.localized_description(language))
                child.setData(0, PLUGIN_ID_ROLE, spec.plugin_id)
                child.setData(0, ITEM_SOURCE_ROLE, "catalog")
                child.setIcon(0, self._plugin_icon(spec))
                child.setFont(0, item_font)
                child.setForeground(0, item_brush)
                child.setSizeHint(0, QSize(0, 40))
                category_item.addChild(child)
        self._adjust_sidebar_width()

    def _open_initial_page(self) -> None:
        initial_id = self.initial_plugin_id if self.initial_plugin_id in self.plugin_by_id else None
        if initial_id is None:
            configured_id = str(self.services.config.get("default_start_plugin") or "").strip()
            if configured_id == INSPECTOR_PLUGIN_ID and not self.services.developer_mode_enabled():
                configured_id = ""
            initial_id = configured_id if configured_id in self.plugin_by_id else None
        if initial_id is None:
            initial_id = DASHBOARD_PLUGIN_ID if DASHBOARD_PLUGIN_ID in self.plugin_by_id else None
        if initial_id is None and self.plugin_specs:
            initial_id = self.plugin_specs[0].plugin_id
        if initial_id is not None:
            self._select_plugin_item(initial_id)
            self.open_plugin(initial_id)

    def _select_plugin_item(self, plugin_id: str) -> None:
        root = self.sidebar_tree.invisibleRootItem()
        current_item = self.sidebar_tree.currentItem()
        preferred_source = None
        if current_item is not None and current_item.data(0, PLUGIN_ID_ROLE) == plugin_id:
            preferred_source = current_item.data(0, ITEM_SOURCE_ROLE)

        matches: list[QTreeWidgetItem] = []
        for i in range(root.childCount()):
            top_item = root.child(i)
            if top_item.data(0, PLUGIN_ID_ROLE) == plugin_id:
                matches.append(top_item)
            for j in range(top_item.childCount()):
                item = top_item.child(j)
                if item.data(0, PLUGIN_ID_ROLE) == plugin_id:
                    matches.append(item)

        for item in matches:
            if preferred_source and item.data(0, ITEM_SOURCE_ROLE) == preferred_source:
                self.sidebar_tree.setCurrentItem(item)
                return

        for item in matches:
            if item.data(0, ITEM_SOURCE_ROLE) == "catalog":
                self.sidebar_tree.setCurrentItem(item)
                return

        if matches:
            self.sidebar_tree.setCurrentItem(matches[0])
            return

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        root = self.sidebar_tree.invisibleRootItem()
        language = self.services.i18n.current_language()
        for i in range(root.childCount()):
            item = root.child(i)
            plugin_id = item.data(0, PLUGIN_ID_ROLE)
            if plugin_id:
                spec = self.plugin_by_id.get(plugin_id)
                haystack = " ".join(
                    [
                        self.services.plugin_display_name(spec) if spec else "",
                        spec.localized_description(language) if spec else "",
                    ]
                ).lower()
                item.setHidden(bool(needle) and needle not in haystack)
                continue

            visible_children = 0
            for j in range(item.childCount()):
                child = item.child(j)
                child_plugin_id = child.data(0, PLUGIN_ID_ROLE)
                spec = self.plugin_by_id.get(child_plugin_id)
                haystack = " ".join(
                    [
                        self.services.plugin_display_name(spec) if spec else "",
                        spec.localized_description(language) if spec else "",
                        spec.localized_category(language) if spec else "",
                    ]
                ).lower()
                hidden = bool(needle) and needle not in haystack
                child.setHidden(hidden)
                if not hidden:
                    visible_children += 1
            item.setHidden(visible_children == 0 and bool(needle))
            if needle and visible_children:
                item.setExpanded(True)

    def _handle_selection_change(self) -> None:
        item = self.sidebar_tree.currentItem()
        if item is None:
            return
        plugin_id = item.data(0, PLUGIN_ID_ROLE)
        if plugin_id:
            self.open_plugin(plugin_id)

    def _handle_sidebar_click(self, item: QTreeWidgetItem, _column: int) -> None:
        if item is None:
            return
        plugin_id = item.data(0, PLUGIN_ID_ROLE)
        if plugin_id:
            return
        item.setExpanded(not item.isExpanded())

    def _store_group_state(self, item: QTreeWidgetItem, *, expanded: bool) -> None:
        if item is None:
            return
        group_key = item.data(0, GROUP_KEY_ROLE)
        if not group_key:
            return
        self._set_group_collapsed_state(str(group_key), not expanded)

    def _toggle_current_quick_access(self):
        if self.current_plugin_id is None or self.current_plugin_id not in {spec.plugin_id for spec in self.services.pinnable_plugin_specs()}:
            return {"pinned": False}
        pinned = self.services.toggle_quick_access(self.current_plugin_id)
        self.pin_current_button.setChecked(pinned)
        self.pin_current_button.setIcon(
            self._named_icon(
                "unpin" if pinned else "pin",
                fallback=QStyle.StandardPixmap.SP_DialogCancelButton if pinned else QStyle.StandardPixmap.SP_DialogApplyButton,
            )
        )
        return {"pinned": pinned}

    def open_plugin(self, plugin_id: str) -> None:
        spec = self.plugin_by_id.get(plugin_id)
        if spec is None:
            return

        try:
            with self.loading_context(self.services.i18n.tr("shell.loading", "Loading...")):
                if plugin_id not in self.page_indices:
                    plugin = self.plugin_manager.load_plugin(plugin_id)
                    plugin_widget = plugin.create_widget(self.services)
                    self._normalize_theme_styles(plugin_widget)
                    self._configure_tables(plugin_widget)
                    self._suppress_duplicate_page_header(plugin_widget, spec)
                    if plugin_id in UNSCROLLED_PLUGIN_IDS:
                        page_widget = plugin_widget
                    else:
                        scroll_area = QScrollArea()
                        scroll_area.setWidgetResizable(True)
                        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
                        scroll_area.setWidget(plugin_widget)
                        page_widget = scroll_area

                    page_index = self.page_stack.addWidget(page_widget)
                    self.page_indices[plugin_id] = page_index
        except Exception as exc:
            self._handle_plugin_open_error(spec, exc)
            return

        self.current_plugin_id = plugin_id
        self._sync_system_toolbar_selection(plugin_id)
        if plugin_id in SYSTEM_TOOLBAR_PLUGIN_IDS:
            self.sidebar_tree.blockSignals(True)
            self.sidebar_tree.clearSelection()
            self.sidebar_tree.setCurrentItem(None)
            self.sidebar_tree.blockSignals(False)
        else:
            self._select_plugin_item(plugin_id)
        self.page_stack.setCurrentIndex(self.page_indices[plugin_id])
        self._sync_header(spec)
        self.services.logger.set_status(f"Loaded {self.services.plugin_display_name(spec)}")
        if spec.source_type == "custom":
            self.services.plugin_state_manager.clear_failures(plugin_id)

    def _sync_header(self, spec: PluginSpec) -> None:
        language = self.services.i18n.current_language()
        self.page_title.setText(self.services.plugin_display_name(spec))
        self.page_description.setText(spec.localized_description(language))
        if spec.plugin_id == DASHBOARD_PLUGIN_ID:
            self.page_context.setText(self.services.i18n.tr("shell.dashboard", "Dashboard"))
        elif spec.plugin_id in SYSTEM_TOOLBAR_PLUGIN_IDS:
            self.page_context.setText(self.services.i18n.tr("shell.system_tools", "System Tools"))
        else:
            self.page_context.setText(spec.localized_category(language) or self.services.i18n.tr("shell.tools", "Tools"))

        is_pinnable = spec.plugin_id in {item.plugin_id for item in self.services.pinnable_plugin_specs()}
        self.pin_current_button.setVisible(is_pinnable)
        is_pinned = is_pinnable and self.services.is_quick_access(spec.plugin_id)
        self.pin_current_button.setChecked(is_pinned)
        self.pin_current_button.setIcon(
            self._named_icon(
                "unpin" if is_pinned else "pin",
                fallback=QStyle.StandardPixmap.SP_DialogCancelButton if is_pinned else QStyle.StandardPixmap.SP_DialogApplyButton,
            )
        )
        self.pin_current_button.setToolTip(
            self.services.i18n.tr("shell.unpin", "Unpin from quick access")
            if is_pinned
            else self.services.i18n.tr("shell.pin", "Pin to quick access")
        )

    def _suppress_duplicate_page_header(self, plugin_widget: QWidget, spec: PluginSpec) -> None:
        if spec.plugin_id == DASHBOARD_PLUGIN_ID:
            return

        layout = plugin_widget.layout()
        if layout is None:
            return

        hidden_labels = 0
        for index in range(min(layout.count(), 4)):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if not isinstance(widget, QLabel):
                continue

            text = self._normalized_text(widget.text())
            if not text:
                continue
            widget.hide()
            hidden_labels += 1
            if hidden_labels >= 2:
                break

    @staticmethod
    def _normalized_text(value: str) -> str:
        return " ".join(str(value or "").split()).strip().casefold()

    def _normalize_theme_styles(self, root_widget: QWidget) -> None:
        replacements = self._theme_style_replacements()
        widgets = [root_widget] + root_widget.findChildren(QWidget)
        for widget in widgets:
            current = widget.styleSheet()
            if not current:
                continue
            original = widget.property("_micro_original_stylesheet")
            if original is None:
                widget.setProperty("_micro_original_stylesheet", current)
                original = current
            themed = str(original)
            for source, target in replacements.items():
                themed = themed.replace(source, target)
            if themed != current:
                widget.setStyleSheet(themed)

    def _configure_tables(self, root_widget: QWidget) -> None:
        for table in [root_widget, *root_widget.findChildren(QWidget)]:
            if isinstance(table, (QTableView, QTableWidget)):
                try:
                    configure_resizable_table(table)
                except Exception:
                    continue

    def _theme_style_replacements(self) -> dict[str, str]:
        palette = self.services.theme_manager.current_palette()
        return {
            "color: palette(mid);": f"color: {palette.text_muted};",
            "border: 1px solid palette(mid);": f"border: 1px solid {palette.border};",
            "background: palette(base);": f"background: {palette.input_bg};",
            "#10232c": palette.text_primary,
            "#8a1f11": palette.danger,
            "#6a2218": palette.danger,
            "#43535c": palette.text_muted,
            "#56646b": palette.text_muted,
            "#34444d": palette.text_muted,
            "#6a382f": palette.text_muted,
            "#7c5c57": palette.text_muted,
            "#fffdf9": palette.surface_alt_bg,
            "#fffaf3": palette.surface_bg,
            "#fff7f2": palette.surface_alt_bg,
            "#eadfce": palette.border,
            "#e0d5c6": palette.border,
            "#efd3c9": palette.border,
            "#b63f26": palette.danger,
            "#9e341e": palette.danger,
            "#d79a8b": palette.border,
        }

    def _append_log(self, timestamp: str, level: str, message: str) -> None:
        self.log_output.appendPlainText(f"{timestamp} [{level}] {message}")

    def _apply_shell_texts(self) -> None:
        tr = self.services.i18n.tr
        self.search_input.setPlaceholderText(tr("shell.search", "Search..."))
        for plugin_id, label in (
            (DASHBOARD_PLUGIN_ID, tr("shell.dashboard", "Dashboard")),
            ("clip_manager", tr("shell.clipboard", "Clipboard")),
            ("workflow_studio", tr("shell.workflows", "Workflows")),
            ("plugin_manager", tr("shell.plugins", "Plugins")),
            ("about_center", tr("shell.about", "About")),
            ("settings_center", tr("shell.settings", "Settings")),
            (INSPECTOR_PLUGIN_ID, tr("shell.inspector", "Inspector")),
        ):
            button = self.system_toolbar_buttons.get(plugin_id)
            if button is not None:
                spec = self.plugin_by_id.get(plugin_id)
                if plugin_id == "plugin_manager":
                    button.setToolTip(label)
                else:
                    button.setToolTip(self.services.plugin_display_name(spec) if spec is not None else label)
                button.setIcon(self._system_component_icon(plugin_id))
        self.console_button.setToolTip(tr("shell.activity", "Activity"))
        self.console_button.setIcon(self._named_icon("console", fallback=QStyle.StandardPixmap.SP_FileDialogContentsView))
        self.terminal_button.setToolTip(tr("shell.terminal", "Terminal"))
        self.terminal_button.setIcon(self._named_icon("terminal", fallback=QStyle.StandardPixmap.SP_ComputerIcon))
        self._update_dock_title()
        if not self.page_title.text():
            self.page_title.setText(tr("shell.welcome.title", "Dashboard"))
        if not self.page_description.text():
            self.page_description.setText(tr("shell.welcome.description", "Pick a tool from the left to load it into the workspace."))
        self.status_label.setText(tr("shell.ready", "Ready"))
        self.placeholder_eyebrow.setText(tr("shell.placeholder.eyebrow", "Platform Layer"))
        self.placeholder_title.setText(tr("shell.placeholder.title", "The app core is built for desktop use."))
        self.placeholder_body.setText(
            tr(
                "shell.placeholder.body",
                "Themes, language switching, workflows, shortcuts, startup behavior, and tray integration now live directly in the app core.",
            )
        )

    def _register_shortcuts(self) -> None:
        self.services.shortcut_manager.register_action("focus_search", "Focus search", "Ctrl+K", self.focus_search)
        self.services.shortcut_manager.register_action("open_settings", "Open settings", "Ctrl+,", self.open_settings_center)
        self.services.shortcut_manager.register_action("open_workflows", "Open workflows", "Ctrl+Shift+W", lambda: self.open_plugin("workflow_studio"))
        self.services.shortcut_manager.register_action("open_clipboard", "Open clipboard", "Ctrl+Shift+V", lambda: self.open_plugin("clip_manager"))
        self.services.shortcut_manager.register_action("open_inspector", "Open inspector", "Ctrl+Shift+I", self.open_inspector_center)
        self.services.shortcut_manager.register_action(
            "show_clipboard_quick_panel",
            "Quick clipboard history",
            "Ctrl+Alt+V",
            self.services.clipboard_quick_panel.toggle,
            default_scope="global",
        )
        self.services.shortcut_manager.register_action("toggle_activity", "Toggle activity panel", "F12", self.toggle_activity_dock)
        self.services.shortcut_manager.register_action("toggle_terminal", "Toggle terminal panel", "Ctrl+`", self.toggle_terminal_dock)

    def focus_search(self):
        self.restore_from_tray()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def open_plugin_manager(self) -> None:
        self.open_plugin("settings_center")
        settings_page = self._plugin_content_widget("settings_center")
        if settings_page is not None:
            open_plugins_tab = getattr(settings_page, "open_plugins_tab", None)
            if callable(open_plugins_tab):
                open_plugins_tab()
        self._sync_system_toolbar_selection("settings_center")

    def open_settings_center(self) -> None:
        self.open_plugin("settings_center")
        settings_page = self._plugin_content_widget("settings_center")
        if settings_page is not None:
            open_general_tab = getattr(settings_page, "open_general_tab", None)
            if callable(open_general_tab):
                open_general_tab()
        self._sync_system_toolbar_selection("settings_center")

    def open_inspector_center(self) -> None:
        if not self.services.developer_mode_enabled():
            self.services.logger.set_status(self.services.i18n.tr("shell.inspector.locked", "Enable developer mode to use the inspector."))
            return {"opened": False, "reason": "developer_mode_disabled"}
        self.open_plugin(INSPECTOR_PLUGIN_ID)
        self._sync_system_toolbar_selection(INSPECTOR_PLUGIN_ID)
        return {"opened": True}

    def toggle_activity_dock(self):
        return self.toggle_dock_mode("activity")

    def toggle_terminal_dock(self):
        return self.toggle_dock_mode("terminal")

    def toggle_dock_mode(self, mode: str):
        mode = "terminal" if mode == "terminal" else "activity"
        if self.current_dock_mode == mode and self.log_dock.isVisible():
            self.log_dock.setVisible(False)
            self._sync_dock_buttons()
            return {"visible": False, "mode": mode}
        self._set_dock_mode(mode)
        self.log_dock.setVisible(True)
        if mode == "terminal":
            self.terminal_output.focus_prompt()
        self._sync_dock_buttons()
        self._schedule_save_activity_dock_state()
        return {"visible": True, "mode": mode}

    def _sync_console_button(self, visible: bool) -> None:
        self._sync_dock_buttons()

    def _sync_dock_buttons(self) -> None:
        visible = bool(self.log_dock.isVisible())
        self.console_button.blockSignals(True)
        self.console_button.setChecked(visible and self.current_dock_mode == "activity")
        self.console_button.blockSignals(False)
        self.terminal_button.blockSignals(True)
        self.terminal_button.setChecked(visible and self.current_dock_mode == "terminal")
        self.terminal_button.blockSignals(False)

    def _set_dock_mode(self, mode: str) -> None:
        mode = "terminal" if mode == "terminal" else "activity"
        self.current_dock_mode = mode
        self.dock_stack.setCurrentWidget(self.terminal_output if mode == "terminal" else self.log_output)
        self._update_dock_title()

    def _update_dock_title(self) -> None:
        if self.current_dock_mode == "terminal":
            self.log_dock.setWindowTitle(self.services.i18n.tr("shell.terminal", "Terminal"))
        else:
            self.log_dock.setWindowTitle(self.services.i18n.tr("shell.activity", "Activity"))

    def restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        return {"restored": True}

    def quit_from_tray(self):
        if not self._confirm_exit():
            return
        self._quitting = True
        self.close()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            if self.services.config.get("minimize_to_tray") and self.services.tray_manager.can_hide_to_tray():
                QTimer.singleShot(0, self._hide_to_tray)

    def closeEvent(self, event) -> None:
        if not self._quitting and self.services.config.get("close_to_tray") and self.services.tray_manager.can_hide_to_tray():
            event.ignore()
            self._hide_to_tray()
            return
        if not self._quitting and not self._confirm_exit():
            event.ignore()
            return
        self._quitting = True
        if hasattr(self, "terminal_output"):
            self.terminal_output.shutdown()
        super().closeEvent(event)
        if event.isAccepted():
            app = QApplication.instance()
            if app is not None:
                app.quit()

    def _hide_to_tray(self) -> None:
        self.hide()
        self.services.tray_manager.show_message(
            self.services.i18n.tr("tray.hidden.title", "Running in tray"),
            self.services.i18n.tr("tray.hidden.body", "Micro Toolkit is still running in the system tray."),
        )

    def reload_plugin_catalog(self, *, preferred_plugin_id: str | None = None) -> None:
        with self.loading_context(self.services.i18n.tr("shell.refreshing", "Refreshing...")):
            current_plugin_id = preferred_plugin_id or self.current_plugin_id
            self._refresh_specs()
            self.page_indices.clear()

            self.sidebar_tree.blockSignals(True)
            self._populate_sidebar()
            self.sidebar_tree.blockSignals(False)

            while self.page_stack.count():
                widget = self.page_stack.widget(0)
                self.page_stack.removeWidget(widget)
                widget.deleteLater()
            placeholder = self._build_placeholder_page()
            self.page_stack.addWidget(placeholder)
            self.page_stack.setCurrentWidget(placeholder)

            target_id = current_plugin_id if current_plugin_id in self.plugin_by_id else None
            if target_id is None:
                target_id = DASHBOARD_PLUGIN_ID if DASHBOARD_PLUGIN_ID in self.plugin_by_id else None
            if target_id is None and self.plugin_specs:
                target_id = self.plugin_specs[0].plugin_id
        if target_id is not None:
            self._select_plugin_item(target_id)
            self.open_plugin(target_id)

    def refresh_sidebar(self) -> None:
        current_plugin_id = self.current_plugin_id
        self._refresh_specs()
        self.sidebar_tree.blockSignals(True)
        self._populate_sidebar()
        self.sidebar_tree.blockSignals(False)
        if current_plugin_id is not None and current_plugin_id not in SYSTEM_TOOLBAR_PLUGIN_IDS:
            self._select_plugin_item(current_plugin_id)

    def refresh_plugin_visuals(self, plugin_id: str | None = None) -> None:
        self.refresh_sidebar()
        self._sync_system_toolbar_selection(self.current_plugin_id)
        if self.current_plugin_id is not None:
            spec = self.plugin_by_id.get(self.current_plugin_id)
            if spec is not None:
                self._sync_header(spec)
        self._apply_shell_texts()

    def _plugin_icon(self, spec: PluginSpec) -> QIcon:
        override = self.services.plugin_icon_override(spec)
        if override:
            path = Path(override)
            if path.exists():
                return QIcon(str(path))
            registry_icon = icon_from_name(override, self)
            if registry_icon is not None:
                return registry_icon
            qt_icon = self._qt_icon_from_name(override)
            if qt_icon is not None:
                return qt_icon
        for candidate in self._plugin_icon_candidates(spec):
            if candidate.exists():
                return QIcon(str(candidate))
        preferred = icon_from_name(spec.preferred_icon, self) or self._qt_icon_from_name(spec.preferred_icon)
        if preferred is not None:
            return preferred
        fallback = self._default_plugin_icon(spec)
        if fallback is not None:
            return fallback
        return self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    def _named_icon(self, icon_name: str, *, fallback: QStyle.StandardPixmap) -> QIcon:
        return icon_from_name(icon_name, self) or self.style().standardIcon(fallback)

    def _plugin_content_widget(self, plugin_id: str) -> QWidget | None:
        page_index = self.page_indices.get(plugin_id)
        if page_index is None:
            return None
        page_widget = self.page_stack.widget(page_index)
        if isinstance(page_widget, QScrollArea):
            inner = page_widget.widget()
            return inner if isinstance(inner, QWidget) else None
        return page_widget if isinstance(page_widget, QWidget) else None

    def _system_component_icon(self, plugin_id: str) -> QIcon:
        named = {
            DASHBOARD_PLUGIN_ID: "dashboard",
            "clip_manager": "clipboard",
            "workflow_studio": "workflow",
            "plugin_manager": "plugin",
            "about_center": "info",
            "settings_center": "settings",
            INSPECTOR_PLUGIN_ID: "inspect",
        }
        if plugin_id in named:
            fallback_map = {
                DASHBOARD_PLUGIN_ID: QStyle.StandardPixmap.SP_DirHomeIcon,
                "clip_manager": QStyle.StandardPixmap.SP_FileDialogContentsView,
                "workflow_studio": QStyle.StandardPixmap.SP_BrowserReload,
                "plugin_manager": QStyle.StandardPixmap.SP_FileIcon,
                "about_center": QStyle.StandardPixmap.SP_FileDialogInfoView,
                "settings_center": QStyle.StandardPixmap.SP_FileDialogDetailedView,
                INSPECTOR_PLUGIN_ID: QStyle.StandardPixmap.SP_FileDialogDetailedView,
            }
            return self._named_icon(
                named[plugin_id],
                fallback=fallback_map.get(plugin_id, QStyle.StandardPixmap.SP_FileIcon),
            )
        mapping = {
            DASHBOARD_PLUGIN_ID: QStyle.StandardPixmap.SP_DirHomeIcon,
            "clip_manager": QStyle.StandardPixmap.SP_FileDialogContentsView,
            "workflow_studio": QStyle.StandardPixmap.SP_BrowserReload,
            "about_center": QStyle.StandardPixmap.SP_FileDialogInfoView,
            "settings_center": QStyle.StandardPixmap.SP_FileDialogDetailedView,
            INSPECTOR_PLUGIN_ID: QStyle.StandardPixmap.SP_FileDialogDetailedView,
        }
        return self.style().standardIcon(mapping.get(plugin_id, QStyle.StandardPixmap.SP_FileIcon))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "loading_overlay"):
            self.loading_overlay.setGeometry(self.rect())
        self._schedule_save_activity_dock_state()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.log_dock and event.type() in {QEvent.Type.Resize, QEvent.Type.Move}:
            self._schedule_save_activity_dock_state()
        return super().eventFilter(watched, event)

    def _schedule_save_activity_dock_state(self) -> None:
        self._dock_state_timer.start()

    def _save_activity_dock_state(self) -> None:
        try:
            encoded = bytes(self.saveState()).hex()
            self.services.config.update_many(
                {
                    "activity_dock_state": encoded,
                    "activity_dock_visible": bool(self.log_dock.isVisible()),
                    "activity_dock_mode": self.current_dock_mode,
                }
            )
        except Exception:
            return

    def _restore_activity_dock_state(self) -> None:
        self._set_dock_mode(str(self.services.config.get("activity_dock_mode") or "activity"))
        raw = str(self.services.config.get("activity_dock_state") or "").strip()
        restored = False
        if raw:
            try:
                restored = self.restoreState(QByteArray.fromHex(raw.encode("ascii")))
            except Exception:
                restored = False
        visible = bool(self.services.config.get("activity_dock_visible"))
        if not restored:
            self.resizeDocks([self.log_dock], [120], Qt.Orientation.Vertical)
        self.log_dock.setVisible(visible)
        self._sync_dock_buttons()

    def _adjust_sidebar_width(self) -> None:
        fm = QFontMetrics(self.sidebar_tree.font())
        max_text = 0
        root = self.sidebar_tree.invisibleRootItem()
        for i in range(root.childCount()):
            top = root.child(i)
            max_text = max(max_text, fm.horizontalAdvance(top.text(0)))
            for j in range(top.childCount()):
                child = top.child(j)
                max_text = max(max_text, fm.horizontalAdvance(child.text(0)) + 22)
        width = max(236, min(312, max_text + 88))
        self.sidebar_card.setFixedWidth(width)

    def _sync_system_toolbar_selection(self, plugin_id: str | None) -> None:
        active_id = plugin_id if plugin_id in SYSTEM_TOOLBAR_PLUGIN_IDS else None
        if plugin_id == "settings_center":
            settings_page = self._plugin_content_widget("settings_center")
            current_section_id = getattr(settings_page, "current_section_id", None)
            if callable(current_section_id) and current_section_id() == "plugins":
                active_id = "plugin_manager"
        if active_id == INSPECTOR_PLUGIN_ID and not self._system_toolbar_button_visible(INSPECTOR_PLUGIN_ID):
            active_id = None
        for button_plugin_id, button in self.system_toolbar_buttons.items():
            button.blockSignals(True)
            button.setChecked(button_plugin_id == active_id)
            button.blockSignals(False)

    def _system_toolbar_button_visible(self, plugin_id: str) -> bool:
        if plugin_id == INSPECTOR_PLUGIN_ID:
            return self.services.developer_mode_enabled()
        return True

    def refresh_system_toolbar_visibility(self) -> None:
        for plugin_id, button in self.system_toolbar_buttons.items():
            button.setVisible(self._system_toolbar_button_visible(plugin_id))
        if not self._system_toolbar_button_visible(INSPECTOR_PLUGIN_ID) and self.current_plugin_id == INSPECTOR_PLUGIN_ID:
            self.open_settings_center()
        self._sync_system_toolbar_selection(self.current_plugin_id)

    def _plugin_icon_candidates(self, spec: PluginSpec) -> list[Path]:
        stem_name = spec.file_path.stem
        return [
            spec.file_path.with_suffix(".ico"),
            spec.file_path.parent / f"{stem_name}.ico",
            spec.file_path.parent / "plugin.ico",
            spec.container_path / "plugin.ico" if spec.container_path.exists() else spec.file_path.parent / "plugin.ico",
        ]

    def _group_icon(self, specs: list[PluginSpec]) -> QIcon:
        for candidate in self._group_icon_candidates(specs):
            if candidate.exists():
                return QIcon(str(candidate))
        return self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)

    def _group_icon_candidates(self, specs: list[PluginSpec]) -> list[Path]:
        candidates: list[Path] = []
        seen: set[Path] = set()
        for spec in specs:
            parent = spec.file_path.parent
            for candidate in (parent / "folder.ico", parent / "group.ico", spec.container_path / "folder.ico"):
                if candidate not in seen:
                    seen.add(candidate)
                    candidates.append(candidate)
        return candidates

    def _default_plugin_icon(self, spec: PluginSpec) -> QIcon | None:
        by_id = {
            "welcome_overview": "home",
            "clip_manager": "clipboard",
            "workflow_studio": "workflow",
            "about_center": "info",
            "settings_center": "settings",
            INSPECTOR_PLUGIN_ID: "inspect",
        }
        if spec.plugin_id in by_id:
            icon = icon_from_name(by_id[spec.plugin_id], self)
            if icon is not None:
                return icon
        category = (spec.category or "").lower()
        if "file" in category:
            return icon_from_name("folder-open", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        if "office" in category:
            return icon_from_name("office", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)
        if "media" in category:
            return icon_from_name("media", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        if "it" in category or "system" in category:
            return icon_from_name("computer", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        if "validation" in category or "analysis" in category:
            return icon_from_name("analytics", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        return None

    def _qt_icon_from_name(self, icon_name: str) -> QIcon | None:
        key = str(icon_name or "").strip()
        if not key:
            return None
        mapping = {
            "desktop": QStyle.StandardPixmap.SP_DesktopIcon,
            "computer": QStyle.StandardPixmap.SP_ComputerIcon,
            "folder": QStyle.StandardPixmap.SP_DirIcon,
            "folder-open": QStyle.StandardPixmap.SP_DirOpenIcon,
            "file": QStyle.StandardPixmap.SP_FileIcon,
            "settings": QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "clipboard": QStyle.StandardPixmap.SP_FileDialogContentsView,
            "workflow": QStyle.StandardPixmap.SP_BrowserReload,
            "analytics": QStyle.StandardPixmap.SP_DialogApplyButton,
            "office": QStyle.StandardPixmap.SP_FileDialogListView,
            "media": QStyle.StandardPixmap.SP_MediaPlay,
            "search": QStyle.StandardPixmap.SP_FileDialogContentsView,
            "info": QStyle.StandardPixmap.SP_FileDialogInfoView,
        }
        pixmap = mapping.get(key.lower())
        if pixmap is None:
            return None
        return self.style().standardIcon(pixmap)

    def _handle_language_change(self) -> None:
        self._apply_shell_texts()
        current_plugin_id = self.current_plugin_id
        self.refresh_sidebar()
        if current_plugin_id is not None and current_plugin_id in self.plugin_by_id:
            if current_plugin_id not in SYSTEM_TOOLBAR_PLUGIN_IDS:
                self._select_plugin_item(current_plugin_id)
            spec = self.plugin_by_id.get(current_plugin_id)
            if spec is not None:
                self._sync_header(spec)
        self._sync_system_toolbar_selection(current_plugin_id)

    def _handle_theme_change(self, _mode: str) -> None:
        for plugin_id, page_index in list(self.page_indices.items()):
            page = self.page_stack.widget(page_index)
            if isinstance(page, QScrollArea):
                widget = page.widget()
            else:
                widget = page
            if isinstance(widget, QWidget):
                self._normalize_theme_styles(widget)
        self.refresh_plugin_visuals()

    def _confirm_exit(self) -> bool:
        if not bool(self.services.config.get("confirm_on_exit")):
            return True
        confirmed, always_ask = confirm_action_with_option(
            self,
            title=self.services.i18n.tr("confirm.exit.title", "Exit Micro Toolkit?"),
            body=self.services.i18n.tr(
                "confirm.exit.body",
                "This will close the application window and stop background features for this session. Do you want to continue?",
            ),
            confirm_text=self.services.i18n.tr("confirm.exit.confirm", "Exit"),
            cancel_text=self.services.i18n.tr("confirm.cancel", "Cancel"),
            option_text=self.services.i18n.tr("confirm.exit.ask_always", "Always ask on exit"),
            option_checked=True,
        )
        self.services.config.set("confirm_on_exit", always_ask)
        return confirmed

    def _handle_plugin_open_error(self, spec: PluginSpec, exc: Exception) -> None:
        message = str(exc)
        self.services.log(f"Plugin '{spec.plugin_id}' failed to open: {message}", "ERROR")
        if spec.source_type == "custom":
            state = self.services.plugin_state_manager.record_failure(spec.plugin_id, message)
            if state.get("quarantined"):
                self.services.log(
                    f"Custom plugin '{spec.plugin_id}' was quarantined after repeated failures.",
                    "WARNING",
                )
                self.reload_plugin_catalog(preferred_plugin_id="settings_center")
        self.page_stack.setCurrentIndex(0)
        self.page_title.setText(spec.localized_name(self.services.i18n.current_language()))
        self.page_description.setText(message)
        self.placeholder_eyebrow.setText(self.services.i18n.tr("shell.activity", "Activity"))
        self.placeholder_title.setText(f"Could not open {spec.localized_name(self.services.i18n.current_language())}")
        self.placeholder_body.setText(message)
        self.services.logger.set_status(message)
