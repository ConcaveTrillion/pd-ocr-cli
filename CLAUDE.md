# CLAUDE — pd-ocr-cli

CLI tool that turns scanned book pages into clean `.txt` files. Wraps
`pd-book-tools` OCR/layout primitives with auto-rotation, layout-aware
reading-order reconstruction, and a user-facing `pd-ocr` command.

## Commands

| target | does |
|---|---|
| `make setup` | dev venv + pre-commit hooks (pinned `pd-book-tools` tag) |
| `make local-setup` | setup + clone `../pd-book-tools` for side-by-side editing |
| `make dev-local` | swap pinned dep for editable `../pd-book-tools` in the venv |
| `make test` | fast suite (`uv run pytest -n auto`; skips `@pytest.mark.slow`) |
| `make test-slow` | full suite incl. real-model integration tests |
| `make lint` / `make format` | ruff |
| `make build` | sdist + wheel into `dist/` |
| `make ci` | setup → pre-commit → test → build |
| `make upgrade-pd-book-tools` | bump pin to latest GitHub tag |
| `make release-{patch,minor,major}` | tag locally; `git push --tags` triggers release workflow |
| `make refresh-version` | re-derive `pd-ocr --version` after tag changes (hatch-vcs) |

Append `AI=1` to any target for agent-friendly output — verbose output is
captured to `.ci-ai.log`; stdout shows `✅ <target> passed` on success or
filtered failure sections on error. Works for every target: `make ci AI=1`,
`make test AI=1`, etc.

Full target list: `make help`. Full dev setup: [`DEVELOPMENT.md`](DEVELOPMENT.md).

## Rules

- Make targets first; fall back to `uv run …` only when no target exists.
- Never `python -m pytest`. Always `uv run pytest -n auto` or `make test`. Bare `python`/`python3`/`.venv/bin/python` miss the venv.
- Never silently drop OCR words. Reorg, caption suppression, and all output paths must preserve every word — roles may change, words may not disappear.
- `--no-illustration-placeholders` (planned) suppresses the placeholder block, not caption text. Caption words must survive in the output.
- `pd-book-tools` is upstream for OCR/layout/image primitives; coordinate with that agent before adding logic that belongs in the library.
- `pd-book-tools` is pinned in `pyproject.toml`; upgrade with `make upgrade-pd-book-tools`.
- Version is derived from git tags via `hatch-vcs` — no hardcoded version in `pyproject.toml`.

## Sibling repos

- `../pd-book-tools/` — upstream dependency. Side-by-side editing: `make local-setup` + `make dev-local`.

## Docs

- [`DEVELOPMENT.md`](DEVELOPMENT.md) — dev setup, Make targets, release steps.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — open priorities.
- [`docs/layout-aware-ocr.md`](docs/layout-aware-ocr.md) — layout-aware OCR behavior.
- [`docs/usage.md`](docs/usage.md) — end-user usage reference.
