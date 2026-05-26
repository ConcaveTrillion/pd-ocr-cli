# dev-local-aware `upgrade-deps` flow

**Status:** Implemented in `Makefile` (`upgrade-deps` guard + `upgrade-deps-local` recipe).

## Problem

`make upgrade-deps` today ends with `uv sync --group dev`, which
**silently reverts** a venv that was set up via `make dev-local` back to
the canonical published-and-CPU baseline.

A `dev-local` venv is materially different from the canonical one:

- `pdomain-book-tools` is installed **editable** from `../pdomain-book-tools`
  (not the pinned tag in `pyproject.toml`).
- `doctr` may be installed from a git ref rather than the published
  wheel.
- The `[gpu]` extras of `pdomain-book-tools` (CuPy etc.) may be present.

`uv sync` doesn't know any of that; it resolves against `pyproject.toml`
and `uv.lock` and rewrites the venv to match. The user loses their
in-tree editable, the GPU extras, and any non-pinned `doctr`. The
breakage is silent — the next `pd-ocr` invocation just quietly runs
against the canonical pin.

This same trap is being fixed in lockstep across every `pd-*` repo;
this doc captures the contract on the `pdomain-ocr-cli` side.

## Required behavior

1. **Detect mode before clobbering.** `upgrade-deps` and any sibling
   recipe that rebuilds the venv (anything that effectively runs
   `uv sync`) MUST detect dev-local vs canonical mode **before** running
   the sync.

2. **Detection mechanism — preferred order:**

   1. **Probe `uv pip show pdomain-book-tools`** for an
      `Editable project location:` field. This is the cross-repo
      contract: the `pdomain-book-tools` agent is documenting the matching
      half (its venv exposes the editable marker; downstream repos read
      it). Presence of that field == dev-local mode.
   2. **Marker file** written by `make dev-local`, lifecycle anchored
      to `.venv/` so `make remove-venv` / `make reset` clear it
      automatically. (Fallback for environments where step 1 is
      ambiguous, e.g. uv version skew.)
   3. **Env var `PD_DEV_LOCAL=1`** opt-in. Last resort — useful for
      CI matrix jobs that want to force dev-local semantics without
      touching the venv first.

3. **UX on detection:** by default **refuse**, with a clear message
   that names what was detected and how to proceed. Provide a sibling
   `upgrade-deps-local` recipe that does
   `uv lock --upgrade` → `uv sync` → restore dev-local
   (re-run the editable + GPU-extra installs from `dev-local`) in one
   shot.

   Approximate message shape:

   ```text
   ⚠️  Detected dev-local venv (pdomain-book-tools editable at ../pdomain-book-tools).
       Running `uv sync` here would revert the venv to the canonical baseline.
       Use:  make upgrade-deps-local   (lock + sync + restore dev-local)
       Or:   PD_DEV_LOCAL=0 make upgrade-deps   (canonical mode, intentional clobber)
   ```

4. **Canonical-mode behavior unchanged** from the current `upgrade-deps`
   (commit eca808e era): `uv lock --upgrade` then `uv sync --group dev`.

5. **Cross-platform.** Linux devcontainer + macOS. Detection must not
   rely on GNU-only flags; `uv pip show` output parsing should tolerate
   either `LF` or `CRLF` line endings.

## Out of scope for this pass

- Any other Makefile target. `setup`, `reset`, `ci`, `ci-slow` may all
  also need dev-local-awareness, but that's a separate audit pass —
  see roadmap entry.
- Auto-restoring dev-local after a canonical `upgrade-deps`. The
  refusal-by-default UX is intentional; auto-restore would hide the
  intent.

## References

- `Makefile` — current `upgrade-deps` recipe (lines ~75–80) and the
  `dev-local` / `check-local-editable` targets it will need to call
  back into.
- `scripts/check-editable.py` — already does the editable-resolution
  probe; the implementation can lean on (or extend) it rather than
  re-parsing `uv pip show` from scratch.
- Workspace-level standardization: same fix landing in `pdomain-book-tools`,
  `pd-ocr-labeler`, `pd-ocr-trainer`, etc.
