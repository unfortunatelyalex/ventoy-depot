from __future__ import annotations

from urllib.error import URLError

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, ProgressBar, Select, Static

from .catalog import Catalog, CatalogError
from .devices import DeviceError, discover_ventoy_devices
from .iso import find_isos
from .models import Device, Distro, IsoEntry, UpdateAction, UpdatePlan, is_newer_version
from .transfer import download_and_apply


class ConfirmDownloads(ModalScreen[bool]):
    """Explicitly confirm the set of background downloads."""

    CSS = """
    ConfirmDownloads { align: center middle; }
    #dialog { width: 70; height: auto; border: thick $warning; background: $surface; padding: 1 2; }
    #dialog Button { margin-top: 1; margin-right: 1; }
    """

    def __init__(self, count: int) -> None:
        super().__init__()
        self.count = count

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Static(
                f"{self.count} ISO-Update(s) werden nacheinander heruntergeladen, "
                "geprüft und zusätzlich auf den Ventoy-Stick kopiert. "
                "Bestehende ISOs werden nicht gelöscht."
            )
            with Horizontal():
                yield Button("Downloads starten", id="confirm", variant="warning")
                yield Button("Abbrechen", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class VentoyUpdaterApp(App[None]):
    CSS = """
    Screen { align: center top; }
    #content { width: 90%; max-width: 110; }
    #status { margin: 1 0; }
    Select, Button { margin-right: 1; }
    #progress { margin: 1 0; }
    """
    TITLE = "Ventoy ISO Updater"

    def __init__(self) -> None:
        super().__init__()
        self.devices: dict[str, Device] = {}
        self.pending_updates: tuple[str, list[IsoEntry]] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="content"):
            yield Static(
                "Wähle ein erkanntes Ventoy-Laufwerk. Das Tool schreibt nie ohne "
                "weitere Bestätigung.",
                id="status",
            )
            yield Select([], prompt="Ventoy-Laufwerk auswählen", id="device")
            with Horizontal():
                yield Button("Laufwerke suchen", id="refresh", variant="primary")
                yield Button("ISOs prüfen", id="scan", disabled=True)
                yield Button("Aktualisieren", id="update", disabled=True, variant="warning")
            yield ProgressBar(total=100, show_eta=False, id="progress")
            yield Static("", id="results")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_devices()

    def on_select_changed(self, event: Select.Changed) -> None:
        self.query_one("#scan", Button).disabled = event.value is Select.BLANK
        self.query_one("#update", Button).disabled = event.value is Select.BLANK

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh":
            self._refresh_devices()
        elif event.button.id == "scan":
            self._scan_isos()
        elif event.button.id == "update":
            self._update_isos()

    def _refresh_devices(self) -> None:
        status = self.query_one("#status", Static)
        try:
            found = discover_ventoy_devices()
        except DeviceError as error:
            status.update(f"[red]{error}[/red]")
            return
        self.devices = {device.identifier: device for device in found}
        choices = [(device.display_name, device.identifier) for device in found]
        self.query_one("#device", Select).set_options(choices)
        status.update(
            "Wähle ein Ventoy-Laufwerk und prüfe seine ISOs."
            if choices
            else "[yellow]Kein eingehängtes Ventoy-Laufwerk gefunden.[/yellow]"
        )

    def _scan_isos(self) -> None:
        selected = self.query_one("#device", Select).value
        if selected is Select.BLANK:
            return
        device = self.devices[str(selected)]
        entries = find_isos(device.mount_path)
        lines = [
            f"{entry.path.relative_to(device.mount_path)} — {entry.distro.value}"
            + (f" {entry.version}" if entry.version else " (unbekannt)")
            for entry in entries
        ]
        self.query_one("#results", Static).update(
            "\n".join(lines) if lines else "[yellow]Keine ISO-Dateien gefunden.[/yellow]"
        )

    def _update_isos(self) -> None:
        selected = self.query_one("#device", Select).value
        if selected is Select.BLANK:
            return
        device = self.devices[str(selected)]
        supported = {Distro.ARCH, Distro.DEBIAN, Distro.FEDORA, Distro.UBUNTU}
        isos = [iso for iso in find_isos(device.mount_path) if iso.distro in supported]
        if not isos:
            self.query_one("#results", Static).update(
                "[yellow]Keine ISO mit automatischer offizieller Quelle gefunden.[/yellow]"
            )
            return
        self.pending_updates = (device.identifier, isos)
        self.push_screen(ConfirmDownloads(len(isos)), self._confirm_updates)

    def _confirm_updates(self, confirmed: bool) -> None:
        if not confirmed or self.pending_updates is None:
            self.pending_updates = None
            return
        device_id, isos = self.pending_updates
        self.pending_updates = None
        self._perform_updates(device_id, isos)

    @work(thread=True, exclusive=True)
    def _perform_updates(self, device_id: str, isos: list[IsoEntry]) -> None:
        self.call_from_thread(self._set_update_running, True)
        results: list[str] = []
        for index, iso in enumerate(isos, start=1):
            try:
                self.call_from_thread(
                    self._set_current_update,
                    index,
                    len(isos),
                    f"{iso.path.name}: Quelle wird geprüft",
                )
                release = Catalog().resolve(iso.distro, iso.architecture or "amd64")
                if not is_newer_version(release.version, iso.version):
                    results.append(f"[dim]{iso.path.name}: bereits aktuell[/dim]")
                    continue
                destination = download_and_apply(
                    UpdatePlan(iso, release, UpdateAction.ADD),
                    lambda completed, total, current_index=index, current_name=iso.path.name: (
                        self.call_from_thread(
                            self._set_download_progress,
                            current_index,
                            len(isos),
                            current_name,
                            completed,
                            total,
                        )
                    ),
                )
            except (CatalogError, OSError, URLError) as error:
                results.append(f"[red]{iso.path.name}: {error}[/red]")
            else:
                results.append(f"[green]{iso.path.name}: {destination.name} gespeichert[/green]")
        self.call_from_thread(self._finish_updates, results)

    def _set_update_running(self, running: bool) -> None:
        for button_id in ("refresh", "scan", "update"):
            self.query_one(f"#{button_id}", Button).disabled = running
        if running:
            self.query_one("#status", Static).update(
                "[yellow]Updates laufen im Hintergrund. Das Fenster bleibt bedienbar.[/yellow]"
            )

    def _set_current_update(self, index: int, total: int, message: str) -> None:
        self.query_one("#status", Static).update(f"Update {index}/{total}: {message}")
        self.query_one("#progress", ProgressBar).update(progress=(index - 1) * 100 / total)

    def _set_download_progress(
        self, index: int, total: int, name: str, completed: int, size: int
    ) -> None:
        if size:
            fraction = completed / size
            progress = ((index - 1) + fraction) * 100 / total
            detail = f"{completed / 1024 / 1024:.0f} / {size / 1024 / 1024:.0f} MiB"
        else:
            progress = (index - 1) * 100 / total
            detail = f"{completed / 1024 / 1024:.0f} MiB heruntergeladen"
        self.query_one("#progress", ProgressBar).update(progress=progress)
        self.query_one("#status", Static).update(f"Update {index}/{total}: {name} — {detail}")

    def _finish_updates(self, results: list[str]) -> None:
        self._set_update_running(False)
        self.query_one("#progress", ProgressBar).update(progress=100)
        self.query_one("#status", Static).update(
            "[bold green]Update-Lauf abgeschlossen.[/bold green]"
        )
        self.query_one("#results", Static).update("\n".join(results))


def main() -> None:
    VentoyUpdaterApp().run()
