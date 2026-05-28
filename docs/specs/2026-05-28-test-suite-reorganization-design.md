# Test-suite reorganization — pdomain-ocr-cli

**Date:** 2026-05-28
**Status:** Approved design, pending implementation plan
**Scope:** `tests/` and test-related CI/devcontainer wiring only. No
production logic changes except `install.ps1` CI/devcontainer wiring and a
small number of justified `# pragma: no cover` markers.

## Definition of done (non-negotiable)

Nothing in scope is deferred, skipped, ignored, or punted to "later":

- No `@pytest.mark.skip` / `skipif` added to dodge an environment gap.
- No `# pragma: no cover` used to avoid testing reachable behavior. Pragma is
  permitted **only** on lines genuinely unexecutable from a test, and each
  use carries a one-line justification comment.
- Behavior gaps identified here are closed **in this effort**, not tracked as
  follow-up issues.
- `make ci` and `make test-slow` both green at the end. Coverage stays at
  `fail_under=100`, achieved by testing real behavior — not by exclusion.

## Problem

The suite is 251 test functions across 14 flat files under an enforced 100%
branch-coverage gate. The audit found:

1. **Tautological tests.** `test_install_ps1_cuda_parse.py` (~22 tests) tests
   a Python reimplementation of the PowerShell regexes, never the real
   `install.ps1`. Editing the real script leaves every test passing.
   `test_cuda_tag_format` asserts a value against its own inline construction.
2. **Mock-call-args instead of behavior.** ~5 tests in `test_main_mocked.py`
   (e.g. `test_main_default_passes_drop_layout_words_false_to_reorganize`)
   assert on `reorganize_page.call_args` kwargs against a `MagicMock`. They
   pass even if the flag is wired to the wrong downstream effect.
3. **Happy-path content gap.** Real recognized-text correctness is only
   asserted in `test_pipeline_integration.py`, which is `@pytest.mark.slow`
   and skipped by default `make ci`. The fast suite's oracle is the echoed
   `"FAKE OCR TEXT"` string — it proves plumbing, not output.
4. **Weak oracles.** `test_main_layout_debug_writes_debug_file` asserts
   nothing about its named behavior; `test_main_noise_drop_warning_skipped_when_no_drops`
   uses an `or`-of-negatives that passes trivially.
5. **Heavy duplication.** `_FakePage` defined 3×; `patched_main` /
   `_patch_common` ~90% identical; `_run_main` / `_invoke_main` copied 3×; the
   `copy image + make out dir` triad ~40×; `_FakeArray` 3×; `_ns()` 2×.
6. **Two oversized files.** `test_main_mocked.py` (52 tests, ~1994 lines) and
   `test_pipeline_helpers.py` (55 tests, ~790 lines).
7. **Misc.** `test_setup_layout_debug_env_*` mutate real `os.environ` with
   manual teardown that leaks on assertion failure; the KeyboardInterrupt test
   mutates a class-level attribute.

## Goals

- Every test has a clear correct ("good") oracle and validates actual output
  against it — no mock-call-args-only and no "did not raise" tests where a
  real oracle is available.
- Shared scaffolding extracted once; no duplicated fakes/helpers/setup.
- Files sized so each is readable in one sitting.
- Default fast CI verifies real OCR output content and real flag→output
  effects.
- `install.ps1` is exercised as the real script, everywhere.

## Non-goals

- No `unit/` vs `integration/` directory split — the `slow` marker already
  isolates the single integration file.
- No changes to `pdomain_ocr_cli/` production logic.
- No new test framework or runner; stay on pytest + pytest-xdist + coverage.

## Design

Phased refactor. Each phase is its own commit(s) and leaves `make ci` green
before the next begins. Restructuring phases (0–2) preserve behavior — the
existing assertions keep passing. The strengthen phase (3) is test-driven:
write the failing assertion first, then make the fake/production path satisfy
it.

### Phase 0 — Shared scaffolding foundation (no behavior change)

