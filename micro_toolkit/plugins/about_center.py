from __future__ import annotations

import platform
from importlib import metadata

import psutil
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit import __version__
from micro_toolkit.core.icon_registry import icon_from_name
from micro_toolkit.core.page_style import card_style, muted_text_style, page_title_style, section_title_style
from micro_toolkit.core.plugin_api import QtPlugin


class AboutCenterPlugin(QtPlugin):
    plugin_id = "about_center"
    name = "About"
    description = "Project information, support links, runtime versions, and system details."
    category = ""
    standalone = True
    preferred_icon = "info"

    def create_widget(self, services) -> QWidget:
        return AboutCenterPage(services, self.plugin_id)


class AboutCenterPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._build_ui()
        self._apply_texts()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(18)

        self.hero_card = self._make_card()
        hero_layout = QVBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(20, 20, 20, 20)
        hero_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 30px; font-weight: 700;")
        title_row.addWidget(self.title_label, 1)

        self.github_button = QToolButton()
        self.github_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.github_button.setIcon(
            icon_from_name("github", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView)
        )
        self.github_button.setAutoRaise(True)
        self.github_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/debeski/micro-Toolkit"))
        )
        title_row.addWidget(self.github_button, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(title_row)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        hero_layout.addWidget(self.summary_label)

        self.identity_label = QLabel()
        self.identity_label.setWordWrap(True)
        hero_layout.addWidget(self.identity_label)
        outer.addWidget(self.hero_card)

        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(14)
        info_grid.setVerticalSpacing(14)

        self.project_card = self._make_card()
        project_layout = QVBoxLayout(self.project_card)
        project_layout.setContentsMargins(18, 16, 18, 16)
        project_layout.setSpacing(8)
        self.project_heading = QLabel()
        self.project_heading.setStyleSheet("font-size: 18px; font-weight: 700;")
        project_layout.addWidget(self.project_heading)
        self.project_body = QLabel()
        self.project_body.setWordWrap(True)
        project_layout.addWidget(self.project_body)
        info_grid.addWidget(self.project_card, 0, 0)

        self.license_card = self._make_card()
        license_layout = QVBoxLayout(self.license_card)
        license_layout.setContentsMargins(18, 16, 18, 16)
        license_layout.setSpacing(8)
        self.license_heading = QLabel()
        self.license_heading.setStyleSheet("font-size: 18px; font-weight: 700;")
        license_layout.addWidget(self.license_heading)
        self.license_body = QLabel()
        self.license_body.setWordWrap(True)
        license_layout.addWidget(self.license_body)
        info_grid.addWidget(self.license_card, 0, 1)

        self.system_card = self._make_card()
        system_layout = QVBoxLayout(self.system_card)
        system_layout.setContentsMargins(18, 16, 18, 16)
        system_layout.setSpacing(8)
        self.system_heading = QLabel()
        self.system_heading.setStyleSheet("font-size: 18px; font-weight: 700;")
        system_layout.addWidget(self.system_heading)
        self.system_body = QLabel()
        self.system_body.setWordWrap(True)
        system_layout.addWidget(self.system_body)
        info_grid.addWidget(self.system_card, 1, 0)

        self.support_card = self._make_card()
        support_layout = QVBoxLayout(self.support_card)
        support_layout.setContentsMargins(18, 16, 18, 16)
        support_layout.setSpacing(8)
        self.support_heading = QLabel()
        self.support_heading.setStyleSheet("font-size: 18px; font-weight: 700;")
        support_layout.addWidget(self.support_heading)
        self.support_body = QLabel()
        self.support_body.setWordWrap(True)
        self.support_body.setOpenExternalLinks(True)
        support_layout.addWidget(self.support_body)
        info_grid.addWidget(self.support_card, 1, 1)

        outer.addLayout(info_grid)

        self.libs_card = self._make_card()
        libs_layout = QVBoxLayout(self.libs_card)
        libs_layout.setContentsMargins(18, 16, 18, 16)
        libs_layout.setSpacing(10)
        self.libs_heading = QLabel()
        self.libs_heading.setStyleSheet("font-size: 18px; font-weight: 700;")
        libs_layout.addWidget(self.libs_heading)

        self.libs_table = QTableWidget(0, 2)
        self.libs_table.setAlternatingRowColors(True)
        self.libs_table.verticalHeader().setVisible(False)
        self.libs_table.horizontalHeader().setStretchLastSection(True)
        self.libs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.libs_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        libs_layout.addWidget(self.libs_table, 1)
        outer.addWidget(self.libs_card, 1)

    def _apply_texts(self) -> None:
        self._apply_theme_styles()
        self.title_label.setText(self._pt("title", "About Micro Toolkit"))
        self.summary_label.setText(
            self._pt(
                "summary",
                "Micro Toolkit is a fast desktop companion for office and home use, built around a dynamic plugin engine, lazy loading, app-level services, multilingual UI support, workflow automation, and desktop-native integrations.",
            )
        )
        self.identity_label.setText(
            self._pt(
                "identity",
                "DeBeski (micro)\nLibyan Economic Information and Documentation Center\n2026",
            )
        )
        self.project_heading.setText(self._pt("project.heading", "Project"))
        self.project_body.setText(
            self._pt(
                "project.body",
                "The app shell, plugin discovery, translations, workflows, elevated broker, hotkey helper, and runtime services are all part of the same underlying desktop codebase rather than stitched-on external layers.",
            )
        )
        self.license_heading.setText(self._pt("license.heading", "License"))
        self.license_body.setText(self._pt("license.body", "NON-COMMERCIAL LICENSE"))
        self.system_heading.setText(self._pt("system.heading", "System"))
        self.system_body.setText(self._system_summary())
        self.support_heading.setText(self._pt("support.heading", "Support"))
        self.support_body.setText(
            self._pt(
                "support.body",
                'Report issues at: <a href="https://github.com/debeski/micro-Toolkit/issues">github.com/debeski/micro-Toolkit/issues</a>',
            )
        )
        self.libs_heading.setText(self._pt("libs.heading", "Used Tools and Libraries"))
        self.github_button.setToolTip(self._pt("github.tooltip", "Open GitHub repository"))
        self._populate_libs()

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_texts()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        for frame in (
            self.hero_card,
            self.project_card,
            self.license_card,
            self.system_card,
            self.support_card,
            self.libs_card,
        ):
            frame.setStyleSheet(card_style(palette))
        self.title_label.setStyleSheet(page_title_style(palette))
        self.summary_label.setStyleSheet(muted_text_style(palette))
        self.identity_label.setStyleSheet(muted_text_style(palette))
        for heading in (
            self.project_heading,
            self.license_heading,
            self.system_heading,
            self.support_heading,
            self.libs_heading,
        ):
            heading.setStyleSheet(section_title_style(palette))
        for body in (
            self.project_body,
            self.license_body,
            self.system_body,
            self.support_body,
        ):
            body.setStyleSheet(muted_text_style(palette))

    def _populate_libs(self) -> None:
        rows = [
            ("Micro Toolkit", __version__),
            ("Python", platform.python_version()),
            ("PySide6", self._version("PySide6")),
            ("numpy", self._version("numpy")),
            ("pandas", self._version("pandas")),
            ("openpyxl", self._version("openpyxl")),
            ("python-docx", self._version("python-docx")),
            ("PyPDF2", self._version("PyPDF2")),
            ("Pillow", self._version("Pillow")),
            ("pillow-heif", self._version("pillow-heif")),
            ("cryptography", self._version("cryptography")),
            ("python-dateutil", self._version("python-dateutil")),
            ("qt-material", self._version("qt-material")),
            ("psutil", self._version("psutil")),
            ("keyboard", self._version("keyboard")),
            ("Bundled SVG icons", "Bootstrap Icons"),
        ]
        self.libs_table.setRowCount(len(rows))
        self.libs_table.setHorizontalHeaderLabels(
            [
                self._pt("libs.name", "Component"),
                self._pt("libs.version", "Version"),
            ]
        )
        for row, (name, version) in enumerate(rows):
            self.libs_table.setItem(row, 0, QTableWidgetItem(name))
            self.libs_table.setItem(row, 1, QTableWidgetItem(version))

    def _system_summary(self) -> str:
        total_memory = psutil.virtual_memory().total / (1024 ** 3)
        cpu_name = platform.processor() or platform.machine() or self._pt("system.unknown", "Unknown")
        return "\n".join(
            [
                f"{self._pt('system.os', 'Operating system')}: {platform.system()} {platform.release()}",
                f"{self._pt('system.cpu', 'Processor')}: {cpu_name}",
                f"{self._pt('system.memory', 'Memory')}: {total_memory:.1f} GB",
                f"{self._pt('system.runtime', 'Runtime')}: Python {platform.python_version()}",
            ]
        )

    @staticmethod
    def _version(package_name: str) -> str:
        try:
            return metadata.version(package_name)
        except metadata.PackageNotFoundError:
            return "Not installed"
        except Exception:
            return "Unavailable"

    def _make_card(self) -> QFrame:
        return QFrame()
