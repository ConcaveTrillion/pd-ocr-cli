# Done — `--no-illustration-placeholders` flag

Shipped on branch `feat/no-illustration-placeholders` (merged to local
`main`). Originally an open item under "Open — layout output" in
[`docs/plans/roadmap.md`](../../plans/roadmap.md).

## What shipped

A CLI flag `--no-illustration-placeholders` (default OFF) that forwards
`emit_illustration_placeholders=False` to `Page.reorganize_page(...)`.
When set, high-confidence figure / decoration / table regions no longer
contribute an empty placeholder block (a stray blank paragraph in the
`.txt`; an `[Illustration: ...]` wrapper downstream) to the reorganized
output.

Default stays `True` so existing users — and pdomain-prep-for-pgdp, which
anchors `[Illustration: ...]` serialisation on the placeholder — see no
behaviour change.

## No-silent-drops invariant

This suppresses the *placeholder block*, not caption text. Caption words
are preserved by the library (the `associate_captions(emit_placeholders=
...)` plumbing keeps caption words regardless). The CLI side only forwards
the flag.

## Dependency

Required `pdomain-book-tools` ≥ 0.12.0 (the `emit_illustration_placeholders`
kwarg landed in upstream commit `1206fbd`, released in `v0.12.0`). The
CLI pin was bumped from `>=0.11.1` to `>=0.12.0` as part of this work and
`uv.lock` relocked.

## Tests

- `tests/test_parse_args.py` — flag parses, defaults False.
- `tests/test_main_mocked.py` — default forwards `True`, flag forwards
  `False`, `--no-reorg` + flag emits a no-op warning.
