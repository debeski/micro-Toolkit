# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH)
package_root = project_root / "dngine"


def collect_tree(relative_root: str):
    root = project_root / relative_root
    items = []
    for path in root.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            items.append((str(path), str(path.parent.relative_to(project_root))))
    return items


datas = []
datas.append((str(project_root / "dngine" / "builtin_plugin_manifest.json"), "dngine"))
datas.append((str(project_root / "dngine" / "VERSION"), "dngine"))
datas += collect_tree("dngine/assets")
datas += collect_tree("dngine/i18n")
datas += collect_tree("dngine/plugins")

hiddenimports = collect_submodules("dngine.plugins")
hiddenimports += collect_submodules("pip")

icon_path = project_root / "app.ico"
exe_icon = str(icon_path) if icon_path.exists() else None
app_icon_path = project_root / "app.icns"
app_icon = str(app_icon_path) if app_icon_path.exists() else None

a = Analysis(
    ["dngine/__main__.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dngine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=exe_icon,
)

# macOS background subcommands are launched through this helper so they do not
# come up as a second Dock-visible GUI app instance.
helper_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dngine-helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    helper_exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="dngine",
)

app = BUNDLE(
    coll,
    name="DNgine.app",
    icon=app_icon,
    bundle_identifier="com.debeski.dngine",
)
