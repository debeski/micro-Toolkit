from __future__ import annotations

import json
import shutil
from pathlib import Path

from dngine.core.shell_registry import DASHBOARD_PLUGIN_ID
from dngine.core.storage_paths import DATABASE_FILENAME, LEGACY_DATABASE_FILENAME, resolve_runtime_path


DEFAULT_CONFIG = {
    "clip_monitor_enabled": True,
    "confirm_on_exit": True,
    "run_on_startup": False,
    "start_minimized": False,
    "appearance_mode": "light",
    "material_theme": "light_pink_500.xml",
    "material_color": "pink",
    "material_dark": False,
    "ui_font_family": "Amiri",
    "density_scale": 0,
    "grayscale": False,
    "invert_colors": False,
    "high_contrast": False,
    "ui_scaling": 1.0,
    "backup_schedule": "monthly",
    "backup_last_created_at": "",
    "default_output_path": "",
    "default_start_plugin": DASHBOARD_PLUGIN_ID,
    "language": "en",
    "hotkeys": {},
    "quick_access": [],
    "collapsed_groups": {},
    "plugin_overrides": {},
    "activity_dock_state": "",
    "activity_dock_visible": True,
    "activity_dock_mode": "activity",
    "developer_mode": False,
}

_BOOL_KEYS = {
    "clip_monitor_enabled",
    "confirm_on_exit",
    "run_on_startup",
    "start_minimized",
    "material_dark",
    "grayscale",
    "invert_colors",
    "high_contrast",
    "developer_mode",
}
_STR_KEYS = {"default_output_path", "default_start_plugin", "language", "appearance_mode", "material_theme", "material_color", "ui_font_family", "backup_schedule", "backup_last_created_at", "activity_dock_state", "activity_dock_mode"}
_NUM_KEYS = {"ui_scaling", "density_scale"}
_DICT_KEYS = {"hotkeys", "collapsed_groups", "plugin_overrides"}
_LIST_KEYS = {"quick_access"}


class AppConfig:
    def __init__(self, config_path: Path, default_output_path: Path, database_path: Path | None = None):
        self.config_path = Path(config_path)
        self.default_output_path = Path(default_output_path)
        self.database_path = Path(database_path) if database_path is not None else resolve_runtime_path(self.config_path.parent, DATABASE_FILENAME, LEGACY_DATABASE_FILENAME)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.default_output_path.mkdir(parents=True, exist_ok=True)
        self.config = DEFAULT_CONFIG.copy()
        self.config["default_output_path"] = str(self.default_output_path)
        self.load()

    def load(self) -> None:
        if not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(data, dict):
            self.config.update(data)
        if self._normalize_legacy_paths():
            self.save()

    def save(self) -> None:
        self.config_path.write_text(json.dumps(self.config, indent=4), encoding="utf-8")

    def get(self, key):
        return self.config.get(key)

    def set(self, key, value) -> None:
        self.config[key] = value
        self.save()

    def update_many(self, values: dict) -> None:
        changed = False
        for key, value in values.items():
            if self.config.get(key) != value:
                self.config[key] = value
                changed = True
        if changed:
            self.save()

    def get_all(self):
        return self.config

    def export_settings(self, path):
        try:
            Path(path).write_text(json.dumps(self.config, indent=4), encoding="utf-8")
            return True, "Settings exported successfully."
        except Exception as exc:
            return False, str(exc)

    def import_settings(self, path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            return False, f"Read error: {exc}"

        if not isinstance(data, dict):
            return False, "Invalid file format: expected a JSON object."

        validated = DEFAULT_CONFIG.copy()
        validated["default_output_path"] = self.config.get("default_output_path", str(self.default_output_path))
        warnings = []

        for key in DEFAULT_CONFIG:
            if key not in data:
                warnings.append(f"Missing key '{key}' - using default.")
                continue

            value = data[key]
            if key in _BOOL_KEYS and not isinstance(value, bool):
                warnings.append(f"Invalid type for '{key}' - expected bool, using default.")
                continue
            if key in _STR_KEYS and not isinstance(value, str):
                warnings.append(f"Invalid type for '{key}' - expected string, using default.")
                continue
            if key in _DICT_KEYS and not isinstance(value, dict):
                warnings.append(f"Invalid type for '{key}' - expected dict, using default.")
                continue
            if key in _LIST_KEYS and not isinstance(value, list):
                warnings.append(f"Invalid type for '{key}' - expected list, using default.")
                continue
            if key in _NUM_KEYS and not isinstance(value, (int, float)):
                warnings.append(f"Invalid type for '{key}' - expected numeric, using default.")
                continue
            validated[key] = value

        unknown = set(data.keys()) - set(DEFAULT_CONFIG.keys())
        if unknown:
            warnings.append(f"Ignored unknown keys: {', '.join(sorted(unknown))}")

        self.config = validated
        self.save()

        message = "Settings imported successfully."
        if warnings:
            message += "\n" + "\n".join(warnings)
        return True, message

    def backup_now(self, log_cb=print):
        base = str(self.config.get("default_output_path", "")).strip()
        if not base:
            return False, "No default output path set."

        backup_dir = Path(base) / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        copied = []
        if self.config_path.exists():
            destination = backup_dir / self.config_path.name
            shutil.copy2(self.config_path, destination)
            copied.append(str(destination))

        if self.database_path.exists():
            destination = backup_dir / self.database_path.name
            shutil.copy2(self.database_path, destination)
            copied.append(str(destination))

        logs_dir = self.config_path.parent.parent / "logs"
        if logs_dir.is_dir():
            destination = backup_dir / "logs"
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(logs_dir, destination)
            copied.append(str(destination))

        return True, f"Backup complete. {len(copied)} items copied to {backup_dir}."

    def flush_backup(self):
        base = str(self.config.get("default_output_path", "")).strip()
        if not base:
            return False, "No default output path set."

        backup_dir = Path(base) / "backups"
        if backup_dir.is_dir():
            shutil.rmtree(backup_dir)
            return True, f"Flushed backup directory: {backup_dir}"
        return False, "No backup directory found."

    def _normalize_legacy_paths(self) -> bool:
        changed = False
        configured_output = str(self.config.get("default_output_path") or "").strip()
        if configured_output:
            output_path = Path(configured_output)
            if output_path.name == "output" and output_path.parent.name == "qt_app":
                self.config["default_output_path"] = str(self.default_output_path)
                changed = True
        return changed

    def migrate_plugin_ids(self, mapping: dict[str, str]) -> bool:
        changed = False
        quick_access = self.config.get("quick_access")
        if isinstance(quick_access, list):
            updated = [mapping.get(str(item), str(item)) for item in quick_access]
            if updated != quick_access:
                self.config["quick_access"] = updated
                changed = True

        overrides = self.config.get("plugin_overrides")
        if isinstance(overrides, dict):
            updated_overrides = {}
            for key, value in overrides.items():
                updated_overrides[mapping.get(str(key), str(key))] = value
            if updated_overrides != overrides:
                self.config["plugin_overrides"] = updated_overrides
                changed = True

        if changed:
            self.save()
        return changed