- **`tests/_fakes.py`** (new, importable): the single canonical `FakePage`
  (parametrizable so one class serves `test_main_*` and `test_batch_pages`),
  plus `FakeArray`, `FakeSnapshot`, `FakeWord`, `FakeRegion`, `FakeDoc`, and a
  unified `make_namespace(**overrides)` replacing both `_ns()` copies.
- **`tests/conftest.py`** gains fixtures:
  - `mock_heavy_deps` — one wiring fixture replacing `patched_main` and
    `_patch_common`.
  - `run_main` — callable fixture replacing `_run_main` / `_invoke_main`.
  - `single_image` — returns `(img_path, out_dir)`, replacing the ~40×
    copy-and-mkdir triad.
- Migrate each existing test file onto these, one file per step, staying green.

### Phase 1 — Split the giants

- `test_main_mocked.py` → `test_main_happy.py`, `test_main_errors.py`
  (SystemExit / atomicity / KeyboardInterrupt cluster), `test_main_flag_wiring.py`,
  `test_main_warnings.py`.
- `test_pipeline_helpers.py` → `test_pipeline_paths.py`,
  `test_pipeline_warnings.py`, `test_pipeline_atomic_write.py`.
- Remaining 12 files stay flat — they already map one-to-one to modules.

### Phase 2 — Parametrize

- Collapse the 9-test "silent no-op warning" family into one
  `@pytest.mark.parametrize` over `(flags, expected_substrings)`.
- `resolve_ocr_models` detection/recognition-without-counterpart pair → a
  2-case parametrize.

### Phase 3 — Strengthen, fix, delete (test-driven)

- Make `FakePage.reorganize_page` actually transform `page.text` according to
  `drop_layout_words` and `emit_illustration_placeholders`. Rewrite the
  call-args tests to assert on the written `.txt` content. (Per the
  no-silent-word-drops rule: dropped words must be role-labeled in the fake,
  not deleted, so the test can assert the labeled output.)
- Add at least one fast-suite test asserting happy-path OCR **content** shape
  (not the echoed placeholder), so default CI verifies output.
- Fix/rename `test_main_layout_debug_writes_debug_file` so it asserts its
  named behavior; delete `test_main_noise_drop_warning_skipped_when_no_drops`
  (superseded by `_silent_with_zero_count`).
- Convert `test_setup_layout_debug_env_*` to `monkeypatch.setenv` (no manual
  teardown to leak); replace the KeyboardInterrupt test's class-level flag with
  an instance flag.

### Phase 4 — install.ps1 real pwsh

- Replace the Python-reimplementation file with tests that invoke the real
  `install.ps1` / `Get-CudaVersion` through `pwsh`.
- Install PowerShell in the CI workflow **and** the devcontainer so the script
  is exercised in both. No `skipif` — a missing `pwsh` is a failure, not a
  skip, since skipping would recreate the gap this closes.
- Delete `test_cuda_tag_format` (asserts a value against its own construction).

### Phase 5 — Coverage reconciliation

- Keep `fail_under=100`. Where Phase 3/4 leaves a line genuinely unexecutable
  from a test, mark it `# pragma: no cover` with a one-line reason. Reachable
  behavior gets a real test, never a pragma.
- Final gate: `make ci` (fast) and `make test-slow` (incl. integration) green.

## Testing

- Restructuring phases verified by the unchanged assertions continuing to
  pass plus unchanged-or-higher coverage.
- New behavior tests (Phase 3) verified by the red→green TDD cycle.
- Phase 4 verified by `pwsh` being present and the real script driving the
  assertions in CI.
- Whole-effort gate: `make ci` + `make test-slow`, coverage == 100%.

## Risks

- **pwsh as a hard dependency** (CI + devcontainer). Accepted per the
  definition of done — the script must be tested for real everywhere.
- **Coverage churn during deletes.** Mitigated by the phase ordering: behavior
  tests added (Phase 3) before/with deletions (Phase 4) so the gate never goes
  red mid-stream.
