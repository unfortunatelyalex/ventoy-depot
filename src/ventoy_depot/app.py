from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from threading import Event

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    ProgressBar,
    Select,
    Static,
    TextArea,
)

from .assignments import AssignmentCatalog
from .config import Settings, cache_path, load_settings, save_settings
from .devices import DeviceError, discover_ventoy_devices, revalidate_device
from .i18n import translate
from .iso import verify_detected_iso
from .models import Device, IsoIdentity, LocalVerification, PlanItem, UpdatePlan
from .network import configure_proxy
from .planner import build_add_plan, build_plan, toggle_replace_action
from .providers import Provider, provider_map
from .report import ItemResult, ResultStatus, RunReport
from .security import safe_subdirectory
from .transfer import TransferCancelled, apply_item


class ConfirmUpdatePlan(ModalScreen[bool]):
    CSS = """
    ConfirmUpdatePlan { align: center middle; }
    #dialog {
        width: 90%; max-width: 100; height: 80%;
        border: thick $warning; background: $surface; padding: 1 2;
    }
    #plan-lines { height: 1fr; margin: 1 0; }
    #dialog Button { margin-right: 1; }
    """

    def __init__(self, plan: UpdatePlan, items: tuple[PlanItem, ...], language: str) -> None:
        super().__init__()
        self.plan = plan
        self.items = items
        self.language = language

    def compose(self) -> ComposeResult:
        known_size = sum(item.required_bytes or 0 for item in self.items)
        unknown = sum(item.required_bytes is None for item in self.items)
        size = f"{known_size / 2**30:.1f} GiB"
        if unknown:
            size += f" + {unknown} unknown size(s)"
        policy = translate(
            "replace_warning"
            if any(item.action.value == "replace" for item in self.items)
            else "keep_old",
            self.language,
        )
        lines = []
        for item in self.items:
            assert item.target is not None
            identity = item.local.identity
            variant = (
                " / ".join(value for value in (identity.edition, identity.flavor) if value)
                if identity
                else ""
            )
            lines.append(
                f"• {item.action.value.upper()}: {item.local.path.name}"
                f"\n  → {item.target.filename}"
                f" ({variant or 'default'}, {item.verification_level.value})"
            )
        with Container(id="dialog"):
            yield Static(
                f"[bold]{translate('confirm_title', self.language)}[/bold]\n"
                f"{len(self.items)} ISO(s), {size}\n"
                f"{policy}"
            )
            with VerticalScroll(id="plan-lines"):
                yield Static("\n".join(lines))
            with Horizontal():
                yield Button(
                    translate("start_updates", self.language), id="confirm", variant="warning"
                )
                yield Button(translate("cancel", self.language), id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


_ASSIGNMENT_PROFILES = (
    ("Alpine Linux", "alpine", "alpine-linux", "x86_64"),
    ("Rocky Linux", "rocky-linux", "rocky-linux", "x86_64"),
    ("AlmaLinux OS", "almalinux", "almalinux", "x86_64"),
    ("Arch Linux", "arch", "archlinux", "x86_64"),
    ("Ubuntu", "ubuntu", "ubuntu", "amd64"),
    ("Debian", "debian", "debian", "amd64"),
    ("Debian Live", "debian", "debian", "amd64"),
    ("Fedora", "fedora", "fedora", "x86_64"),
    ("Linux Mint", "linux-mint", "linux-mint", "x86_64"),
    ("EndeavourOS", "endeavouros", "endeavouros", "x86_64"),
    ("GParted Live", "gparted-live", "gparted-live", "amd64"),
    ("Kali Linux", "kali-linux", "kali-linux", "amd64"),
    ("NixOS", "nixos", "nixos", "x86_64"),
    ("CachyOS", "cachyos", "cachyos", "x86_64"),
    ("Clonezilla Live", "clonezilla", "clonezilla-live", "amd64"),
    ("SystemRescue", "systemrescue", "systemrescue", "amd64"),
    ("openSUSE Tumbleweed", "opensuse-tumbleweed", "opensuse-tumbleweed", "x86_64"),
    ("FreeBSD", "freebsd", "freebsd", "amd64"),
    ("Grml", "grml", "grml", "amd64"),
    ("Qubes OS", "qubes-os", "qubes-os", "x86_64"),
    ("Proxmox VE", "proxmox", "proxmox-ve", "amd64"),
    ("Proxmox Backup Server", "proxmox", "proxmox-backup-server", "amd64"),
    ("Proxmox Mail Gateway", "proxmox", "proxmox-mail-gateway", "amd64"),
    ("Proxmox Datacenter Manager", "proxmox", "proxmox-datacenter-manager", "amd64"),
    ("Rescuezilla", "rescuezilla", "rescuezilla", "amd64"),
    ("Tails", "tails", "tails", "amd64"),
    ("Memtest86+", "memtest86-plus", "memtest86-plus", "x86_64"),
    ("Omarchy", "omarchy", "omarchy", "x86_64"),
    ("Manjaro", "manjaro", "manjaro", "x86_64"),
    ("Pop!_OS", "pop-os", "pop-os", "amd64"),
    ("Nobara", "nobara", "nobara", "x86_64"),
    ("Vanilla OS", "vanilla-os", "vanilla-os", "amd64"),
    ("Windows 11", "windows-11", "windows-11", "x86_64"),
    ("Zorin OS", "zorin-os", "zorin-os", "x86_64"),
    ("netboot.xyz", "netboot-xyz", "netboot-xyz", "x86_64"),
    ("Gentoo Linux", "gentoo", "gentoo", "amd64"),
    ("Hiren's BootCD PE", "hirens-bootcd-pe", "hirens-bootcd-pe", "x86_64"),
    ("ShredOS", "shredos", "shredos", "x86_64"),
    ("NetBSD", "netbsd", "netbsd", "amd64"),
)

_VOLUME_PROFILE_HINTS = (
    ("ENDEAVOUR", "endeavouros"),
    ("SYSTEMRESCUE", "systemrescue"),
    ("RESCUEZILLA", "rescuezilla"),
    ("CLONEZILLA", "clonezilla"),
    ("LINUX MINT", "linux-mint"),
    ("GPARTED", "gparted-live"),
    ("OPENSUSE", "opensuse-tumbleweed"),
    ("NETBOOT.XYZ", "netboot-xyz"),
    ("HIREN", "hirens-bootcd-pe"),
    ("SHREDOS", "shredos"),
    ("GENTOO", "gentoo"),
    ("NETBSD", "netbsd"),
    ("FREEBSD", "freebsd"),
    ("PROXMOX", "proxmox"),
    ("CACHYOS", "cachyos"),
    ("MANJARO", "manjaro"),
    ("NOBARA", "nobara"),
    ("VANILLA", "vanilla-os"),
    ("ZORIN", "zorin-os"),
    ("KALI", "kali-linux"),
    ("NIXOS", "nixos"),
    ("FEDORA", "fedora"),
    ("DEBIAN", "debian"),
    ("UBUNTU", "ubuntu"),
    ("ARCH", "arch"),
)


def _suggested_profile(volume_id: str | None) -> str | None:
    if not volume_id:
        return None
    normalized = volume_id.upper()
    return next(
        (provider_id for marker, provider_id in _VOLUME_PROFILE_HINTS if marker in normalized),
        None,
    )


class SettingsDialog(ModalScreen[Settings | None]):
    CSS = """
    SettingsDialog { align: center middle; }
    #settings-dialog {
        width: 80; max-width: 95%; height: auto; max-height: 95%;
        border: thick $accent; background: $surface; padding: 1 2;
    }
    #settings-dialog Input, #settings-dialog Select { margin-bottom: 1; }
    #local-manifests { height: 6; margin-bottom: 1; }
    #settings-error { color: $error; height: auto; }
    #settings-dialog Button { margin-right: 1; }
    """

    def __init__(self, settings: Settings, language: str) -> None:
        super().__init__()
        self.settings = settings
        self.language = language

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="settings-dialog"):
            yield Static(f"[bold]{translate('settings_title', self.language)}[/bold]")
            yield Static(translate("language_setting", self.language))
            yield Select(
                [("English", "en"), ("Deutsch", "de")],
                allow_blank=False,
                value=self.settings.language,
                id="settings-language",
            )
            yield Checkbox(
                translate("registry_updates", self.language),
                value=self.settings.registry_updates,
                id="settings-registry",
            )
            yield Checkbox(
                translate("download_cache", self.language),
                value=self.settings.download_cache,
                id="settings-cache",
            )
            yield Static(translate("proxy_setting", self.language))
            yield Input(
                self.settings.proxy or "",
                placeholder="http://proxy.example:8080",
                id="settings-proxy",
            )
            yield Static(translate("parallelism_setting", self.language))
            yield Input(
                str(self.settings.metadata_parallelism), type="integer", id="settings-parallelism"
            )
            yield Static(translate("default_action_setting", self.language))
            yield Select(
                [
                    (translate("default_add", self.language), "add"),
                    (translate("default_skip", self.language), "skip"),
                ],
                allow_blank=False,
                value=self.settings.default_action,
                id="settings-default-action",
            )
            yield Static(translate("local_manifests_setting", self.language))
            yield TextArea("\n".join(self.settings.local_manifests), id="local-manifests")
            yield Static("", id="settings-error")
            with Horizontal():
                yield Button(translate("save_settings", self.language), id="settings-save")
                yield Button(translate("cancel", self.language), id="settings-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-cancel":
            self.dismiss(None)
            return
        if event.button.id != "settings-save":
            return
        try:
            language = self.query_one("#settings-language", Select).value
            default_action = self.query_one("#settings-default-action", Select).value
            if language is Select.NULL or default_action is Select.NULL:
                raise ValueError("Language and default action are required.")
            parallelism = int(self.query_one("#settings-parallelism", Input).value)
            proxy = self.query_one("#settings-proxy", Input).value.strip() or None
            manifests = tuple(
                line.strip()
                for line in self.query_one("#local-manifests", TextArea).text.splitlines()
                if line.strip()
            )
            settings = Settings(
                language=str(language),
                registry_updates=self.query_one("#settings-registry", Checkbox).value,
                download_cache=self.query_one("#settings-cache", Checkbox).value,
                proxy=proxy,
                metadata_parallelism=parallelism,
                default_action=str(default_action),
                local_manifests=manifests,
            )
        except (TypeError, ValueError) as error:
            self.query_one("#settings-error", Static).update(str(error))
            return
        self.dismiss(settings)


class AssignIdentity(ModalScreen[IsoIdentity | None]):
    CSS = """
    AssignIdentity { align: center middle; }
    #assign-dialog {
        width: 80; max-width: 95%; height: auto; max-height: 95%;
        border: thick $accent; background: $surface; padding: 1 2;
    }
    #assign-dialog Input, #assign-dialog Select { margin-bottom: 1; }
    #assign-error { color: $error; height: auto; }
    #assign-dialog Button { margin-right: 1; }
    """

    def __init__(self, path: Path, language: str, volume_id: str | None = None) -> None:
        super().__init__()
        self.path = path
        self.language = language
        self.volume_id = volume_id

    def compose(self) -> ComposeResult:
        options = [
            (label, f"{provider_id}|{product_id}|{architecture}")
            for label, provider_id, product_id, architecture in _ASSIGNMENT_PROFILES
        ]
        suggested = _suggested_profile(self.volume_id)
        initial = next(
            (value for _label, value in options if value.split("|", 1)[0] == suggested),
            options[0][1],
        )
        with VerticalScroll(id="assign-dialog"):
            yield Static(f"[bold]{translate('assign_title', self.language)}[/bold]")
            yield Static(self.path.name)
            if self.volume_id:
                yield Static(
                    translate("volume_id_hint", self.language).format(volume_id=self.volume_id)
                )
            yield Static(translate("assign_help", self.language))
            yield Static(translate("provider_product", self.language))
            yield Select(options, allow_blank=False, value=initial, id="assign-profile")
            yield Static(translate("edition", self.language))
            yield Input(placeholder="desktop, server, core, kde …", id="assign-edition")
            yield Static(translate("flavor", self.language))
            yield Input(placeholder="minimal, nvidia, edge …", id="assign-flavor")
            yield Static(translate("channel", self.language))
            yield Input("stable", id="assign-channel")
            yield Static(translate("architecture", self.language))
            yield Input("x86_64", id="assign-architecture")
            yield Static(translate("language", self.language))
            yield Input(placeholder="en-us, de-de …", id="assign-language")
            yield Static(translate("installed_version", self.language))
            yield Input(placeholder="24.04, 40, 2026.08.15 …", id="assign-version")
            yield Static(translate("build_optional", self.language))
            yield Input(id="assign-build")
            yield Static("", id="assign-error")
            with Horizontal():
                yield Button(translate("save_assignment", self.language), id="assign-save")
                yield Button(translate("cancel", self.language), id="assign-cancel")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "assign-profile" or event.value is Select.NULL:
            return
        architecture = str(event.value).rsplit("|", 1)[-1]
        self.query_one("#assign-architecture", Input).value = architecture

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "assign-cancel":
            self.dismiss(None)
            return
        if event.button.id != "assign-save":
            return
        profile = self.query_one("#assign-profile", Select).value
        version = self.query_one("#assign-version", Input).value.strip()
        architecture = self.query_one("#assign-architecture", Input).value.strip().lower()
        channel = self.query_one("#assign-channel", Input).value.strip().lower()
        if profile is Select.NULL or not version or not architecture or not channel:
            self.query_one("#assign-error", Static).update(
                translate("assignment_required", self.language)
            )
            return
        provider_id, product_id, _default_architecture = str(profile).split("|", 2)

        def optional(input_id: str) -> str | None:
            value = self.query_one(input_id, Input).value.strip().lower()
            return value or None

        self.dismiss(
            IsoIdentity(
                provider_id=provider_id,
                product_id=product_id,
                edition=optional("#assign-edition"),
                flavor=optional("#assign-flavor"),
                channel=channel,
                architecture=architecture,
                language=optional("#assign-language"),
                version=version,
                build=optional("#assign-build"),
            )
        )


@dataclass(frozen=True)
class _AddProfile:
    label: str
    provider_id: str
    product_id: str
    edition: str | None
    channel: str
    architecture: str


class AddIsoDialog(ModalScreen[IsoIdentity | None]):
    CSS = """
    AddIsoDialog { align: center middle; }
    #add-dialog {
        width: 80; max-width: 95%; height: auto; max-height: 95%;
        border: thick $accent; background: $surface; padding: 1 2;
    }
    #add-dialog Input, #add-dialog Select { margin-bottom: 1; }
    #add-error { color: $error; height: auto; }
    #add-dialog Button { margin-right: 1; }
    """

    def __init__(self, providers: tuple[Provider, ...], language: str) -> None:
        super().__init__()
        self.language = language
        self.profiles = tuple(
            _AddProfile(
                (
                    provider.display_name
                    if len(provider.products) == 1
                    else f"{provider.display_name} — {product}"
                ),
                provider.provider_id,
                product,
                provider.capabilities.editions[0] if provider.capabilities.editions else None,
                provider.capabilities.channels[0],
                provider.capabilities.architectures[0],
            )
            for provider in sorted(providers, key=lambda item: item.display_name.lower())
            for product in provider.products
            if provider.capabilities.channels and provider.capabilities.architectures
        )

    def compose(self) -> ComposeResult:
        if not self.profiles:
            with VerticalScroll(id="add-dialog"):
                yield Static(translate("no_add_providers", self.language), id="add-error")
                yield Button(translate("cancel", self.language), id="add-cancel")
            return
        profile = self.profiles[0]
        options = [(item.label, str(index)) for index, item in enumerate(self.profiles)]
        with VerticalScroll(id="add-dialog"):
            yield Static(f"[bold]{translate('add_title', self.language)}[/bold]")
            yield Static(translate("add_help", self.language))
            yield Select(options, allow_blank=False, value="0", id="add-profile")
            yield Static(translate("edition", self.language))
            yield Input(profile.edition or "", id="add-edition")
            yield Static(translate("flavor", self.language))
            yield Input(id="add-flavor")
            yield Static(translate("channel", self.language))
            yield Input(profile.channel, id="add-channel")
            yield Static(translate("architecture", self.language))
            yield Input(profile.architecture, id="add-architecture")
            yield Static(translate("language", self.language))
            yield Input(id="add-language")
            yield Static("", id="add-error")
            with Horizontal():
                yield Button(translate("prepare_add", self.language), id="add-save")
                yield Button(translate("cancel", self.language), id="add-cancel")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "add-profile" or event.value is Select.NULL:
            return
        profile = self.profiles[int(str(event.value))]
        self.query_one("#add-edition", Input).value = profile.edition or ""
        self.query_one("#add-flavor", Input).value = ""
        self.query_one("#add-channel", Input).value = profile.channel
        self.query_one("#add-architecture", Input).value = profile.architecture
        self.query_one("#add-language", Input).value = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-cancel":
            self.dismiss(None)
            return
        if event.button.id != "add-save" or not self.profiles:
            return
        selected = self.query_one("#add-profile", Select).value
        channel = self.query_one("#add-channel", Input).value.strip().lower()
        architecture = self.query_one("#add-architecture", Input).value.strip().lower()
        if selected is Select.NULL or not channel or not architecture:
            self.query_one("#add-error", Static).update(translate("add_required", self.language))
            return
        profile = self.profiles[int(str(selected))]

        def optional(input_id: str) -> str | None:
            value = self.query_one(input_id, Input).value.strip().lower()
            return value or None

        self.dismiss(
            IsoIdentity(
                profile.provider_id,
                profile.product_id,
                optional("#add-edition"),
                optional("#add-flavor"),
                channel,
                architecture,
                optional("#add-language"),
                None,
                None,
            )
        )


class VentoyDepotApp(App[None]):
    CSS = """
    #content { width: 96%; max-width: 150; margin: 1 2; }
    #device-card { margin: 1 0; }
    #progress { margin: 1 0; }
    #actions { height: auto; overflow-x: auto; }
    DataTable { height: 1fr; min-height: 12; }
    Button { margin-right: 1; }
    """
    TITLE = "Ventoy Depot"
    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("s", "scan", "Check updates"),
        ("space", "toggle_selection", "Select ISO"),
        ("x", "replace_old", "Replace old ISO"),
        ("a", "assign_identity", "Assign ISO"),
        ("n", "add_iso", "Add new ISO"),
        ("v", "verify_iso", "Verify ISO"),
        ("ctrl+s", "settings", "Settings"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, language: str = "en", settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or Settings(language=language)
        self.language = self.settings.language
        self.devices: dict[str, Device] = {}
        self.plan: UpdatePlan | None = None
        self.row_items: list[PlanItem] = []
        self.selected_paths: set[Path] = set()
        self.pending_items: tuple[PlanItem, ...] = ()
        self.operation_running = False
        self.transfer_running = False
        self.cancel_event = Event()
        self.failed_paths: set[Path] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="content"):
            yield Static(translate("choose_device", self.language), id="status")
            yield Select([], prompt=translate("choose_device", self.language), id="device")
            yield Static("", id="device-card")
            with Horizontal(id="actions"):
                yield Button(translate("refresh", self.language), id="refresh", variant="primary")
                yield Button(translate("check_updates", self.language), id="scan", disabled=True)
                yield Button(translate("assign_iso", self.language), id="assign", disabled=True)
                yield Button(translate("add_iso", self.language), id="add", disabled=True)
                yield Button(translate("verify_iso", self.language), id="verify", disabled=True)
                yield Button(
                    translate("update_selected", self.language),
                    id="update",
                    disabled=True,
                    variant="warning",
                )
                yield Button(translate("replace_old", self.language), id="replace", disabled=True)
                yield Button(translate("cancel_run", self.language), id="cancel-run", disabled=True)
                yield Button(translate("retry_failed", self.language), id="retry", disabled=True)
                yield Button(translate("settings", self.language), id="settings")
            yield ProgressBar(total=100, show_eta=True, id="progress")
            yield DataTable(id="isos", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#isos", DataTable)
        table.add_columns(
            "✓",
            "Product",
            "Edition / flavor",
            "Arch / language",
            "Installed",
            "Available",
            "Trust",
            "Action / status",
        )
        self.action_refresh()

    def on_select_changed(self, event: Select.Changed) -> None:
        device = self.devices.get(str(event.value))
        self.query_one("#scan", Button).disabled = device is None
        self.query_one("#update", Button).disabled = True
        self.query_one("#assign", Button).disabled = device is None
        self.query_one("#add", Button).disabled = device is None
        self.query_one("#replace", Button).disabled = True
        self.query_one("#verify", Button).disabled = True
        self.plan = None
        self.row_items.clear()
        self.selected_paths.clear()
        self.failed_paths.clear()
        self.query_one("#isos", DataTable).clear()
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
        elif event.button.id == "assign":
            self.action_assign_identity()
        elif event.button.id == "add":
            self.action_add_iso()
        elif event.button.id == "verify":
            self.action_verify_iso()
        elif event.button.id == "update":
            self.action_update()
        elif event.button.id == "replace":
            self.action_replace_old()
        elif event.button.id == "cancel-run":
            self.action_cancel_run()
        elif event.button.id == "retry":
            self.action_retry_failed()
        elif event.button.id == "settings":
            self.action_settings()

    def on_data_table_row_selected(self, _event: DataTable.RowSelected) -> None:
        self.action_toggle_selection()

    def action_refresh(self) -> None:
        if self.operation_running:
            return
        try:
            devices = discover_ventoy_devices()
        except DeviceError as error:
            self.query_one("#status", Static).update(f"[red]{error}[/red]")
            return
        self.devices = {device.identifier: device for device in devices}
        self.plan = None
        self.row_items.clear()
        self.selected_paths.clear()
        self.failed_paths.clear()
        self.query_one("#scan", Button).disabled = True
        self.query_one("#update", Button).disabled = True
        self.query_one("#replace", Button).disabled = True
        self.query_one("#assign", Button).disabled = True
        self.query_one("#add", Button).disabled = True
        self.query_one("#verify", Button).disabled = True
        self.query_one("#device-card", Static).update("")
        self.query_one("#isos", DataTable).clear()
        self.query_one("#device", Select).set_options(
            [(item.display_name, item.identifier) for item in devices]
        )
        self.query_one("#status", Static).update(
            translate("choose_device" if devices else "no_devices", self.language)
        )

    def action_settings(self) -> None:
        if self.operation_running:
            return
        self.push_screen(
            SettingsDialog(self.settings, self.language),
            self._settings_chosen,
        )

    def _settings_chosen(self, settings: Settings | None) -> None:
        if settings is None:
            return
        try:
            save_settings(settings)
        except OSError as error:
            self._show_error(str(error))
            return
        self.settings = settings
        self.language = settings.language
        configure_proxy(settings.proxy)
        self.query_one("#status", Static).update(translate("settings_saved", self.language))

    def action_scan(self) -> None:
        if self.operation_running:
            return
        selected = self.query_one("#device", Select).value
        device = self.devices.get(str(selected))
        if device is not None:
            self._set_running(True, translate("checking_metadata", self.language))
            self._build_plan(device)

    def action_add_iso(self) -> None:
        if self.operation_running:
            return
        selected = self.query_one("#device", Select).value
        device = self.devices.get(str(selected))
        if device is None:
            return
        try:
            providers = tuple(provider_map().values())
        except Exception as error:
            self._show_error(str(error))
            return
        self.push_screen(
            AddIsoDialog(providers, self.language),
            partial(self._new_iso_chosen, device),
        )

    def action_verify_iso(self) -> None:
        if self.operation_running:
            return
        table = self.query_one("#isos", DataTable)
        if not self.row_items or table.cursor_row >= len(self.row_items):
            return
        item = self.row_items[table.cursor_row]
        if not item.local.path.is_file():
            self.query_one("#status", Static).update(translate("verify_missing", self.language))
            return
        self._set_running(True, translate("verifying_iso", self.language))
        self._verify_iso(item)

    @work(thread=True, exclusive=True, group="metadata")
    def _verify_iso(self, item: PlanItem) -> None:
        try:
            result = verify_detected_iso(item.local, item.target)
        except Exception as error:
            self.call_from_thread(self._show_error, str(error))
        else:
            self.call_from_thread(self._show_verification, result)

    def _show_verification(self, result: LocalVerification) -> None:
        self._set_running(False, "")
        if result.verified is True:
            message = translate("verify_match", self.language)
            color = "green"
        elif result.verified is False:
            message = translate("verify_mismatch", self.language)
            color = "red"
        else:
            message = translate("verify_hash_only", self.language)
            color = "yellow"
        self.query_one("#status", Static).update(
            f"[{color}]{message}[/{color}]\n{result.algorithm.upper()}: {result.checksum}"
        )

    def _new_iso_chosen(self, device: Device, identity: IsoIdentity | None) -> None:
        if identity is not None:
            self._build_add_plan(device, identity)

    @work(thread=True, exclusive=True, group="metadata")
    def _build_add_plan(self, device: Device, identity: IsoIdentity) -> None:
        self.call_from_thread(
            self._set_running, True, translate("resolving_new_iso", self.language)
        )
        try:
            plan = build_add_plan(device, identity, refresh=True)
        except Exception as error:
            self.call_from_thread(self._show_error, str(error))
        else:
            self.call_from_thread(self._show_plan, plan)

    @work(thread=True, exclusive=True, group="metadata")
    def _build_plan(self, device: Device) -> None:
        self.call_from_thread(
            self._set_running, True, translate("checking_metadata", self.language)
        )
        try:
            plan = build_plan(
                device,
                refresh=True,
                metadata_parallelism=self.settings.metadata_parallelism,
            )
        except Exception as error:
            self.call_from_thread(self._show_error, str(error))
        else:
            self.call_from_thread(self._show_plan, plan)

    def _show_plan(self, plan: UpdatePlan) -> None:
        self.plan = plan
        self.row_items = list(plan.items)
        self.selected_paths = (
            {item.local.path for item in plan.items if item.writable}
            if self.settings.default_action == "add"
            else set()
        )
        self._render_plan()
        available = len(self.selected_paths)
        self.query_one("#status", Static).update(
            translate("updates_found", self.language).format(count=available)
        )
        self._set_running(False, "")

    def _render_plan(self) -> None:
        table = self.query_one("#isos", DataTable)
        cursor_row = table.cursor_row
        table.clear()
        for item in self.row_items:
            identity = item.local.identity
            if identity is None:
                product, variant, arch, installed = "Unknown", "—", "—", "—"
            else:
                product = identity.product_id
                variant = (
                    " / ".join(value for value in (identity.edition, identity.flavor) if value)
                    or "—"
                )
                arch = " / ".join(
                    value for value in (identity.architecture, identity.language) if value
                )
                installed = identity.version or "—"
            target = item.target
            selected = item.local.path in self.selected_paths
            messages = (*item.blocking_errors, *item.warnings)
            status = item.action.value.upper()
            if messages:
                status += ": " + "; ".join(messages)
            table.add_row(
                Text("[x]" if selected else "[ ]"),
                product,
                variant,
                arch,
                installed,
                target.version if target else "—",
                item.verification_level.value,
                status,
                key=str(item.local.path),
            )
        if self.row_items:
            table.move_cursor(row=min(cursor_row, len(self.row_items) - 1), scroll=False)
        self.query_one("#update", Button).disabled = not self.selected_paths
        self.query_one("#replace", Button).disabled = not any(
            item.replacement_allowed for item in self.row_items
        )
        self.query_one("#verify", Button).disabled = not any(
            item.local.path.is_file() for item in self.row_items
        )

    def action_toggle_selection(self) -> None:
        if self.operation_running:
            return
        table = self.query_one("#isos", DataTable)
        if not self.row_items or table.cursor_row >= len(self.row_items):
            return
        item = self.row_items[table.cursor_row]
        if not item.writable:
            return
        if item.local.path in self.selected_paths:
            self.selected_paths.remove(item.local.path)
        else:
            self.selected_paths.add(item.local.path)
        self._render_plan()

    def action_assign_identity(self) -> None:
        if self.operation_running:
            return
        table = self.query_one("#isos", DataTable)
        if not self.row_items or table.cursor_row >= len(self.row_items):
            self.query_one("#status", Static).update(translate("scan_before_assign", self.language))
            return
        item = self.row_items[table.cursor_row]
        if item.local.identity is not None:
            self.query_one("#status", Static).update(
                translate("already_identified", self.language).format(name=item.local.path.name)
            )
            return
        self.push_screen(
            AssignIdentity(item.local.path, self.language, item.local.volume_id),
            partial(self._assignment_chosen, item.local.path),
        )

    def action_replace_old(self) -> None:
        if self.operation_running or self.plan is None:
            return
        table = self.query_one("#isos", DataTable)
        if not self.row_items or table.cursor_row >= len(self.row_items):
            return
        item = self.row_items[table.cursor_row]
        try:
            self.plan = toggle_replace_action(self.plan, item.local.path)
        except ValueError:
            self.query_one("#status", Static).update(
                translate("replace_unavailable", self.language)
            )
            return
        self.row_items = list(self.plan.items)
        changed = self.row_items[table.cursor_row]
        if changed.writable:
            self.selected_paths.add(changed.local.path)
        else:
            self.selected_paths.discard(changed.local.path)
        self._render_plan()

    def _assignment_chosen(self, path: Path, identity: IsoIdentity | None) -> None:
        selected = self.query_one("#device", Select).value
        device = self.devices.get(str(selected))
        if identity is not None and device is not None:
            self._save_assignment(device, path, identity)

    @work(thread=True, exclusive=True, group="metadata")
    def _save_assignment(self, device: Device, path: Path, identity: IsoIdentity) -> None:
        self.call_from_thread(
            self._set_running, True, translate("saving_assignment", self.language)
        )
        try:
            revalidate_device(device)
            AssignmentCatalog(device.mount_path).assign(path, identity)
        except Exception as error:
            self.call_from_thread(self._show_error, str(error))
        else:
            self.call_from_thread(self._assignment_saved, device)

    def _assignment_saved(self, device: Device) -> None:
        self.query_one("#status", Static).update(translate("assignment_saved", self.language))
        self._build_plan(device)

    def action_update(self) -> None:
        if self.operation_running or self.plan is None:
            return
        items = tuple(
            item
            for item in self.plan.items
            if item.local.path in self.selected_paths and item.writable
        )
        if not items:
            return
        self.pending_items = items
        self.push_screen(ConfirmUpdatePlan(self.plan, items, self.language), self._confirm_updates)

    def _confirm_updates(self, confirmed: bool | None) -> None:
        items = self.pending_items
        self.pending_items = ()
        if confirmed and self.plan is not None and items:
            self.cancel_event.clear()
            self.transfer_running = True
            self._set_running(True, translate("updating", self.language))
            self._perform_updates(self.plan, items)

    def action_cancel_run(self) -> None:
        if self.transfer_running:
            self.cancel_event.set()
            self.query_one("#status", Static).update(translate("cancelling", self.language))

    def action_retry_failed(self) -> None:
        if self.operation_running or self.plan is None or not self.failed_paths:
            return
        items = tuple(
            item
            for item in self.plan.items
            if item.local.path in self.failed_paths and item.writable
        )
        if items:
            self.pending_items = items
            self.push_screen(
                ConfirmUpdatePlan(self.plan, items, self.language), self._confirm_updates
            )

    @work(thread=True, exclusive=True, group="transfer")
    def _perform_updates(self, plan: UpdatePlan, items: tuple[PlanItem, ...]) -> None:
        self.call_from_thread(self._set_running, True, translate("updating", self.language))
        results: list[ItemResult] = []
        for index, item in enumerate(items, start=1):
            if self.cancel_event.is_set():
                results.extend(
                    ItemResult(
                        str(remaining.local.path),
                        ResultStatus.CANCELLED,
                        translate("cancelled", self.language),
                    )
                    for remaining in items[index - 1 :]
                )
                break
            try:
                destination = apply_item(
                    item,
                    progress=partial(
                        self._thread_progress,
                        index,
                        len(items),
                        item.local.path.name,
                    ),
                    cache_dir=(
                        cache_path() / "downloads" if self.settings.download_cache else None
                    ),
                    device=plan.device,
                    cancelled=self.cancel_event.is_set,
                )
            except TransferCancelled as error:
                results.append(ItemResult(str(item.local.path), ResultStatus.CANCELLED, str(error)))
                results.extend(
                    ItemResult(
                        str(remaining.local.path),
                        ResultStatus.CANCELLED,
                        translate("cancelled", self.language),
                    )
                    for remaining in items[index:]
                )
                break
            except Exception as error:
                results.append(ItemResult(str(item.local.path), ResultStatus.FAILED, str(error)))
            else:
                results.append(
                    ItemResult(str(destination), ResultStatus.SUCCESS, f"Saved {destination.name}")
                )
        report = RunReport(plan.plan_id, tuple(results))
        try:
            _write_report(plan.device, report)
        except Exception:
            pass
        self.call_from_thread(self._finish_updates, report)

    def _thread_progress(
        self,
        index: int,
        count: int,
        name: str,
        stage: str,
        completed: int,
        total: int,
    ) -> None:
        self.call_from_thread(self._show_progress, index, count, name, stage, completed, total)

    def _show_progress(
        self, index: int, count: int, name: str, stage: str, completed: int, total: int
    ) -> None:
        fraction = completed / total if total else 0.0
        progress = ((index - 1) + fraction) * 100 / count
        self.query_one("#progress", ProgressBar).update(progress=progress)
        detail = (
            f"{completed / 2**20:.0f}/{total / 2**20:.0f} MiB"
            if total
            else f"{completed / 2**20:.0f} MiB"
        )
        self.query_one("#status", Static).update(f"{index}/{count}: {name} · {stage} · {detail}")

    def _finish_updates(self, report: RunReport) -> None:
        self.transfer_running = False
        self.cancel_event.clear()
        self.failed_paths = {
            Path(result.path) for result in report.results if result.status == ResultStatus.FAILED
        }
        self.selected_paths.clear()
        self._set_running(False, "")
        self._render_plan()
        self.query_one("#progress", ProgressBar).update(progress=100)
        lines = [
            f"{result.status.value.upper()}: {Path(result.path).name} — {result.message}"
            for result in report.results
        ]
        color = "green" if report.successful else "red"
        self.query_one("#status", Static).update(
            f"[{color}]{translate('run_finished', self.language)}[/{color}]\n" + "\n".join(lines)
        )
        self.query_one("#retry", Button).disabled = not self.failed_paths

    def _set_running(self, running: bool, message: str) -> None:
        self.operation_running = running
        for button_id in (
            "refresh",
            "scan",
            "assign",
            "add",
            "verify",
            "replace",
            "update",
            "retry",
            "settings",
        ):
            self.query_one(f"#{button_id}", Button).disabled = (
                running
                or (
                    button_id == "replace"
                    and not any(item.replacement_allowed for item in self.row_items)
                )
                or (
                    button_id == "add"
                    and self.devices.get(str(self.query_one("#device", Select).value)) is None
                )
                or (
                    button_id == "verify"
                    and not any(item.local.path.is_file() for item in self.row_items)
                )
                or (button_id == "update" and not self.selected_paths)
                or (button_id == "retry" and not self.failed_paths)
            )
        self.query_one("#cancel-run", Button).disabled = not self.transfer_running
        self.query_one("#device", Select).disabled = running
        if message:
            self.query_one("#status", Static).update(message)

    def _show_error(self, message: str) -> None:
        self._set_running(False, "")
        self.query_one("#status", Static).update(f"[red]{message}[/red]")


def run_tui() -> None:
    settings = load_settings()
    configure_proxy(settings.proxy)
    VentoyDepotApp(settings=settings).run()


def _write_report(device: Device, report: RunReport) -> Path:
    revalidate_device(device)
    report_dir = safe_subdirectory(device.mount_path, ".ventoy-depot", "reports")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"{stamp}-{report.plan_id}.json"
    report.write(path)
    return path
