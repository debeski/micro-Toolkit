from __future__ import annotations


DASHBOARD_PLUGIN_ID = "welcome_overview"
SYSTEM_TOOLBAR_PLUGIN_IDS = (DASHBOARD_PLUGIN_ID, "clip_manager", "workflow_studio", "about_center", "settings_center")
SYSTEM_COMPONENT_PLUGIN_IDS = frozenset(SYSTEM_TOOLBAR_PLUGIN_IDS)
NON_SIDEBAR_PLUGIN_IDS = frozenset(SYSTEM_TOOLBAR_PLUGIN_IDS)
UNSCROLLED_PLUGIN_IDS = frozenset()


def is_system_component(plugin_id: str) -> bool:
    return str(plugin_id or "").strip() in SYSTEM_COMPONENT_PLUGIN_IDS
