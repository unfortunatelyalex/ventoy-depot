from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from .devices import revalidate_device
from .models import Device, PlanItem, UpdateAction, VerificationLevel
from .network import SafeHttpClient
from .security import SecurityError, safe_filename


class TransferError(RuntimeError):
    pass


Progress = Callable[[str, int, int], None]


def apply_item(
    item: PlanItem,
    progress: Progress | None = None,
    cache_dir: Path | None = None,
    trusted_keyring: Path | None = None,
) -> Path:
    artifact = item.target
    if artifact is None or item.local.identity is None:
        raise TransferError("Plan item has no resolved target.")
    if item.action == UpdateAction.SKIP:
        raise TransferError("Skipped plan items cannot be applied.")
    if artifact.verification_level == VerificationLevel.UNVERIFIED:
        raise TransferError("Unverified artifacts cannot be applied automatically.")
    device_root = _device_root(item.local.path)
    destination = item.local.path.parent / safe_filename(artifact.filename)
    _within(device_root, destination)
    if destination.exists():
        raise TransferError(f"Target ISO already exists: {destination.name}")
    device = _device_for_path(device_root)
    revalidate_device(device)
    required = artifact.size_bytes or 0
    if shutil.disk_usage(device_root).free < required:
        raise TransferError("Insufficient free space on the Ventoy drive.")

    client = SafeHttpClient(artifact.allowed_hosts, timeout=60)
    temporary_context = (
        tempfile.TemporaryDirectory(prefix="ventoy-depot-") if cache_dir is None else None
    )
    staging = Path(temporary_context.name) if temporary_context else cache_dir
    assert staging is not None
    staging.mkdir(parents=True, exist_ok=True)
    downloaded = staging / f"{artifact.filename}.download"
    partial = destination.with_name(f"{destination.name}.partial")
    try:
        _download(client, artifact.download_url, downloaded, artifact.size_bytes, progress)
        _verify(downloaded, artifact.checksum_algorithm, artifact.checksum)
        if artifact.verification_level == VerificationLevel.SIGNED:
            if trusted_keyring is None:
                raise TransferError("Signed artifact requires a trusted provider keyring.")
            assert artifact.signature_url is not None
            signature_path = staging / f"{artifact.filename}.sig"
            signature_path.write_bytes(client.metadata(artifact.signature_url))
            _verify_openpgp(
                downloaded,
                signature_path,
                trusted_keyring,
                artifact.signer_fingerprints,
            )
        if progress:
            progress("download-verify", downloaded.stat().st_size, downloaded.stat().st_size)
        revalidate_device(device)
        if shutil.disk_usage(device_root).free < downloaded.stat().st_size:
            raise TransferError("Insufficient free space on the Ventoy drive before copying.")
        _copy(downloaded, partial, progress)
        _verify(partial, artifact.checksum_algorithm, artifact.checksum)
        _fsync_file(partial)
        os.replace(partial, destination)
        _fsync_directory(destination.parent)
        if item.action == UpdateAction.REPLACE and item.local.path != destination:
            _trash(item.local.path, device_root)
        return destination
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    finally:
        if temporary_context is not None:
            temporary_context.cleanup()


def verify_file(path: Path, algorithm: str, expected: str) -> bool:
    try:
        _verify(path, algorithm, expected)
    except TransferError:
        return False
    return True


def _download(
    client: SafeHttpClient,
    url: str,
    target: Path,
    expected_size: int | None,
    progress: Progress | None,
) -> None:
    validator_path = target.with_suffix(target.suffix + ".json")
    validator = _load_download_validator(validator_path)
    existing = target.stat().st_size if target.exists() and validator else 0
    headers: dict[str, str] = {}
    if existing and validator is not None:
        headers["Range"] = f"bytes={existing}-"
        headers["If-Range"] = validator
    response = client.open(url, headers)
    status = getattr(response, "status", 200)
    mode = "ab" if existing and status == 206 else "wb"
    completed = existing if mode == "ab" else 0
    total = expected_size or completed + int(response.headers.get("Content-Length", 0))
    if total and shutil.disk_usage(target.parent).free < max(total - completed, 0):
        response.close()
        raise TransferError("Insufficient free space in the download staging directory.")
    current_validator = response.headers.get("ETag") or response.headers.get("Last-Modified")
    if current_validator:
        validator_path.write_text(
            json.dumps({"validator": current_validator}) + "\n", encoding="utf-8"
        )
    else:
        validator_path.unlink(missing_ok=True)
    with target.open(mode) as output:
        while block := response.read(1024 * 1024):
            completed += len(block)
            if expected_size is not None and completed > expected_size:
                raise TransferError("Download exceeded its advertised size.")
            output.write(block)
            if progress:
                progress("download", completed, total)
        output.flush()
        os.fsync(output.fileno())
    response.close()
    if expected_size is not None and completed != expected_size:
        raise TransferError("Download size does not match provider metadata.")


