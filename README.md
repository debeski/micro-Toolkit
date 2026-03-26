# Micro Toolkit

Micro Toolkit is a fast, cross-platform, multilingual, plugin-driven desktop companion for day-to-day office and home use. It is built with `PySide6` and designed to feel like a native desktop application: quick to open, responsive while working, tray-friendly, and flexible enough to grow through drop-in plugins.

Current app version: `0.6.3`

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
- Five curated theme colors with a dark-mode toggle
- Live preview for language, direction, density, and UI scaling
- Standardized per-user runtime storage across Windows, macOS, and Linux
- Tray integration for all-day companion use
- Dashboard shell with a workspace pulse panel, usage snapshots, and recent activity
- Settings support for default output path and default startup page selection
- Workflow engine and CLI command surface
- Importable/exportable custom plugin packaging
- Plugin-local translations through sidecar locale files
- Opt-in plugin display name and icon customization
- Headless tool commands for workflows and automation
- Capability-based elevated broker for future admin/root operations
- Dedicated elevated hotkey helper for Linux global shortcuts
- Developer inspector system page gated behind developer mode
- Multi-format clipboard history with pinned snippets, labels, and categories

## Included Tools

### Validation and Analysis

- Chart Builder
- Folder Mapper
- Deep-Scan Auditor
- Sequence Auditor
- Data-Link Auditor

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

- System Overview
- Credential Scanner
- Network Port Scanner
- Wi-Fi Profiles
- Privacy Data Shredder

### Media Utilities

- Image Transformer
- Image Tagger
- Color Picker

### Standalone Companion Pages

- Dashboard
- Clipboard Manager
- Settings
- Workflow Studio
- About
- Inspector (`Developer mode`)

## Built-In Tool Notes

### Dashboard

- Acts as the app landing page
- Shows a welcome header, greeting, date, usage snapshots, and recent activity
- Includes a workspace pulse panel for output, backups, workflows, shortcuts, and useful next actions

### Clipboard Manager

- Captures plain text, code, URLs, file lists, rich text / HTML, and images
- Restores entries back to the system clipboard in their original supported format
- Supports labels, categories, pinned snippets, quick history access, and persistent local storage
- Pinned entries stay above normal history and are not removed when non-pinned history is trimmed

### Folder Mapper

- Maps a full folder tree into an Excel workbook with file metadata, paths, permissions, and dates
- Useful as an inventory/export view before file operations or audits

### Deep-Scan Auditor

- Folder mode accepts multiple folders at once
- Folder duplicate matching can use `Name`, `Size`, `Created Date`, and optional `Hash`
- Excel mode accepts multiple workbook files
- Each workbook can define its own one-or-more target column names, comma-separated

### Sequence Auditor

- Audits folder listings or workbook columns for missing numbered items
- Exports a workbook that includes missing entries plus surrounding context rows

### Data-Link Auditor

- Audits filenames referenced in an Excel workbook against one or more source folders
- Can optionally move confirmed matches into a destination structure while exporting missing-value and missing-file reports

### System Overview

- Replaces the earlier hardware audit view
- Shows live CPU, memory, and disk visualization plus current runtime and system details

### Wi-Fi Profiles

- Lists saved Wi-Fi profiles and current network information when the platform backend allows it
- Passwords are masked by default and can be revealed or copied on demand

### Color Picker

- Picks colors from anywhere on the screen
- Shows a preview plus `HEX`, `RGB`, and `HSL`
- Uses a virtual multi-screen picker surface so all connected displays can be sampled

### Inspector

