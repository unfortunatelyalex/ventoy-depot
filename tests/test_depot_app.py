import asyncio
from importlib.metadata import version
from pathlib import Path

import pytest
from rich.text import Text
from textual.widgets import Button, Static, TextArea

from ventoy_depot.app import (
    _ASSIGNMENT_PROFILES,
    AddIsoDialog,
    AssignIdentity,
    SettingsDialog,
    VentoyDepotApp,
    _write_report,
)
from ventoy_depot.config import Settings
from ventoy_depot.models import (
    DetectedIso,
    Device,
    IsoIdentity,
    PlanItem,
    ReleaseArtifact,
    UpdateAction,
    UpdatePlan,
    VerificationLevel,
)
from ventoy_depot.providers.builtin import BUILTIN_PROVIDERS
from ventoy_depot.report import ItemResult, ResultStatus, RunReport


def test_supported_textual_major_is_installed() -> None:
    assert version("textual").split(".", 1)[0] == "8"


def test_assignment_profiles_use_supported_product_and_architecture_defaults() -> None:
    profiles = {label: values for label, *values in _ASSIGNMENT_PROFILES}
    assert profiles["Debian Live"] == ["debian", "debian", "amd64"]
    assert profiles["Linux Mint"][-1] == "x86_64"
    assert profiles["Zorin OS"][-1] == "x86_64"
    assert profiles["Parrot OS"] == ["parrot-os", "parrot-os", "amd64"]
    assert profiles["Void Linux"] == ["void-linux", "void-linux", "x86_64"]
    assert profiles["Mageia"] == ["mageia", "mageia", "x86_64"]
    assert profiles["CentOS Stream"] == ["centos-stream", "centos-stream", "x86_64"]


def test_tui_mounts_without_stylesheet_errors(monkeypatch) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            assert app.is_running
            assert app.query_one("#isos")
            assert app.query_one("#update").disabled
            assert app.query_one("#cancel-run").disabled
            assert app.query_one("#retry").disabled
            assert app.query_one("#verify").disabled

    asyncio.run(exercise())


def test_refresh_clears_a_selection_that_is_no_longer_available(monkeypatch) -> None:
    device = Device(
        identifier="device-1",
        display_name="Ventoy",
        mount_path=Path("/media/ventoy"),
        size_bytes=1024,
        free_bytes=512,
        is_removable=True,
        is_ventoy=True,
        detection_reason="volume-label",
    )
    responses = iter(([device], []))
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: next(responses))

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#device").value = device.identifier
            await pilot.pause()
            app.action_refresh()
            await pilot.pause()
            assert app.query_one("#scan").disabled
            assert app.query_one("#device-card", Static).content == ""
            assert not app.devices

    asyncio.run(exercise())


def test_selected_row_shows_literal_checked_marker(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])
    iso = tmp_path / "arch.iso"
    identity = IsoIdentity("arch", "archlinux", None, None, "stable", "x86_64", None, "1", None)
    artifact = ReleaseArtifact(
        "2",
        None,
        "arch-2.iso",
        "https://example.test/arch-2.iso",
        1,
        "sha256",
        "a" * 64,
        None,
        (),
        frozenset({"example.test"}),
    )
    item = PlanItem(
        DetectedIso(iso, identity, 1.0, "test"),
        artifact,
        UpdateAction.ADD,
        2,
        1,
        VerificationLevel.CHECKSUM,
    )

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test() as pilot:
            app.row_items = [item]
            app.selected_paths = {iso}
            app._render_plan()
            await pilot.pause()
            marker = app.query_one("#isos").get_row_at(0)[0]
            assert isinstance(marker, Text)
            assert marker.plain == "[x]"

    asyncio.run(exercise())


