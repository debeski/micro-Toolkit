from __future__ import annotations

import json
import shutil
from pathlib import Path


DEFAULT_CONFIG = {
    "minimize_to_tray": False,
    "close_to_tray": False,
    "run_on_startup": False,
    "start_minimized": False,
    "appearance_mode": "system",
    "grayscale": False,
    "invert_colors": False,
    "high_contrast": False,
    "ui_scaling": 1.0,
    "default_output_path": "",
    "language": "en",
    "hotkeys": {},
}

_BOOL_KEYS = {
    "minimize_to_tray",
    "close_to_tray",
    "run_on_startup",
    "start_minimized",
    "grayscale",
    "invert_colors",
    "high_contrast",
}
_STR_KEYS = {"default_output_path", "language", "appearance_mode"}
_NUM_KEYS = {"ui_scaling"}
_DICT_KEYS = {"hotkeys"}


class AppConfig:
    def __init__(self, config_path: Path, default_output_path: Path):
        self.config_path = Path(config_path)
        self.default_output_path = Path(default_output_path)
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

        database_path = self.config_path.parent / "micro_toolkit.db"
        if database_path.exists():
            destination = backup_dir / database_path.name
            shutil.copy2(database_path, destination)
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
