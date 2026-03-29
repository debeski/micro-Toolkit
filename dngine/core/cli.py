from __future__ import annotations

import argparse
import json

from dngine import APP_NAME
from dngine.core.elevated_broker import build_elevated_broker_parser, run_elevated_broker_service
from dngine.core.hotkey_helper import build_helper_parser, run_hotkey_helper_service
from dngine.core.services import AppServices


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m dngine", description=APP_NAME)
    subparsers = parser.add_subparsers(dest="command")

    gui = subparsers.add_parser("gui", help="Launch the desktop application")
    gui.add_argument("--plugin-id", default=None)
    gui.add_argument("--start-minimized", action="store_true")
    gui.add_argument("--force-visible", action="store_true")

    plugins = subparsers.add_parser("plugins", help="Inspect discovered plugins")
    plugins_sub = plugins.add_subparsers(dest="plugins_command", required=True)
    plugins_sub.add_parser("list", help="List plugins")
    plugin_info = plugins_sub.add_parser("info", help="Show plugin details")
    plugin_info.add_argument("plugin_id")

    history = subparsers.add_parser("history", help="Show recent execution history")
    history.add_argument("--limit", type=int, default=20)

    config = subparsers.add_parser("config", help="Inspect configuration")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("show", help="Show config")
    config_startup = config_sub.add_parser("startup", help="Update startup preferences")
    startup_toggle = config_startup.add_mutually_exclusive_group(required=True)
    startup_toggle.add_argument("--enable", action="store_true")
    startup_toggle.add_argument("--disable", action="store_true")
    config_startup.add_argument("--start-minimized", action="store_true")

    workflows = subparsers.add_parser("workflows", help="Manage saved workflows")
    workflows_sub = workflows.add_subparsers(dest="workflows_command", required=True)
    workflows_sub.add_parser("list", help="List workflows")
    workflow_show = workflows_sub.add_parser("show", help="Show a workflow JSON payload")
    workflow_show.add_argument("name")
    workflow_run = workflows_sub.add_parser("run", help="Run a workflow from the CLI")
    workflow_run.add_argument("name")

    commands = subparsers.add_parser("commands", help="List registered workflow/CLI commands")
    commands_sub = commands.add_subparsers(dest="commands_command", required=True)
    commands_sub.add_parser("list", help="List commands")
    commands_run = commands_sub.add_parser("run", help="Run one registered command")
    commands_run.add_argument("command_id")
    commands_run.add_argument("--args", default="{}", help="JSON object of keyword arguments")

    broker = subparsers.add_parser("broker", help="Inspect or control broker namespaces")
    broker_ns = broker.add_subparsers(dest="broker_namespace", required=True)

    elevated = broker_ns.add_parser("elevated", help="Inspect or control the elevated broker")
    elevated_sub = elevated.add_subparsers(dest="broker_command", required=True)
    elevated_sub.add_parser("capabilities", help="List registered elevated capabilities")
    elevated_sub.add_parser("start", help="Start the elevated broker for the current session")
    elevated_sub.add_parser("stop", help="Stop the elevated broker")
    broker_run = elevated_sub.add_parser("run", help="Run one elevated capability")
    broker_run.add_argument("capability_id")
    broker_run.add_argument("--payload", default="{}", help="JSON object payload")

    build_helper_parser(subparsers)
    build_elevated_broker_parser(subparsers)

    return parser


def execute_cli(args) -> int:
    services = AppServices()

    if args.command == "plugins":
        specs = services.plugin_manager.discover_plugins()
        if args.plugins_command == "list":
            for spec in specs:
                print(f"{spec.plugin_id}\t{spec.name}\t{spec.category or 'Standalone'}")
            return 0
        spec = services.plugin_manager.get_spec(args.plugin_id)
        if spec is None:
            raise SystemExit(f"Unknown plugin id: {args.plugin_id}")
        print(json.dumps(spec.__dict__, indent=2, default=str))
        return 0

    if args.command == "history":
        rows = services.session_manager.get_history(limit=max(1, args.limit))
        for row in rows:
            print("\t".join(str(item) for item in row))
        return 0

    if args.command == "config" and args.config_command == "show":
        print(json.dumps(services.config.get_all(), indent=2))
        return 0

    if args.command == "config" and args.config_command == "startup":
        enabled = bool(args.enable) and not bool(args.disable)
        result = services.set_startup_preferences(enabled, start_minimized=bool(args.start_minimized))
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "workflows":
        if args.workflows_command == "list":
            for name in services.workflow_manager.list_workflows():
                print(name)
            return 0
        if args.workflows_command == "show":
            print(json.dumps(services.workflow_manager.load_workflow(args.name), indent=2))
            return 0
        if args.workflows_command == "run":
            services.ensure_plugin_commands_registered()
            result = services.workflow_manager.run_workflow(
                args.name,
                services.command_registry,
                log_cb=lambda message: print(message),
            )
            print(json.dumps(services.serialize_result(result), indent=2, ensure_ascii=False))
            return 0

    if args.command == "commands":
        services.ensure_plugin_commands_registered()
        if args.commands_command == "list":
            for spec in services.command_registry.list_commands():
                print(f"{spec.command_id}\t{spec.title}")
            return 0
        if args.commands_command == "run":
            try:
                payload = json.loads(args.args or "{}")
            except Exception as exc:
                raise SystemExit(f"Invalid JSON for --args: {exc}") from exc
            if not isinstance(payload, dict):
                raise SystemExit("Command arguments must be a JSON object.")
            result = services.command_registry.execute(args.command_id, **payload)
            print(json.dumps(services.serialize_result(result), indent=2, ensure_ascii=False))
            return 0

    if args.command == "broker" and args.broker_namespace == "elevated":
        if args.broker_command == "capabilities":
            print(json.dumps(services.elevated_broker.list_capabilities(), indent=2, ensure_ascii=False))
            return 0
        if args.broker_command == "start":
            ok, message = services.elevated_broker.start()
            print(message)
            return 0 if ok else 1
        if args.broker_command == "stop":
            ok, message = services.elevated_broker.stop()
            print(message)
            return 0 if ok else 1
        if args.broker_command == "run":
            try:
                payload = json.loads(args.payload or "{}")
            except Exception as exc:
                raise SystemExit(f"Invalid JSON for --payload: {exc}") from exc
            if not isinstance(payload, dict):
                raise SystemExit("Broker payload must be a JSON object.")
            result = services.elevated_broker.request(args.capability_id, payload)
            print(json.dumps(services.serialize_result(result), indent=2, ensure_ascii=False))
            return 0

    if args.command == "hotkey-helper":
        return run_hotkey_helper_service(args)

    if args.command == "elevated-broker":
        return run_elevated_broker_service(args)

    raise SystemExit(2)
