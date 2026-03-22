# Micro Toolkit

Micro Toolkit is a fast, multilingual, plugin-driven desktop companion for day-to-day office and home use. It is built with `PySide6` and designed to feel like a native desktop application: quick to open, responsive while working, tray-friendly, and flexible enough to grow through drop-in plugins.

Current app version: `1.1.0`

## Overview

Micro Toolkit brings practical desktop utilities into one cohesive shell:

- file utilities
- spreadsheet and office helpers
- IT and system tools
- clipboard history and quick access
- media and image tools
- workflows and CLI automation
- custom plugin loading

The app is intentionally desktop-first. It is not a browser wrapper, and it is not built around always-online services. It is meant to stay light, quick, and usable throughout the day.

## Highlights

- Native desktop UX built on `PySide6`
- Lazy plugin discovery and lazy page creation for fast startup
- English and Arabic support with RTL-aware layout direction
- Light, dark, and system theme modes
- Tray integration for all-day companion use
- Workflow engine and CLI command surface
- Importable/exportable custom plugin packaging
- Plugin-local translations through sidecar locale files
- Headless tool commands for workflows and automation
- Capability-based elevated broker for future admin/root operations
- Dedicated privileged hotkey helper for Linux global shortcuts

## Included Tools

### Validation and Analysis

- Quick Analytics
- Folder Exporter
- Duplicate Finder
- Sequence Finder
- File Validator

### Office Utilities

- Data Cleaner
- Data Cross Joiner
- PDF Core Engine
- Document Bridge (`Markdown -> DOCX` and `DOCX -> Markdown`)

### File Utilities

- Deep File Searcher
- Batch File Renamer
- Smart File Organizer
- Disk Space Visualizer

### IT Utilities

- System Hardware Audit
- Credential Scanner
- Network Port Scanner
- Privacy Data Shredder

### Media Utilities

- Image Transformer
- Image Tagger

### Standalone Companion Pages

- Clipboard Manager
- Settings
- Workflow Studio
- Welcome Overview

## Architecture

### Package Layout

```text
micro_toolkit/
  __main__.py
  app.py
  main.py
  assets/
  core/
  i18n/
  plugins/
data/
output/
build_linux.sh
build_macos.sh
build_windows.sh
build_windows.bat
micro-toolkit.spec
```

### Runtime Layout

- [micro_toolkit](/home/debeski/depy/tools/micro-toolkit/micro_toolkit) contains code, assets, built-in plugins, and locale files.
- [data](/home/debeski/depy/tools/micro-toolkit/data) contains runtime state such as config, database, plugin state, workflows, and custom plugins.
- [output](/home/debeski/depy/tools/micro-toolkit/output) is the default export/output folder for generated files.

### Plugin Engine

The plugin engine is built around:

- AST-based metadata discovery
- lazy module import
- lazy widget creation
- plugin-local `en/ar` sidecar locales
- optional headless command registration
- optional privileged capability registration
- import/export of custom plugin bundles

That means a plugin can contribute:

- metadata
- a `QWidget` page
- locale bundles
- CLI/workflow commands
- narrow privileged capabilities when truly needed

without changing the core shell.

## Multilingual and RTL Support

The shell supports English and Arabic, and plugins can ship their own translations alongside the plugin file.

Example:

```text
my_plugin.py
my_plugin.en.json
my_plugin.ar.json
```

The shell handles:

- current language
- layout direction
- RTL-aware app chrome
- plugin metadata localization
- plugin UI strings through `services.plugin_text(...)`

## Performance Model

Micro Toolkit is designed to stay responsive:

- plugin metadata is discovered before modules are imported
- pages are only created when opened
- opened pages stay cached
- heavy work is expected to run in background tasks
- headless command functions are separated from UI code where possible

## Privileged Access Model

Micro Toolkit now has two separate elevated helpers, each with a narrow purpose:

### 1. Hotkey Helper

The hotkey helper exists only for global shortcut capture on Linux sessions where the keyboard backend requires elevated input access. It is intentionally narrow and should not be reused for general privileged work.

### 2. Elevated Broker

The elevated broker is the general capability-based elevation layer for future tool/plugin needs.

Important design rules:

- the main app stays unprivileged
- plugins do not get arbitrary root/admin command execution
- privileged actions must be registered as named capabilities
- each capability should do one narrow job
- capabilities should accept structured payloads and return structured results

Examples of good broker capability shapes:

- `filesystem.stat_path`
- `filesystem.secure_delete`
- `system.read_protected_info`
- `network.bind_privileged_port`

Examples of bad designs to avoid:

