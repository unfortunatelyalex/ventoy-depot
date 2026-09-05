from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from .devices import revalidate_device
from .models import Device, PlanItem, UpdateAction, VerificationLevel
from .network import SafeHttpClient
from .security import (
    SecurityError,
    safe_filename,
    safe_subdirectory,
    validate_signer_fingerprints,
)


class TransferError(RuntimeError):
    pass


class TransferCancelled(TransferError):
    pass


Progress = Callable[[str, int, int], None]
CancelCheck = Callable[[], bool]


def apply_item(
    item: PlanItem,
    progress: Progress | None = None,
    cache_dir: Path | None = None,
    trusted_keyring: Path | None = None,
    device: Device | None = None,
    cancelled: CancelCheck | None = None,
) -> Path:
    artifact = item.target
    if artifact is None or item.local.identity is None:
        raise TransferError("Plan item has no resolved target.")
    if item.action == UpdateAction.SKIP:
        raise TransferError("Skipped plan items cannot be applied.")
    if artifact.verification_level == VerificationLevel.UNVERIFIED:
        raise TransferError("Unverified artifacts cannot be applied automatically.")
    if device is None:
        device_root = _device_root(item.local.path)
        device = _device_for_path(device_root)
    else:
        device_root = device.mount_path.resolve(strict=True)
        _within(device_root, item.local.path)
    destination = item.local.path.parent / safe_filename(artifact.filename)
    _within(device_root, destination)
    same_file_replace = bool(
        item.action == UpdateAction.REPLACE
        and destination.exists()
        and destination.resolve(strict=True) == item.local.path.resolve(strict=True)
    )
    if destination.exists() and not same_file_replace:
        raise TransferError(f"Target ISO already exists: {destination.name}")
    original_signature = (
        _file_signature(item.local.path) if item.action == UpdateAction.REPLACE else None
    )
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
    checked_progress = _checked_progress(progress, cancelled)
    try:
        _raise_if_cancelled(cancelled)
        _download(client, artifact.download_url, downloaded, artifact.size_bytes, checked_progress)
        try:
            _verify(
                downloaded,
                artifact.checksum_algorithm,
                artifact.checksum,
                cancelled=cancelled,
                progress=checked_progress,
                stage="download-verify",
            )
        except TransferError:
            downloaded.unlink(missing_ok=True)
            downloaded.with_suffix(downloaded.suffix + ".json").unlink(missing_ok=True)
            raise
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
        _raise_if_cancelled(cancelled)
        revalidate_device(device)
        if shutil.disk_usage(device_root).free < downloaded.stat().st_size:
            raise TransferError("Insufficient free space on the Ventoy drive before copying.")
        _copy(downloaded, partial, checked_progress)
        _verify(
            partial,
            artifact.checksum_algorithm,
            artifact.checksum,
            cancelled=cancelled,
            progress=checked_progress,
            stage="copy-verify",
        )
        _raise_if_cancelled(cancelled)
        revalidate_device(device)
        if original_signature is not None:
            _require_unchanged(item.local.path, original_signature)
        _fsync_file(partial)
        if same_file_replace:
            assert original_signature is not None
            _require_unchanged(item.local.path, original_signature)
            trashed = _trash(item.local.path, device_root)
            _fsync_directory(trashed.parent)
            _fsync_directory(destination.parent)
            try:
                os.replace(partial, destination)
            except Exception:
                try:
                    if trashed.exists() and not destination.exists():
                        os.replace(trashed, destination)
                        _fsync_directory(destination.parent)
                except Exception as restore_error:
                    raise TransferError(
                        "The new ISO could not be published and the old ISO remains in "
                        f"the Ventoy trash: {trashed}"
                    ) from restore_error
                raise
            _fsync_directory(destination.parent)
        else:
            if destination.exists():
                raise TransferError(f"Target ISO already exists: {destination.name}")
            os.replace(partial, destination)
            _fsync_directory(destination.parent)
            if item.action == UpdateAction.REPLACE:
                assert original_signature is not None
                _require_unchanged(item.local.path, original_signature)
                _trash(item.local.path, device_root)
                _fsync_directory(item.local.path.parent)
        return destination
    except Exception:
        if partial.exists():
            try:
                revalidate_device(device)
            except Exception:
                pass
            else:
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
    available = shutil.disk_usage(target.parent).free
    maximum_size = existing + available
    if expected_size is not None and existing == expected_size:
        if progress:
            progress("download", existing, expected_size)
        return
    if expected_size is not None and existing > expected_size:
        target.unlink(missing_ok=True)
        validator_path.unlink(missing_ok=True)
        existing = 0
        validator = None
    headers: dict[str, str] = {}
    if existing and validator is not None:
        headers["Range"] = f"bytes={existing}-"
        headers["If-Range"] = validator
    response = client.open(url, headers)
    try:
        status = getattr(response, "status", 200)
        mode = "ab" if existing and status == 206 else "wb"
        completed = existing if mode == "ab" else 0
        total = expected_size or completed + int(response.headers.get("Content-Length", 0))
        if total and shutil.disk_usage(target.parent).free < max(total - completed, 0):
            raise TransferError("Insufficient free space in the download staging directory.")
        current_validator = response.headers.get("ETag") or response.headers.get("Last-Modified")
        if mode == "ab" and current_validator and current_validator != validator:
            target.unlink(missing_ok=True)
            validator_path.unlink(missing_ok=True)
            response.close()
            return _download(client, url, target, expected_size, progress)
        if current_validator:
            validator_path.write_text(
                json.dumps({"validator": current_validator}) + "\n", encoding="utf-8"
            )
        else:
            validator_path.unlink(missing_ok=True)
        with target.open(mode) as output:
            while block := response.read(1024 * 1024):
                if completed + len(block) > maximum_size:
                    raise TransferError(
                        "Download exceeds the available space in the staging directory."
                    )
                completed += len(block)
                if expected_size is not None and completed > expected_size:
                    raise TransferError("Download exceeded its advertised size.")
                output.write(block)
                if progress:
                    progress("download", completed, total)
            output.flush()
            os.fsync(output.fileno())
    finally:
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


