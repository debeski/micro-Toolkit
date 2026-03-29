#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "build_macos.sh should be run on macOS."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to build DNgine."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing build dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

echo "Generating builtin plugin manifest..."
python tools/generate_builtin_plugin_manifest.py

echo "Cleaning previous build artifacts..."
rm -rf build dist

echo "Building macOS app bundle..."
python -m PyInstaller --noconfirm --clean dngine.spec

deactivate
echo "Build complete: dist/DNgine.app"
echo "Launcher: dist/DNgine.app"
