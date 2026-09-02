import asyncio
from importlib.metadata import version
from pathlib import Path

from textual.widgets import Static

from ventoy_depot.app import VentoyDepotApp
from ventoy_depot.models import Device


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
