from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dngine.core.builtin_manifest import BuiltinManifestEntry, sha256_file, write_builtin_manifest, write_manifest_hash
from dngine.core.plugin_manager import _parse_plugin_specs


def main() -> int:
    plugins_root = ROOT / "dngine" / "plugins"
    manifest_path = ROOT / "dngine" / "builtin_plugin_manifest.json"
    hash_module_path = ROOT / "dngine" / "_manifest_hash.py"
    entries: dict[str, BuiltinManifestEntry] = {}

    for file_path in sorted(plugins_root.rglob("*.py")):
        if file_path.name.startswith("__"):
            continue
        specs = _parse_plugin_specs(file_path, plugins_root, source_type="imported")
        if not specs:
            continue
        relative_path = str(file_path.relative_to(plugins_root)).replace("\\", "/")
        entries[relative_path] = BuiltinManifestEntry(
            relative_path=relative_path,
            sha256=sha256_file(file_path),
            plugins=tuple(sorted((spec.plugin_id, spec.class_name) for spec in specs)),
        )

    written = write_builtin_manifest(manifest_path, entries)
    print(f"Wrote builtin plugin manifest: {written}")
    print(f"Entries: {len(entries)}")

    digest = write_manifest_hash(manifest_path, hash_module_path)
    print(f"Manifest SHA-256 imprinted: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
