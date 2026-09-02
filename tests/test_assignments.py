from pathlib import Path

from ventoy_depot.assignments import AssignmentCatalog
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
            )

        def is_newer(self, artifact, installed):
            return True

    monkeypatch.setattr("ventoy_depot.planner.provider_map", lambda: {"test": StubProvider()})
    plan = build_plan(device)
    assert plan.items[0].local.identity == identity
    assert plan.items[0].local.detection_source == "catalog-sha256"
    assert plan.items[0].writable