- “run any shell command”
- “execute this Python string”
- one giant admin capability that does many unrelated things

### Broker Namespace Commands

List capabilities:

```bash
python -m micro_toolkit broker elevated capabilities
```

Start the broker explicitly:

```bash
python -m micro_toolkit broker elevated start
```

Run one capability:

```bash
python -m micro_toolkit broker elevated run system.identity --payload '{}'
```

Stop the broker:

```bash
python -m micro_toolkit broker elevated stop
```

## Installation

### Requirements

- Python 3.10+
- the packages listed in [requirements.txt](/home/debeski/depy/tools/micro-toolkit/requirements.txt)

### Linux Note

On some X11 systems, Qt 6.5+ may require:

```bash
sudo apt-get install -y libxcb-cursor0
```

### Setup

```bash
git clone https://github.com/debeski/micro-toolkit.git
cd micro-toolkit
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running the App

Launch the desktop app:

```bash
python -m micro_toolkit
```

Launch directly into GUI mode:

```bash
python -m micro_toolkit gui
```

Open a specific plugin on startup:

```bash
python -m micro_toolkit gui --plugin-id clip_manager
```

## CLI Examples

List plugins:

```bash
python -m micro_toolkit plugins list
```

List registered workflow and tool commands:

```bash
python -m micro_toolkit commands list
```

Run a headless tool command:

```bash
python -m micro_toolkit commands run tool.doc_bridge.md_to_docx --args '{"markdown_path": "notes.md"}'
```

Run a saved workflow:

```bash
python -m micro_toolkit workflows run my_workflow
```

## Custom Plugin Development

This section is the main guide for writing Micro Toolkit plugins.

### Where Custom Plugins Live

You have two supported options:

1. Import them through `Settings -> Plugins`
2. Place them inside the writable custom plugin area under:

```text
data/plugins/<your_plugin_package>/
```

Example:

```text
data/plugins/my_tools/
  my_plugin.py
  my_plugin.en.json
  my_plugin.ar.json
  helpers.py
```

### Minimal Plugin Shape

```python
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from micro_toolkit.core.plugin_api import QtPlugin


class MyPlugin(QtPlugin):
    plugin_id = "my_plugin"
    name = "My Plugin"
    description = "Example plugin."
    category = "General"
    version = "1.0.0"

    def create_widget(self, services) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Hello from Micro Toolkit"))
        return page
```

### What to Import

Use:

- `from micro_toolkit.core.plugin_api import QtPlugin`
- `from micro_toolkit.core.command_runtime import HeadlessTaskContext` for headless command work
- `from micro_toolkit.core.app_utils import ...` for shared helpers where appropriate
- `services.run_task(...)` for background work
- `services.plugin_text(...)` for localized plugin strings
- `services.request_privileged(...)` only when a capability-based privileged operation is truly required

Avoid:

- imports from deprecated old app folders such as `.xpose`
- imports from removed `tkinter`/`customtkinter` code paths
- top-level heavy imports if they are only needed when the user actually runs the tool
- doing large file/network/CPU work directly on the UI thread

### Translations

Preferred pattern:

```text
my_plugin.py
my_plugin.en.json
my_plugin.ar.json
```

Example `my_plugin.en.json`:

```json
{
  "plugin.name": "My Plugin",
  "plugin.description": "Example plugin.",
  "plugin.category": "General",
  "ui.title": "My Plugin",
  "ui.run": "Run"
}
```

Example usage inside the widget:

```python
title = QLabel(services.plugin_text("my_plugin", "ui.title", "My Plugin"))
```

You can also keep a tiny inline `translations = {...}` fallback in the plugin class, but sidecar files are the preferred pattern.

### Headless Commands

If your tool should work in workflows and CLI, register commands:

```python
from micro_toolkit.core.command_runtime import HeadlessTaskContext


def run_my_task(context, source_path: str):
    context.log(f"Processing {source_path}")
    context.progress(0.5)
    return {"source_path": source_path, "ok": True}


class MyPlugin(QtPlugin):
    plugin_id = "my_plugin"
    name = "My Plugin"

    def register_commands(self, registry, services) -> None:
        registry.register(
            "tool.my_plugin.run",
            "Run My Plugin",
            "Run the plugin headlessly.",
            lambda source_path: run_my_task(
                HeadlessTaskContext(services, command_id="tool.my_plugin.run"),
                source_path,
            ),
        )
