from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, ProgressBar, Select, Static

from .assignments import AssignmentCatalog
from .config import cache_path, load_settings
from .devices import DeviceError, discover_ventoy_devices
from .i18n import translate
from .models import Device, IsoIdentity, PlanItem, UpdatePlan
from .planner import build_plan
from .report import ItemResult, ResultStatus, RunReport
from .transfer import apply_item


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
                f"• {item.local.path.name}\n  → {item.target.filename}"
                f" ({variant or 'default'}, {item.verification_level.value})"
            )
        with Container(id="dialog"):
            yield Static(
                f"[bold]{translate('confirm_title', self.language)}[/bold]\n"
                f"{len(self.items)} ISO(s), {size}\n"
                f"{translate('keep_old', self.language)}"
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
    ("Arch Linux", "arch", "archlinux", "x86_64"),
    ("Ubuntu", "ubuntu", "ubuntu", "amd64"),
    ("Debian", "debian", "debian", "amd64"),
    ("Debian Live", "debian", "debian-live", "amd64"),
    ("Fedora", "fedora", "fedora", "x86_64"),
    ("Linux Mint", "linux-mint", "linux-mint", "amd64"),
    ("EndeavourOS", "endeavouros", "endeavouros", "x86_64"),
    ("CachyOS", "cachyos", "cachyos", "x86_64"),
    ("Omarchy", "omarchy", "omarchy", "x86_64"),
    ("Manjaro", "manjaro", "manjaro", "x86_64"),
    ("Pop!_OS", "pop-os", "pop-os", "amd64"),
    ("Nobara", "nobara", "nobara", "x86_64"),
    ("Vanilla OS", "vanilla-os", "vanilla-os", "amd64"),
    ("Zorin OS", "zorin-os", "zorin-os", "amd64"),
)


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

    def __init__(self, path: Path, language: str) -> None:
        super().__init__()
        self.path = path
        self.language = language

    def compose(self) -> ComposeResult:
        options = [
            (label, f"{provider_id}|{product_id}|{architecture}")
            for label, provider_id, product_id, architecture in _ASSIGNMENT_PROFILES
        ]
        with VerticalScroll(id="assign-dialog"):
            yield Static(f"[bold]{translate('assign_title', self.language)}[/bold]")
            yield Static(self.path.name)
            yield Static(translate("assign_help", self.language))
            yield Static(translate("provider_product", self.language))
            yield Select(options, allow_blank=False, value=options[0][1], id="assign-profile")
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


