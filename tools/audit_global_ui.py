from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_CARD_COLORS = ("#fffdf9", "#fffaf3", "#fff7f2", "#eadfce", "#e0d5c6", "#efd3c9")
NORMAL_CONTROL_SELECTORS = (
    "QLineEdit",
    "QTextEdit",
    "QPlainTextEdit",
    "QComboBox",
    "QSpinBox",
    "QDoubleSpinBox",
    "QPushButton",
    "QListWidget",
    "QTableView",
    "QTableWidget",
)
TRIPLE_STYLE_BLOCK = re.compile(r"setStyleSheet\(\s*(?:f)?([\"']{3})(?P<body>.*?)(?:\1)\s*\)", re.DOTALL)
PAGE_WIDGET_CLASS = re.compile(r"class\s+\w+Page\s*\(\s*QWidget\s*\)")


def iter_python_files(paths: list[str]) -> list[Path]:
    resolved: list[Path] = []
    for raw_path in paths:
        path = (REPO_ROOT / raw_path).resolve()
        if path.is_file() and path.suffix == ".py":
            resolved.append(path)
            continue
        if path.is_dir():
            resolved.extend(sorted(candidate for candidate in path.rglob("*.py") if candidate.is_file()))
    return resolved


def line_number_for_offset(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def audit_file(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    relative = path.relative_to(REPO_ROOT)
    findings: list[str] = []

    for match in re.finditer(r"def\s+_pt\s*\(", content):
        findings.append(f"{relative}:{line_number_for_offset(content, match.start())}: local _pt wrapper still present")
    for match in re.finditer(r"def\s+_tr\s*\(", content):
        findings.append(f"{relative}:{line_number_for_offset(content, match.start())}: local _tr wrapper still present")
    for match in re.finditer(r"\bself\._pt\b", content):
        findings.append(f"{relative}:{line_number_for_offset(content, match.start())}: stale self._pt reference still present")
    for match in re.finditer(r"\bself\._t\b", content):
        findings.append(f"{relative}:{line_number_for_offset(content, match.start())}: stale self._t reference still present")

    if "plugins" in relative.parts:
        for match in re.finditer(r"\bplugin_text\s*\(", content):
            findings.append(
                f"{relative}:{line_number_for_offset(content, match.start())}: direct plugin_text wrapper/use still present"
            )
        for match in re.finditer(r'InlineIconButton', content):
            findings.append(
                f"{relative}:{line_number_for_offset(content, match.start())}: legacy InlineIconButton object-name pattern still present"
            )

    if relative != Path("micro_toolkit/app.py"):
        for color in LEGACY_CARD_COLORS:
            for match in re.finditer(re.escape(color), content, flags=re.IGNORECASE):
                findings.append(f"{relative}:{line_number_for_offset(content, match.start())}: legacy card color {color} still present")

    for match in TRIPLE_STYLE_BLOCK.finditer(content):
        body = match.group("body")
        if any(selector in body for selector in NORMAL_CONTROL_SELECTORS):
            line = line_number_for_offset(content, match.start())
            findings.append(f"{relative}:{line}: raw descendant stylesheet still targets normal controls")

    if "plugins" in relative.parts:
        for match in re.finditer(r"\bQProgressBar\s*\(", content):
            findings.append(f"{relative}:{line_number_for_offset(content, match.start())}: plugin-local QProgressBar still present")
        if PAGE_WIDGET_CLASS.search(content) and "bind_tr(" in content and "language_changed.connect" not in content:
            findings.append(f"{relative}: missing live language_changed wiring for page widget")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Micro Toolkit UI files for zero-boilerplate style regressions.")
    parser.add_argument(
        "paths",
        nargs="*",
        default=["micro_toolkit/plugins/system", "micro_toolkit/core", "micro_toolkit/app.py"],
        help="Files or directories to audit, relative to the repo root.",
    )
    args = parser.parse_args()

    files = iter_python_files(args.paths)
    if not files:
        print("No Python files matched the requested audit scope.", file=sys.stderr)
        return 1

    findings: list[str] = []
    for path in files:
        findings.extend(audit_file(path))

    if findings:
        print("\n".join(findings))
        return 1

    print(f"UI audit passed for {len(files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