- Hidden unless `Developer mode` is enabled
- Lets you inspect live widgets, object names, hierarchy, palette roles, and stylesheet state
- Can temporarily unlock static app text so labels become highlightable and copyable
- While inspect mode is active, use right-click navigation to move around the app and left-click to select the target widget
- Useful for debugging layout, theming, and shell paint issues without external Qt tooling

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
build_linux.sh
build_macos.sh
build_windows.sh
build_windows.bat
micro-toolkit.spec
```

### Runtime Layout

- [micro_toolkit](/home/debeski/depy/tools/micro-toolkit/micro_toolkit) contains code, assets, built-in plugins, and locale files.
- Runtime state lives in a per-user storage root, not in the project directory.
- Windows uses `%LOCALAPPDATA%\\Micro Toolkit`
- macOS uses `~/Library/Application Support/Micro Toolkit`
- Linux uses `$XDG_DATA_HOME/micro-toolkit` or `~/.local/share/micro-toolkit`
- Inside that root, `data/` contains config, database, plugin state, workflows, and custom plugins.
- Inside that root, `output/` is the default export/output folder for generated files.
- `MICRO_TOOLKIT_HOME` can override the storage root for development or portable testing.

### Plugin Engine

The plugin engine is built around:

- AST-based metadata discovery
- lazy module import
- lazy widget creation
- plugin-local `en/ar` sidecar locales
- optional headless command registration
- optional elevated capability registration
- import/export of custom plugin bundles
- manifest-verified builtin plugin discovery in packaged builds
- custom plugin trust review and quarantine state

That means a plugin can contribute:

- metadata
- a `QWidget` page
- locale bundles
- CLI/workflow commands
- narrow elevated capabilities when truly needed

without changing the core shell.

In packaged `onedir` builds, bundled first-party plugins are verified against `builtin_plugin_manifest.json` before they are treated as builtin. Extra or modified files dropped into the shipped plugin folder do not automatically become first-class app plugins.

### Custom Plugin Safety Model

Custom plugins are supported, but they are not treated like built-in code.

Micro Toolkit now applies several safety measures:

- packaged first-party plugins are identified through a build-generated manifest
- imported plugins start disabled and untrusted
- manually dropped custom plugins are still discovered as untrusted
- custom plugins stay out of the sidebar until explicitly trusted
- static safety scans inspect plugin Python files for risky imports and calls
- critical-risk imports are blocked during import and remain quarantined
- repeated load or command-registration failures cause automatic quarantine
- trust, risk, failure, and quarantine state are visible in `Settings -> Plugins`

Important limit:

- this is not a full OS sandbox

Trusted plugins still run Python code in the app process. The review and quarantine system reduces accidental breakage and raises the bar against obviously unsafe plugins, but users should still only install plugins they trust.

### Plugin Origins

Micro Toolkit is designed around three plugin origins:

- `builtin`: shipped with the app and verified by the build manifest
- `signed`: reserved for future signer-verified third-party distribution
- `custom`: local or imported plugins that go through review and trust controls

At the moment, `builtin` and `custom` are active. The `signed` tier is reserved in the architecture so a future trusted-signer flow can be added without redesigning the whole plugin model.

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
- global Dubai-based font stack with fallbacks

## Performance Model

Micro Toolkit is designed to stay responsive:

- plugin metadata is discovered before modules are imported
- pages are only created when opened
- opened pages stay cached
- heavy work is expected to run in background tasks
- headless command functions are separated from UI code where possible

## Elevated Access Model

Micro Toolkit now has two separate elevated helpers, each with a narrow purpose:

### 1. Hotkey Helper

The hotkey helper exists only for global shortcut capture on Linux sessions where the keyboard backend requires elevated input access. It is intentionally narrow and should not be reused for general elevated work.

### 2. Elevated Broker

The elevated broker is the general capability-based elevation layer for future tool/plugin needs.

Important design rules:

- the main app stays non-elevated
- plugins do not get arbitrary root/admin command execution
- elevated actions must be registered as named capabilities
- each capability should do one narrow job
- capabilities should accept structured payloads and return structured results

Examples of good broker capability shapes:

- `filesystem.stat_path`
- `filesystem.secure_delete`
- `system.read_protected_info`
- `network.bind_elevated_port`

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
<storage_root>/data/plugins/<your_plugin_package>/
```

Example:

