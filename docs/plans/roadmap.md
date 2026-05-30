# Roadmap

Forward-looking work in `pdomain-ocr-cli` — items that belong in the CLI
itself rather than in the upstream `pdomain-book-tools` library. Where a
CLI feature is a thin pass-through to a library knob, the library
work is tracked in `pdomain-book-tools/docs/plans/roadmap.md` and the CLI
item here just covers the surfacing (flag name, help text, defaults, docs)
and any caller-side glue.

This file is the standing list of open priorities. Items move out
when they ship (link the PR / commit and drop a brief "Done" entry at
the bottom if useful).

> Shipped items are moved to `docs/archive/plans/` per the
> workspace-standard docs layout.

## Open — developer workflow

_No open items._ (Shipped items moved to `docs/archive/plans/`.)

## Done — 2026-05-29 review remediation

- Added `RunPolicy`, `BatchPlan`, `RuntimeSession`, artifact transaction
  helpers, model trust warnings, and startup notice seams.
- Added installer contract tests, real OCR/default-layout slow coverage,
  workflow static checks, and wheel smoke for Python 3.11, 3.12, and 3.13.
- Hardened release gating so path-sourced runtime dependencies block release
  until they resolve from `pdomain-index-pip`.

## Note: pdomain-ops path source

After Wave 4 Task 5 (`--batch-pages` / `run_doctr_batch`), `pyproject.toml`
uses a path-sourced `pdomain-ops` entry in `[tool.uv.sources]` because
pdomain-ops is not yet published to `pdomain-index-pip`. Once pdomain-ops
cuts a release, update the source to `{ index = "pdomain-index-pip" }`.
