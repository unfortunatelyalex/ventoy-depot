from pathlib import Path

from ventoy_depot.assignments import AssignmentCatalog
from ventoy_depot.models import IsoIdentity


def test_assignment_is_bound_to_file_hash(tmp_path: Path) -> None:
    iso = tmp_path / "renamed.iso"
    iso.write_bytes(b"first")
    identity = IsoIdentity("arch", "archlinux", None, None, "stable", "x86_64", None, "1", None)
    catalog = AssignmentCatalog(tmp_path)
    catalog.assign(iso, identity)
    assert catalog.lookup(iso) == identity
    iso.write_bytes(b"changed")
    assert catalog.lookup(iso) is None
