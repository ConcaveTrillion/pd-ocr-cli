# Developing pdomain-ocr-cli

This document covers the developer workflows for `pdomain-ocr-cli`. End-user
install / usage docs live in [`README.md`](README.md).

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python package + tool manager)
- Python `>=3.11,<3.14` (uv will provision one if needed)
- `git`
- For local-dev workflows: `pdomain-book-tools` available as a sibling checkout
  at `../pdomain-book-tools`. `make local-setup` clones it for you.
- Until `pdomain-ops` is published to `pdomain-index-pip`, this repo also
  expects a sibling `../pdomain-ops` checkout for local development and CI.
- Optional: NVIDIA GPU + CUDA Toolkit for GPU-accelerated OCR (see README).

## Quick start

Two paths depending on what you're doing.

### A. Just developing pdomain-ocr-cli (no pdomain-book-tools edits)

```sh
git clone https://github.com/pdomain/pdomain-ocr-cli.git
cd pdomain-ocr-cli
make setup
```

This syncs the dev deps from `pyproject.toml`, including `pdomain-book-tools`
at the pinned git tag, and installs pre-commit hooks. You can now run
`uv run pdomain-ocr ...` without installing globally.

### B. Editing pdomain-ocr-cli **and** pdomain-book-tools side-by-side

```sh
git clone https://github.com/pdomain/pdomain-ocr-cli.git
cd pdomain-ocr-cli
make local-setup
```

`local-setup` does:

1. Clones `pdomain-book-tools` to `../pdomain-book-tools` (skipped if it already exists).
2. Runs `make dev-local`, which:
   - `uv sync --group dev` (installs deps from `pyproject.toml`)
   - `uv pip install -e ../pdomain-book-tools` (replaces the pinned tag with
     the local editable checkout)
   - Verifies via `make check-local-editable` that imports resolve to
     the sibling, not the cached tag.

If you also want pdomain-book-tools' own venv (to run its tests):

```sh
(cd ../pdomain-book-tools && make setup)
```

## Make targets

`make help` is authoritative. Highlights:

### General

| Target | Purpose |
| --- | --- |
| `setup` | Install dev deps + pre-commit hooks (uses pinned `pdomain-book-tools` tag). |
| `refresh-version` | Force-reinstall the editable package so `pdomain-ocr --version` re-derives from current git state (hatch-vcs bakes the version at install time, not at runtime — run this after `git pull` / new local tags). |
| `install` | Install `pdomain-ocr` as a `uv tool` from local source, auto-detecting CUDA. |
| `uninstall` | Remove the installed `pdomain-ocr` uv tool. |
| `lint` | Run ruff (with auto-fix). |
| `format` | Run ruff format, then lint. |
| `pre-commit-check` | Run pre-commit on all files. |
| `test` | Run the pytest suite (`tests/`). |
| `build` | `uv build` — produce sdist + wheel in `dist/`. |
| `wheel-smoke` | Build the wheel, install it into isolated Python 3.11 / 3.12 / 3.13 environments, and run `pdomain-ocr --version`. Override with `PYTHON_VERSIONS="3.13"` for a focused local run. |
| `wheel-smoke-one` | Focused wheel smoke for one interpreter. Set `PYTHON_VERSION=3.11`, `3.12`, or `3.13`. |
| `check-release-deps` | Fail release while runtime dependencies, currently `pdomain-ops`, are path-sourced instead of package-index sourced. |
| `ci` | `setup` → `pre-commit-check` → `format-check` → `typecheck` → `coverage` → `installer-test` → `wheel-smoke`. |
| `ci-slow` | Full release-grade CI including slow integration coverage, build, and wheel smoke. |
| `clean` | Remove caches and `dist/`. |
| `reset` | `clean` + remove `.venv` + `setup`. |
| `upgrade-deps` | Upgrade the lockfile and sync the venv. **Refuses when a dev-local venv is detected** — use `upgrade-deps-local` instead (or set `PDOMAIN_DEV_LOCAL=0` to intentionally clobber). |
| `upgrade-deps-local` | Upgrade the lockfile, sync to canonical baseline, then restore the dev-local editable install — all in one shot. |
| `upgrade-pdomain-book-tools` | Bump the `pdomain-book-tools` pin to the latest GitHub tag. |
| `release-{patch,minor,major}` | Tag a new release locally (push with `git push --tags`). |

### Local-dev (require `../pdomain-book-tools` sibling)

These targets are guarded — if the sibling is missing they print a clear
message and exit 1. None of them mutate `pyproject.toml`; they swap the
pinned dep with an editable install in the venv (or in the `uv tool`
install).