def test_replace_action_is_explicit_and_selects_the_row(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])
    iso = tmp_path / "constant.iso"
    iso.write_bytes(b"old")
    identity = IsoIdentity("test", "test", None, None, "stable", "x86_64", None, "1", None)
    artifact = ReleaseArtifact(
        "2",
        None,
        iso.name,
        "https://example.test/constant.iso",
        1,
        "sha256",
        "a" * 64,
        None,
        (),
        frozenset({"example.test"}),
        identity,
    )
    item = PlanItem(
        DetectedIso(iso, identity, 1.0, "test"),
        artifact,
        UpdateAction.SKIP,
        2,
        1,
        VerificationLevel.CHECKSUM,
        replacement_allowed=True,
    )
    device = Device("id", "Ventoy", tmp_path, 2, 2, True, True)
    plan = UpdatePlan(device, (item,), "before")

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test() as pilot:
            app.plan = plan
            app.row_items = [item]
            app._render_plan()
            app.action_replace_old()
            await pilot.pause()
            assert app.plan is not None
            assert app.plan.items[0].action == UpdateAction.REPLACE
            assert iso in app.selected_paths
            assert app.query_one("#isos").get_row_at(0)[0].plain == "[x]"

    asyncio.run(exercise())


def test_safe_skip_default_does_not_preselect_updates(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])
    iso = tmp_path / "arch.iso"
    identity = IsoIdentity("arch", "archlinux", None, None, "stable", "x86_64", None, "1", None)
    item = PlanItem(
        DetectedIso(iso, identity, 1.0, "test"),
        ReleaseArtifact(
            "2",
            None,
            "arch-2.iso",
            "https://example.test/arch-2.iso",
            1,
            "sha256",
            "a" * 64,
            None,
            (),
            frozenset({"example.test"}),
            identity,
        ),
        UpdateAction.ADD,
        2,
        1,
        VerificationLevel.CHECKSUM,
    )

    async def exercise() -> None:
        app = VentoyDepotApp(settings=Settings(default_action="skip"))
        async with app.run_test() as pilot:
            app._show_plan(
                UpdatePlan(Device("id", "Ventoy", tmp_path, 2, 2, True, True), (item,), "plan")
            )
            await pilot.pause()
            assert not app.selected_paths
            assert app.query_one("#update", Button).disabled

    asyncio.run(exercise())


def test_assignment_dialog_requires_version(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test() as pilot:
            app.push_screen(AssignIdentity(tmp_path / "renamed.iso", "en"))
            await pilot.pause()
            app.screen.query_one("#assign-save", Button).press()
            await pilot.pause()
            assert "required" in str(app.screen.query_one("#assign-error", Static).content)

    asyncio.run(exercise())


def test_assignment_dialog_uses_volume_id_as_nonbinding_profile_hint(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test() as pilot:
            app.push_screen(
                AssignIdentity(tmp_path / "renamed.iso", "en", "Ubuntu 26.04 LTS amd64")
            )
            await pilot.pause()
            selected = str(app.screen.query_one("#assign-profile").value)
            assert selected.startswith("ubuntu|")
            assert any(
                "Ubuntu 26.04" in str(widget.content) for widget in app.screen.query("Static")
            )

    asyncio.run(exercise())


def test_add_iso_dialog_builds_versionless_explicit_identity(monkeypatch) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])
    arch = next(provider for provider in BUILTIN_PROVIDERS if provider.provider_id == "arch")
    chosen: list[IsoIdentity | None] = []

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test() as pilot:
            app.push_screen(AddIsoDialog((arch,), "en"), chosen.append)
            await pilot.pause()
            app.screen.query_one("#add-save", Button).press()
            await pilot.pause()

    asyncio.run(exercise())
    assert chosen == [
        IsoIdentity(
            "arch",
            "archlinux",
            None,
            None,
            "stable",
            "x86_64",
            None,
            None,
            None,
        )
    ]


def test_keyboard_refresh_is_ignored_while_operation_runs(monkeypatch) -> None:
    calls = 0

    def discover() -> list[Device]:
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", discover)

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert calls == 1
            app._set_running(True, "busy")
            app.action_refresh()
            assert calls == 1

    asyncio.run(exercise())


