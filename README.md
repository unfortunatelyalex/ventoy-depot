# Ventoy Depot

Ventoy Depot is a safe, extensible TUI and read-only CLI for discovering, checking,
downloading, and managing Linux, BSD, rescue and public installation ISOs on Ventoy
drives. The application runs on Linux and Windows. Windows 11 media can be recognized
and locally verified; automatic Microsoft download-link acquisition is not implemented yet.
It never writes to a drive merely because it is removable or happens to be `/dev/sdb1`.

> Ventoy Depot is an independent community project. It is not affiliated with,
> endorsed by, or supported by the Ventoy project.

## Status

Version 0.2 provides an extensible identity and provider model, variant-preserving ISO
detection, a structured update planner, a read-only automation CLI and a transactional
transfer pipeline. The interactive TUI remains the only place where writes can be
confirmed.

The update dialog is explicit. **Check updates** performs the official metadata lookups
needed to construct the complete plan. After confirmation, downloads, checksum validation,
and USB copies run in the background; the TUI remains responsive and shows the active ISO
and byte progress. Safe additions remain the default. An old ISO is replaced only after
the user explicitly changes that row to `REPLACE` and confirms the complete plan.

To update ISOs in the TUI:

1. Select the Ventoy data partition and choose **Check updates**.
2. Review installed and available versions. Press Space or Enter on a row to toggle its
   visible `[ ]` / `[x]` selection marker.
3. To remove an old version after a successful update, highlight it and choose
   **Replace old ISO** (or press `X`). Otherwise the old ISO remains on the drive.
4. Choose **Update selected**, review the complete plan, then confirm the transfer.

To add a supported ISO that is not yet on the drive, choose **Add new ISO** (or press
`N`), select the exact product, edition, channel and architecture, and review the generated
add-only plan. An existing target filename is never overwritten by this workflow.

For a renamed ISO that cannot be recognized, highlight its row and choose **Assign ISO**
(or press `A`). Select the original product and enter the variant and installed version.
The mapping is stored in `.ventoy-depot/catalog.json` on that drive and is bound to the
ISO's SHA-256 hash, so replacing or modifying the file invalidates stale mappings. The
assignment dialog reads the ISO-9660 volume identifier without mounting the image and uses
it only to suggest a product; the user still confirms every identity field.

Automatic official resolution currently covers Arch Linux, Ubuntu, Debian, Fedora
Workstation/Server/KDE, Alpine Linux, Rocky Linux, AlmaLinux, Linux Mint stable editions,
EndeavourOS, CachyOS, Clonezilla, Gentoo, GhostBSD, GParted Live, Grml, Haiku,
Hiren's BootCD PE, Kali Linux, KDE neon,
netboot.xyz, NixOS, SystemRescue, openSUSE Tumbleweed, FreeBSD, Omarchy, Parrot OS,
Pop!_OS, PorteuX,
Proxmox, Rescuezilla, Solus, TrueNAS Community Edition, Void Linux, Vanilla OS and the free Zorin OS
editions and Tails. Qubes OS and Memtest86+ are recognized but remain
download-disabled until their mirror, signature-chain or archive-extraction requirements
can be represented safely. A variant without an exact official mapping remains visibly
skipped; it is never silently converted.

### Custom declarative providers

Local JSON manifests are disabled by default. To activate one explicitly, add its absolute
path to `local_manifests` in the platform-specific `config.json`, for example:

```json
{"schema_version": 1, "local_manifests": ["/absolute/path/my-provider.json"]}
```

Each file is schema- and security-validated, cannot execute code, cannot replace a curated
provider ID, is labeled `custom`, and may only add a newly verified ISO.

## Installation

Install Python 3.11 or newer, then use one of:

```console
# Linux or Windows, recommended
pipx install ventoy-depot

# If pipx is unavailable
python -m pip install --user ventoy-depot
```

Run `ventoy-depot` in a terminal. The former `ventoy-iso-updater` command is a
deprecated compatibility alias. On Linux, mount the Ventoy data partition
before launching it. On Windows, connect the drive and ensure it has a drive letter.

Read-only commands include `devices`, `scan`, `plan`, `providers list`,
`providers validate`, `providers doctor`, and `verify`. Add `--json` for stable,
schema-versioned machine output.

`providers doctor` validates all loaded provider definitions without network traffic;
specifying one provider ID additionally resolves its current official metadata. `verify PATH`
identifies the ISO and compares it with the publisher checksum when the file is the current
release. A confirmed mismatch exits with status 4; unknown or historical images are hashed
without being falsely reported as verified.

## Safety model

- The app lists only removable, mounted volumes that have a Ventoy label or a Ventoy
  filesystem marker. It does not blindly use `/dev/sdb1`.
- Provider identity includes product, edition, flavor, channel, architecture and
  language; updates may not silently change any of these dimensions.
- It keeps the existing ISO until a newly downloaded file has passed the publisher's
  SHA-256 or SHA-512 checksum, has been copied as `.partial`, flushed and verified.
- Explicit replacements move old files into `.ventoy-depot/trash`; they are not
  permanently deleted by an update.
- A replacement must be explicitly selected and confirmed per ISO; the prior file is
  moved to `.ventoy-depot/trash` only after the new copy has been verified.
- Release metadata and ISO downloads must use HTTPS official endpoints. An unknown ISO
  is reported rather than guessed.

## Development

```console
python -m pip install -e '.[dev]'
pytest
ruff check .
```

Tests use temporary directories and mocked system boundaries where appropriate; they
never inspect, mount, or modify actual disks.
