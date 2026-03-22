from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal


RTL_LANGUAGES = {"ar", "fa", "he", "ur"}


class TranslationManager(QObject):
    language_changed = Signal(str)
    direction_changed = Signal(object)

    def __init__(self, config, locales_root: Path):
        super().__init__()
        self.config = config
        self.locales_root = Path(locales_root)
        self._catalogs = self._load_catalogs()

    def available_languages(self) -> list[tuple[str, str]]:
        supported = []
        for code, data in sorted(self._catalogs.items()):
            supported.append((code, data.get("_meta", {}).get("label", code)))
        return supported or [("en", "English")]

    def current_language(self) -> str:
        language = str(self.config.get("language") or "en").strip().lower()
        return language if language in self._catalogs else "en"

    def set_language(self, language: str) -> None:
        normalized = (language or "en").strip().lower()
        if normalized not in self._catalogs:
            normalized = "en"
        self.config.set("language", normalized)
        self.language_changed.emit(normalized)
        self.direction_changed.emit(self.layout_direction())

    def tr(self, key: str, default: str | None = None, **kwargs) -> str:
        catalog = self._catalogs.get(self.current_language(), {})
        text = catalog.get(key)
        if text is None:
            text = self._catalogs.get("en", {}).get(key, default if default is not None else key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except Exception:
                pass
        return text

    def is_rtl(self) -> bool:
        return self.current_language() in RTL_LANGUAGES

    def layout_direction(self) -> Qt.LayoutDirection:
        return Qt.LayoutDirection.RightToLeft if self.is_rtl() else Qt.LayoutDirection.LeftToRight

    def apply(self, app) -> None:
        app.setLayoutDirection(self.layout_direction())
        self.language_changed.emit(self.current_language())
        self.direction_changed.emit(self.layout_direction())

    def _load_catalogs(self) -> dict[str, dict]:
        catalogs: dict[str, dict] = {}
        if not self.locales_root.exists():
            return {"en": {}}
        for file_path in sorted(self.locales_root.glob("*.json")):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                catalogs[file_path.stem.lower()] = payload
        return catalogs or {"en": {}}
