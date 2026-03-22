import sys

from micro_toolkit.core.cli import build_parser, execute_cli
from micro_toolkit.main import launch_gui


if __name__ == "__main__":
    if len(sys.argv) == 1:
        raise SystemExit(launch_gui())

    parser = build_parser()
    parsed = parser.parse_args()
    if parsed.command in {None, "gui"}:
        raise SystemExit(launch_gui(initial_plugin_id=getattr(parsed, "plugin_id", None), start_minimized=getattr(parsed, "start_minimized", False)))
    raise SystemExit(execute_cli(parsed))
