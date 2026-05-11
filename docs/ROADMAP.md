# Roadmap

Forward-looking work in `pd-ocr-cli` — items that belong in the CLI
itself rather than in the upstream `pd-book-tools` library. Where a
CLI feature is a thin pass-through to a library knob, the library
work is tracked in `pd-book-tools/docs/ROADMAP.md` and the CLI item
here just covers the surfacing (flag name, help text, defaults, docs)
and any caller-side glue.

This file is the standing list of open priorities. Items move out
when they ship (link the PR / commit and drop a brief "Done" entry at
the bottom if useful).

> Shipped items live in [`ROADMAP-shipped.md`](ROADMAP-shipped.md).

## Open — layout output

### Opt-in flag to skip illustration placeholder blocks

Today, when `pd-ocr` produces reading-order text with the layout
detector enabled, every high-confidence figure / decoration / table
region surfaces as a placeholder block in the reorganised output. In
the `.txt` file these placeholders manifest as a stray blank
paragraph (the block has no text but contributes a paragraph break in
`Page.text`); downstream PGDP serialisation wraps the same block as
`[Illustration: ...]`. Plain-text consumers — anyone running `pd-ocr`
to get a clean prose `.txt` — generally don't want either form.

Proposed shape: a CLI flag, name to be confirmed but most likely
`--no-illustration-placeholders` (matches the existing `--no-reorg`
negation-flag pattern; pairs naturally with `--extract-illustrations`,
which also operates on the same regions). When set, the CLI passes
`emit_illustration_placeholders=False` through to
`Page.reorganize_page(...)`. Default stays `True` so existing users —
and pd-prep-for-pgdp, which relies on the placeholder to anchor
`[Illustration: ...]` serialisation — see no behaviour change.

**No-silent-drops invariant.** This is opt-out of the *placeholder
block*, not of the caption text. Caption *words* must still be
preserved on the page — either kept in their originally-detected
block or attached as a `caption`-roled paragraph alongside the
surrounding body text. Suppressing the placeholder must never drop
OCR words. This matches the project-wide "never silently drop OCR
words" rule that already governs reorg in pd-book-tools and
pd-ocr-cli.

**Dependency.** Blocked on the matching pd-book-tools work landing
first: the `Page.reorganize_page(emit_illustration_placeholders=...)`
parameter and the underlying `associate_captions(emit_placeholders=
...)` plumbing don't exist yet. Until the library knob ships there is
nothing for the CLI flag to forward into. The library item is tracked
under "Open — layout consumption" in the pd-book-tools roadmap (entry
on opt-in suppression of placeholder illustration blocks); coordinate
with the upstream agent before starting the CLI side.

**Test surface.** A fixture page with one figure and an adjacent
caption, exercised through the CLI:

- Default invocation — exactly one illustration-roled block surfaces
  in the reorganised output, geometry-only, no text.
- With the new flag — zero illustration-roled blocks surface, *and*
  every input OCR word from the caption (and the rest of the page)
  is still present in the page's words / text. The "no silent drops"
  assertion is the load-bearing one; the "zero placeholder blocks"
  check on its own is necessary but not sufficient.

A small integration test against the real reorg path is preferable
to a pure unit test here — the placeholder emission lives deep in
`associate_captions` and the value of this test is that the CLI flag
actually reaches it.

## Open — developer workflow

### dev-local-aware `upgrade-deps` (and friends)

`make upgrade-deps` currently ends in `uv sync --group dev`, which
silently reverts a `dev-local` venv (editable in-tree pd-book-tools,
GPU extras, doctr-from-git) back to the canonical published/CPU
baseline. Spec for the fix lives in
[`docs/dev-local-upgrade-flow.md`](./dev-local-upgrade-flow.md).

Implementation pass should:

- Add detection (probe `uv pip show pd-book-tools` for
  `Editable project location:`; fall back to a `.venv/`-anchored
  marker; last-resort `PD_DEV_LOCAL=1` opt-in).
- Make `upgrade-deps` refuse by default when dev-local is detected,
  pointing at a new `upgrade-deps-local` recipe that does lock + sync
  + dev-local restore in one shot.
- Audit sibling recipes that also rebuild the venv (`setup`, `reset`,
  `ci`, `ci-slow`) — they may need the same guard. Out of scope for
  the first pass; track separately.
- Coordinate with the `pd-book-tools` agent: the editable-marker
  contract is cross-repo, and the same fix is landing in every `pd-*`
  repo's Makefile in lockstep.
