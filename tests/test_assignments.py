from pathlib import Path

import pytest

from ventoy_depot.assignments import AssignmentCatalog, AssignmentError
from ventoy_depot.models import Device, IsoIdentity
from ventoy_depot.planner import build_plan


def test_assignment_is_bound_to_file_hash(tmp_path: Path) -> None:
    iso = tmp_path / "renamed.iso"
    iso.write_bytes(b"first")
    identity = IsoIdentity("arch", "archlinux", None, None, "stable", "x86_64", None, "1", None)
    catalog = AssignmentCatalog(tmp_path)
    catalog.assign(iso, identity)
    assert catalog.lookup(iso) == identity
    iso.write_bytes(b"changed")
    assert catalog.lookup(iso) is None


def test_planner_uses_hash_bound_assignment(monkeypatch, tmp_path: Path) -> None:
    iso = tmp_path / "renamed.iso"
    iso.write_bytes(b"iso")
    identity = IsoIdentity("test", "test-product", None, None, "stable", "x86_64", None, "1", None)
    AssignmentCatalog(tmp_path).assign(iso, identity)
    device = Device("id", "Ventoy", tmp_path, 100, 100, True, True)

    class StubProvider:
        def detect(self, path):
            return None

        def resolve(self, assigned):
            assert assigned == identity
            from ventoy_depot.models import ReleaseArtifact

            return ReleaseArtifact(
                "2",
                None,
                "target.iso",
                "https://example.test/target.iso",
                1,
                "sha256",
                "a" * 64,
                None,
                (),
                frozenset({"example.test"}),
                IsoIdentity(
                    "test",
                    "test-product",
                    None,
                    None,
                    "stable",
                    "x86_64",
                    None,
                    "2",
                    None,
                ),
            )

        def is_newer(self, artifact, installed):
            return True

        def validate_binding(self, current, target):
            assert current.variant_key() == target.variant_key()

    monkeypatch.setattr(
        "ventoy_depot.planner.provider_map", lambda **_kwargs: {"test": StubProvider()}
    )
    plan = build_plan(device)
    assert plan.items[0].local.identity == identity
    assert plan.items[0].local.detection_source == "catalog-sha256"
    assert plan.items[0].writable


def test_assignment_catalog_rejects_non_object_root(tmp_path: Path) -> None:
    directory = tmp_path / ".ventoy-depot"
    directory.mkdir()
    (directory / "catalog.json").write_text("[]", encoding="utf-8")
    with pytest.raises(AssignmentError, match="invalid"):
        AssignmentCatalog(tmp_path).lookup(tmp_path / "missing.iso")


def test_assignment_catalog_rejects_symlinked_metadata_directory(tmp_path: Path) -> None:
    mount = tmp_path / "ventoy"
    outside = tmp_path / "outside"
    mount.mkdir()
    outside.mkdir()
    (mount / ".ventoy-depot").symlink_to(outside, target_is_directory=True)
    iso = mount / "renamed.iso"
    iso.write_bytes(b"iso")
    identity = IsoIdentity("arch", "archlinux", None, None, "stable", "x86_64", None, "1", None)

    with pytest.raises(AssignmentError, match="[Ss]ymlink"):
        AssignmentCatalog(mount).assign(iso, identity)

    assert not (outside / "catalog.json").exists()
