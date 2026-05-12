# CLAUDE — pd-ocr-cli

CLI tool that turns scanned book pages into clean `.txt` files. Wraps `pd-book-tools` OCR and layout primitives with auto-rotation, layout-aware reading-order reconstruction, and a user-facing `pd-ocr` command.

## Commands

| target | does |
|---|---|
| `make setup` | provision dev venv + pre-commit hooks (pinned `pd-book-tools` tag) |
| `make local-setup` | setup + clone `../pd-book-tools` sibling for side-by-side editing |
| `make dev-local` | swap pinned dep for editable `../pd-book-tools` in the venv |
| `make test` | `uv run pytest -n auto` (fast; skips `@pytest.mark.slow`) |
| `make test-slow` | full suite including integration tests that download a real model |
| `make lint` / `make format` | ruff check + ruff format |
| `make build` | `uv build` → sdist + wheel in `dist/` |
| `make ci` | setup → pre-commit-check → test → build |
| `make upgrade-pd-book-tools` | bump `pd-book-tools` pin to latest GitHub tag |
| `make release-{patch,minor,major}` | tag locally; `git push --tags` triggers release workflow |
| `make refresh-version` | re-derive `pd-ocr --version` after tag changes (hatch-vcs) |

Full target list: `make help`. Full dev setup: [`DEVELOPMENT.md`](DEVELOPMENT.md).

## Rules

- Make targets first; fall back to `uv run …` only when no target exists.
- Never `python -m pytest`. Always `make test` or `uv run pytest -n auto`.
- Never silently drop OCR words. Reorg, caption suppression, and all output paths must preserve every word — roles may change, words may not disappear.
- `--no-illustration-placeholders` (planned) suppresses the placeholder block, not caption text. Caption words must survive in the output.
- `pd-book-tools` is the upstream for all OCR/layout/image primitives; coordinate with that agent before adding logic that belongs in the library.
- `pd-book-tools` is pinned in `pyproject.toml`; upgrade with `make upgrade-pd-book-tools`.
- Version is derived from git tags via `hatch-vcs` — no hardcoded version in `pyproject.toml`.

## Sibling repos

- `../pd-book-tools/` — shared OCR/layout/image primitives (upstream dependency). Use `make local-setup` + `make dev-local` for side-by-side editing.

## Docs

- [`DEVELOPMENT.md`](DEVELOPMENT.md) — dev setup, Make targets, release steps.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — open priorities.
- [`docs/layout-aware-ocr.md`](docs/layout-aware-ocr.md) — layout-aware OCR behavior.
- [`docs/usage.md`](docs/usage.md) — end-user usage reference.
