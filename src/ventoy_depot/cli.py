from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .app import run_tui
from .devices import DeviceError, discover_ventoy_devices, find_device
from .iso import find_isos, sha256_file
from .models import to_jsonable
from .planner import build_plan
from .providers import provider_map
from .security import SecurityError, load_and_validate_manifest

SCHEMA_VERSION = "1"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="ventoy-depot")
    sub = result.add_subparsers(dest="command")
    devices = sub.add_parser("devices", help="list detected Ventoy drives")
    devices.add_argument("--json", action="store_true")
    scan = sub.add_parser("scan", help="scan a Ventoy drive without writing")
    scan.add_argument("device")
    scan.add_argument("--json", action="store_true")
    plan = sub.add_parser("plan", help="build a complete read-only update plan")
    plan.add_argument("device")
    plan.add_argument("--refresh", action="store_true")
    plan.add_argument("--json", action="store_true")
    providers = sub.add_parser("providers")
    provider_commands = providers.add_subparsers(dest="provider_command", required=True)
    listing = provider_commands.add_parser("list")
    listing.add_argument("--json", action="store_true")
    validate = provider_commands.add_parser("validate")
    validate.add_argument("file", type=Path)
    doctor = provider_commands.add_parser("doctor")
    doctor.add_argument("provider", nargs="?")
    verify = sub.add_parser("verify", help="calculate the SHA-256 of an existing ISO")
    verify.add_argument("path", type=Path)
    verify.add_argument("--json", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command is None:
            run_tui()
            return 0
        return _dispatch(arguments)
    except (DeviceError, SecurityError, OSError, ValueError) as error:
        _emit({"error": str(error)}, True)
        return 2


def _dispatch(arguments: argparse.Namespace) -> int:
    if arguments.command == "devices":
        return _output(discover_ventoy_devices(), arguments.json)
    if arguments.command == "scan":
        return _output(find_isos(find_device(arguments.device).mount_path), arguments.json)
    if arguments.command == "plan":
        return _output(build_plan(find_device(arguments.device), arguments.refresh), arguments.json)
    if arguments.command == "verify":
        if not arguments.path.is_file():
            raise OSError(f"ISO file not found: {arguments.path}")
        verification = {
            "path": str(arguments.path),
            "algorithm": "sha256",
            "checksum": sha256_file(arguments.path),
        }
        return _output(verification, arguments.json)
    if arguments.provider_command == "list":
        listing = [
            {
                "provider_id": item.provider_id,
                "display_name": item.display_name,
                "capabilities": to_jsonable(item.capabilities),
                "origin": item.origin,
                "custom": item.custom,
            }
            for item in provider_map().values()
        ]
        return _output(listing, arguments.json)
    if arguments.provider_command == "validate":
        manifest = load_and_validate_manifest(arguments.file)
        print(f"valid provider manifest: {manifest['provider_id']}")
        return 0
    selected = [
        item
        for item in provider_map().values()
        if not arguments.provider or item.provider_id == arguments.provider
    ]
    if not selected:
        _emit({"error": "provider not found"}, True)
        return 3
    return _output(
        [
            {
                "provider_id": item.provider_id,
                "status": item.origin,
                "custom": item.custom,
                "network_checked": False,
            }
            for item in selected
        ],
        False,
    )


def _output(value: Any, as_json: bool) -> int:
    if as_json:
        _emit({"data": to_jsonable(value)})
    elif isinstance(value, list):
        for item in value:
            if hasattr(item, "display_name"):
                print(f"{item.identifier}\t{item.display_name}\t{item.mount_path}")
            elif hasattr(item, "path"):
                identity = item.identity.product_id if item.identity else "unknown"
                print(f"{item.path}\t{identity}")
            else:
                print(json.dumps(to_jsonable(item), ensure_ascii=False))
    else:
        print(json.dumps(to_jsonable(value), ensure_ascii=False, indent=2))
    return 0


def _emit(payload: dict[str, Any], error: bool = False) -> None:
    document = {"schema_version": SCHEMA_VERSION, **payload}
    print(json.dumps(document, ensure_ascii=False), file=sys.stderr if error else sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
