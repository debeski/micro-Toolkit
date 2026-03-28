# Plugin Standardization Audit Report

This report reflects the current state of the Micro Toolkit plugin tree after the remaining compliance pass. The standard baseline is now:

- `bind_tr(...)` for page translation
- `apply_page_chrome(...)` for normal page chrome
- live `theme_changed` and `language_changed` refresh wiring
- shared semantic classes for previews, charts, outputs, hero surfaces, and other approved special cases

## Compliance Levels

| Status | Meaning |
| :--- | :--- |
| ✅ **Compliant** | Uses `apply_page_chrome`, `bind_tr`, and both live theme/language refresh signals correctly. Any remaining local styling is limited to approved special surfaces or specialized value displays. |
| ⚠️ **Partial** | Intentionally deviates from the standard page-chrome model because the page layout is custom, but still uses the shared translation and theme foundations. |
| ❌ **Legacy** | Still relies on avoidable manual page chrome or legacy translation patterns. |

## Audit Results by Category

### System Utilities
- [dash_hub.py](micro_toolkit/plugins/system/dash_hub.py): ⚠️ **Partial**. Approved custom-layout exception. Keeps its dashboard/hero structure, uses `bind_tr`, and refreshes on both theme/language changes, but intentionally does not use the standard `apply_page_chrome(...)` page shape.
- [command_center.py](micro_toolkit/plugins/system/command_center.py): ✅ **Compliant**.
- [clip_snip.py](micro_toolkit/plugins/system/clip_snip.py): ✅ **Compliant**.
- [about_info.py](micro_toolkit/plugins/system/about_info.py): ✅ **Compliant**.
- [dev_lab.py](micro_toolkit/plugins/system/dev_lab.py): ✅ **Compliant**.
- [workflow_studio.py](micro_toolkit/plugins/system/workflow_studio.py): ✅ **Compliant**.

### IT Tools
- [privacy_shredder.py](micro_toolkit/plugins/it_tools/privacy_shredder.py): ✅ **Compliant**.
- [system_audit.py](micro_toolkit/plugins/it_tools/system_audit.py): ✅ **Compliant**.
- [wifi_profiles.py](micro_toolkit/plugins/it_tools/wifi_profiles.py): ✅ **Compliant**.
- [network_scanner.py](micro_toolkit/plugins/it_tools/network_scanner.py): ✅ **Compliant**.
- [credential_scanner.py](micro_toolkit/plugins/it_tools/credential_scanner.py): ✅ **Compliant**.

### Media Tools
- [image_transformer.py](micro_toolkit/plugins/media_tools/image_transformer.py): ✅ **Compliant**.
- [image_tagger.py](micro_toolkit/plugins/media_tools/image_tagger.py): ✅ **Compliant**.
- [color_picker.py](micro_toolkit/plugins/media_tools/color_picker.py): ✅ **Compliant**.

### Data Tools
- [chart_builder.py](micro_toolkit/plugins/data_tools/chart_builder.py): ✅ **Compliant**.
- [data_link_auditor.py](micro_toolkit/plugins/data_tools/data_link_auditor.py): ✅ **Compliant**.
- [deep_scan_auditor.py](micro_toolkit/plugins/data_tools/deep_scan_auditor.py): ✅ **Compliant**.
- [folder_mapper.py](micro_toolkit/plugins/data_tools/folder_mapper.py): ✅ **Compliant**.
- [sequence_auditor.py](micro_toolkit/plugins/data_tools/sequence_auditor.py): ✅ **Compliant**.

### Office Tools
- [cross_joiner.py](micro_toolkit/plugins/office_tools/cross_joiner.py): ✅ **Compliant**.
- [data_cleaner.py](micro_toolkit/plugins/office_tools/data_cleaner.py): ✅ **Compliant**.
- [document_bridge.py](micro_toolkit/plugins/office_tools/document_bridge.py): ✅ **Compliant**.
- [pdf_suite.py](micro_toolkit/plugins/office_tools/pdf_suite.py): ✅ **Compliant**.

## Summary of Findings

1. **Standard pages are now compliant**: the remaining normal plugin pages use the shared translation helper path, the shared page-chrome path, and live language/theme refresh.
2. **Live language refresh gap closed**: the previous missing-language pages were brought onto live `language_changed` wiring:
   - [clip_snip.py](micro_toolkit/plugins/system/clip_snip.py)
   - [chart_builder.py](micro_toolkit/plugins/data_tools/chart_builder.py)
   - [data_link_auditor.py](micro_toolkit/plugins/data_tools/data_link_auditor.py)
   - [deep_scan_auditor.py](micro_toolkit/plugins/data_tools/deep_scan_auditor.py)
   - [folder_mapper.py](micro_toolkit/plugins/data_tools/folder_mapper.py)
   - [sequence_auditor.py](micro_toolkit/plugins/data_tools/sequence_auditor.py)
3. **Former outlier fixed**: [document_bridge.py](micro_toolkit/plugins/office_tools/document_bridge.py) now uses `apply_page_chrome(...)` and is no longer a manual page-chrome exception.
4. **Only intentional exception remains**: [dash_hub.py](micro_toolkit/plugins/system/dash_hub.py) is now the sole documented `Partial` page because its dashboard/hero composition is intentionally custom.
5. **Guardrail status**: the plugin tree passes [audit_global_ui.py](tools/audit_global_ui.py), including the added live-language wiring check for page widgets.