def _load_download_validator(path: Path) -> str | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("validator")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return str(value) if value else None


def _copy(source: Path, target: Path, progress: Progress | None) -> None:
    total = source.stat().st_size
    completed = 0
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        while block := incoming.read(1024 * 1024):
            outgoing.write(block)
            completed += len(block)
            if progress:
                progress("copy", completed, total)
        outgoing.flush()
        os.fsync(outgoing.fileno())


def _verify(path: Path, algorithm: str, expected: str) -> None:
    if algorithm not in {"sha256", "sha512"}:
        raise TransferError("Only SHA-256 and SHA-512 are accepted.")
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    if not expected or digest.hexdigest().lower() != expected.lower():
        raise TransferError("Artifact checksum does not match official metadata.")


def _verify_openpgp(
    artifact: Path,
    signature: Path,
    keyring: Path,
    fingerprints: tuple[str, ...],
) -> None:
    executable = shutil.which("gpgv")
    if executable is None:
        hint = "Install GnuPG (for example: apt install gpgv)."
        if platform.system() == "Windows":
            hint = "Install Gpg4win and ensure gpgv.exe is on PATH."
        raise TransferError(f"GnuPG is required for this provider. {hint}")
    if not keyring.is_file():
        raise TransferError("Trusted provider keyring is missing.")
    with tempfile.TemporaryDirectory(prefix="ventoy-depot-gpg-") as home:
        result = subprocess.run(
            [
                executable,
                "--homedir",
                home,
                "--status-fd",
                "1",
                "--keyring",
                str(keyring.resolve()),
                str(signature),
                str(artifact),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode:
        raise TransferError("Publisher signature verification failed.")
    valid = {
        line.split()[2].upper()
        for line in result.stdout.splitlines()
        if line.startswith("[GNUPG:] VALIDSIG ") and len(line.split()) > 2
    }
    pinned = {fingerprint.upper() for fingerprint in fingerprints}
    if not valid.intersection(pinned):
        raise TransferError("Signature is valid but its signer fingerprint is not pinned.")


def _trash(path: Path, root: Path) -> Path:
    _within(root, path)
    trash = root / ".ventoy-depot" / "trash"
    trash.mkdir(parents=True, exist_ok=True)
    candidate = trash / path.name
    index = 1
    while candidate.exists():
        candidate = trash / f"{path.stem}.{index}{path.suffix}"
        index += 1
    os.replace(path, candidate)
    return candidate


def _within(root: Path, path: Path) -> None:
    if path.is_symlink():
        raise SecurityError("Symlink destinations are not allowed.")
    try:
        path.resolve().relative_to(root.resolve(strict=True))
    except ValueError as error:
        raise SecurityError("Path escapes the Ventoy mountpoint.") from error


def _device_root(path: Path) -> Path:
    current = path.resolve(strict=True).parent
    while current.parent != current:
        if (current / ".ventoy").exists() or (current / "ventoy").is_dir():
            return current
        current = current.parent
    raise TransferError("Could not locate the Ventoy mountpoint for this ISO.")


def _device_for_path(root: Path) -> Device:
    from .devices import manual_device

    return manual_device(root)


def _fsync_file(path: Path) -> None:
    # Windows requires a writable descriptor for FlushFileBuffers via os.fsync.
    with path.open("r+b") as file:
        os.fsync(file.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
