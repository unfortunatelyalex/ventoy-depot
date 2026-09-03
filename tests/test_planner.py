from dataclasses import replace
from pathlib import Path
from threading import Barrier, current_thread
from types import SimpleNamespace

import pytest

from ventoy_depot.models import DetectedIso, Device, IsoIdentity, ReleaseArtifact, UpdateAction
from ventoy_depot.planner import build_add_plan, build_plan, toggle_replace_action
from ventoy_depot.security import SecurityError


def identity(product: str) -> IsoIdentity:
    return IsoIdentity("test", product, None, None, "stable", "x86_64", None, "1", None)


def artifact(filename: str, size: int) -> ReleaseArtifact:
    return ReleaseArtifact(
        "2",
        None,
        filename,
        f"https://example.test/{filename}",
        size,
        "sha256",
        "a" * 64,
        None,
        (),
        frozenset({"example.test"}),
    )


class StubProvider:
    custom = False

    def __init__(self, targets: dict[str, ReleaseArtifact]) -> None:
        self.targets = targets

    def resolve(self, assigned: IsoIdentity) -> ReleaseArtifact:
        return replace(self.targets[assigned.product_id], identity=replace(assigned, version="2"))

    def is_newer(self, target: ReleaseArtifact, installed: IsoIdentity) -> bool:
        return True

    def validate_binding(self, current: IsoIdentity, target: IsoIdentity) -> None:
        assert current.variant_key() == target.variant_key()


def device(path: Path) -> Device:
    return Device("id", "Ventoy", path, 1_000, 100, True, True)


def test_plan_reserves_space_across_all_selected_updates(monkeypatch, tmp_path: Path) -> None:
    detected = [
        DetectedIso(tmp_path / "old-a.iso", identity("a"), 1.0, "filename"),
        DetectedIso(tmp_path / "old-b.iso", identity("b"), 1.0, "filename"),
    ]
    provider = StubProvider({"a": artifact("new-a.iso", 60), "b": artifact("new-b.iso", 60)})
    monkeypatch.setattr("ventoy_depot.planner.find_isos", lambda path, providers: detected)
    monkeypatch.setattr("ventoy_depot.planner.provider_map", lambda **_kwargs: {"test": provider})
    monkeypatch.setattr(
        "ventoy_depot.planner.shutil.disk_usage", lambda path: SimpleNamespace(free=100)
    )

    plan = build_plan(device(tmp_path))

    assert plan.items[0].writable
    assert not plan.items[1].writable
    assert plan.items[1].blocking_errors == ("Insufficient free space on the Ventoy drive.",)
    assert plan.required_bytes == 60


def test_plan_rejects_duplicate_target_path(monkeypatch, tmp_path: Path) -> None:
    detected = [
        DetectedIso(tmp_path / "old-a.iso", identity("a"), 1.0, "filename"),
        DetectedIso(tmp_path / "old-b.iso", identity("b"), 1.0, "filename"),
    ]
    provider = StubProvider({"a": artifact("same.iso", 1), "b": artifact("same.iso", 1)})
    monkeypatch.setattr("ventoy_depot.planner.find_isos", lambda path, providers: detected)
    monkeypatch.setattr("ventoy_depot.planner.provider_map", lambda **_kwargs: {"test": provider})
    monkeypatch.setattr(
        "ventoy_depot.planner.shutil.disk_usage", lambda path: SimpleNamespace(free=100)
    )

    plan = build_plan(device(tmp_path))

    assert plan.items[0].writable
    assert not plan.items[1].writable
    assert "same target path" in plan.items[1].blocking_errors[0]


def test_metadata_resolution_uses_configured_bounded_parallelism(
    monkeypatch, tmp_path: Path
) -> None:
    detected = [
        DetectedIso(tmp_path / "old-a.iso", identity("a"), 1.0, "filename"),
        DetectedIso(tmp_path / "old-b.iso", identity("b"), 1.0, "filename"),
    ]
    barrier = Barrier(2)
    threads: list[str] = []

    class ConcurrentProvider(StubProvider):
        def resolve(self, assigned: IsoIdentity) -> ReleaseArtifact:
            threads.append(current_thread().name)
            barrier.wait(timeout=1)
            return super().resolve(assigned)

    provider = ConcurrentProvider({"a": artifact("new-a.iso", 1), "b": artifact("new-b.iso", 1)})
    monkeypatch.setattr("ventoy_depot.planner.find_isos", lambda path, providers: detected)
    monkeypatch.setattr("ventoy_depot.planner.provider_map", lambda **_kwargs: {"test": provider})
    monkeypatch.setattr(
        "ventoy_depot.planner.shutil.disk_usage", lambda path: SimpleNamespace(free=100)
    )

    plan = build_plan(device(tmp_path), metadata_parallelism=2)

    assert all(item.writable for item in plan.items)
    assert len(threads) == 2
    assert all(name.startswith("ventoy-metadata") for name in threads)


