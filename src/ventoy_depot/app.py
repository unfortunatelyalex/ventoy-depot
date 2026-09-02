from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, DataTable, Footer, Header, Select, Static

from .devices import DeviceError, discover_ventoy_devices
from .i18n import translate
from .iso import find_isos
from .models import Device


class VentoyDepotApp(App[None]):
    CSS = """
    #content { width: 96%; max-width: 140; margin: 1 2; }
    #device-card { margin: 1 0; }
    DataTable { height: 1fr; min-height: 12; }
    """
    TITLE = "Ventoy Depot"
    BINDINGS = [("r", "refresh", "Refresh"), ("s", "scan", "Scan"), ("q", "quit", "Quit")]

    def __init__(self, language: str = "en") -> None:
        super().__init__()
        self.language = language
        self.devices: dict[str, Device] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="content"):
            yield Static(translate("choose_device", self.language), id="status")
            yield Select([], prompt=translate("choose_device", self.language), id="device")
            yield Static("", id="device-card")
            with Horizontal():
                yield Button(translate("refresh", self.language), id="refresh", variant="primary")
                yield Button(translate("scan", self.language), id="scan", disabled=True)
            yield DataTable(id="isos", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#isos", DataTable)
        table.add_columns(
            "Product", "Edition / flavor", "Arch / language", "Installed", "Trust", "Status"
        )
        self.action_refresh()

    def on_select_changed(self, event: Select.Changed) -> None:
        device = self.devices.get(str(event.value))
        self.query_one("#scan", Button).disabled = device is None
        if device is None:
            self.query_one("#device-card", Static).update("")
            return
        free = (
            f"{device.free_bytes / 2**30:.1f} GiB free"
            if device.free_bytes is not None
            else "free space unknown"
        )
        self.query_one("#device-card", Static).update(
            f"{device.display_name}\n{device.mount_path} · {free} · {device.detection_reason}"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh":
            self.action_refresh()
        elif event.button.id == "scan":
            self.action_scan()

    def action_refresh(self) -> None:
        try:
            devices = discover_ventoy_devices()
        except DeviceError as error:
            self.query_one("#status", Static).update(f"[red]{error}[/red]")
            return
        self.devices = {device.identifier: device for device in devices}
        self.query_one("#device", Select).set_options(
            [(item.display_name, item.identifier) for item in devices]
        )
        self.query_one("#status", Static).update(
            translate("choose_device" if devices else "no_devices", self.language)
        )

    def action_scan(self) -> None:
        selected = self.query_one("#device", Select).value
        device = self.devices.get(str(selected))
        if device is None:
            return
        table = self.query_one("#isos", DataTable)
        table.clear()
        for item in find_isos(device.mount_path):
            identity = item.identity
            if identity is None:
                table.add_row("Unknown", "—", "—", "—", "unverified", "Needs assignment")
            else:
                variant = (
                    " / ".join(value for value in (identity.edition, identity.flavor) if value)
                    or "—"
                )
                arch = " / ".join(
                    value for value in (identity.architecture, identity.language) if value
                )
                table.add_row(
                    identity.product_id,
                    variant,
                    arch,
                    identity.version or "—",
                    "local",
                    f"Detected ({item.confidence:.0%})",
                )


def run_tui() -> None:
    VentoyDepotApp().run()
