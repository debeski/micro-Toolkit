from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.plugin_manager import PluginSpec
from micro_toolkit.core.services import AppServices

PLUGIN_ID_ROLE = Qt.ItemDataRole.UserRole + 1


class MicroToolkitWindow(QMainWindow):
    def __init__(self, services: AppServices, *, initial_plugin_id: str | None = None):
        super().__init__()
        self.services = services
        self.plugin_manager = self.services.plugin_manager
        self.plugin_specs = self.plugin_manager.sidebar_plugins()
        self.plugin_by_id = {spec.plugin_id: spec for spec in self.plugin_specs}
        self.page_indices: dict[str, int] = {}
        self.initial_plugin_id = initial_plugin_id
        self._quitting = False

        self.setWindowTitle("Micro Toolkit")
        self.resize(1360, 860)
        self.setMinimumSize(1180, 720)

        self._build_ui()
        self._bind_signals()
        self._populate_sidebar()
        self._open_initial_page()
        self._register_shortcuts()
        self._apply_shell_texts()
        self.services.attach_main_window(self)

    def _build_ui(self) -> None:
        central = QWidget(self)
        outer_layout = QHBoxLayout(central)
        outer_layout.setContentsMargins(18, 18, 18, 18)
        outer_layout.setSpacing(18)
        self.setCentralWidget(central)

        sidebar_card = QFrame()
        sidebar_card.setObjectName("SidebarCard")
        sidebar_card.setFixedWidth(320)
        sidebar_layout = QVBoxLayout(sidebar_card)
        sidebar_layout.setContentsMargins(18, 18, 18, 18)
        sidebar_layout.setSpacing(14)

        self.sidebar_eyebrow = QLabel()
        self.sidebar_eyebrow.setObjectName("SectionEyebrow")
        sidebar_layout.addWidget(self.sidebar_eyebrow)

        self.app_title_label = QLabel("Micro Toolkit")
        self.app_title_label.setObjectName("AppTitle")
        sidebar_layout.addWidget(self.app_title_label)

        self.subtitle_label = QLabel()
        self.subtitle_label.setWordWrap(True)
        sidebar_layout.addWidget(self.subtitle_label)

        self.search_input = QLineEdit()
        sidebar_layout.addWidget(self.search_input)

        self.sidebar_tree = QTreeWidget()
        self.sidebar_tree.setHeaderHidden(True)
        self.sidebar_tree.setRootIsDecorated(False)
        self.sidebar_tree.setIndentation(14)
        self.sidebar_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sidebar_tree.setUniformRowHeights(True)
        sidebar_layout.addWidget(self.sidebar_tree, 1)

        self.sidebar_note = QLabel()
        self.sidebar_note.setWordWrap(True)
        self.sidebar_note.setStyleSheet("color: #56646b; font-size: 12px;")
        sidebar_layout.addWidget(self.sidebar_note)

        content_shell = QWidget()
        content_layout = QVBoxLayout(content_shell)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(18)

        header_card = QFrame()
        header_card.setObjectName("HeaderCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(6)

        self.page_eyebrow = QLabel()
        self.page_eyebrow.setObjectName("SectionEyebrow")
        header_layout.addWidget(self.page_eyebrow)

        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        header_layout.addWidget(self.page_title)

        self.page_description = QLabel()
        self.page_description.setWordWrap(True)
        self.page_description.setStyleSheet("color: #56646b;")
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
        self.log_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(800)
        self.log_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.log_dock.setWidget(self.log_output)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)

        status = QStatusBar()
        self.status_label = QLabel()
        status.addPermanentWidget(self.status_label, 1)
        self.setStatusBar(status)

        placeholder = self._build_placeholder_page()
        self.page_stack.addWidget(placeholder)
        self.page_stack.setCurrentWidget(placeholder)

    def _bind_signals(self) -> None:
        self.search_input.textChanged.connect(self._apply_filter)
        self.sidebar_tree.itemSelectionChanged.connect(self._handle_selection_change)
        self.services.logger.message_logged.connect(self._append_log)
        self.services.logger.status_changed.connect(self.status_label.setText)
        self.services.i18n.language_changed.connect(self._handle_language_change)

    def _build_placeholder_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        self.placeholder_eyebrow = QLabel()
        self.placeholder_eyebrow.setObjectName("SectionEyebrow")
        layout.addWidget(self.placeholder_eyebrow)

        self.placeholder_title = QLabel()
        self.placeholder_title.setStyleSheet("font-size: 28px; font-weight: 700; color: #10232c;")
        layout.addWidget(self.placeholder_title)

        self.placeholder_body = QLabel()
        self.placeholder_body.setWordWrap(True)
        self.placeholder_body.setStyleSheet("font-size: 15px; color: #34444d; line-height: 1.4;")
        layout.addWidget(self.placeholder_body)
        layout.addStretch(1)
        return page

    def _populate_sidebar(self) -> None:
        categories: dict[str, list[PluginSpec]] = defaultdict(list)
        standalone_specs: list[PluginSpec] = []
        language = self.services.i18n.current_language()
        for spec in self.plugin_specs:
            if spec.standalone:
                standalone_specs.append(spec)
            else:
                categories[spec.localized_category(language)].append(spec)

        for spec in sorted(standalone_specs, key=lambda item: item.name.lower()):
            item = QTreeWidgetItem([spec.localized_name(language)])
            item.setToolTip(0, spec.localized_description(language))
            item.setData(0, PLUGIN_ID_ROLE, spec.plugin_id)
            self.sidebar_tree.addTopLevelItem(item)

        for category in sorted(categories):
            category_item = QTreeWidgetItem([category])
            category_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            category_item.setFirstColumnSpanned(True)
            category_item.setData(0, PLUGIN_ID_ROLE, None)
            category_item.setExpanded(True)
            self.sidebar_tree.addTopLevelItem(category_item)

            for spec in sorted(categories[category], key=lambda item: item.name.lower()):
                child = QTreeWidgetItem([spec.localized_name(language)])
                child.setToolTip(0, spec.localized_description(language))
                child.setData(0, PLUGIN_ID_ROLE, spec.plugin_id)
                category_item.addChild(child)

        self.sidebar_tree.expandAll()

    def _open_initial_page(self) -> None:
        initial_id = self.initial_plugin_id if self.initial_plugin_id in self.plugin_by_id else None
        if initial_id is None:
            initial_id = "welcome_overview" if "welcome_overview" in self.plugin_by_id else None
        if initial_id is None and self.plugin_specs:
            initial_id = self.plugin_specs[0].plugin_id
        if initial_id is not None:
            self._select_plugin_item(initial_id)
            self.open_plugin(initial_id)

    def _select_plugin_item(self, plugin_id: str) -> None:
        root = self.sidebar_tree.invisibleRootItem()
        for i in range(root.childCount()):
            top_item = root.child(i)
            if top_item.data(0, PLUGIN_ID_ROLE) == plugin_id:
                self.sidebar_tree.setCurrentItem(top_item)
                return
            for j in range(top_item.childCount()):
                item = top_item.child(j)
                if item.data(0, PLUGIN_ID_ROLE) == plugin_id:
                    self.sidebar_tree.setCurrentItem(item)
                    return

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        root = self.sidebar_tree.invisibleRootItem()
        for i in range(root.childCount()):
            category_item = root.child(i)
            category_plugin_id = category_item.data(0, PLUGIN_ID_ROLE)
            if category_plugin_id:
                spec = self.plugin_by_id.get(category_plugin_id)
                haystack = " ".join(
                    [
                        spec.localized_name(self.services.i18n.current_language()) if spec else "",
                        spec.localized_description(self.services.i18n.current_language()) if spec else "",
                    ]
                ).lower()
                hide_item = bool(needle) and needle not in haystack
                category_item.setHidden(hide_item)
                continue
            visible_children = 0
            for j in range(category_item.childCount()):
                child = category_item.child(j)
                plugin_id = child.data(0, PLUGIN_ID_ROLE)
                spec = self.plugin_by_id.get(plugin_id)
                haystack = " ".join(
                    [
                        spec.localized_name(self.services.i18n.current_language()) if spec else "",
                        spec.localized_description(self.services.i18n.current_language()) if spec else "",
                        spec.localized_category(self.services.i18n.current_language()) if spec else "",
                    ]
                ).lower()
                hide_item = bool(needle) and needle not in haystack
                child.setHidden(hide_item)
                if not hide_item:
                    visible_children += 1
            category_item.setHidden(visible_children == 0)
            category_item.setExpanded(True)

    def _handle_selection_change(self) -> None:
        item = self.sidebar_tree.currentItem()
        if item is None:
            return
        plugin_id = item.data(0, PLUGIN_ID_ROLE)
        if plugin_id:
            self.open_plugin(plugin_id)

    def open_plugin(self, plugin_id: str) -> None:
        spec = self.plugin_by_id.get(plugin_id)
        if spec is None:
            return

        if plugin_id not in self.page_indices:
            plugin = self.plugin_manager.load_plugin(plugin_id)
            plugin_widget = plugin.create_widget(self.services)

            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll_area.setWidget(plugin_widget)

            page_index = self.page_stack.addWidget(scroll_area)
            self.page_indices[plugin_id] = page_index

        self.page_stack.setCurrentIndex(self.page_indices[plugin_id])
        localized_name = spec.localized_name(self.services.i18n.current_language())
        self.page_title.setText(localized_name)
        self.page_description.setText(spec.localized_description(self.services.i18n.current_language()))
        self.services.logger.set_status(f"Loaded {localized_name}")

    def _append_log(self, timestamp: str, level: str, message: str) -> None:
        self.log_output.appendPlainText(f"{timestamp} [{level}] {message}")

    def _apply_shell_texts(self) -> None:
        tr = self.services.i18n.tr
        self.sidebar_eyebrow.setText(tr("shell.sidebar.eyebrow", "Desktop Suite"))
        self.subtitle_label.setText(
            tr(
                "shell.subtitle",
                "A fast, native-feeling desktop toolkit with lazy plugin discovery, translated shell chrome, tray integration, and cached tool pages.",
            )
        )
        self.search_input.setPlaceholderText(tr("shell.search", "Filter tools..."))
        self.sidebar_note.setText(
            tr(
                "shell.note",
                "Pages are created only when you open them. Modules stay unloaded until the matching tool is requested.",
            )
        )
        self.page_eyebrow.setText(tr("shell.current_tool", "Current Tool"))
        self.log_dock.setWindowTitle(tr("shell.activity", "Activity"))
        if not self.page_title.text():
            self.page_title.setText(tr("shell.welcome.title", "Welcome"))
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
        current_item = self.sidebar_tree.currentItem()
        if current_item is not None:
            plugin_id = current_item.data(0, PLUGIN_ID_ROLE)
            if plugin_id:
                spec = self.plugin_by_id.get(plugin_id)
                if spec is not None:
                    self.page_title.setText(spec.localized_name(self.services.i18n.current_language()))
                    self.page_description.setText(spec.localized_description(self.services.i18n.current_language()))

    def _register_shortcuts(self) -> None:
        self.services.shortcut_manager.register_action("focus_search", "Focus search", "Ctrl+K", self.focus_search)
        self.services.shortcut_manager.register_action("open_settings", "Open settings", "Ctrl+,", lambda: self.open_plugin("settings_center"))
        self.services.shortcut_manager.register_action("open_workflows", "Open workflows", "Ctrl+Shift+W", lambda: self.open_plugin("workflow_studio"))
        self.services.shortcut_manager.register_action("open_clipboard", "Open clipboard", "Ctrl+Shift+V", lambda: self.open_plugin("clip_manager"))
        self.services.shortcut_manager.register_action(
            "show_clipboard_quick_panel",
            "Quick clipboard history",
            "Ctrl+Alt+V",
            self.services.clipboard_quick_panel.toggle,
            default_scope="global",
        )
        self.services.shortcut_manager.register_action("toggle_activity", "Toggle activity panel", "F12", self.toggle_activity_dock)

    def focus_search(self):
        self.restore_from_tray()
        self.search_input.setFocus()
        self.search_input.selectAll()
        return {"focused": "search"}

    def toggle_activity_dock(self):
        self.log_dock.setVisible(not self.log_dock.isVisible())
        return {"visible": self.log_dock.isVisible()}

    def restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        return {"restored": True}

    def quit_from_tray(self):
        self._quitting = True
        self.close()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            if self.services.config.get("minimize_to_tray") and self.services.tray_manager.tray_icon is not None:
                QTimer.singleShot(0, self._hide_to_tray)

    def closeEvent(self, event) -> None:
        if not self._quitting and self.services.config.get("close_to_tray") and self.services.tray_manager.tray_icon is not None:
            event.ignore()
            self._hide_to_tray()
            return
        self._quitting = True
        super().closeEvent(event)

    def _hide_to_tray(self) -> None:
        self.hide()
        self.services.tray_manager.show_message(
            self.services.i18n.tr("tray.hidden.title", "Running in tray"),
            self.services.i18n.tr("tray.hidden.body", "Micro Toolkit is still running in the system tray."),
        )

    def reload_plugin_catalog(self, *, preferred_plugin_id: str | None = None) -> None:
        current_plugin_id = preferred_plugin_id
        current_item = self.sidebar_tree.currentItem()
        if current_plugin_id is None and current_item is not None:
            current_plugin_id = current_item.data(0, PLUGIN_ID_ROLE)

        self.plugin_specs = self.plugin_manager.sidebar_plugins()
        self.plugin_by_id = {spec.plugin_id: spec for spec in self.plugin_specs}
        self.page_indices.clear()

        self.sidebar_tree.blockSignals(True)
        self.sidebar_tree.clear()
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
            target_id = "settings_center" if "settings_center" in self.plugin_by_id else None
        if target_id is None and self.plugin_specs:
            target_id = self.plugin_specs[0].plugin_id
        if target_id is not None:
            self._select_plugin_item(target_id)
            self.open_plugin(target_id)
        self._apply_shell_texts()

    def _handle_language_change(self) -> None:
        current_item = self.sidebar_tree.currentItem()
        current_plugin_id = current_item.data(0, PLUGIN_ID_ROLE) if current_item is not None else None
        self.reload_plugin_catalog(preferred_plugin_id=current_plugin_id)
