from __future__ import annotations


DASHBOARD_PLUGIN_ID = "dash_hub"
INSPECTOR_PLUGIN_ID = "dev_lab"
SYSTEM_TOOLBAR_PLUGIN_IDS = (DASHBOARD_PLUGIN_ID, "clip_snip", "workflow_studio", "command_center", "about_info", INSPECTOR_PLUGIN_ID)
SYSTEM_COMPONENT_PLUGIN_IDS = frozenset(SYSTEM_TOOLBAR_PLUGIN_IDS)
NON_SIDEBAR_PLUGIN_IDS = frozenset(SYSTEM_TOOLBAR_PLUGIN_IDS)
UNSCROLLED_PLUGIN_IDS = frozenset()


def is_system_component(plugin_id: str) -> bool:
    return str(plugin_id or "").strip() in SYSTEM_COMPONENT_PLUGIN_IDS
