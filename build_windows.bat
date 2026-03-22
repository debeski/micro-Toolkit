@echo off
setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0"
pushd "%ROOT_DIR%"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
) else (
    set "PYTHON_CMD=python"
)

if not exist "venv" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv venv
)

call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo Failed to activate the virtual environment.
    popd
    exit /b 1
)

echo Installing build dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

echo Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Building Windows onedir package...
python -m PyInstaller --noconfirm --clean micro-toolkit.spec
if errorlevel 1 (
    echo Build failed.
    popd
    exit /b 1
)

echo Build complete: dist\micro-toolkit\
echo Launcher: dist\micro-toolkit\micro-toolkit.exe
popd
endlocal
