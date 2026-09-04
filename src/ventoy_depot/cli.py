from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .app import run_tui
from .devices import DeviceError, discover_ventoy_devices, find_device
from .iso import find_isos, identify_iso, verify_detected_iso
from .models import IsoIdentity, VerificationLevel, to_jsonable
from .planner import build_plan
from .providers import Provider, ProviderError, provider_map
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
    doctor.add_argument("--json", action="store_true")
    verify = sub.add_parser(
        "verify", help="verify a current recognized ISO against official metadata when possible"
    )
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
        return _verify(arguments.path, arguments.json)
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
    network = arguments.provider is not None
    results = [_doctor(item, network=network) for item in selected]
    exit_code = _output(results, arguments.json)
    return 4 if network and any(item["status"] != "healthy" for item in results) else exit_code


def _verify(path: Path, as_json: bool) -> int:
    if path.is_symlink() or not path.is_file():
        raise OSError(f"ISO file not found or unsafe: {path}")
    detected = identify_iso(path)
    target = None
    resolution_error = None
    if detected.identity is not None:
        provider = provider_map().get(detected.identity.provider_id)
        if provider is None:
            resolution_error = f"Provider is not available: {detected.identity.provider_id}"
        else:
            try:
                target = provider.resolve(detected.identity)
                if target.identity is None:
                    raise ProviderError("Provider did not declare the target ISO identity.")
                provider.validate_binding(detected.identity, target.identity)
            except Exception as error:
                resolution_error = str(error)
    result = verify_detected_iso(detected, target)
    document = {
        **to_jsonable(result),
        "identity": to_jsonable(detected.identity),
        "detection_source": detected.detection_source,
        "official_metadata_error": resolution_error,
    }
    _output(document, as_json)
    return 4 if result.verified is False else 0


def _doctor(provider: Provider, *, network: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "provider_id": provider.provider_id,
        "origin": provider.origin,
        "custom": provider.custom,
        "status": "configured",
        "network_checked": False,
    }
    if not network:
        return result
    try:
        identity = _doctor_identity(provider)
        artifact = provider.resolve(identity)
        if artifact.identity is None:
            raise ProviderError("Provider did not declare the target ISO identity.")
        provider.validate_binding(identity, artifact.identity)
        if artifact.verification_level == VerificationLevel.UNVERIFIED:
            raise ProviderError("Provider returned an unverified artifact.")
    except Exception as error:
        result.update(status="unavailable", network_checked=True, error=str(error))
        return result
    result.update(
        status="healthy",
        network_checked=True,
        version=artifact.version,
        filename=artifact.filename,
        verification_level=artifact.verification_level.value,
    )
    return result


def _doctor_identity(provider: Provider) -> IsoIdentity:
    capabilities = provider.capabilities
    products = provider.products
    if not products or not capabilities.architectures or not capabilities.channels:
        raise ProviderError("Provider does not declare a probeable product identity.")
    flavor_defaults = {
        "fedora": "live",
        "manjaro": "full",
        "rescuezilla": capabilities.flavors[-1] if capabilities.flavors else None,
        "void-linux": "glibc",
    }
    language_required = {"windows-11"}
    return IsoIdentity(
        provider.provider_id,
        products[0],
        capabilities.editions[0] if capabilities.editions else None,
        flavor_defaults.get(provider.provider_id),
        capabilities.channels[0],
        capabilities.architectures[0],
        capabilities.languages[0]
        if provider.provider_id in language_required and capabilities.languages
        else None,
        None,
        None,
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
