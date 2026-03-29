from __future__ import annotations

import sys


def build_gui_launch_args(*, plugin_id: str | None = None, start_minimized: bool = False, force_visible: bool = False) -> list[str]:
    if getattr(sys, "frozen", False):
        args = [sys.executable, "gui"]
    else:
        args = [sys.executable, "-m", "dngine", "gui"]
    if plugin_id:
        args.extend(["--plugin-id", plugin_id])
    if start_minimized:
        args.append("--start-minimized")
    if force_visible:
        args.append("--force-visible")
    return args


def build_background_subcommand_args(subcommand: str, *args: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, subcommand, *args]
    return [sys.executable, "-m", "dngine", subcommand, *args]
