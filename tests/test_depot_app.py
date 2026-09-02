import asyncio
from importlib.metadata import version
from pathlib import Path

from rich.text import Text
from textual.widgets import Button, Static

from ventoy_depot.app import AssignIdentity, VentoyDepotApp
from ventoy_depot.models import (
    DetectedIso,
    Device,
    IsoIdentity,
    PlanItem,
    ReleaseArtifact,
    UpdateAction,
    VerificationLevel,
)


def test_supported_textual_major_is_installed() -> None:
    assert version("textual").split(".", 1)[0] == "8"


def test_tui_mounts_without_stylesheet_errors(monkeypatch) -> None:
    monkeypatch.setattr("ventoy_depot.app.discover_ventoy_devices", lambda: [])

    async def exercise() -> None:
        app = VentoyDepotApp()
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            assert app.is_running
            assert app.query_one("#isos")
            assert app.query_one("#update").disabled

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
    identity = IsoIdentity(
        "arch", "archlinux", None, None, "stable", "x86_64", None, "1", None
    )
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
