import asyncio
from pathlib import Path

from ventoy_iso_updater.app import ConfirmDownloads, VentoyUpdaterApp
from ventoy_iso_updater.models import Device


def test_update_opens_an_explicit_confirmation_dialog(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "archlinux-2025.01.01-x86_64.iso").touch()
    device = Device(
        identifier="/dev/sdb1",
        display_name="/dev/sdb1 (Ventoy)",
        mount_path=tmp_path,
        size_bytes=1,
        is_removable=True,
        is_ventoy=True,
    )
    monkeypatch.setattr("ventoy_iso_updater.app.discover_ventoy_devices", lambda: [device])

    async def exercise() -> None:
        app = VentoyUpdaterApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#device").value = device.identifier
            await pilot.pause()
            app._update_isos()
            await pilot.pause()
            assert isinstance(app.screen, ConfirmDownloads)

    asyncio.run(exercise())
