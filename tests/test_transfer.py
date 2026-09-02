from pathlib import Path

import pytest

from ventoy_iso_updater.catalog import CatalogError
from ventoy_iso_updater.models import Distro, IsoEntry, Release, UpdateAction, UpdatePlan
from ventoy_iso_updater.transfer import download_and_apply


def test_refuses_to_overwrite_existing_iso_with_same_name(tmp_path: Path) -> None:
    existing = tmp_path / "ubuntu-24.04-desktop-amd64.iso"
    existing.write_bytes(b"existing")
    release = Release(
        Distro.UBUNTU,
        "24.04",
        "amd64",
        "https://releases.ubuntu.com/24.04/ubuntu-24.04-desktop-amd64.iso",
        "https://releases.ubuntu.com/24.04/SHA256SUMS",
        existing.name,
    )
    plan = UpdatePlan(
        IsoEntry(existing, Distro.UBUNTU, "24.04", "amd64"),
        release,
        UpdateAction.ADD,
    )

    with pytest.raises(CatalogError, match="refusing to overwrite"):
        download_and_apply(plan)