```text
<storage_root>/data/plugins/my_tools/
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
- `services.request_elevated(...)` only when a capability-based elevated operation is truly required
- `register_elevated_capabilities(...)` only for narrow, explicit elevated operations
- `allow_name_override` and `allow_icon_override` when the plugin should permit user-side display customization
- `preferred_icon` when the plugin wants a default app icon without shipping a custom `.ico`

Avoid:

- imports from non-existent folders
- top-level heavy imports if they are only needed when the user actually runs the tool
- doing large file/network/CPU work directly on the UI thread

### How Custom Plugin Review Works

When a plugin is imported through `Settings -> Plugins`, or even when it is copied manually into `<storage_root>/data/plugins`, the app treats it as a custom plugin with review state.

This review flow does not apply to packaged first-party plugins that were verified through the builtin manifest during app startup.

Default behavior:

- `trusted = false`
- `enabled = false`
- `hidden = false`
- the plugin is not loaded into the main shell

Review flow:

1. Open `Settings -> Plugins`
2. Inspect the plugin `Risk` and `Status` columns
3. Review the plugin code and sidecar files yourself
4. Mark the plugin as `Trusted` only if you accept running that code
5. Enable it if you want it available in the main app

Risk behavior:

- `low`: no obvious risky patterns were found by the static scan
- `medium` or `high`: the app asks for confirmation before trust is applied
- `critical`: import is blocked or the plugin remains quarantined and disabled
- direct elevation patterns such as `sudo`, `pkexec`, `runas`, or similar self-elevation code are treated as high risk
- the broker-based `register_elevated_capabilities(...)` path is the approved exception and is not itself a risk marker

Current protective scope:

- static AST scanning
- explicit trust review
- disabled-by-default custom imports
- load-time failure containment
- automatic quarantine after repeated failures

Current non-goals:

- full sandboxing
- arbitrary-code trust bypass
- generic elevated execution

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

### Display Name and Icon Customization

Plugins can opt into user-side display customization from `Settings -> Plugins`.

Available metadata flags:

- `allow_name_override = True`
- `allow_icon_override = True`
- `preferred_icon = "analytics"`

Example:

```python
class MyPlugin(QtPlugin):
    plugin_id = "my_plugin"
    name = "My Plugin"
    description = "Example plugin."
    category = "General"
    allow_name_override = True
    allow_icon_override = True
    preferred_icon = "search"
```

How it works:

- if allowed, the user can override the display name without changing the plugin code
- if allowed, the user can choose an icon from the app icon library
- if no override is set, the shell falls back to plugin-provided icons or Qt defaults
- if a plugin sets either flag to `False`, the UI keeps that aspect locked

Current icon sources are used in this order:

1. user override from settings
2. sidecar plugin icon such as `my_plugin.ico` or `plugin.ico`
3. plugin `preferred_icon`
4. shell fallback icon by tool/category

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

### Elevated Broker Capabilities

If a plugin really needs elevated access, do not shell out to `sudo`, `pkexec`, or platform elevation tools directly from the plugin page.

Instead:

1. Register a narrow capability
2. Request it through `services.request_elevated(...)`

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

    def register_elevated_capabilities(self, registry, runtime) -> None:
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
result = services.request_elevated(
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
<storage_root>/data/plugins/my_tools/
  my_plugin.py
  my_plugin.en.json
  my_plugin.ar.json
  my_plugin_helpers.py
```

Recommended split:

- plugin class for metadata and widget creation
- helper functions for data processing
- command functions for workflows/CLI
- elevated capability handlers only when absolutely required

## Build and Packaging

Micro Toolkit uses `PyInstaller` in `onedir` mode.

