# Repository Guidelines

## Project Structure & Module Organization

Ventoy Depot is a Python 3.11+ TUI/CLI. Active code lives in `src/ventoy_depot/`:
`app.py` contains the Textual UI, `cli.py` the read-only CLI, `planner.py` builds update
plans, and `transfer.py` performs verified transactional copies. Provider contracts and
official-source resolvers live under `src/ventoy_depot/providers/`; the bundled manifest
schema is in `src/ventoy_depot/registry/`. `src/ventoy_iso_updater/` is the deprecated
compatibility package and should only receive compatibility fixes. Tests mirror behavior
in `tests/test_*.py`. Security and recovery guidance belongs in `docs/`.

## Build, Test, and Development Commands

Create an environment and install development tools:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Use `ventoy-depot` to launch the TUI, or try a read-only command such as
`ventoy-depot providers list --json`. Before submitting changes, run:

```bash
ruff format --check .
ruff check .
mypy
pytest -q
python -m build
```

CI repeats these checks on Linux and Windows with Python 3.11–3.14 and installs the
built wheel for CLI/TUI smoke tests.

## Coding Style & Naming Conventions

Use four-space indentation, Python type annotations, immutable dataclasses for domain
objects, and `snake_case` for modules/functions. Classes use `PascalCase`; constants use
`UPPER_SNAKE_CASE`. Ruff enforces formatting, import order, pyupgrade, and common bug
rules with a 100-character line limit. Mypy is strict for `ventoy_depot`; avoid untyped
escape hatches and broad exception handling outside structured provider boundaries.

## Testing Guidelines

Use pytest and name tests `test_<behavior>`. Add a regression test for every bug and
positive/negative fixtures for provider filename rules. Normal tests must not access live
networks or real removable drives; use temporary directories, saved official metadata,
and mocked HTTP clients. Transfer tests must prove that failures preserve old ISOs and
never expose partial files.

## Commit & Pull Request Guidelines

Write short, imperative commit subjects, for example `Fix transfers on label-detected
Ventoy drives`. Keep commits focused. Pull requests must explain the change, its safety
impact, and verification performed; link relevant issues and include screenshots for
visible TUI changes. All CI checks must pass before merge.

## Security & Configuration Tips

Accept only official HTTPS sources and SHA-256/SHA-512 verification. Preserve variant,
architecture, language, and channel. Never commit credentials, private/TUF keys,
downloaded ISOs, caches, or generated secrets. Do not weaken device revalidation,
mountpoint containment, host allow-lists, or atomic-copy guarantees.