```

Guidance:

- keep the command function separate from widget code
- accept structured keyword arguments
- return structured dict/list/scalar results
- make the command usable without GUI state

### Background Work

If the plugin has a GUI and the task is expensive, use `services.run_task(...)`:

```python
self.services.run_task(
    lambda context: run_my_task(context, file_path),
    on_result=self._handle_result,
    on_error=self._handle_error,
    on_finished=self._finish_run,
    on_progress=self._handle_progress,
)
```

### Privileged Broker Capabilities

If a plugin really needs elevated access, do not shell out to `sudo`, `pkexec`, or platform elevation tools directly from the plugin page.

Instead:

1. Register a narrow capability
2. Request it through `services.request_privileged(...)`

Example capability registration:

```python
from pathlib import Path


def stat_sensitive_path(context, payload: dict[str, object]):
    target = Path(str(payload["path"])).expanduser().resolve()
    context.log(f"Checking {target}")
    stat_result = target.stat()
    return {"path": str(target), "size": stat_result.st_size}


class MyPlugin(QtPlugin):
    plugin_id = "my_plugin"
    name = "My Plugin"

    def register_privileged_capabilities(self, registry, runtime) -> None:
        registry.register(
            "my_plugin.stat_sensitive_path",
            "Stat Sensitive Path",
            "Return metadata for a path that may require elevated access.",
            stat_sensitive_path,
            provider=self.plugin_id,
        )
```

Example usage from the normal app process:

```python
result = services.request_privileged(
    "my_plugin.stat_sensitive_path",
    {"path": "/some/protected/location"},
)
```

Broker guidance:

- keep handlers deterministic and narrow
- accept JSON-serializable payloads
- return JSON-serializable results
- keep handlers separate from Qt widgets
- avoid generic command execution capabilities
- avoid mixing many unrelated actions into one capability

### What to Avoid

Avoid these patterns in plugins:

- heavy imports at module top level unless they are truly cheap
- storing mutable runtime data beside the plugin code
- building giant all-in-one widget classes with task logic embedded everywhere
- hardcoding translated strings into the widget when plugin locale files are available
- blocking the UI thread with file scans, pandas work, image processing, or network operations
- using the hotkey helper for anything except global hotkeys
- treating the elevated broker like a generic admin shell

### Recommended Plugin Structure

For anything beyond a tiny tool, use:

```text
data/plugins/my_tools/
  my_plugin.py
  my_plugin.en.json
  my_plugin.ar.json
  my_plugin_helpers.py
```

Recommended split:

- plugin class for metadata and widget creation
- helper functions for data processing
- command functions for workflows/CLI
- privileged capability handlers only when absolutely required

## Build and Packaging

Micro Toolkit uses `PyInstaller` in `onedir` mode.

Why `onedir`:

- better fit for Qt applications
- more reliable than `onefile`
- easier data/plugin packaging
- easier debugging and post-build inspection

### Linux

```bash
./build_linux.sh
```

Launcher:

```text
dist/micro-toolkit/micro-toolkit
```

### macOS

```bash
./build_macos.sh
```

Launcher:

```text
dist/micro-toolkit/micro-toolkit
```

### Windows Native

Run on Windows:

```bat
build_windows.bat
```

Launcher:

```text
dist\micro-toolkit\micro-toolkit.exe
```

### Windows Cross-Build from Linux

Optional Docker-based build:

```bash
./build_windows.sh
```

This is convenient, but native Windows builds are still the more reliable option for final release packaging.

## Product Goals

Micro Toolkit is meant to feel:

- fast enough to keep open all day
- light enough to revisit often
- native enough to not feel like a web wrapper
- practical enough to help with everyday office and home workflows

It is not a monolithic enterprise suite. It is a personal productivity and utility companion designed to stay useful, responsive, and extensible.

## Version History

| Version | Status | Highlights |
| --- | --- | --- |
| 1.1.0 | Current | Added Document Bridge, plugin-backed `Markdown -> DOCX` and `DOCX -> Markdown`, Linux hotkey helper architecture, capability-based elevated broker, and expanded custom plugin authoring guidance. |
| 1.0.0 | Stable milestone | First full Micro Toolkit desktop release on `PySide6`, with lazy plugin engine, multilingual shell, tray integration, workflows, CLI, plugin packaging, and cross-platform `onedir` build flow. |
| 0.9.0 | Internal milestone | Completed migration of the core tool suite into the new plugin engine and made the desktop shell self-contained. |
| 0.8.0 | Internal milestone | Added settings, themes, language switching, tray behavior, autostart, workflow studio, and command registry foundations. |
| 0.7.0 | Internal milestone | Added custom plugin import/export, enable/disable/hide controls, and plugin-local locale sidecar support. |
| 0.6.0 | Internal milestone | Introduced headless tool commands for workflows and CLI plus the quick clipboard panel with shortcut and tray access. |
