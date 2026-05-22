# Roadmap

Forward-looking work in `pd-ocr-cli` — items that belong in the CLI
itself rather than in the upstream `pd-book-tools` library. Where a
CLI feature is a thin pass-through to a library knob, the library
work is tracked in `pd-book-tools/docs/plans/roadmap.md` and the CLI
item here just covers the surfacing (flag name, help text, defaults, docs)
and any caller-side glue.

This file is the standing list of open priorities. Items move out
when they ship (link the PR / commit and drop a brief "Done" entry at
the bottom if useful).

> Shipped items are moved to `docs/archive/plans/` per the
> workspace-standard docs layout.

## Open — developer workflow

### dev-local-aware `upgrade-deps` (and friends)

`make upgrade-deps` currently ends in `uv sync --group dev`, which
silently reverts a `dev-local` venv (editable in-tree pd-book-tools,
GPU extras, doctr-from-git) back to the canonical published/CPU
baseline. Spec for the fix lives in
[`docs/runbooks/dev-local-upgrade-flow.md`](../runbooks/dev-local-upgrade-flow.md).

Implementation pass should:

- Add detection (probe `uv pip show pd-book-tools` for
  `Editable project location:`; fall back to a `.venv/`-anchored
  marker; last-resort `PD_DEV_LOCAL=1` opt-in).
- Make `upgrade-deps` refuse by default when dev-local is detected,
  pointing at a new `upgrade-deps-local` recipe that does
  lock + sync + dev-local restore in one shot.
- Audit sibling recipes that also rebuild the venv (`setup`, `reset`,
  `ci`, `ci-slow`) — they may need the same guard. Out of scope for
  the first pass; track separately.
- Coordinate with the `pd-book-tools` agent: the editable-marker
  contract is cross-repo, and the same fix is landing in every `pd-*`
  repo's Makefile in lockstep.