def test_finished_run_clears_visible_selection_marker(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])
    iso = tmp_path / "arch.iso"
    identity = IsoIdentity("arch", "archlinux", None, None, "stable", "x86_64", None, "1", None)
    artifact = ReleaseArtifact(
        "2",
        None,
        "arch-2.iso",
        "https://example.test/arch-2.iso",
        1,
        "sha256",
        "a" * 64,
        None,
        (),
        frozenset({"example.test"}),
    )
    item = PlanItem(
        DetectedIso(iso, identity, 1.0, "test"),
        artifact,
        UpdateAction.ADD,
        2,
        1,
        VerificationLevel.CHECKSUM,
    )

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test() as pilot:
            app.row_items = [item]
            app.selected_paths = {iso}
            app._render_plan()
            app._finish_updates(
                RunReport("plan", (ItemResult(str(iso), ResultStatus.SUCCESS, "saved"),))
            )
            await pilot.pause()
            marker = app.query_one("#isos").get_row_at(0)[0]
            assert isinstance(marker, Text)
            assert marker.plain == "[ ]"

    asyncio.run(exercise())


def test_failed_run_enables_retry_and_cancel_sets_event(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test() as pilot:
            app._finish_updates(
                RunReport(
                    "plan",
                    (ItemResult(str(tmp_path / "failed.iso"), ResultStatus.FAILED, "error"),),
                )
            )
            assert not app.query_one("#retry", Button).disabled
            app.transfer_running = True
            app._set_running(True, "busy")
            assert not app.query_one("#cancel-run", Button).disabled
            app.action_cancel_run()
            assert app.cancel_event.is_set()
            await pilot.pause()

    asyncio.run(exercise())


def test_settings_dialog_saves_explicit_local_manifest(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])
    saved: list[Settings] = []
    monkeypatch.setattr("ventoy_depot.app.save_settings", saved.append)
    manifest = tmp_path / "provider.json"

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test() as pilot:
            app.push_screen(SettingsDialog(app.settings, "en"), app._settings_chosen)
            await pilot.pause()
            app.screen.query_one("#local-manifests", TextArea).load_text(str(manifest))
            app.screen.query_one("#settings-save", Button).press()
            await pilot.pause()
            assert saved and saved[0].local_manifests == (str(manifest),)
            assert app.settings == saved[0]

    asyncio.run(exercise())


def test_settings_dialog_rejects_relative_manifest_path(monkeypatch) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test() as pilot:
            app.push_screen(SettingsDialog(app.settings, "en"))
            await pilot.pause()
            app.screen.query_one("#local-manifests", TextArea).load_text("provider.json")
            app.screen.query_one("#settings-save", Button).press()
            await pilot.pause()
            assert "absolute" in str(app.screen.query_one("#settings-error", Static).content)

    asyncio.run(exercise())


def test_run_report_revalidates_device_and_rejects_symlinked_directory(
    monkeypatch, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".ventoy-depot").symlink_to(outside, target_is_directory=True)
    device = Device("id", "Ventoy", tmp_path, 100, 100, True, True)
    calls: list[Device] = []
    monkeypatch.setattr(
        "ventoy_depot.app.revalidate_device", lambda current: calls.append(current) or current
    )

    with pytest.raises(Exception, match="[Ss]ymlink"):
        _write_report(device, RunReport("plan", ()))

    assert calls == [device]
    assert not (outside / "reports").exists()


def test_run_report_replaces_destination_symlink_without_following_it(
    monkeypatch, tmp_path: Path
) -> None:
    device = Device("id", "Ventoy", tmp_path, 100, 100, True, True)
    monkeypatch.setattr("ventoy_depot.app.revalidate_device", lambda current: current)
    monkeypatch.setattr(
        "ventoy_depot.app.datetime",
        type(
            "Clock",
            (),
            {
                "now": staticmethod(
                    lambda _zone: type(
                        "Moment", (), {"strftime": lambda self, _format: "20260903T120000Z"}
                    )()
                )
            },
        ),
    )
    report_dir = tmp_path / ".ventoy-depot" / "reports"
    report_dir.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("do not replace", encoding="utf-8")
    destination = report_dir / "20260903T120000Z-plan.json"
    destination.symlink_to(outside)

    written = _write_report(device, RunReport("plan", ()))

    assert written == destination
    assert not destination.is_symlink()
    assert outside.read_text(encoding="utf-8") == "do not replace"