class VentoyDepotApp(App[None]):
    CSS = """
    #content { width: 96%; max-width: 150; margin: 1 2; }
    #device-card { margin: 1 0; }
    #progress { margin: 1 0; }
    DataTable { height: 1fr; min-height: 12; }
    Button { margin-right: 1; }
    """
    TITLE = "Ventoy Depot"
    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("s", "scan", "Check updates"),
        ("space", "toggle_selection", "Select ISO"),
        ("a", "assign_identity", "Assign ISO"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, language: str = "en") -> None:
        super().__init__()
        self.language = language
        self.devices: dict[str, Device] = {}
        self.plan: UpdatePlan | None = None
        self.row_items: list[PlanItem] = []
        self.selected_paths: set[Path] = set()
        self.pending_items: tuple[PlanItem, ...] = ()

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="content"):
            yield Static(translate("choose_device", self.language), id="status")
            yield Select([], prompt=translate("choose_device", self.language), id="device")
            yield Static("", id="device-card")
            with Horizontal():
                yield Button(translate("refresh", self.language), id="refresh", variant="primary")
                yield Button(translate("check_updates", self.language), id="scan", disabled=True)
                yield Button(translate("assign_iso", self.language), id="assign", disabled=True)
                yield Button(
                    translate("update_selected", self.language),
                    id="update",
                    disabled=True,
                    variant="warning",
                )
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
        self.plan = None
        self.selected_paths.clear()
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
        elif event.button.id == "update":
            self.action_update()

    def on_data_table_row_selected(self, _event: DataTable.RowSelected) -> None:
        self.action_toggle_selection()

    def action_refresh(self) -> None:
        try:
            devices = discover_ventoy_devices()
        except DeviceError as error:
            self.query_one("#status", Static).update(f"[red]{error}[/red]")
            return
        self.devices = {device.identifier: device for device in devices}
        self.plan = None
        self.row_items.clear()
        self.selected_paths.clear()
        self.query_one("#scan", Button).disabled = True
        self.query_one("#update", Button).disabled = True
        self.query_one("#assign", Button).disabled = True
        self.query_one("#device-card", Static).update("")
        self.query_one("#isos", DataTable).clear()
        self.query_one("#device", Select).set_options(
            [(item.display_name, item.identifier) for item in devices]
        )
        self.query_one("#status", Static).update(
            translate("choose_device" if devices else "no_devices", self.language)
        )

    def action_scan(self) -> None:
        selected = self.query_one("#device", Select).value
        device = self.devices.get(str(selected))
        if device is not None:
            self._build_plan(device)

    @work(thread=True, exclusive=True, group="metadata")
    def _build_plan(self, device: Device) -> None:
        self.call_from_thread(
            self._set_running, True, translate("checking_metadata", self.language)
        )
        try:
            plan = build_plan(device, refresh=True)
        except Exception as error:
            self.call_from_thread(self._show_error, str(error))
        else:
            self.call_from_thread(self._show_plan, plan)

    def _show_plan(self, plan: UpdatePlan) -> None:
        self.plan = plan
        self.row_items = list(plan.items)
        self.selected_paths = {item.local.path for item in plan.items if item.writable}
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
            status = "; ".join(messages) if messages else item.action.value.upper()
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

    def action_toggle_selection(self) -> None:
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
            AssignIdentity(item.local.path, self.language),
            partial(self._assignment_chosen, item.local.path),
        )

    def _assignment_chosen(self, path: Path, identity: IsoIdentity | None) -> None:
        if identity is not None:
            self._save_assignment(path, identity)

    @work(thread=True, exclusive=True, group="metadata")
    def _save_assignment(self, path: Path, identity: IsoIdentity) -> None:
        selected = self.query_one("#device", Select).value
        device = self.devices.get(str(selected))
        if device is None:
            return
        self.call_from_thread(
            self._set_running, True, translate("saving_assignment", self.language)
        )
        try:
            AssignmentCatalog(device.mount_path).assign(path, identity)
        except Exception as error:
            self.call_from_thread(self._show_error, str(error))
        else:
            self.call_from_thread(self._assignment_saved, device)

    def _assignment_saved(self, device: Device) -> None:
        self.query_one("#status", Static).update(translate("assignment_saved", self.language))
        self._build_plan(device)

    def action_update(self) -> None:
        if self.plan is None:
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
            self._perform_updates(self.plan, items)

    @work(thread=True, exclusive=True, group="transfer")
    def _perform_updates(self, plan: UpdatePlan, items: tuple[PlanItem, ...]) -> None:
        self.call_from_thread(self._set_running, True, translate("updating", self.language))
        results: list[ItemResult] = []
        for index, item in enumerate(items, start=1):
            try:
                destination = apply_item(
                    item,
                    progress=partial(
                        self._thread_progress,
                        index,
                        len(items),
                        item.local.path.name,
                    ),
                    cache_dir=cache_path() / "downloads",
                )
            except Exception as error:
                results.append(ItemResult(str(item.local.path), ResultStatus.FAILED, str(error)))
            else:
                results.append(
                    ItemResult(str(destination), ResultStatus.SUCCESS, f"Saved {destination.name}")
                )
        report = RunReport(plan.plan_id, tuple(results))
        report_dir = plan.device.mount_path / ".ventoy-depot" / "reports"
        try:
            report_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            report.write(report_dir / f"{stamp}-{plan.plan_id}.json")
        except OSError:
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
        self._set_running(False, "")
        self.query_one("#progress", ProgressBar).update(progress=100)
        lines = [
            f"{result.status.value.upper()}: {Path(result.path).name} — {result.message}"
            for result in report.results
        ]
        color = "green" if report.successful else "red"
        self.query_one("#status", Static).update(
            f"[{color}]{translate('run_finished', self.language)}[/{color}]\n" + "\n".join(lines)
        )
        self.selected_paths.clear()
        self.query_one("#update", Button).disabled = True

    def _set_running(self, running: bool, message: str) -> None:
        for button_id in ("refresh", "scan", "assign", "update"):
            self.query_one(f"#{button_id}", Button).disabled = running or (
                button_id == "update" and not self.selected_paths
            )
        self.query_one("#device", Select).disabled = running
        if message:
            self.query_one("#status", Static).update(message)

    def _show_error(self, message: str) -> None:
        self._set_running(False, "")
        self.query_one("#status", Static).update(f"[red]{message}[/red]")


def run_tui() -> None:
    settings = load_settings()
    VentoyDepotApp(settings.language).run()
