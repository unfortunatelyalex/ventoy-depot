from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .catalog import CatalogError
from .models import Release, UpdatePlan


def download_and_apply(
    plan: UpdatePlan, progress: Callable[[int, int], None] | None = None
) -> Path:
    """Stage, checksum-verify, then copy a release before removing an older ISO."""
    destination = plan.existing.path.parent / Path(plan.release.download_url).name
    if destination.exists() and destination != plan.existing.path:
        raise CatalogError(f"Target ISO already exists: {destination.name}.")
    if destination == plan.existing.path:
        raise CatalogError(
            f"The official filename matches the existing ISO ({destination.name}); "
            "refusing to overwrite it."
        )
    with tempfile.TemporaryDirectory(prefix="ventoy-iso-updater-") as temporary:
        staged = Path(temporary) / destination.name
        _download(plan.release.download_url, staged, progress)
        expected = _checksum_for_release(plan.release)
        actual = _digest(staged, plan.release.checksum_algorithm)
        if actual.lower() != expected.lower():
            raise CatalogError("Downloaded ISO checksum does not match the official checksum.")
        shutil.copy2(staged, destination)
        if _digest(destination, plan.release.checksum_algorithm) != actual:
            destination.unlink(missing_ok=True)
            raise CatalogError("Checksum changed while copying the ISO to the Ventoy drive.")
    if plan.action.value == "replace" and destination != plan.existing.path:
        plan.existing.path.unlink()
    return destination


def _download(url: str, target: Path, progress: Callable[[int, int], None] | None) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ventoy-iso-updater/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as output:
        total = int(response.headers.get("Content-Length", 0))
        transferred = 0
        while block := response.read(1024 * 1024):
            output.write(block)
            transferred += len(block)
            if progress:
                progress(transferred, total)


def _checksum_for_release(release: Release) -> str:
    with urllib.request.urlopen(release.checksum_url, timeout=30) as response:
        checksums = response.read().decode("utf-8", errors="strict")
    for line in checksums.splitlines():
        match = re.fullmatch(
            rf"(?i){release.checksum_algorithm}\s+\({re.escape(release.checksum_filename)}\)\s+=\s+([a-f0-9]+)",
            line.strip(),
        )
        if match:
            return match.group(1)
        fields = line.replace("*", " ").split()
        digest_length = hashlib.new(release.checksum_algorithm).digest_size * 2
        if (
            len(fields) >= 2
            and fields[-1] == release.checksum_filename
            and len(fields[0]) == digest_length
        ):
            return fields[0]
    raise CatalogError(f"Official checksum list did not include {release.checksum_filename}.")


def _digest(path: Path, algorithm: str) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError as error:
        raise CatalogError(f"Unsupported checksum algorithm: {algorithm}.") from error
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