def _verify(
    path: Path,
    algorithm: str,
    expected: str,
    *,
    cancelled: CancelCheck | None = None,
    progress: Progress | None = None,
    stage: str = "verify",
) -> None:
    if algorithm not in {"sha256", "sha512"}:
        raise TransferError("Only SHA-256 and SHA-512 are accepted.")
    digest = hashlib.new(algorithm)
    total = path.stat().st_size
    completed = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            _raise_if_cancelled(cancelled)
            digest.update(block)
            completed += len(block)
            if progress:
                progress(stage, completed, total)
    if not expected or digest.hexdigest().lower() != expected.lower():
        raise TransferError("Artifact checksum does not match official metadata.")


def _verify_openpgp(
    artifact: Path,
    signature: Path,
    keyring: Path,
    fingerprints: tuple[str, ...],
) -> None:
    try:
        validate_signer_fingerprints(fingerprints)
    except SecurityError as error:
        raise TransferError(str(error)) from error
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
    trash = safe_subdirectory(root, ".ventoy-depot", "trash")
    candidate = trash / path.name
    index = 1
    while candidate.exists():
        candidate = trash / f"{path.stem}.{index}{path.suffix}"
        index += 1
    os.replace(path, candidate)
    return candidate


def trash_entries(root: Path) -> tuple[Path, ...]:
    """Return deletable trash files without creating metadata directories."""
    resolved_root = root.resolve(strict=True)
    metadata = resolved_root / ".ventoy-depot"
    trash = metadata / "trash"
    for directory in (metadata, trash):
        if directory.is_symlink():
            raise SecurityError("Symlinked trash directories are not allowed.")
        if not directory.exists():
            return ()
        if not directory.is_dir():
            raise SecurityError("Ventoy Depot trash path is not a directory.")
        _within(resolved_root, directory)
    entries: list[Path] = []
    for entry in sorted(trash.iterdir(), key=lambda item: item.name.casefold()):
        if entry.is_symlink():
            raise SecurityError("Symlinked trash entries are not allowed.")
        details = entry.stat(follow_symlinks=False)
        if not stat.S_ISREG(details.st_mode):
            raise SecurityError("Ventoy Depot trash contains a non-file entry.")
        _within(resolved_root, entry)
        entries.append(entry)
    return tuple(entries)


def empty_trash(device: Device, expected: tuple[Path, ...] | None = None) -> tuple[Path, ...]:
    """Permanently remove only files already inside this revalidated device's trash."""
    revalidate_device(device)
    current = trash_entries(device.mount_path)
    entries = current if expected is None else expected
    if any(entry not in current for entry in entries):
        raise TransferError("The confirmed trash contents changed before deletion.")
    signatures = {entry: _file_signature(entry) for entry in entries}
    for entry in entries:
        revalidate_device(device)
        _within(device.mount_path, entry)
        _require_unchanged(entry, signatures[entry])
        entry.unlink()
        _fsync_directory(entry.parent)
    return entries


def _file_signature(path: Path) -> tuple[int, int, int, int]:
    details = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(details.st_mode):
        raise TransferError("The ISO selected for replacement is not a regular file.")
    return details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns


def _require_unchanged(path: Path, expected: tuple[int, int, int, int]) -> None:
    try:
        actual = _file_signature(path)
    except FileNotFoundError as error:
        raise TransferError("The ISO selected for replacement disappeared.") from error
    if actual != expected:
        raise TransferError("The ISO selected for replacement changed during the update.")


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


def _checked_progress(progress: Progress | None, cancelled: CancelCheck | None) -> Progress:
    def update(stage: str, completed: int, total: int) -> None:
        _raise_if_cancelled(cancelled)
        if progress:
            progress(stage, completed, total)

    return update


def _raise_if_cancelled(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        raise TransferCancelled("Update cancelled by the user.")
