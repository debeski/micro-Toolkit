# Micro Toolkit - Thourough Project Analysis

## High-Level Overview
Micro Toolkit is a cross-platform (Windows, macOS, Linux), multilingual (English and Arabic), plugin-driven desktop companion application built with `PySide6`. It is designed to provide users with a fast, responsive suite of utilities, including file manipulation, media tools, office/spreadsheet analysis, IT/system tools, and clipboard management.

The architecture emphasizes lazy loading of plugins to ensure rapid startup and responsiveness, backed by a capability-based elevated broker for privileged operations.

---

## Directory & Package Structure

### Root Structure
- `/micro_toolkit`: Main package containing application source.
- `/build_*`: Build system scripts for different platforms (Linux, macOS, Windows).
- `/micro-toolkit.iss`, `/micro-toolkit.spec`: Installer and PyInstaller specification files.
- `requirements.txt`: Python package dependencies.
- `README.md`: Central documentation for architecture, goals, and setup.

### `/micro_toolkit` Structure
The core application code is divided mainly into two directories:
1. `core/`: The low-level architecture, base classes, utilities, and background engines.
2. `plugins/`: The high-level tool implementations, grouped into functional categories.
3. `assets/` & `i18n/`: Static resources and global translations.
4. Entry points: `app.py`, `main.py`, `__main__.py` acting as the main GUI runner and CLI endpoint.

---

## Core Architecture & Low-Level Components (`micro_toolkit/core/`)

The `core` directory implements the runtime behavior, plugin management, and foundational services.

- **Plugin Engine**: 
  - `plugin_api.py`, `plugin_manager.py`, `plugin_state.py`, `plugin_packages.py`, `plugin_security.py`
  - Handles AST-based metadata discovery, lazy loading of modules, and UI construction.
  - Implements a trust/quarantine model for custom plugins, preventing malicious code from executing blindly.
- **Commands & Workflows**: 
  - `command_runtime.py`, `commands.py`, `workflows.py`, `cli.py`
  - Allows headlessly invoking tasks. This ties into the Workflow Studio for chaining utilities.
- **Broker & Elevation**: 
  - `elevated_broker.py`, `elevation.py`, `hotkey_helper.py`
  - The hotkey helper manages global hotkeys (particularly on Linux).
  - The elevated broker provides a safe architecture for executing privileged requests (e.g., `filesystem.stat_path`, `system.identity`, `backup.restore_snapshot`) without providing arbitrary shell or python execution to plugins. It spins up an isolated background process communicating via local sockets using a secure token.
- **Global Services**:
  - `services.py`, `app_config.py`, `theme.py`, `i18n.py`, `clipboard_store.py`
  - Managing application state, UI themes, and locale configurations across plugins.
- **Background Execution**:
  - `workers.py`, `session_manager.py`, `backup_manager.py`
  - Provides threaded job execution via `services.run_task` to prevent UI freezing during heavy processes (e.g., deep file scanning).

---

## High-Level Tools & Plugins (`micro_toolkit/plugins/`)

The application's functionality is exposed via "plugins" organized categorically.

### 1. Standalone Companion Pages
- `about_center.py`
- `settings_center.py`: Global settings, plugin trust management, UI customization.
- `clipboard_manager.py`: Advanced multi-format clipboard history, pinning, and categorizing.
- `inspector_center.py`: A `Developer mode` UI inspector to debug PySide6 properties.
- `workflow_studio.py`: Used to construct headless automation pipelines.

### 2. File Utilities (`plugins/file_tools/`)
- `batch_renamer.py`: Rename multiple files using patterns.
- `deep_searcher.py`: Advanced file content or name search.
- `smart_organizer.py`: Rules-based file organization.
- `usage_analyzer.py`: Visualizes disk space consumption based on file sizes.

### 3. Media Utilities (`plugins/media_tools/`)
- `image_transformer.py`: Resizing, converting, and compressing images.
- `image_tagger.py`: Appending or modifying image metadata.
- `color_picker.py`: Screen color sampling across multiple monitors (HEX, RGB, HSL).

### 4. IT & System Utilities (`plugins/it_tools/`)
- `system_audit.py`: Real-time system hardware, disk, and memory profiling.
- `credential_scanner.py`, `privacy_shredder.py`: Security auditing tools.
- `network_scanner.py`: Local port scanning mechanism.
- `wifi_profiles.py`: View and manage saved Wi-Fi networks.

### 5. Office & Document Tools (`plugins/office_tools/`)
- `document_bridge.py`: Conversions between Markdown and DOCX.
- `cross_joiner.py`, `data_cleaner.py`: Spreadsheet data manipulation.
- `pdf_suite.py`: Multi-tool PDF modification engine.

### 6. Validation & Analysis Tools (`plugins/core_tools/`)
- `chart_builder.py`: Rendering data visualizations from tabular data.
- `folder_mapper.py`: Exporting structural file hierarchies into Excel sheets.
- `deep_scan_auditor.py`: Deduplication and cross-sheet column lookups.
- `data_link_auditor.py`: Checking references from a workbook against a real filesystem.
- `sequence_auditor.py`: Finding missing chronological or numerical steps in directories/sheets.

---

## Conclusion
Micro Toolkit is structurally sound, leveraging PySide6 for an integrated local-first desktop experience. Its strict separation between UI, long-running background tasks (`workers.py`), and elevated execution (`elevated_broker.py`) ensures security and stability.

The plugin system's capability to safely quarantine untested code makes the environment robust against bad third-party extensions, while retaining immense customization through workflows and custom plugins.
