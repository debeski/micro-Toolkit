from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from micro_toolkit.core.plugin_manager import PluginManager, PluginSpec


class PluginPackageManager:
    def __init__(self, plugin_manager: PluginManager, custom_plugins_root: Path, state_manager):
        self.plugin_manager = plugin_manager
        self.custom_plugins_root = Path(custom_plugins_root)
        self.state_manager = state_manager
        self.custom_plugins_root.mkdir(parents=True, exist_ok=True)

    def import_plugin_file(self, source_file: Path) -> list[str]:
        source_file = Path(source_file)
        if not source_file.exists() or source_file.suffix != ".py":
            raise ValueError("Choose a valid Python plugin file.")
        specs = self.plugin_manager.inspect_path(source_file)
        if not specs:
            raise ValueError("No compatible plugin class was found in the selected file.")
        plugin_id = specs[0].plugin_id
        self._ensure_no_conflicts(specs, target_package_name=plugin_id)
        target_dir = self.custom_plugins_root / plugin_id
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_dir / source_file.name)
        for sibling in self._matching_sidecars(source_file):
            if sibling.is_file():
                shutil.copy2(sibling, target_dir / sibling.name)
            elif sibling.is_dir():
                shutil.copytree(sibling, target_dir / sibling.name, dirs_exist_ok=True)
        self._reset_states([spec.plugin_id for spec in specs])
        self.plugin_manager.invalidate_cache(clear_instances=True)
        return [spec.plugin_id for spec in specs]

    def import_plugin_folder(self, source_dir: Path) -> list[str]:
        source_dir = Path(source_dir)
        if not source_dir.is_dir():
            raise ValueError("Choose a valid plugin folder.")
        specs = self.plugin_manager.inspect_path(source_dir)
        if not specs:
            raise ValueError("No compatible plugins were found in the selected folder.")
        self._ensure_no_conflicts(specs, target_package_name=source_dir.name)
        target_dir = self.custom_plugins_root / source_dir.name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        self._reset_states([spec.plugin_id for spec in specs])
        self.plugin_manager.invalidate_cache(clear_instances=True)
        return [spec.plugin_id for spec in specs]

    def import_backup(self, archive_path: Path) -> list[str]:
        archive_path = Path(archive_path)
        if not archive_path.exists():
            raise ValueError("Choose a valid backup archive.")
        imported_ids: list[str] = []
        with zipfile.ZipFile(archive_path, "r") as archive:
            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"Invalid plugin backup file: {exc}") from exc
            plugins = manifest.get("plugins", [])
            if not isinstance(plugins, list) or not plugins:
                raise ValueError("Backup archive does not contain any plugins.")

            existing_by_id = {spec.plugin_id: spec for spec in self.plugin_manager.discover_plugins(include_disabled=True)}
            for entry in plugins:
                plugin_id = entry.get("plugin_id")
                package_name = entry.get("package_name")
                source_type = entry.get("source_type", "custom")
                if not plugin_id or not package_name:
                    raise ValueError("Backup manifest is missing plugin metadata.")
                existing = existing_by_id.get(plugin_id)
                if existing is not None and not (existing.source_type == "custom" and existing.package_name == package_name):
                    raise ValueError(f"Cannot import '{plugin_id}' because that plugin id already exists.")
                target_dir = self.custom_plugins_root / package_name
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                target_dir.mkdir(parents=True, exist_ok=True)
                prefix = f"plugins/{package_name}/"
                for name in archive.namelist():
                    if not name.startswith(prefix) or name.endswith("/"):
                        continue
                    relative_name = name[len(prefix):]
                    destination = target_dir / relative_name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as source_handle, destination.open("wb") as dest_handle:
                        shutil.copyfileobj(source_handle, dest_handle)
                imported_ids.append(plugin_id)
        self._reset_states(imported_ids)
        self.plugin_manager.invalidate_cache(clear_instances=True)
        return imported_ids

    def export_plugins(self, specs: list[PluginSpec], destination: Path) -> Path:
        destination = Path(destination)
        if not specs:
            raise ValueError("Select at least one plugin to export.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest_plugins = []
            archive_root = temp_root / "plugins"
            archive_root.mkdir(parents=True, exist_ok=True)
            for spec in specs:
                package_name = spec.package_name or spec.plugin_id
                package_root = archive_root / package_name
                package_root.mkdir(parents=True, exist_ok=True)
                manifest_plugins.append(
                    {
                        "plugin_id": spec.plugin_id,
                        "package_name": package_name,
                        "source_type": spec.source_type,
                        "primary_relative_path": spec.primary_relative_path,
                    }
                )
                for source_path, relative_path in self._package_files(spec):
                    dest_path = package_root / relative_path
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    if source_path.is_file():
                        shutil.copy2(source_path, dest_path)
            (temp_root / "manifest.json").write_text(
                json.dumps({"version": 1, "plugins": manifest_plugins}, indent=2),
                encoding="utf-8",
            )
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file_path in temp_root.rglob("*"):
                    if file_path.is_file():
                        archive.write(file_path, file_path.relative_to(temp_root).as_posix())
        return destination

    def _package_files(self, spec: PluginSpec) -> list[tuple[Path, Path]]:
        files: list[tuple[Path, Path]] = []
        if spec.container_path.is_dir():
            for file_path in sorted(spec.container_path.rglob("*")):
                if file_path.is_file() and "__pycache__" not in file_path.parts:
                    files.append((file_path, file_path.relative_to(spec.container_path)))
            return files
        files.append((spec.file_path, Path(spec.file_path.name)))
        for sibling in self._matching_sidecars(spec.file_path):
            if sibling.is_file():
                files.append((sibling, Path(sibling.name)))
            elif sibling.is_dir():
                for child in sorted(sibling.rglob("*")):
                    if child.is_file() and "__pycache__" not in child.parts:
                        files.append((child, Path(sibling.name) / child.relative_to(sibling)))
        return files

    def _matching_sidecars(self, source_file: Path) -> list[Path]:
        stem = source_file.stem
        matches: list[Path] = []
        for path in source_file.parent.iterdir():
            if path == source_file:
                continue
            if path.name.startswith(f"{stem}."):
                matches.append(path)
            elif path.name == f"{stem}_assets":
                matches.append(path)
        return matches

    def _ensure_no_conflicts(self, specs: list[PluginSpec], *, target_package_name: str) -> None:
        existing_by_id = {spec.plugin_id: spec for spec in self.plugin_manager.discover_plugins(include_disabled=True)}
        for spec in specs:
            existing = existing_by_id.get(spec.plugin_id)
            if existing is None:
                continue
            if existing.source_type == "custom" and existing.package_name == target_package_name:
                continue
            raise ValueError(f"Cannot import '{spec.plugin_id}' because that plugin id already exists.")

    def _reset_states(self, plugin_ids: list[str]) -> None:
        for plugin_id in plugin_ids:
            self.state_manager.reset(plugin_id)
