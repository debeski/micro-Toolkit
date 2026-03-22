# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH)
package_root = project_root / "micro_toolkit"


def collect_tree(relative_root: str):
    root = project_root / relative_root
    items = []
    for path in root.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            items.append((str(path), str(path.parent.relative_to(project_root))))
    return items


datas = []
datas += collect_tree("micro_toolkit/assets")
datas += collect_tree("micro_toolkit/i18n")
datas += collect_tree("micro_toolkit/plugins")

hiddenimports = collect_submodules("micro_toolkit.plugins")

icon_path = project_root / "app.ico"
exe_icon = str(icon_path) if icon_path.exists() else None

a = Analysis(
    ["micro_toolkit/__main__.py"],
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
    name="micro-toolkit",
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

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="micro-toolkit",
)
