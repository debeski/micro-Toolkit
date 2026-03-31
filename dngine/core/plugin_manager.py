from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dngine.core.builtin_manifest import load_builtin_manifest, sha256_file, verify_manifest_integrity
from dngine.core.plugin_api import QtPlugin
from dngine.core.plugin_security import scan_plugin_path


@dataclass(frozen=True)
class PluginSpec:
    plugin_id: str
    name: str
    description: str
    category: str
    version: str
    standalone: bool
    allow_name_override: bool
    allow_icon_override: bool
    preferred_icon: str
    file_path: Path
    module_name: str
    class_name: str
    source_root: Path
    source_type: str
    container_path: Path
    package_name: str
    primary_relative_path: str
    enabled: bool = True
    hidden: bool = False
    trusted: bool = True
    quarantined: bool = False
    signature_status: str = "none"
    signer: str = ""
    risk_level: str = "low"
    risk_summary: str = ""
    last_error: str = ""
    failure_count: int = 0
    locale_bundles: dict[str, dict[str, str]] = field(default_factory=dict)

    def localized_name(self, language: str) -> str:
        bundle = self.locale_bundles.get(language, {})
        return bundle.get("plugin.name", self.name)

    def localized_description(self, language: str) -> str:
        bundle = self.locale_bundles.get(language, {})
        return bundle.get("plugin.description", self.description)

    def localized_category(self, language: str) -> str:
        bundle = self.locale_bundles.get(language, {})
        return bundle.get("plugin.category", self.category)


PLUGIN_DEFAULTS = {
    "plugin_id": None,
    "name": None,
    "description": "",
    "category": "General",
    "version": "0.1.0",
    "standalone": False,
    "allow_name_override": True,
    "allow_icon_override": True,
    "preferred_icon": "",
    "preferred_qt_icon": "",
}


