# Developing pd-ocr-cli

This document covers the developer workflows for `pd-ocr-cli`. End-user
install / usage docs live in [`README.md`](README.md).

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python package + tool manager)
- Python ≥ 3.10 (uv will provision one if needed)
- `git`
- For local-dev workflows: `pd-book-tools` available as a sibling checkout
  at `../pd-book-tools`. `make local-setup` clones it for you.
- Optional: NVIDIA GPU + CUDA Toolkit for GPU-accelerated OCR (see README).

## Quick start

Two paths depending on what you're doing.

### A. Just developing pd-ocr-cli (no pd-book-tools edits)

```sh
git clone https://github.com/ConcaveTrillion/pd-ocr-cli.git
cd pd-ocr-cli
make setup
```

This syncs the dev deps from `pyproject.toml`, including `pd-book-tools`
at the pinned git tag, and installs pre-commit hooks. You can now run
`uv run pd-ocr ...` without installing globally.

### B. Editing pd-ocr-cli **and** pd-book-tools side-by-side

```sh
git clone https://github.com/ConcaveTrillion/pd-ocr-cli.git
cd pd-ocr-cli
make local-setup
```

`local-setup` does:

1. Clones `pd-book-tools` to `../pd-book-tools` (skipped if it already exists).
2. Runs `make dev-local`, which:
   - `uv sync --group dev` (installs deps from `pyproject.toml`)
   - `uv pip install -e ../pd-book-tools` (replaces the pinned tag with
     the local editable checkout)
   - Verifies via `make check-local-editable` that imports resolve to
     the sibling, not the cached tag.

If you also want pd-book-tools' own venv (to run its tests):

```sh
(cd ../pd-book-tools && make setup)
```

## Make targets

`make help` is authoritative. Highlights:

### General

| Target | Purpose |
| --- | --- |
| `setup` | Install dev deps + pre-commit hooks (uses pinned `pd-book-tools` tag). |
| `refresh-version` | Force-reinstall the editable package so `pd-ocr --version` re-derives from current git state (hatch-vcs bakes the version at install time, not at runtime — run this after `git pull` / new local tags). |
| `install` | Install `pd-ocr` as a `uv tool` from local source, auto-detecting CUDA. |
| `uninstall` | Remove the installed `pd-ocr` uv tool. |
| `lint` | Run ruff (with auto-fix). |
| `format` | Run ruff format, then lint. |
| `pre-commit-check` | Run pre-commit on all files. |
| `test` | Run the pytest suite (`tests/`). |
| `build` | `uv build` — produce sdist + wheel in `dist/`. |
| `ci` | `setup` → `pre-commit-check` → `test` → `build`. |
| `clean` | Remove caches and `dist/`. |
| `reset` | `clean` + remove `.venv` + `setup`. |
| `upgrade-pd-book-tools` | Bump the `pd-book-tools` pin to the latest GitHub tag. |
| `release-{patch,minor,major}` | Tag a new release locally (push with `git push --tags`). |

### Local-dev (require `../pd-book-tools` sibling)

These targets are guarded — if the sibling is missing they print a clear
message and exit 1. None of them mutate `pyproject.toml`; they swap the
pinned dep with an editable install in the venv (or in the `uv tool`
install).

| Target | Purpose |
| --- | --- |
| `local-setup` | Clone the sibling if missing, then run `dev-local`. The one-stop entrypoint. |
| `dev-local` | Install `pd-book-tools` from `../pd-book-tools` as editable into this venv. |
| `install-local` | Install `pd-ocr` as a `uv tool` with **both** repos editable — `pd-ocr` on your PATH tracks live edits in either tree. |
| `uninstall-local` | Remove the `uv tool` install. |
| `check-local-editable` | Verify `pd_book_tools` imports resolve to `../pd-book-tools` (not the cached tag). |
| `run-local` | Run `pd-ocr` against the editable workspace. Pass args via `ARGS="…"`. |
| `python-local` | Run `python` against the editable workspace. Pass args via `ARGS="…"`. |

Examples:

```sh
make run-local ARGS='page.png --layout-debug'
make python-local ARGS='-c "import pd_book_tools; print(pd_book_tools.__file__)"'
```

After `install-local`, just run `pd-ocr page.png` — the global tool
points at both editable trees.

To revert to the published version:

```sh
make uninstall-local
curl -sSL https://raw.githubusercontent.com/ConcaveTrillion/pd-ocr-cli/main/install.sh | sh
```

## Project layout

```text
pd_ocr_cli/
├── ocr_to_txt.py        # CLI entrypoint + main() + parse_args()
├── _hf_download.py      # generic hf_hub_download wrapper (sidecar opt-in)
├── _hf_models.py        # OCR + layout model resolution / prefetch / descriptors
├── _text_normalize.py   # curly-quote and em-dash post-processing
└── _update_check.py     # background GitHub-tag upgrade-notice check
```

Files prefixed with `_` are package-internal. The single public entry
point is `pd_ocr_cli.ocr_to_txt:main` (wired via `[project.scripts]`).

## Releasing

1. Make sure the `pd-book-tools` pin in `pyproject.toml` matches the
   intended release. `make upgrade-pd-book-tools` bumps to latest tag.
2. Run `make ci` to lint + build cleanly.
3. Tag and push:

   ```sh
   make release-minor   # or release-patch / release-major
   git push && git push --tags
   ```

   `release-*` only creates a local tag — it does **not** push.

4. Pushing the tag triggers the release workflow, which builds, attests,
   and publishes the wheel as a GitHub Release asset. `install.sh` /
   `install.ps1` resolve the latest non-prerelease GitHub Release and
   download that wheel, so end users get the new release on their next
   `curl | sh`.

Versioning is managed by `hatch-vcs` from git tags — `pyproject.toml`
has no hardcoded version.

## Notes

- `Makefile.local` is gitignored. The earlier separate-file pattern has
  been merged into the main `Makefile` (with peer-existence guards on
  the `*-local` targets), but `-include Makefile.local` is still
  available for personal additions if you want them.
- Pylance / Pyright may flag `pd_book_tools.layout.adapters.pp_doclayout`
  and `transformers.utils` as unresolved. Those are intentional lazy
  imports (heavy deps loaded only when needed). Point your IDE at
  `.venv/bin/python` to silence them.
- `pytest` prints a `DeprecationWarning: defusedxml.cElementTree is deprecated`
  originating from `defusedxml/__init__.py`. This is a bug in `defusedxml`
  itself — its own `__init__.py` imports the deprecated submodule. Watch for
  a `defusedxml` release that fixes it and bump the pin when one appears.
