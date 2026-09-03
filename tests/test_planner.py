from dataclasses import replace
from pathlib import Path
from threading import Barrier, current_thread
from types import SimpleNamespace

from ventoy_depot.models import DetectedIso, Device, IsoIdentity, ReleaseArtifact
from ventoy_depot.planner import build_plan


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
