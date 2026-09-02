# Ventoy Depot

Ventoy Depot is a safe, extensible TUI and read-only CLI for discovering, checking,
downloading, and managing Linux and publicly available Windows ISOs on Ventoy drives.
It supports Linux and Windows, and never writes to a drive merely
because it is removable or happens to be `/dev/sdb1`.

> Ventoy Depot is an independent community project. It is not affiliated with,
> endorsed by, or supported by the Ventoy project.

## Status

Version 0.2 provides an extensible identity and provider model, variant-preserving ISO
detection, a structured update planner, a read-only automation CLI and a transactional
transfer pipeline. The interactive TUI remains the only place where writes can be
confirmed.

The update dialog is explicit. After confirmation, source lookups, downloads, checksum
validation, and USB copies run in the background; the TUI remains responsive and shows
the active ISO and byte progress. The application does not overwrite an ISO that has the
same target filename, preventing a failed or stale update from replacing an existing file.

To update ISOs in the TUI:

1. Select the Ventoy data partition and choose **Check updates**.
2. Review installed and available versions. Press Space or Enter on a row to toggle it.
3. Choose **Update selected**, review the complete plan, then confirm the transfer.

Automatic official resolution currently covers Arch Linux, Ubuntu, Debian, Fedora
Workstation/Server/KDE, Linux Mint stable editions, EndeavourOS, Omarchy, Pop!_OS,
Vanilla OS and the free Zorin OS editions. Manjaro stays disabled when its
official metadata endpoint is unavailable. A variant without an exact official
mapping remains visibly skipped; it is never silently converted to another edition.

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

## Safety model

- The app lists only removable, mounted volumes that have a Ventoy label or a Ventoy
  filesystem marker. It does not blindly use `/dev/sdb1`.
- Provider identity includes product, edition, flavor, channel, architecture and
  language; updates may not silently change any of these dimensions.
- It keeps the existing ISO until a newly downloaded file has passed the publisher's
  SHA-256 or SHA-512 checksum, has been copied as `.partial`, flushed and verified.
- Explicit replacements move old files into `.ventoy-depot/trash`; they are not
  permanently deleted by an update.
- A future delete/replace action must be explicitly selected and confirmed per ISO.
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
