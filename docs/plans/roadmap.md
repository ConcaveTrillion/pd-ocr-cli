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

## Done — 2026-06-01 book-tools 0.18 / pdomain-ops 0.7.2 + HF model v0.7

- Bumped `pdomain-book-tools` floor to `>=0.18.0`; batch OCR now auto-rotates,
  correcting `rotated_page` fixture without any fixture modification.
- Bumped `pdomain-ops` floor to `>=0.7.2`; both resolve from `pdomain-index-pip`.
- Pinned integration-test HF model to `v0.7` (post-pdomain rename, `pdomain-`-prefixed files).
- All 15 slow integration tests pass, including `rotated_page` LEGITIMATELY.

## Done — 2026-06-01 book-tools 0.17 / pdomain-ops 0.7 compatibility

- Bumped `pdomain-book-tools` floor to `>=0.17.0` and `pdomain-ops` floor to `>=0.7.0`; both resolve from `pdomain-index-pip`.
- Adopted `from_image_ocr_via_doctr` tuple return (`tuple[Document, int]`) in
  `_run_doctr_batch_single_image_compat`; added `_SingleImageDocResultLike` protocol.
- Dropped the stale "pdomain-ops path source" note (ops is now in the index).
