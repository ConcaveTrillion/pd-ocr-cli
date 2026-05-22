# Shipped: dev-local-aware `upgrade-deps`

**Status:** Shipped in `feat/upgrade-deps-local`.

## What shipped

- `make upgrade-deps` now refuses when a dev-local venv is detected, printing a
  clear message and pointing at `upgrade-deps-local`.
- `make upgrade-deps-local` does `uv lock --upgrade` + `uv sync --group dev` +
  `make dev-local` in one shot, so the editable install is restored after the
  canonical sync.
- `make dev-local` now writes `.venv/.pd-dev-local` as a marker file (cleared
  automatically when `.venv/` is removed by `make remove-venv` / `make reset`).
- Detection is three-tier: `uv pip show pd-book-tools` editable probe → marker
  file → `PD_DEV_LOCAL=1` env var (last resort / CI override).

## What was deferred

- Auditing `setup`, `reset`, `ci`, `ci-slow` for the same guard — tracked as
  a follow-on roadmap item if needed.
- Cross-repo lockstep: the same pattern should land in `pd-book-tools` and
  other `pd-*` repos with dev-local Makefile targets.
