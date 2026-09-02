import asyncio
from importlib.metadata import version

from ventoy_depot.app import VentoyDepotApp


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
