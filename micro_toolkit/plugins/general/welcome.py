from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from micro_toolkit.core.plugin_api import QtPlugin


class WelcomeOverviewPlugin(QtPlugin):
    plugin_id = "welcome_overview"
    name = "Welcome Overview"
    description = "Overview of the desktop shell, platform services, and plugin architecture."
    category = "General"
    translations = {
        "en": {
            "plugin.name": "Welcome Overview",
            "plugin.description": "Overview of the desktop shell, platform services, and plugin architecture.",
        },
        "ar": {
            "plugin.name": "نظرة ترحيبية",
            "plugin.description": "نظرة عامة على واجهة التطبيق وخدمات المنصة وبنية الإضافات.",
        },
    }

    def create_widget(self, services) -> QWidget:
        plugin_id = self.plugin_id
        def pt(key: str, default: str, **kwargs) -> str:
            return services.plugin_text(plugin_id, key, default, **kwargs)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(18)

        intro = QLabel(pt("title", "What Micro Toolkit already solves"))
        intro.setStyleSheet("font-size: 22px; font-weight: 700; color: #10232c;")
        layout.addWidget(intro)

        body = QLabel(
            pt(
                "body",
                "Micro Toolkit now owns both the plugin shell and the app platform layer: it discovers plugin metadata at startup, imports modules on demand, caches pages after first use, and provides shared services for workflows, settings, themes, shortcuts, startup behavior, and language switching.",
            )
        )
        body.setWordWrap(True)
        body.setStyleSheet("font-size: 14px; color: #34444d;")
        layout.addWidget(body)

        cards = [
            (pt("card.discovery.title", "Lazy discovery"), pt("card.discovery.body", "The sidebar is generated from AST metadata, so heavy libraries stay unloaded.")),
            (pt("card.pages.title", "Lazy pages"), pt("card.pages.body", "Each tool widget is created only when you open it for the first time.")),
            (pt("card.services.title", "Shared services"), pt("card.services.body", "Plugins receive config, logging, session history, workflows, commands, and background workers.")),
            (pt("card.platform.title", "Platform features"), pt("card.platform.body", "Themes, RTL-aware language switching, tray behavior, startup integration, and shortcuts now live in the app core.")),
        ]

        for title, text in cards:
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 16px; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 16, 16, 16)
            card_layout.setSpacing(8)

            heading = QLabel(title)
            heading.setStyleSheet("font-size: 16px; font-weight: 700; color: #10232c;")
            card_layout.addWidget(heading)

            paragraph = QLabel(text)
            paragraph.setWordWrap(True)
            paragraph.setStyleSheet("font-size: 13px; color: #41515a;")
            card_layout.addWidget(paragraph)

            layout.addWidget(card)

        foot = QLabel(
            pt(
                "foot",
                "Next step: keep refining the desktop UX and add more headless command support to plugins that need deeper workflow and CLI automation.",
            )
        )
        foot.setWordWrap(True)
        foot.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        foot.setStyleSheet("font-size: 13px; color: #56646b;")
        layout.addWidget(foot)
        layout.addStretch(1)
        return page
