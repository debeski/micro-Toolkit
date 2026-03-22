#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to build Micro Toolkit."
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

echo "Cleaning previous build artifacts..."
rm -rf build dist

echo "Building Linux onedir package..."
python -m PyInstaller --noconfirm --clean micro-toolkit.spec

deactivate
echo "Build complete: dist/micro-toolkit/"
echo "Launcher: dist/micro-toolkit/micro-toolkit"