The build scripts regenerate the builtin plugin manifest before packaging so shipped first-party plugins can be verified at runtime in packaged builds.

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
| 0.6.3 | Current | Standardized runtime storage onto per-user platform paths, restored the `Default startup page` option in `Settings -> General`, changed the Plugins table to use the page scrollbar instead of its own horizontal scrollbar, tightened several responsive layout breakpoints across Dashboard, Clipboard, Workflows, and Settings, improved the dock Terminal so typing feels more native and the prompt is visibly styled again, and updated macOS packaging/startup behavior with an app-bundle target plus more mac-aware tray and login-launch handling. |
| 0.6.2 | Previous milestone | Refined the shell and workflow UX: moved quick access management fully into Settings, replaced the dashboard quick-launch area with a more useful workspace pulse panel, improved Workflow Studio with clearer page structure and a command reference table, added Inspector text-unlock mode for selectable static labels, made exit confirmation remember an `Always ask on exit` preference, and fixed several UI behavior bugs across clipboard history, safe scrolling controls, and sidebar selection. |
| 0.6.1 | Internal milestone | Expanded the shell into a top-utility-bar dashboard layout, added the developer Inspector, rebuilt Clipboard Manager around multi-format capture and pinned/category support, renamed and refreshed the core audit tools (`Folder Mapper`, `Deep-Scan Auditor`, `Sequence Auditor`, and `Data-Link Auditor`), added Color Picker and Wi-Fi Profiles improvements, introduced terminal/console dock switching, and tightened builtin-plugin manifest verification plus custom-plugin review flow. |
| 0.6.0 | Stable milestone | Added the dashboard shell, sidebar quick access management, global Dubai font usage, live plugin display name/icon customization, and responsive shell/navigation refinements. Refactored Windows autostart to use the Registry, added an Inno Setup installer script, and implemented a Windows Mutex for reliable application shutdown during uninstallation. |
| 0.5.2 | Internal milestone | Added Qt-Material as the default theme, discarded old custom theme engine (kept only basic required functions), added custom-plugins display-name, icon, and locale sidecar support. |
| 0.5.1 | Internal milestone | Added Document Bridge, plugin-backed `Markdown -> DOCX` and `DOCX -> Markdown`, Linux hotkey helper architecture, capability-based elevated broker, and expanded custom plugin authoring guidance. |
| 0.5.0 | Stable milestone | First full Micro Toolkit desktop release on `PySide6`, with lazy plugin engine, multilingual shell, tray integration, workflows, CLI, plugin packaging, and cross-platform `onedir` build flow. |
| 0.4.5 | Internal milestone | Added custom plugin import/export, enable/disable/hide controls, Introduced some pdf related plugins, and improved the plugin engine performance. |
| 0.4.4 | Internal milestone | Introduced headless tool commands for workflows and CLI plus the quick clipboard panel with shortcut and tray access. |
| 0.4.3 | Internal milestone | Rebuilding the rest of the discontinued toolkit's plugins for the new Plugin Engine built with Qt. |
| 0.4.2 | Internal milestone | Rebuilding the system tools suite into the new plugin engine and made the desktop shell self-contained. |
| 0.4.1 | Internal milestone | Added settings, themes, language switching, tray behavior, autostart, workflow studio, and command registry foundations. |
| 0.4.0 | **discontinued** | *Tkinter app was discontinued in favor of PySide6.*, Started development of the new plugin engine, and underlying architecture. |
| 0.3.0 | Major update | Added new Clipboard plugin with Auto-Capture, Improved workflow studio, Improved overall app layout and style. |
| 0.2.4 | Minor update | Introduced new Plugin Manager for managing plugins, New Hotkeys for global and application scoped shortcuts. |
| 0.2.3 | Minor update | Added some Networks and IT plugins for port scanning, wifi info, etc. |
| 0.2.2 | Minor update | Revamped Sidebr, added a dedicated system-bar inside it for system tools, Improved Animations, Added loading spinner, Added multiple new utility plugins |
| 0.2.1 | Minor update | rebuilt and added Image-Tagger as a plugin, Embedded smart luminance rendering tags |
| 0.2.0 | Major update | Rebranded to Micro Toolkit - a plugin script engine, introduced new plugins "e.g. Folder Exporter, Duplicate Finder, Missing Sequence Finder", added workflow studio, and command registry foundations. |
| 0.1.3 | Minor update | Added dynamic UI alignment mirroring, Ensured single-app instance, Re-assigned Tray-clicks directly to Application |
| 0.1.2 | Minor update | Added dynamic Real-Time Arabic/English Localization, Bound application translations directly to Options preferences, Upgraded the interface to a tabbed modern sidebar layout using `customtkinter` |
| 0.1.1 | Minor update | Added "Open" buttons for seamless UX, Implemented robust Options menu, Default Paths, and System Tray toggleability |
| 0.1.0 | Initial commit | Initial commit as "PDF/File Validator" |