def test_same_filename_update_requires_explicit_replace(monkeypatch, tmp_path: Path) -> None:
    iso = tmp_path / "constant-name.iso"
    iso.write_bytes(b"old")
    detected = [DetectedIso(iso, identity("a"), 1.0, "filename")]
    provider = StubProvider({"a": artifact(iso.name, 1)})
    monkeypatch.setattr("ventoy_depot.planner.find_isos", lambda path, providers: detected)
    monkeypatch.setattr("ventoy_depot.planner.provider_map", lambda **_kwargs: {"test": provider})
    monkeypatch.setattr(
        "ventoy_depot.planner.shutil.disk_usage", lambda path: SimpleNamespace(free=100)
    )

    plan = build_plan(device(tmp_path))

    assert plan.items[0].action == UpdateAction.SKIP
    assert plan.items[0].replacement_allowed
    assert not plan.items[0].writable

    replacement = toggle_replace_action(plan, iso)
    assert replacement.items[0].action == UpdateAction.REPLACE
    assert replacement.items[0].writable
    assert replacement.plan_id != plan.plan_id

    safe_again = toggle_replace_action(replacement, iso)
    assert safe_again.items[0].action == UpdateAction.SKIP


def test_custom_provider_can_never_replace_existing_iso(monkeypatch, tmp_path: Path) -> None:
    iso = tmp_path / "constant-name.iso"
    iso.write_bytes(b"old")
    detected = [DetectedIso(iso, identity("a"), 1.0, "filename")]
    provider = StubProvider({"a": artifact(iso.name, 1)})
    provider.custom = True
    monkeypatch.setattr("ventoy_depot.planner.find_isos", lambda path, providers: detected)
    monkeypatch.setattr("ventoy_depot.planner.provider_map", lambda **_kwargs: {"test": provider})
    monkeypatch.setattr(
        "ventoy_depot.planner.shutil.disk_usage", lambda path: SimpleNamespace(free=100)
    )

    plan = build_plan(device(tmp_path))

    assert not plan.items[0].replacement_allowed
    with pytest.raises(ValueError, match="cannot be replaced"):
        toggle_replace_action(plan, iso)


def test_explicit_new_iso_request_builds_add_only_plan(monkeypatch, tmp_path: Path) -> None:
    provider = StubProvider({"a": artifact("new-a.iso", 60)})
    monkeypatch.setattr("ventoy_depot.planner.provider_map", lambda **_kwargs: {"test": provider})
    monkeypatch.setattr(
        "ventoy_depot.planner.shutil.disk_usage", lambda path: SimpleNamespace(free=100)
    )

    plan = build_add_plan(device(tmp_path), identity("a"))

    assert plan.items[0].action == UpdateAction.ADD
    assert plan.items[0].local.path == tmp_path / "new-a.iso"
    assert plan.items[0].local.detection_source == "explicit-add-request"
    assert not plan.items[0].replacement_allowed


def test_explicit_new_iso_request_never_overwrites_existing_target(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "new-a.iso").write_bytes(b"existing")
    provider = StubProvider({"a": artifact("new-a.iso", 1)})
    monkeypatch.setattr("ventoy_depot.planner.provider_map", lambda **_kwargs: {"test": provider})
    monkeypatch.setattr(
        "ventoy_depot.planner.shutil.disk_usage", lambda path: SimpleNamespace(free=100)
    )

    plan = build_add_plan(device(tmp_path), identity("a"))

    assert plan.items[0].action == UpdateAction.SKIP
    assert "already exists" in plan.items[0].blocking_errors[0]


def test_explicit_new_iso_request_rejects_provider_path_traversal(
    monkeypatch, tmp_path: Path
) -> None:
    provider = StubProvider({"a": artifact("../outside.iso", 1)})
    monkeypatch.setattr("ventoy_depot.planner.provider_map", lambda **_kwargs: {"test": provider})

    with pytest.raises(SecurityError, match="must not contain a path"):
        build_add_plan(device(tmp_path), identity("a"))

    assert not (tmp_path.parent / "outside.iso").exists()