def _inherits_qt_plugin(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "QtPlugin":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "QtPlugin":
            return True
    return False


def _extract_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_bool(node: ast.AST) -> bool | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return None


def _extract_string_map(node: ast.AST) -> dict[str, str] | None:
    if not isinstance(node, ast.Dict):
        return None
    payload: dict[str, str] = {}
    for key_node, value_node in zip(node.keys, node.values):
        key = _extract_string(key_node)
        value = _extract_string(value_node)
        if key is None or value is None:
            return None
        payload[key] = value
    return payload


def _extract_translation_map(node: ast.AST) -> dict[str, dict[str, str]] | None:
    if not isinstance(node, ast.Dict):
        return None
    translations: dict[str, dict[str, str]] = {}
    for key_node, value_node in zip(node.keys, node.values):
        language = _extract_string(key_node)
        bundle = _extract_string_map(value_node)
        if language is None or bundle is None:
            return None
        translations[language] = bundle
    return translations


def _load_sidecar_locales(file_path: Path) -> dict[str, dict[str, str]]:
    locales: dict[str, dict[str, str]] = {}
    prefix = f"{file_path.stem}."
    for candidate in sorted(file_path.parent.glob(f"{file_path.stem}.*.json")):
        language = candidate.name[len(prefix):-5]
        if not language:
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            locales[language.lower()] = {str(key): str(value) for key, value in payload.items() if isinstance(value, str)}
    return locales


def _parse_plugin_specs(
    file_path: Path,
    source_root: Path,
    *,
    source_type: str,
    state_manager=None,
    scan_report: dict[str, object] | None = None,
) -> list[PluginSpec]:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except Exception:
        return []

    locale_bundles = _load_sidecar_locales(file_path)
    specs: list[PluginSpec] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not _inherits_qt_plugin(node):
            continue

        values = dict(PLUGIN_DEFAULTS)
        inline_translations: dict[str, dict[str, str]] = {}
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if target.id == "translations":
                        extracted_translations = _extract_translation_map(item.value)
                        if extracted_translations is not None:
                            inline_translations = extracted_translations
                        continue
                    if target.id == "preferred_qt_icon":
                        extracted = _extract_string(item.value)
                        if extracted is not None:
                            values["preferred_icon"] = extracted
                            values["preferred_qt_icon"] = extracted
                        continue
                    if target.id not in values:
                        continue
                    if target.id in {"standalone", "allow_name_override", "allow_icon_override"}:
                        extracted_bool = _extract_bool(item.value)
                        if extracted_bool is not None:
                            values[target.id] = extracted_bool
                        continue
                    extracted = _extract_string(item.value)
                    if extracted is not None:
                        values[target.id] = extracted
            elif isinstance(item, ast.AnnAssign):
                if not isinstance(item.target, ast.Name):
                    continue
                if item.target.id == "translations":
                    extracted_translations = _extract_translation_map(item.value)
                    if extracted_translations is not None:
                        inline_translations = extracted_translations
                    continue
                if item.target.id == "preferred_qt_icon":
                    extracted = _extract_string(item.value)
                    if extracted is not None:
                        values["preferred_icon"] = extracted
                        values["preferred_qt_icon"] = extracted
                    continue
                if item.target.id not in values:
                    continue
                if item.target.id in {"standalone", "allow_name_override", "allow_icon_override"}:
                    extracted_bool = _extract_bool(item.value)
                    if extracted_bool is not None:
                        values[item.target.id] = extracted_bool
                else:
                    extracted = _extract_string(item.value)
                    if extracted is not None:
                        values[item.target.id] = extracted

        if not values["plugin_id"] or not values["name"]:
            continue

        for language, bundle in inline_translations.items():
            locale_bundles.setdefault(language.lower(), {})
            for key, value in bundle.items():
                locale_bundles[language.lower()].setdefault(key, value)

        rel_path = file_path.relative_to(source_root).with_suffix("")
        module_name = f"dngine_dynamic_plugins.{source_type}." + ".".join(rel_path.parts)
        if state_manager is not None:
            has_state = state_manager.has(values["plugin_id"])
            state = state_manager.get(values["plugin_id"])
            if source_type == "builtin":
                state["trusted"] = True
                state["quarantined"] = False
                state["risk_level"] = "low"
                state["risk_summary"] = ""
            elif source_type == "custom" and not has_state:
                state["enabled"] = False
                state["hidden"] = False
                state["trusted"] = False
                state["quarantined"] = False
        else:
            state = {
                "enabled": source_type != "custom",
                "hidden": False,
                "trusted": source_type != "custom",
                "quarantined": False,
                "risk_level": str((scan_report or {}).get("risk_level", "low")),
                "risk_summary": str((scan_report or {}).get("summary", "")),
                "last_error": "",
                "failure_count": 0,
            }
        if source_type == "custom" and scan_report is not None:
            state["risk_level"] = str(scan_report.get("risk_level", state.get("risk_level", "low")))
            state["risk_summary"] = str(scan_report.get("summary", state.get("risk_summary", "")))
            if state["risk_level"] == "critical":
                state["enabled"] = False
                state["trusted"] = False
                state["quarantined"] = True
        container_path, package_name, primary_relative_path = _package_details(file_path, source_root, source_type)
        specs.append(
            PluginSpec(
                plugin_id=values["plugin_id"],
                name=values["name"],
                description=values["description"],
                category=values["category"],
                version=values["version"],
                standalone=values["standalone"],
                allow_name_override=values["allow_name_override"],
                allow_icon_override=values["allow_icon_override"],
                preferred_icon=values["preferred_icon"] or values["preferred_qt_icon"],
                file_path=file_path,
                module_name=module_name,
                class_name=node.name,
                source_root=source_root,
                source_type=source_type,
                container_path=container_path,
                package_name=package_name,
                primary_relative_path=primary_relative_path,
                enabled=state["enabled"],
                hidden=state["hidden"],
                trusted=bool(state.get("trusted", source_type != "custom")),
                quarantined=bool(state.get("quarantined", False)),
                signature_status="verified" if source_type == "builtin" else "none",
                signer="dngine-bundle" if source_type == "builtin" else "",
                risk_level=str(state.get("risk_level", "low")),
                risk_summary=str(state.get("risk_summary", "")),
                last_error=str(state.get("last_error", "")),
                failure_count=int(state.get("failure_count", 0)),
                locale_bundles=locale_bundles,
            )
        )

    return specs


def _package_details(file_path: Path, source_root: Path, source_type: str) -> tuple[Path, str, str]:
    if source_type == "custom":
        rel_parts = file_path.relative_to(source_root).parts
        package_name = rel_parts[0]
        container_path = source_root / package_name
        primary_relative_path = str(file_path.relative_to(container_path)).replace("\\", "/")
        return container_path, package_name, primary_relative_path
    return file_path, file_path.stem, file_path.name


class PluginManager:
    def __init__(
        self,
        builtin_root: Path,
        custom_root: Path | None = None,
        state_manager=None,
        *,
        builtin_manifest_path: Path | None = None,
        enforce_builtin_manifest: bool | None = None,
        dependency_paths_resolver=None,
        dependency_summary_resolver=None,
    ):
        self.builtin_root = Path(builtin_root)
        self.custom_root = Path(custom_root) if custom_root is not None else None
        self.state_manager = state_manager
        self.builtin_manifest_path = Path(builtin_manifest_path) if builtin_manifest_path is not None else None
        self.enforce_builtin_manifest = bool(enforce_builtin_manifest) if enforce_builtin_manifest is not None else False
        self.dependency_paths_resolver = dependency_paths_resolver
        self.dependency_summary_resolver = dependency_summary_resolver
        self._builtin_manifest = (
            load_builtin_manifest(self.builtin_manifest_path)
            if self.builtin_manifest_path is not None
            else {}
        )
        self._manifest_integrity_ok = True
        if self.enforce_builtin_manifest and self.builtin_manifest_path is not None:
            if not verify_manifest_integrity(self.builtin_manifest_path):
                self._builtin_manifest = {}
                self._manifest_integrity_ok = False
        self._specs: list[PluginSpec] | None = None
        self._instances: dict[str, QtPlugin] = {}

    @staticmethod
    def _import_module(spec_obj, module_name: str):
        module = importlib.util.module_from_spec(spec_obj)
        sys.modules[module_name] = module
        try:
            spec_obj.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        return module

    def invalidate_cache(self, *, clear_instances: bool = False) -> None:
        self._specs = None
        if self.builtin_manifest_path is not None:
            self._builtin_manifest = load_builtin_manifest(self.builtin_manifest_path)
            if self.enforce_builtin_manifest:
                if not verify_manifest_integrity(self.builtin_manifest_path):
                    self._builtin_manifest = {}
                    self._manifest_integrity_ok = False
                else:
                    self._manifest_integrity_ok = True
        if clear_instances:
            self._instances = {}

    def inspect_path(self, path: Path) -> list[PluginSpec]:
        path = Path(path)
        specs: list[PluginSpec] = []
        if path.is_file() and path.suffix == ".py":
            specs.extend(_parse_plugin_specs(path, path.parent, source_type="imported"))
            return specs
        if path.is_dir():
            for file_path in sorted(path.rglob("*.py")):
                if file_path.name.startswith("__"):
                    continue
                specs.extend(_parse_plugin_specs(file_path, path, source_type="imported"))
        return specs

    def discover_plugins(self, *, include_disabled: bool = False) -> list[PluginSpec]:
        if self._specs is None:
            specs: list[PluginSpec] = []
            specs.extend(self._discover_from_root(self.builtin_root, source_type="builtin"))
            if self.custom_root is not None and self.custom_root.exists():
                specs.extend(self._discover_from_root(self.custom_root, source_type="custom"))
            deduped: dict[str, PluginSpec] = {}
            for spec in specs:
                existing = deduped.get(spec.plugin_id)
                if existing is None:
                    deduped[spec.plugin_id] = spec
                    continue
                if existing.source_type == "builtin" and spec.source_type == "custom":
                    deduped[spec.plugin_id] = spec
            self._specs = sorted(
                deduped.values(),
                key=lambda spec: (
                    0 if spec.standalone else 1,
                    spec.category.lower(),
                    spec.name.lower(),
                ),
            )
        if include_disabled:
            return list(self._specs)
        return [spec for spec in self._specs if spec.enabled]

    def sidebar_plugins(self) -> list[PluginSpec]:
        return [spec for spec in self.discover_plugins() if not spec.hidden and spec.trusted and not spec.quarantined]

    def get_spec(self, plugin_id: str, *, include_disabled: bool = True) -> PluginSpec | None:
        for spec in self.discover_plugins(include_disabled=include_disabled):
            if spec.plugin_id == plugin_id:
                return spec
        return None

    def plugin_text(self, plugin_id: str, language: str, key: str, default: str | None = None, **kwargs) -> str:
        bundle = self.plugin_locale_bundle(plugin_id, language)
        text = bundle.get(key, default if default is not None else key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except Exception:
                pass
        return text

    def plugin_locale_bundle(self, plugin_id: str, language: str) -> dict[str, str]:
        spec = self.get_spec(plugin_id)
        if spec is None:
            return {}
        bundle = dict(spec.locale_bundles.get(language.lower(), {}))
        instance = self._instances.get(plugin_id)
        if instance is not None:
            inline = getattr(instance, "translations", {}) or {}
            fallback = inline.get(language.lower(), {})
            for key, value in fallback.items():
                bundle.setdefault(key, value)
        return bundle

    def load_plugin(self, plugin_id: str) -> QtPlugin:
        if plugin_id in self._instances:
            return self._instances[plugin_id]

        spec = self.get_spec(plugin_id)
        if spec is None:
            raise KeyError(f"Unknown plugin id: {plugin_id}")
        if not spec.enabled:
            raise RuntimeError(f"Plugin '{plugin_id}' is disabled.")
        if spec.source_type == "custom" and not spec.trusted:
            raise RuntimeError(f"Plugin '{plugin_id}' is not trusted yet. Review it in Settings before loading it.")
        if spec.quarantined:
            raise RuntimeError(f"Plugin '{plugin_id}' is quarantined because it previously failed or was flagged unsafe.")

        if callable(self.dependency_summary_resolver):
            try:
                dependency_summary = self.dependency_summary_resolver(spec)
            except Exception:
                dependency_summary = None
            if (
                dependency_summary is not None
                and getattr(dependency_summary, "has_manifest", False)
                and str(getattr(dependency_summary, "status", "")) not in {"installed", "conflict"}
            ):
                raise RuntimeError(
                    f"Plugin '{plugin_id}' requires dependency installation. "
                    "Open Command Center -> Plugins and install its dependency sidecar first."
                )

        if callable(self.dependency_paths_resolver):
            try:
                for dependency_path in reversed(list(self.dependency_paths_resolver(spec))):
                    dependency_text = str(dependency_path).strip()
                    if dependency_text and dependency_text not in sys.path:
                        sys.path.insert(0, dependency_text)
            except Exception:
                pass

        spec_obj = importlib.util.spec_from_file_location(spec.module_name, spec.file_path)
        if spec_obj is None or spec_obj.loader is None:
            raise ImportError(f"Could not prepare import for plugin '{plugin_id}'")

        module = sys.modules.get(spec.module_name)
        if module is None:
            module = self._import_module(spec_obj, spec.module_name)

        plugin_class = getattr(module, spec.class_name, None)
        if plugin_class is None or not inspect.isclass(plugin_class) or not issubclass(plugin_class, QtPlugin):
            sys.modules.pop(spec.module_name, None)
            module = self._import_module(spec_obj, spec.module_name)
            plugin_class = getattr(module, spec.class_name, None)
        if plugin_class is None or not inspect.isclass(plugin_class) or not issubclass(plugin_class, QtPlugin):
            raise ImportError(f"Invalid plugin class for '{plugin_id}'")

        instance = plugin_class()
        self._instances[plugin_id] = instance
        return instance

    def _discover_from_root(self, root: Path, *, source_type: str) -> list[PluginSpec]:
        specs: list[PluginSpec] = []
        if not root.exists():
            return specs
        scan_cache: dict[Path, dict[str, object]] = {}
        for file_path in sorted(root.rglob("*.py")):
            if file_path.name.startswith("__"):
                continue
            effective_source_type = source_type
            scan_report = None
            if source_type == "builtin" and self.enforce_builtin_manifest:
                if not self._manifest_integrity_ok or not self._builtin_manifest:
                    continue
                relative_path = str(file_path.relative_to(root)).replace("\\", "/")
                manifest_entry = self._builtin_manifest.get(relative_path)
                if manifest_entry is None:
                    continue
                if sha256_file(file_path) != manifest_entry.sha256:
                    continue
                inspected_specs = _parse_plugin_specs(file_path, root, source_type="imported")
                inspected_keys = sorted((spec.plugin_id, spec.class_name) for spec in inspected_specs)
                if tuple(inspected_keys) != manifest_entry.plugins:
                    continue
            if effective_source_type == "custom":
                rel_parts = file_path.relative_to(root).parts
                container = root / rel_parts[0]
                if container not in scan_cache:
                    scan_cache[container] = scan_plugin_path(container).as_dict()
                scan_report = scan_cache[container]
            specs.extend(
                _parse_plugin_specs(
                    file_path,
                    root,
                    source_type=effective_source_type,
                    state_manager=self.state_manager,
                    scan_report=scan_report,
                )
            )
        return specs