| Target | Purpose |
| --- | --- |
| `local-setup` | Clone the sibling if missing, then run `dev-local`. The one-stop entrypoint. |
| `dev-local` | Install `pdomain-book-tools` from `../pdomain-book-tools` as editable into this venv. |
| `install-local` | Install `pdomain-ocr` as a `uv tool` with **both** repos editable — `pdomain-ocr` on your PATH tracks live edits in either tree. |
| `uninstall-local` | Remove the `uv tool` install. |
| `check-local-editable` | Verify `pdomain_book_tools` imports resolve to `../pdomain-book-tools` (not the cached tag). |
| `run-local` | Run `pdomain-ocr` against the editable workspace. Pass args via `ARGS="…"`. |
| `python-local` | Run `python` against the editable workspace. Pass args via `ARGS="…"`. |

Examples:

```sh
make run-local ARGS='page.png --layout-debug'
make python-local ARGS='-c "import pdomain_book_tools; print(pdomain_book_tools.__file__)"'
```

After `install-local`, just run `pdomain-ocr page.png` — the global tool
points at both editable trees.

To revert to the published version:

```sh
make uninstall-local
curl -sSL https://raw.githubusercontent.com/pdomain/pdomain-ocr-cli/main/install.sh | sh
```

## Project layout

```text
pdomain_ocr_cli/
├── ocr_to_txt.py         # CLI parser and high-level orchestration
├── _policy.py            # effective flag policy and no-op warnings
├── _batch_plan.py        # image expansion, output planning, collision checks
├── _runtime.py           # predictor/session setup and batch runtime errors
├── _artifacts.py         # atomic page artifact writes and transactions
├── _model_security.py    # model trust-boundary warnings
├── _startup_notices.py   # update-check and GPU-nudge startup behavior
├── _hf_download.py       # generic hf_hub_download wrapper (sidecar opt-in)
├── _hf_models.py         # OCR + layout model resolution / prefetch / descriptors
├── _text_normalize.py    # curly-quote and em-dash post-processing
└── _update_check.py      # background GitHub-tag upgrade-notice check
```

Files prefixed with `_` are package-internal. The single public entry
point is `pdomain_ocr_cli.ocr_to_txt:main` (wired via `[project.scripts]`).

## Releasing

Release is intentionally blocked while any runtime dependency resolves from a
local path. Today `pdomain-ops` is not published to `pdomain-index-pip`, so
`make check-release-deps` fails with a clear message. Publish `pdomain-ops` to
the pdomain package index first, then change `[tool.uv.sources]` so
`pdomain-ops = { index = "pdomain-index-pip" }`.

While `pdomain-ops` remains path-sourced, `make wheel-smoke` preinstalls the
local sibling into the temporary smoke-test venv and installs the
`pdomain-ocr-cli` wheel with dependency resolution disabled. That keeps local
wheel/console-script validation useful without pretending the release
dependency graph is publishable. The release workflow runs
`make check-release-deps` before `make ci-slow` or `uv build`, so this fallback
cannot publish artifacts.

The GitHub CI workflow also checks out a pinned `pdomain/pdomain-ops` commit and
links it at `../pdomain-ops` so the path-sourced development graph can resolve
on a fresh runner. That checkout is intentionally not used by the release
workflow.

1. Make sure the `pdomain-book-tools` and `pdomain-ops` sources in
   `pyproject.toml` match the intended release. `make upgrade-pdomain-book-tools`
   bumps book-tools to the latest tag.
2. Run `make check-release-deps`; it must pass before any release tag is built.
3. Run `make ci-slow` to execute the release-required validation. CI also runs
   the fast matrix on Python 3.11, 3.12, and 3.13.
4. Tag and push:

   ```sh
   make release-minor   # or release-patch / release-major
   git push && git push --tags
   ```

   `release-*` only creates a local tag — it does **not** push.

5. Pushing the tag triggers the release workflow, which runs
   `make check-release-deps` and `make ci-slow` before building. If either
   fails, no artifacts are published.

6. When the gate passes, the workflow builds, attests,
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
- Pylance / Pyright may flag `pdomain_book_tools.layout.adapters.pp_doclayout`
  and `transformers.utils` as unresolved. Those are intentional lazy
  imports (heavy deps loaded only when needed). Point your IDE at
  `.venv/bin/python` to silence them.
- `pytest` prints a `DeprecationWarning: defusedxml.cElementTree is deprecated`
  originating from `defusedxml/__init__.py`. This is a bug in `defusedxml`
  itself — its own `__init__.py` imports the deprecated submodule. Watch for
  a `defusedxml` release that fixes it and bump the pin when one appears.
