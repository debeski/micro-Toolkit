from __future__ import annotations

import importlib
import json
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from micro_toolkit.core.clipboard_store import ClipboardStore
from micro_toolkit.core.command_runtime import HeadlessTaskContext, describe_command_result


def register_builtin_tool_commands(registry, services) -> None:
    def register_task_command(
        command_id: str,
        title: str,
        description: str,
        plugin_id: str,
        module_path: str,
        function_name: str,
        *,
        argument_adapter=None,
        result_adapter=None,
    ) -> None:
        def handler(**kwargs):
            module = importlib.import_module(module_path)
            task_fn = getattr(module, function_name)
            payload = dict(kwargs)
            if argument_adapter is not None:
                payload = argument_adapter(services, payload)
            context = HeadlessTaskContext(services, command_id=command_id)
            try:
                result = task_fn(context, **payload)
            except Exception as exc:
                services.record_run(plugin_id, "ERROR", str(exc)[:500])
                raise
            if result_adapter is not None:
                result = result_adapter(result)
            services.record_run(plugin_id, "SUCCESS", describe_command_result(result))
            return result

        registry.register(command_id, title, description, handler)

    output_dir_str = lambda svc: str(svc.default_output_path())
    output_dir_path = lambda svc: svc.default_output_path()

    register_task_command(
        "tool.sys_audit.run",
        "Run System Audit",
        "Collect local OS, CPU, memory, and disk details.",
        "sys_audit",
        "micro_toolkit.plugins.it_tools.system_audit",
        "gather_system_audit",
        result_adapter=lambda result: json.loads(result),
    )
    register_task_command(
        "tool.quick_analytics.run",
        "Run Quick Analytics",
        "Group an Excel workbook by selected columns.",
        "quick_analytics",
        "micro_toolkit.plugins.core_tools.quick_analytics",
        "generate_analytics_report",
    )
    register_task_command(
        "tool.cred_scanner.scan",
        "Scan Credentials",
        "Scan a folder for credential-like strings.",
        "cred_scanner",
        "micro_toolkit.plugins.it_tools.credential_scanner",
        "run_credential_scan",
    )
    register_task_command(
        "tool.net_scan.run",
        "Run Network Scan",
        "Scan a host across the requested TCP ports.",
        "net_scan",
        "micro_toolkit.plugins.it_tools.network_scanner",
        "run_network_scan",
        argument_adapter=lambda svc, payload: {
            **payload,
            "timeout_seconds": float(payload.get("timeout_seconds", 0.3)),
            "output_dir": Path(payload["output_dir"]) if payload.get("output_dir") else output_dir_path(svc),
        },
    )
    register_task_command(
        "tool.shredder.run",
        "Shred File",
        "Securely overwrite and delete a file.",
        "shredder",
        "micro_toolkit.plugins.it_tools.privacy_shredder",
        "secure_shred_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "passes": int(payload.get("passes", 3)),
        },
    )
    register_task_command(
        "tool.exporter.run",
        "Export Folder Contents",
        "Export file metadata from a folder tree to Excel.",
        "exporter",
        "micro_toolkit.plugins.core_tools.folder_exporter",
        "export_folder_contents_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.validator.run",
        "Validate Files",
        "Validate workbook filenames against one or more source folders.",
        "validator",
        "micro_toolkit.plugins.core_tools.validator",
        "validate_files_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "source_folders": list(payload.get("source_folders", [])),
            "column_names": list(payload.get("column_names", [])),
            "dest_folder": payload.get("dest_folder"),
            "split_folders": bool(payload.get("split_folders", False)),
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.seq.run",
        "Find Missing Sequence",
        "Find missing sequence values in a folder listing or workbook column.",
        "seq",
        "micro_toolkit.plugins.core_tools.sequence_finder",
        "sequence_finder_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.dups.excel",
        "Find Excel Duplicates",
        "Find duplicate rows in an Excel column.",
        "dups",
        "micro_toolkit.plugins.core_tools.duplicate_finder",
        "find_duplicates_in_excel_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.dups.folder",
        "Find Folder Duplicates",
        "Find duplicate files in a folder tree.",
        "dups",
        "micro_toolkit.plugins.core_tools.duplicate_finder",
        "find_duplicates_in_folders_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "criteria": list(payload.get("criteria", [])),
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.cleaner.run",
        "Run Data Cleaner",
        "Clean an Excel workbook and write a new output file.",
        "cleaner",
        "micro_toolkit.plugins.office_tools.data_cleaner",
        "sanitize_data_task",
        argument_adapter=lambda svc, payload: {
            "file_path": payload["file_path"],
            "trim": bool(payload.get("trim", True)),
            "drop_empty": bool(payload.get("drop_empty", True)),
            "fill_nulls": bool(payload.get("fill_nulls", True)),
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.cross_joiner.run",
        "Run Cross Join",
        "Compare two workbooks and export matches and deltas.",
        "cross_joiner",
        "micro_toolkit.plugins.office_tools.cross_joiner",
        "cross_join_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.pdf_suite.merge",
        "Merge PDFs",
        "Merge multiple PDF files into one output document.",
        "pdf_suite",
        "micro_toolkit.plugins.office_tools.pdf_suite",
        "merge_pdfs_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "file_paths": list(payload.get("file_paths", [])),
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
        },
    )
    register_task_command(
        "tool.batch_renamer.run",
        "Batch Rename Files",
        "Rename files in bulk using text or regex replacement.",
        "batch_renamer",
        "micro_toolkit.plugins.file_tools.batch_renamer",
        "batch_rename_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "replace_str": payload.get("replace_str", ""),
            "use_regex": bool(payload.get("use_regex", False)),
        },
    )
    register_task_command(
        "tool.smart_org.organize",
        "Organize Files",
        "Organize root-level files by extension or date.",
        "smart_org",
        "micro_toolkit.plugins.file_tools.smart_organizer",
        "organize_files_task",
    )
    register_task_command(
        "tool.smart_org.undo",
        "Undo Organization",
        "Undo the last saved smart organization run.",
        "smart_org",
        "micro_toolkit.plugins.file_tools.smart_organizer",
        "undo_organization_task",
    )
    register_task_command(
        "tool.deep_searcher.run",
        "Run Deep Search",
        "Search file contents under a folder tree.",
        "deep_searcher",
        "micro_toolkit.plugins.file_tools.deep_searcher",
        "run_deep_search_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "use_regex": bool(payload.get("use_regex", False)),
        },
    )
    register_task_command(
        "tool.usage_analyzer.run",
        "Analyze Usage",
        "Summarize top-level file and folder sizes.",
        "usage_analyzer",
        "micro_toolkit.plugins.file_tools.usage_analyzer",
        "analyze_usage_task",
    )
    register_task_command(
        "tool.img_trans.run",
        "Transform Images",
        "Batch transform images using rotate, resize, and format options.",
        "img_trans",
        "micro_toolkit.plugins.media_tools.image_transformer",
        "run_image_transform_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "files": list(payload.get("files", [])),
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
            "options": dict(payload.get("options", {})),
        },
    )
    register_task_command(
        "tool.tagger.run",
        "Tag Images",
        "Batch apply date/name tags to images.",
        "tagger",
        "micro_toolkit.plugins.media_tools.image_tagger",
        "run_image_tagger_task",
        argument_adapter=lambda svc, payload: {
            **payload,
            "files": list(payload.get("files", [])),
            "output_dir": payload.get("output_dir", output_dir_str(svc)),
            "custom_date": payload.get("custom_date", ""),
        },
    )

    def clipboard_list(search: str = "", content_type: str = "ALL", label: str = "", limit: int = 50):
        store = ClipboardStore(services.database_path)
        return store.list_entries(
            search=search,
            content_type=content_type or "ALL",
            label=label,
        )[: max(1, int(limit))]

    def clipboard_copy(entry_id: int | None = None, search: str = ""):
        store = ClipboardStore(services.database_path)
        entries = store.list_entries(search=search)
        target = None
        if entry_id is not None:
            for entry in entries:
                if entry.entry_id == int(entry_id):
                    target = entry
                    break
        elif entries:
            target = entries[0]
        if target is None:
            raise ValueError("No clipboard entry matched the requested selection.")
        clipboard = QGuiApplication.clipboard() if QGuiApplication.instance() is not None else None
        copied = False
        if clipboard is not None:
            clipboard.setText(target.content)
            copied = True
        services.record_run("clip_manager", "SUCCESS", f"Clipboard entry {target.entry_id} copied")
        return {
            "entry_id": target.entry_id,
            "content_type": target.content_type,
            "label": target.label,
            "content": target.content,
            "copied_to_system_clipboard": copied,
        }

    def clipboard_clear():
        store = ClipboardStore(services.database_path)
        count = len(store.list_entries())
        store.clear_entries()
        services.record_run("clip_manager", "SUCCESS", f"Cleared {count} clipboard entrie(s)")
        return {"cleared": count}

    registry.register(
        "tool.clipboard.list",
        "List Clipboard Entries",
        "Return recent clipboard history entries from the persistent store.",
        clipboard_list,
    )
    registry.register(
        "tool.clipboard.copy",
        "Copy Clipboard Entry",
        "Copy a clipboard entry by id, or the newest match when no id is provided.",
        clipboard_copy,
    )
    registry.register(
        "tool.clipboard.clear",
        "Clear Clipboard History",
        "Delete all stored clipboard history entries.",
        clipboard_clear,
    )
