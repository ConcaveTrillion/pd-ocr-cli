# pd-ocr-cli Code Review — 2026-05-06

Full architectural review of all source modules. Each finding is tagged with
severity (`[CRITICAL]`, `[MAJOR]`, `[MINOR]`, `[NIT]`) and a file:line citation.
Intended for Opus iteration: work top-to-bottom, mark each item done as you go.

---

## Next item

All round-4 B items (B17–B23) are now done. Trigger round 5 deep
review for the next batch of findings.

### Done

- **B23** — `compute_mirror_root` previously called
  `os.path.commonpath([d.resolve() for d in input_dirs])` with no
  guard. On Windows, paths on different drives raise
  `ValueError("Paths don't have the same drive")`; the call sits
  outside the per-image `try`, so a single batch of inputs spanning
  drives (`pd-ocr C:\scans D:\more_scans -o E:\out`) aborted the
  entire batch with an unhandled traceback before any image was
  processed. Wrapped the `commonpath` call in a `try/except
  ValueError`, fall back to `mirror_root=None` (flat output under
  `--output-dir`), and emit a single stderr WARNING explaining the
  degraded behavior. New regression
  `test_compute_mirror_root_handles_no_common_ancestor` patches
  `os.path.commonpath` to raise the same `ValueError` the real
  Windows stdlib raises (POSIX can't reproduce the cross-drive case
  natively after `.resolve()`), asserts the function returns `None`
  and emits exactly one `WARNING` — confirmed right-reason failure
  before the fix (uncaught `ValueError`) and green after.
- **B22** — `_latest_stable_tag` previously raised `AttributeError`
  on GitHub error-response bodies (rate-limit / auth-required /
  repo-unavailable JSON dicts like
  `{"message": "API rate limit exceeded ...",
  "documentation_url": ...}`). The dict is truthy, so the
  `if not tags: return` guard didn't fire and the dict fell through
  to `_latest_stable_tag` which iterates dict keys (strings) and
  calls `str.get("name", "")` -> AttributeError. That was swallowed
  by the bare `except Exception: pass` in `check_for_update`, so
  users on rate-limited networks never saw an upgrade notice and
  never learned the machinery was broken (every future bug in the
  block was also masked). Fix: `if not isinstance(payload, list)
  or not payload: return` before the call. New regression
  `test_github_error_dict_body_does_not_reach_latest_stable_tag`
  spies on `_latest_stable_tag` and asserts it is never invoked
  with a dict-shaped error body — confirmed right-reason failure
  before the fix (spy recorded the dict call) and green after.
- **B21** — `--layout-confidence` previously used plain `type=float`,
  silently accepting `nan` (every `x < nan` is False, so the crop
  filter is turned off and every region passes), `inf`/`-inf`
  (no region passes; `--extract-illustrations` produces zero crops
  with no warning), negatives, and values >1 (e.g. user typo `50`
  meaning `0.5`). New `_confidence_threshold` argparse type rejects
  non-finite values and anything outside `[0.0, 1.0]` with a clear
  `--layout-confidence must be a finite number in [0, 1]; got X`
  error at the CLI boundary, before the value is handed to the
  layout backend. Two regression tests in `tests/test_parse_args.py`:
  `test_layout_confidence_accepts_inclusive_bounds` (0, 0.0, 1, 1.0
  still pass) and `test_layout_confidence_rejects_out_of_range_or_nonfinite`
  parametrized over `nan`, `NaN`, `inf`, `-inf`, `Infinity`, `-1`,
  `-0.0001`, `1.0001`, `50`, `not-a-number` — confirmed
  right-reason failure (`DID NOT RAISE SystemExit`) before the fix
  and green after.
- **B17** — The per-image `except Exception` branch now prints a
  bare `print()` to terminate the unterminated `Processing X ...`
  stdout line (which `ocr_to_txt.main` emits with `end=" "`) before
  the `ERROR processing` stderr message. Without it, consecutive
  failed images glued their stdout into one line — `Processing a
  ... Processing b ... Done (2 error(s)).` — and the trailing
  `Done` summary glued onto the last failure too. The `page is
  None` (B13) and `KeyboardInterrupt` (B20) siblings already did
  this; this was the last gap. New regression
  `test_main_per_image_exception_terminates_processing_stdout_line`
  drives a two-image batch where the document factory raises for
  both, and asserts there are exactly two separate `Processing`
  lines on stdout — confirmed right-reason failure before the fix
  (a single glued line) and green after.
- **B19** — The canonical `.txt` is now written *last* in the
  per-page artifact set, after `doc.to_json_file`, the diagnostic
  snapshots, and the illustration crop loop. Previously, the order
  was txt → json → diagnostics → crops, so any failure in the
  later steps was caught by the per-image `except Exception`,
  bumped the `errors` counter, and left an orphan `.txt` next to a
  missing sidecar. Downstream pipelines that key on `.txt`
  existence as "this page completed successfully" would have
  silently consumed the orphan as a clean run. Reordered to
  crops → diagnostics → json → `.txt` so a failure anywhere in the
  chain leaves no `.txt` for that page; combined with B18's
  atomic-write invariant, the per-page artifact set is now
  all-or-nothing. The existing
  `test_main_save_json_failure_cleans_up_tmp_and_increments_errors`
  was extended with a `not (out / "page.txt").exists()` assertion
  to lock in the new ordering — confirmed right-reason failure
  before the fix, then green after.
- **B18** — All disk writes from `ocr_to_txt.main` and
  `write_diagnostic_snapshots` now go through a sibling temp +
  `os.replace` atomic pattern, so a SIGKILL/OOM/`ENOSPC` mid-write
  can no longer leave a truncated file at the canonical path. Two
  helpers `atomic_write_text` / `atomic_write_bytes` were added to
  `_pipeline.py`; the `out_path.write_text` site, the four
  diagnostic-snapshot writes, the `cv2.imwrite` crop site, and the
  `doc.to_json_file` JSON sidecar all use the same temp+rename. JSON
  and crops use inline temp+rename rather than the helper because
  they delegate the actual byte-write to upstream code (pd-book-tools
  `Document.to_json_file` and OpenCV `cv2.imwrite`); both wrap that
  call in a try with a defensive `unlink()` on failure. The crop
  site additionally checks `cv2.imwrite`'s bool return and emits a
  warning + cleans the tmp on `False` rather than silently advancing.
  Regression tests in `tests/test_pipeline_helpers.py`
  (`test_atomic_write_text_*`, `test_atomic_write_bytes_*`) cover
  the helper invariants directly: prior file untouched on failure,
  no canonical-path partial when there was no prior file, no leftover
  sibling tmp. Tests in `tests/test_main_mocked.py`
  (`test_main_save_json_failure_cleans_up_tmp_and_increments_errors`,
  `test_main_save_json_failure_with_no_tmp_swallows_unlink_error`,
  `test_main_extract_illustrations_imwrite_failure_skips_and_cleans_tmp`,
  `test_main_extract_illustrations_imwrite_returns_false_no_tmp_swallows_unlink`)
  cover the wired-up call sites end-to-end. Existing
  `test_main_extract_illustrations_writes_crops` updated: the mock
  imwrite now actually creates the file at the path it's handed (so
  the subsequent `os.replace` succeeds) and the assertion verifies
  the canonical `i_page_01.jpg` lands in the output dir after the
  rename, with imwrite invoked against the sibling
  `.i_page_01.tmp.jpg` path.
- **B20** — `KeyboardInterrupt` mid-batch no longer escapes the
  per-image `try/except Exception` (KeyboardInterrupt inherits from
  `BaseException`, not `Exception`). A dedicated
  `except KeyboardInterrupt` branch in the per-image loop now (1)
  closes the unterminated `Processing X ...` stdout line, (2) sets
  an `interrupted` flag and `break`s out of the loop, after which
  the existing post-loop block joins the update-notice thread, prints
  `Interrupted after {processed}/{len(images)} image(s); {errors}
  error(s) so far.` to stderr, and `sys.exit(130)` (SIGINT
  convention). The `finally: clear_layout_debug_env()` still fires
  on the in-flight image. Regression test
  `test_main_keyboard_interrupt_mid_batch_emits_summary_and_exits_130`
  added in `tests/test_main_mocked.py`: 3-image batch with the
  factory raising `KeyboardInterrupt` on the 2nd call, asserts
  `SystemExit(130)`, the 3rd image is never visited, the recorded
  update thread is joined, the partial-progress summary names
  `1/3 image(s)` on stderr, and neither `Done.` nor `Done (N
  error(s)).` appear on stdout.
- **B16** — `--save-reorganize-diagnostics` without `--save-json`
  now emits a stderr warning at the top-of-`main` arg-validation
  block, matching the B3/B11/B15 silent-no-op pattern. The export
  was gated on `args.save_json and args.save_reorganize_diagnostics`
  in the per-image loop, so passing only `--save-reorganize-diagnostics`
  (or its legacy alias `--save-pre-reorg-json`) silently produced no
  diagnostic files. Regression test
  `test_main_save_reorganize_diagnostics_without_save_json_warns`
  added in `tests/test_main_mocked.py`.
- **B15** — `--experimental-drop-layout-words` / `--edl` combined
  with `--no-reorg` now emits a stderr warning at the top-of-`main`
  arg-validation block, matching the B3/B9/B11 silent-no-op pattern.
  The flag is only ever consumed inside `if do_reorg:`, so combining
  with `--no-reorg` was a quiet no-op. Regression test
  `test_main_no_reorg_with_experimental_drop_layout_words_warns`
  added in `tests/test_main_mocked.py`.
- **B14** — `dest_dir.mkdir(parents=True, exist_ok=True)` at
  `ocr_to_txt.py:531` is now called *inside* the per-image `try` in
  `ocr_to_txt.py:main()`, so a filesystem failure (e.g. `-o` points at
  a regular file, or a mirror path collides with an existing file) is
  recorded as one per-image error and the loop continues to the next
  image instead of aborting `main()` outright with `FileExistsError`.
  `out_path`/`json_path` and `setup_layout_debug_env` were also moved
  inside the try; the existing `finally: clear_layout_debug_env()` and
  `except` block (which only references `img_path`) remain correct
  since `debug_file` is still initialised to `None` before the try.
  Regression test
  `test_main_dest_dir_mkdir_failure_recorded_per_image_not_batch_abort`
  added in `tests/test_main_mocked.py`: passes a regular file as `-o`
  across a 2-image batch and asserts both images are visited and
  tallied as `2 error(s)`.
- **B13** — `page is None` branch in `ocr_to_txt.py:main()` now (1)
  prints the closing newline so the `Processing X ...` line is
  terminated before subsequent stdout, (2) names the image in the
  warning (`WARNING: no pages in result for {img_path}`), and (3)
  increments the per-image `errors` counter so an all-empty batch
  exits 1 rather than misleading shell scripts that branch on `$?`.
  Regression test
  `test_main_doc_with_no_pages_warns_increments_errors_and_exits_1`
  in `tests/test_main_mocked.py` runs a 2-image batch with an empty-
  pages factory and asserts exit code 1, both image paths in the
  stderr warnings, `Done (2 error(s))` on stdout, and that each
  `Processing` line starts at column zero. Replaces the old
  `test_main_doc_with_no_pages_warns_and_continues` which codified
  the buggy "exit 0 + no img_path" behavior.
- **B12** — `collect_images` now dedupes by resolved absolute path
  (first-seen order preserved), so passing a file directly and via a
  parent directory (or repeating a path / overlapping `-r` trees) no
  longer double-OCRs the image. Regression tests
  `test_collect_dedupes_file_also_inside_passed_directory`,
  `test_collect_dedupes_same_file_passed_twice`, and
  `test_collect_dedupes_overlapping_directories` added in
  `tests/test_collect_images.py`.
- **B11** — `--layout-debug-dir DIR` without `--layout-debug` now
  emits a stderr warning at the top-of-`main` arg-validation block,
  matching the B3 silent-no-op pattern. Regression test
  `test_main_layout_debug_dir_without_layout_debug_warns` added in
  `tests/test_main_mocked.py`.
- **B10** — `check_for_update` now fires the upgrade notice for
  pre-release users whose release prefix matches the latest stable
  (e.g. `VERSION="1.2.3.dev1+gHASH"` with latest tag `v1.2.3`). A
  version is treated as pre-release when `_parse_stable_tag(VERSION)`
  returns None; for those the comparison becomes `latest >= current`
  rather than strict `>`. PEP 440 says `1.2.3.dev1 < 1.2.3`, so the
  stable IS strictly newer and the notice must fire. Regression test
  `test_notice_when_dev_prefix_equals_latest_stable` added in
  `tests/test_update_check_network.py`.
- **B9** — `--no-reorg --layout-debug` is now treated as a silent
  no-op identical to the B3 cases: a stderr warning is emitted at
  arg-validation time, and the success-line `layout-debug: <path>`
  segment is suppressed by gating on `do_reorg` so the CLI never
  advertises a file `reorganize_page()` was never going to write.
  Regression test
  `test_main_no_reorg_with_layout_debug_warns_and_suppresses_success_path`
  added in `tests/test_main_mocked.py`: asserts both the stderr warn
  and the absence of `layout-debug:` on stdout.
- **B8** — `setup_layout_debug_env(args, dest_dir, img_stem)` is now
  called *inside* the per-image `try` in `ocr_to_txt.py:main()`, so an
  unwritable `--layout-debug-dir` (e.g. path that already exists as a
  regular file, raising `FileExistsError` from `mkdir`) is recorded as
  one per-image error and the loop continues to the next image instead
  of aborting `main()` outright. `debug_file` is initialised to `None`
  before the try so the existing `finally: clear_layout_debug_env()`
  and the success-line `extra_paths.append(...)` gate stay correct.
  Regression test
  `test_main_layout_debug_setup_failure_recorded_per_image_not_batch_abort`
  added in `tests/test_main_mocked.py`: passes a regular file as
  `--layout-debug-dir` across a 2-image batch and asserts both images
  are visited and tallied as `2 error(s)`.
- **B7** — `diagnostic_output_paths` now builds names with
  `path.with_name(f"{path.stem}.pure-ocr.json")` instead of
  double-`with_suffix`, preserving multi-dot stems
  (e.g. `page.001.txt` → `page.001.pure-ocr.txt`); regression test
  `test_diagnostic_output_paths_preserves_multi_dot_stem` added in
  `tests/test_pipeline_helpers.py`.
- **B6** — `check_for_update` now sends an explicit
  `User-Agent: pd-ocr-cli/{VERSION}` header on the GitHub tags request;
  test `test_tags_request_sets_explicit_user_agent` added in
  `tests/test_update_check_network.py`.
- **B1** — `format_noise_drop_warning` `(+N more)` miscount fixed; tests added
  in `tests/test_pipeline_helpers.py` (`..._no_phantom_more_when_blanks_within_sample`,
  `..._more_count_reflects_unseen_words`).
- **B2** — `_load_validate_word_preservation()` hoisted out of the per-image
  loop; test added in `tests/test_main_mocked.py`
  (`test_main_validate_reorg_loader_called_once_across_images`).
- **B3** — Silent-no-op stderr warnings added for the three flag combos
  (`--no-reorg --save-reorganize-diagnostics`, `--no-reorg --validate-reorg`,
  `--layout-model none --layout-debug`); tests added in
  `tests/test_main_mocked.py` (`test_main_no_reorg_with_save_diag_warns`,
  `test_main_no_reorg_with_validate_reorg_warns`,
  `test_main_layout_none_with_layout_debug_warns`).
- **B4** — `write_diagnostic_snapshots` no longer accepts the unused
  `json_path` / `txt_path` parameters; caller in `ocr_to_txt.py` updated
  and signature-guard test added in `tests/test_pipeline_helpers.py`
  (`test_write_diagnostic_snapshots_signature_has_no_unused_path_params`).
- **B5** — GitHub tags API URL now appends `?per_page=100` so the latest
  stable tag cannot silently fall off page 1 once the project crosses 30
  tags; test `test_tags_request_uses_per_page_100` added in
  `tests/test_update_check_network.py`.

---

## Module Inventory

| File | Purpose |
|------|---------|
| `pd_ocr_cli/__init__.py` | Empty package marker |
| `pd_ocr_cli/ocr_to_txt.py` | CLI entry point — argument parsing, model loading, per-image loop |
| `pd_ocr_cli/_pipeline.py` | Pure-function helpers — path resolution, warning formatters, diagnostic writers, env-var layout-debug scaffolding |
| `pd_ocr_cli/_text_normalize.py` | Curly-quote and em-dash normalization |
| `pd_ocr_cli/_hf_models.py` | Argparse adapters around `pd_book_tools.hf` model resolution |
| `pd_ocr_cli/_update_check.py` | Background GitHub tag update-notice check |

---

## Bugs

### B1 [MAJOR] `format_noise_drop_warning` miscounts `(+N more)` suffix — DONE

**File:** `pd_ocr_cli/_pipeline.py:219`

```python
extra = f" (+{count - len(samples)} more)" if count > len(samples) else ""
```

`samples` is sliced to `sample_size` entries first, then filtered to remove
blank-text tokens. When blank tokens appear among the first `sample_size` words
and `count <= sample_size`, the blank-filter shrinks `len(samples)` below
`sample_size`, making `count > len(samples)` true even though all words were
already shown.

**Example:** 2 words (`["", "real"]`), `sample_size=8` → `len(samples)=1`
after blank-filtering → warning reads `"real" (+1 more)` implying an unseen
word that does not exist.

**Fix:**
```python
extra = f" (+{count - min(count, sample_size)} more)" if count > sample_size else ""
```

No existing test catches this; `test_pipeline_helpers.py:381` does not assert
on the `+N more` suffix.

---

### B2 [MAJOR] `_load_validate_word_preservation()` called inside the per-image loop

**File:** `pd_ocr_cli/ocr_to_txt.py:540`

All other `_load_*` helpers (`_load_predictor`, `_load_layout_detector`,
`_load_document_factory`, `_load_illustration_deps`) are called once before the
image loop (`ocr_to_txt.py:441`, `455`, `466`, `468`). This one is called once
per image whenever `--validate-reorg` is active. Python's import cache makes it
cheap but it breaks the `_load_*` pattern's monkeypatch contract: a test that
wants to monkeypatch this function after the first image cannot do so.

**Fix:** Move the call to before the loop alongside the other `_load_*` calls.

---

### B3 [MINOR] Silent no-ops — flags that interact but produce no warning — DONE

**File:** `pd_ocr_cli/ocr_to_txt.py:508–512`

Three flag combinations silently do nothing with no user-visible warning:

1. `--no-reorg --save-reorganize-diagnostics` → `want_diagnostic_export = False`
   at line 508–510; diagnostics never written, no warning emitted.
2. `--no-reorg --validate-reorg` → `if do_reorg and args.validate_reorg:` at
   line 512 short-circuits; validation silently skipped, no warning.
3. `--layout-model none --layout-debug` → `setup_layout_debug_env()` runs
   unconditionally (line 485); the debug file path is announced to stdout
   (lines 572–573) but no layout model ran so the file is never written.

**Fix:** Emit a `print(f"warning: ...", file=sys.stderr)` for each case, or
add them to the `validate_extract_illustrations`-style gate.

---

### B4 [MINOR] `write_diagnostic_snapshots` accepts but ignores `json_path`/`txt_path`

**File:** `pd_ocr_cli/_pipeline.py:289`

```python
_ = (json_path, txt_path)  # accepted so callers keep snapshot pairs grouped
```

These positional parameters are silently discarded. A caller who passes the
wrong paths gets no error. Either remove the parameters and update callers, or
document them as intentionally unused with a comment that makes the invariant
explicit.

---

### B5 [MINOR] GitHub tags API fetches only 30 items (no pagination)

**File:** `pd_ocr_cli/_update_check.py:63`

```python
url = "https://api.github.com/repos/.../tags"
```

GitHub defaults to `per_page=30`. Once the project accumulates >30 tags the
latest stable release may not appear in the first page and the update check
will silently miss it.

**Fix:** Append `?per_page=100` to the URL.

---

### B6 [MINOR] `check_for_update` sends no `User-Agent` header

**File:** `pd_ocr_cli/_update_check.py:63`

`urllib.request` adds `Python-urllib/3.x` by default, which GitHub may
rate-limit. Setting an explicit `User-Agent: pd-ocr-cli/{VERSION}` is better
practice.

---

## Structural Issues

### S1 [MINOR] `main()` is 200 lines — extract illustration-crop block

**File:** `pd_ocr_cli/ocr_to_txt.py:575–594`

The illustration-crop block inside the per-image loop is 20 lines of logic
orthogonal to the rest of the loop body. Extract to:

```python
def _process_illustration_crops(
    page_layout, cv2, crop_types, args, dest_dir, img_path, img_stem
) -> None: ...
```

---

### S2 [MINOR] `validate_extract_illustrations` calls `sys.exit` in a pure-function module

**File:** `pd_ocr_cli/_pipeline.py` (first ~10 lines of the function)

`_pipeline.py` is documented as housing pure helpers, but this function calls
`sys.exit(1)` on validation failure. It is more logically a CLI gate and should
live in `main()` or a dedicated argument-validation block at the top of
`ocr_to_txt.py`.

---

### S3 [MINOR] `_load_layout_detector` and `setup_layout_debug_env` take full `args` namespace

**Files:** `pd_ocr_cli/ocr_to_txt.py:132`, `pd_ocr_cli/_pipeline.py` (`setup_layout_debug_env`)

Both functions use only 2–3 fields from `args` but accept the full namespace.
This couples them to argparse structure and makes independent unit tests require
constructing a full `Namespace`. Pass the scalar values directly.

---

### S4 [MINOR] `det_source_descriptor` / `reco_source_descriptor` are nearly identical

**File:** `pd_ocr_cli/_hf_models.py:89–100`

Both functions differ only in which arg attributes and path variables they
reference. A single generic helper parameterised by model type would remove the
duplication.

---

### S5 [MINOR] `parse_args()` is 209 lines — inconsistent argument grouping

**File:** `pd_ocr_cli/ocr_to_txt.py:181–389`

The model-source flags use `add_argument_group` but all other flags go to the
top-level parser. Consistent use of groups would aid readability. Not a bug but
the inconsistency makes the flag taxonomy hard to scan.

---

## Test Isolation Risk

### T1 [MINOR] `os.environ` leak if assertion fails between setup/clear

**File:** `tests/test_pipeline_helpers.py:228–241`, `250–254`

Tests call `setup_layout_debug_env()` then assert, then `clear_layout_debug_env()`.
If the assertion fails the env vars (`PD_OCR_LAYOUT_DEBUG`,
`PD_OCR_LAYOUT_DEBUG_FILE`) leak into subsequent tests. Wrap with
`try/finally` or replace with `monkeypatch.setenv` so pytest guarantees
cleanup.

---

## Test Coverage Gaps

### TC1 `format_noise_drop_warning` `(+N more)` miscounting (see B1)
**File:** `tests/test_pipeline_helpers.py:381` — does not assert on the suffix string.

### TC2 Silent no-ops (see B3)
`--no-reorg --save-reorganize-diagnostics` and `--no-reorg --validate-reorg`
main-loop behavior is not tested in the fast suite.

### TC3 Multi-image runs with partial failure
Single-image error path is covered; a run where image N fails and N+1 succeeds
is not.

### TC4 GitHub pagination edge case (see B5)
No test for the case where the newest tag is on page 2+ of the tags API.

---

## Documentation Inconsistencies

### D1 [MINOR] `DEVELOPMENT.md` file tree is stale

`DEVELOPMENT.md:117` lists `_hf_download.py` as a module — this file does not
exist. `_pipeline.py` is absent from the table entirely.

---

### D2 [MINOR] Makefile help-text says `COV_FAIL_UNDER` defaults to 50

**File:** `Makefile:94`, `Makefile:99`, `Makefile:108`, `Makefile:116`

Help-text comments say the default is 50 (or 70 in two places). Actual default
is `COV_FAIL_UNDER ?= 100` at Makefile line 6, matching `pyproject.toml:78`.

---

### D3 [MINOR] Agent CLAUDE.md references non-existent make targets and wrong default

`.claude/agents/pd-ocr-cli.md:48–49` cites `make test-k K='pattern'` and
`make test-single TEST='tests/...::test_name'` — neither target exists in the
Makefile. The same file states `COV_FAIL_UNDER` defaults to 50; actual default
is 100.

---

## Candidate Upstream Migration

### U1 `_text_normalize.py` → `pd-book-tools`

`normalize_curly_quotes` and `normalize_em_dash` are generic post-OCR text
utilities with no CLI-specific logic. If `pd-ocr-labeler` or `pd-prep-for-pgdp`
ever need the same normalization this code will be duplicated. Consider moving
it into `pd_book_tools.text` and having the CLI import from there.

---

## Per-Module Method Inventory

### `ocr_to_txt.py`

| Function | Signature | Purpose | Side effects |
|----------|-----------|---------|--------------|
| `_detect_torch_device` | `() -> str` | Returns `"cuda"`, `"mps"`, or `"cpu"` | torch import |
| `_load_predictor` | `(det_path, reco_path)` | Returns DocTR predictor | triggers DL import chain |
| `_load_layout_detector` | `(args, device)` | Returns layout detector or `None` | silences transformers stderr |
| `_load_document_factory` | `()` | Returns `Document.from_image_ocr_via_doctr` callable | import only |
| `_load_validate_word_preservation` | `()` | Returns `validate_word_preservation` function | import only |
| `_load_illustration_deps` | `() -> tuple[cv2, set]` | Returns cv2 module + crop type set | import only |
| `_start_update_check_thread` | `(disabled: bool) -> Thread \| None` | Spawns daemon update-check thread | spawns thread |
| `_env_truthy` | `(name: str) -> bool` | Reads env var, tests for 1/true/yes/on | none |
| `parse_args` | `() -> argparse.Namespace` | Builds and parses CLI args | calls `sys.exit` on bad input |
| `collect_images` | `(inputs: list[str], recursive: bool) -> list[Path]` | Expands file/dir args to sorted image path list | writes warnings to stderr |
| `main` | `()` | Full orchestration: parse → load models → per-image loop → cleanup | everything |

### `_pipeline.py`

| Function | Signature | Purpose | Side effects |
|----------|-----------|---------|--------------|
| `validate_extract_illustrations` | `(args) -> None` | Exits 1 if `--extract-illustrations` + `--layout-model none` | `sys.exit` |
| `compute_mirror_root` | `(inputs, output_dir) -> Path \| None` | Common prefix dir for input directories | none |
| `resolve_dest_dir` | `(img_path, output_dir, mirror_root) -> Path` | Per-image output directory | none |
| `output_paths_for` | `(img_path, dest_dir) -> (Path, Path)` | Returns `(txt_path, json_path)` | none |
| `illustration_crop_path` | `(dest_dir, stem, idx) -> Path` | Returns `i_{stem}_{idx:02d}.jpg` path | none |
| `apply_text_normalizations` | `(text, *, straight_quotes, em_dash_to_double_hyphen) -> str` | Applies quote/dash normalizations | none |
| `setup_layout_debug_env` | `(args, dest_dir, img_stem) -> Path \| None` | Sets debug env vars, creates dir | mutates `os.environ` |
| `clear_layout_debug_env` | `() -> None` | Removes debug env vars | mutates `os.environ` |
| `format_drops_warning` | `(drops, source_name, *, max_lines) -> list[str]` | Formats validate-reorg drop warning | none |
| `_word_text` | `(word) -> str` | Best-effort text extraction from Word or test fake | none |
| `format_noise_drop_warning` | `(dropped_words, source_name, diagnostic_flag_name, *, sample_size) -> list[str]` | Formats always-on noise-drop warning | none |
| `write_diagnostic_snapshots` | `(page, json_path, txt_path, *, pure_ocr_json, pure_ocr_txt, post_noise_json, post_noise_txt) -> tuple[list[Path], list[str]]` | Writes 4 diagnostic snapshot files | file I/O |
| `diagnostic_output_paths` | `(json_path, txt_path) -> dict[str, Path]` | Computes 4 sibling diagnostic paths | none |
| `iter_crop_regions` | `(regions, confidence_threshold, crop_types) -> Iterator[(int, region)]` | Filters regions by type + confidence, yields 1-based pairs | none |

### `_text_normalize.py`

| Function | Signature | Purpose | Side effects |
|----------|-----------|---------|--------------|
| `normalize_curly_quotes` | `(text: str) -> str` | Replaces 8 curly-quote variants with ASCII equivalents | none |
| `normalize_em_dash` | `(text: str) -> str` | Replaces U+2014 em dash with `--` | none |

### `_hf_models.py`

| Function | Signature | Purpose | Side effects |
|----------|-----------|---------|--------------|
| `resolve_ocr_models` | `(args) -> tuple[Path, Path]` | Validates det/reco pair, delegates to library, exits on `FileNotFoundError` | `sys.exit` |
| `det_source_descriptor` | `(args, det_path: Path) -> str` | Human-readable detection model source string | none |
| `reco_source_descriptor` | `(args, reco_path: Path) -> str` | Human-readable recognition model source string | none |
| `resolve_layout_source` | `(args) -> tuple[str \| None, str \| None, str]` | Delegates to `_resolve_layout_source_kwargs` | none |

### `_update_check.py`

| Function | Signature | Purpose | Side effects |
|----------|-----------|---------|--------------|
| `_parse_stable_tag` | `(version: str) -> tuple[int,int,int] \| None` | Strict semver parser (rejects pre-release) | none |
| `_parse_release_prefix` | `(version: str) -> tuple[int,int,int] \| None` | Lenient semver prefix parser (tolerates dev suffixes) | none |
| `_latest_stable_tag` | `(tags: list[dict]) -> tuple[str, tuple] \| None` | Finds highest stable tag from GitHub response | none |
| `check_for_update` | `() -> None` | HTTP GET to GitHub tags API; prints upgrade notice to stderr | network I/O, stderr |

---

## Round 2 bugs

Fresh deep pass after B1..B6 shipped. Each finding is a real defect
(correctness / silent failure / misreporting) — not style or refactor.

### B7 [MAJOR] `diagnostic_output_paths` collapses multi-dot stems, causing collisions

**File:** `pd_ocr_cli/_pipeline.py:297-304`

```python
stem_json = json_path.with_suffix("")  # strip .json
stem_txt = txt_path.with_suffix("")    # strip .txt
return {
    "pure_ocr_json": stem_json.with_suffix(".pure-ocr.json"),
    ...
}
```

`Path.with_suffix(".pure-ocr.json")` replaces the **last** suffix, not
appends. For an image named `page.001.png`:

- `out_path` = `dest/page.001.txt` (correct — `with_suffix(".txt")` only
  replaced `.png`).
- `txt_path.with_suffix("")` → `Path("dest/page.001")`.
- `Path("dest/page.001").with_suffix(".pure-ocr.txt")` strips `.001` and
  yields `dest/page.pure-ocr.txt`.

**Verified:**
```
>>> Path('dest/page.001.txt').with_suffix('').with_suffix('.pure-ocr.txt')
PosixPath('dest/page.pure-ocr.txt')
```

So `page.001.png`, `page.002.png`, `page.003.png` all write the same
four diagnostic files (`dest/page.pure-ocr.{json,txt}`,
`dest/page.post-noise.{json,txt}`) — each later page silently overwrites
the previous one. Multi-dot stems are common for scanned books
(`book.001.png`, `vol2.ch3.png`, `0001.bin.png`).

**Suggested fix:**
```python
def diagnostic_output_paths(json_path: Path, txt_path: Path) -> dict[str, Path]:
    return {
        "pure_ocr_json": json_path.with_name(f"{json_path.stem}.pure-ocr.json"),
        "pure_ocr_txt":  txt_path.with_name(f"{txt_path.stem}.pure-ocr.txt"),
        "post_noise_json": json_path.with_name(f"{json_path.stem}.post-noise.json"),
        "post_noise_txt":  txt_path.with_name(f"{txt_path.stem}.post-noise.txt"),
    }
```

`Path.stem` strips only the last suffix — `Path("page.001.txt").stem`
is `"page.001"`, which is what we want. Add a regression test using a
stem with embedded dots.

---

### B8 [MAJOR] `setup_layout_debug_env` runs outside the per-image `try` — one bad page kills the whole batch

**File:** `pd_ocr_cli/ocr_to_txt.py:507-510`

```python
print(f"Processing {img_path} ...", end=" ", flush=True)
debug_file = setup_layout_debug_env(args, dest_dir, img_path.stem)

try:
    doc = document_factory(...)
```

`setup_layout_debug_env` calls `Path.mkdir(parents=True, exist_ok=True)`
on a user-supplied `--layout-debug-dir`. If that dir is unwritable
(read-only mount, permission denied, name collides with an existing
file), `mkdir` raises `OSError` / `FileExistsError`. Because the call
sits **outside** the per-image `try`, the exception aborts `main()`
entirely — every subsequent image in the batch is skipped, no `Done.`
summary, no `errors += 1`. A 500-page batch dies on page 1 with the
filesystem error and 499 pages remain unprocessed even though they
might have succeeded with the debug-dir issue resolved.

The same risk applies if a future change to `setup_layout_debug_env`
raises (e.g. validating `args.layout_debug_dir` shape).

**Suggested fix:** move the call inside the `try`, or wrap it in its
own try/except that records the failure as a per-image error and
continues with `debug_file = None`:

```python
try:
    debug_file = setup_layout_debug_env(args, dest_dir, img_path.stem)
    doc = document_factory(...)
    ...
```

The `finally: clear_layout_debug_env()` on line 628 already covers the
cleanup path, so moving the setup inside the try is a minimal change.

---

### B9 [MINOR] `--no-reorg --layout-debug` falsely reports a layout-debug file that is never written

**File:** `pd_ocr_cli/ocr_to_txt.py:592-593`

```python
if args.layout_debug and debug_file is not None:
    extra_paths.append(f"layout-debug: {debug_file}")
```

The layout-debug report is written by
`pd_book_tools.ocr.reorganize_page_utils.write_layout_debug_report`,
which is invoked from inside `Page.reorganize_page()`. With
`--no-reorg`, `reorganize_page()` is never called (line 538:
`if do_reorg:`), so no debug file is created — yet the CLI still
appends `layout-debug: {debug_file}` to `extra_paths` and prints it on
the success line. The user is told an artifact exists at a path that
contains nothing.

This is a sibling of the three silent-no-op cases B3 covered. B3
warned for `--layout-debug` + `--layout-model none`; the
`--layout-debug` + `--no-reorg` combination has the same outcome and
needs the same warning, plus the spurious success-line entry should
be suppressed.

**Suggested fix:** add a fourth warning at the top of `main()`:

```python
if args.no_reorg and args.layout_debug:
    print("warning: --layout-debug has no effect with --no-reorg ...",
          file=sys.stderr)
```

and gate the `extra_paths.append(...)` on `do_reorg` as well, or check
`debug_file.exists()` before reporting.

---

### B10 [MINOR] Dev/pre-release users never receive the upgrade notice for the matching stable — DONE

**File:** `pd_ocr_cli/_update_check.py:85-90`

```python
current = _parse_release_prefix(VERSION)
...
if latest > current:
    print(...)
```

`_parse_release_prefix` strips dev/local suffixes:
`"1.2.3.dev1+abc"` parses to `(1, 2, 3)`. When the actual stable
`v1.2.3` is the latest tag, `latest = (1, 2, 3)` and
`current = (1, 2, 3)`, so `latest > current` is False and no notice is
printed. A user installed from a pre-release commit (which is what
`uv tool install git+...@main` typically yields when no tag is at
HEAD — hatch-vcs adds a `.devN+gHASH` suffix) is therefore *less*
likely to be told about the actual release than someone on an old
stable.

**Suggested fix:** treat any version whose raw `VERSION` differs from
its parsed prefix as pre-release, and notify when `latest >= current`
(not strictly greater) for those cases. Sketch:

```python
is_prerelease = _parse_stable_tag(VERSION) is None
if latest > current or (is_prerelease and latest >= current):
    print(...)
```

Add tests in `tests/test_update_check_parsers.py` covering
`VERSION="1.2.3.dev1+abc"` with latest tag `v1.2.3`.

---

### B11 [MINOR] `--layout-debug-dir DIR` without `--layout-debug` is silently ignored — DONE

**File:** `pd_ocr_cli/_pipeline.py:144-151`

```python
def setup_layout_debug_env(args, dest_dir, img_stem):
    if not args.layout_debug:
        return None
    debug_dir = Path(args.layout_debug_dir) if args.layout_debug_dir else dest_dir
    ...
```

A user who passes only `--layout-debug-dir /tmp/dbg` (forgetting the
boolean `--layout-debug` toggle) gets nothing — no warning, no
artifacts. This is the same family as the silent no-ops B3 already
caught for the three other flag combinations. Sibling defect; B3
just missed this combination.

**Suggested fix:** add to the warning block at `ocr_to_txt.py:418-437`:

```python
if args.layout_debug_dir and not args.layout_debug:
    print(
        "warning: --layout-debug-dir has no effect without --layout-debug; "
        "ignoring.",
        file=sys.stderr,
    )
```

---

### B12 [MINOR] `collect_images` does not deduplicate, double-processing files passed both directly and via a parent dir — DONE

**File:** `pd_ocr_cli/ocr_to_txt.py:392-409`

```python
def collect_images(inputs, recursive):
    images = []
    for inp in inputs:
        p = Path(inp)
        if p.is_file():
            ...
            images.append(p)
        elif p.is_dir():
            ...
            for child in sorted(p.glob(pattern)):
                ... images.append(child)
    return images
```

Calling `pd-ocr scans/ scans/page1.png` (or with overlapping `-r`
trees, e.g. `pd-ocr scans/ scans/sub/`) appends `scans/page1.png`
twice. The image is OCR'd twice and the second pass overwrites the
first (same `dest_dir`, same output paths) — wasted work, doubled
elapsed time, and `Done. (0 errors)` even though the user wouldn't
have asked to do it twice if they realised. Multi-image runs that
already take minutes per page make this measurable.

**Suggested fix:** deduplicate before returning:

```python
seen: set[Path] = set()
deduped: list[Path] = []
for img in images:
    resolved = img.resolve()
    if resolved in seen:
        continue
    seen.add(resolved)
    deduped.append(img)
return deduped
```

Add a regression test passing both a directory and a file inside it.

---

### B13 [MINOR] Empty-pages images are silently dropped without incrementing the error counter

**File:** `pd_ocr_cli/ocr_to_txt.py:512-515`

```python
page = doc.pages[0] if doc.pages else None
if page is None:
    print("WARNING: no pages in result", file=sys.stderr)
    continue
```

Three issues bundled:

1. The WARNING omits `img_path` — every other warning includes it
   (`f"WARNING: empty text result for {img_path}"`,
   `f"WARNING: could not re-read {img_path} ..."`). Bare
   `"WARNING: no pages in result"` is unattributable in a 500-image
   batch.
2. `errors` is **not** incremented, so the run exits 0 even when 100%
   of inputs produced no pages (e.g. a corrupt JPEG batch). The user's
   shell scripts that branch on `pd-ocr ...` exit code think the batch
   succeeded.
3. `Processing {img_path} ...` was printed with `end=" "` (no
   newline). `continue` skips the trailing `-> {out_path}` line, so
   the next iteration's `Processing` prints concatenate onto the same
   stdout line. Cosmetic fallout from issue 2.

**Suggested fix:**

```python
if page is None:
    print(f"WARNING: no pages in result for {img_path}", file=sys.stderr)
    print()  # close the "Processing X ..." line
    errors += 1
    continue
```

Add a multi-image test where the document factory returns an empty
`pages` list and assert exit code 1 plus the warning text.

---

## Round 3 bugs

Fresh deep pass after B7..B13 shipped. Re-scanned `_pipeline.py`,
`ocr_to_txt.py` body + warning block, `_update_check.py` parsing,
and `collect_images` flow. Each finding is a real defect — not style.

### B14 [MAJOR] `dest_dir.mkdir` runs outside the per-image `try` — one bad path kills the whole batch

**File:** `pd_ocr_cli/ocr_to_txt.py:530-531`

```python
for img_path in images:
    dest_dir = resolve_dest_dir(img_path, output_dir, mirror_root)
    dest_dir.mkdir(parents=True, exist_ok=True)

    out_path, json_path = output_paths_for(img_path, dest_dir)

    print(f"Processing {img_path} ...", end=" ", flush=True)
    debug_file = None

    try:
```

This is the same defect class as the (now-fixed) **B8**:
`mkdir(parents=True, exist_ok=True)` does NOT swallow every failure —
it only treats *existing directories* as success. If any of these
hold:

- `--output-dir DIR` was passed and `DIR` is a regular file →
  `FileExistsError`.
- A parent component of the resolved `dest_dir` is a regular file
  (e.g. `--output-dir scans/page1.png/out`) → `NotADirectoryError`.
- The destination is on a read-only mount → `PermissionError` /
  `OSError(EROFS)`.

…then the very first image's `mkdir` raises and aborts `main()` before
the per-image `try` is entered. A 500-page batch dies on page 1 with
the filesystem error and 499 pages remain unprocessed even though they
might have lived on a different filesystem (e.g. mirrored output where
the first input directory's destination is bad but later ones are
fine).

Verified locally:
```
>>> Path('/tmp/file_not_dir/subdir').mkdir(parents=True, exist_ok=True)
NotADirectoryError: [Errno 20] Not a directory: '/tmp/file_not_dir/subdir'
```

**Suggested fix:** move the `mkdir` inside the per-image `try` (and
above the `setup_layout_debug_env` call so the debug-dir variant gets
the same treatment via B8's existing handler). The `finally:
clear_layout_debug_env()` already covers cleanup. Sketch:

```python
print(f"Processing {img_path} ...", end=" ", flush=True)
debug_file = None
try:
    dest_dir.mkdir(parents=True, exist_ok=True)
    debug_file = setup_layout_debug_env(args, dest_dir, img_path.stem)
    ...
```

Add a regression test mirroring B8's
`test_main_layout_debug_setup_failure_recorded_per_image_not_batch_abort`
— pass `--output-dir <regular_file>` across a 2-image batch and
assert exit code 1 plus `Done (2 error(s))` (currently the test would
see the unhandled exception bubble out of `main()`).

---

### B15 [MINOR] `--experimental-drop-layout-words` / `--edl` is silently ignored under `--no-reorg`

**File:** `pd_ocr_cli/ocr_to_txt.py:578-586`

```python
if do_reorg:
    drop_layout_words = args.experimental_drop_layout_words
    if page_layout is not None:
        page.reorganize_page(layout=page_layout, drop_layout_words=drop_layout_words)
    else:
        page.reorganize_page(drop_layout_words=drop_layout_words)
```

`drop_layout_words` is consumed only inside the `if do_reorg:` branch,
so passing `--edl --no-reorg` (or `--experimental-drop-layout-words
--no-reorg`) silently does nothing — same family as the silent no-ops
B3/B9/B11 already cover. Users opting in to the experimental drop
behavior would have a strong reason to expect it to apply, and the
flag's `--edl` short alias makes the combination easy to type by
accident in shell history (`-edl --no-reorg`).

**Suggested fix:** add a fifth warning to the arg-validation block at
`ocr_to_txt.py:434-465`:

```python
if args.no_reorg and args.experimental_drop_layout_words:
    print(
        "warning: --experimental-drop-layout-words has no effect with --no-reorg "
        "(the drop only applies during reorganize_page); ignoring.",
        file=sys.stderr,
    )
```

Add a regression test alongside the existing B3 cluster in
`tests/test_main_mocked.py`.

---

### B16 [MINOR] `--save-reorganize-diagnostics` without `--save-json` is silently ignored

**File:** `pd_ocr_cli/ocr_to_txt.py:571-573`

```python
want_diagnostic_export = (
    do_reorg and args.save_json and args.save_reorganize_diagnostics
)
```

The diagnostic export is gated on `args.save_json`, but a user who
passes only `--save-reorganize-diagnostics` (or its legacy alias
`--save-pre-reorg-json`) gets nothing — no `.pure-ocr.{json,txt}`,
no `.post-noise.{json,txt}`, no warning. The argparse help text says
"When --save-json is set ..." but new users typically read flag names
and try the most direct invocation. This is the exact silent-no-op
pattern that B3/B11 set the precedent for warning about.

**Suggested fix:** add to the arg-validation block:

```python
if args.save_reorganize_diagnostics and not args.save_json:
    print(
        "warning: --save-reorganize-diagnostics has no effect without --save-json "
        "(diagnostic exports are siblings of the .json sidecar); ignoring.",
        file=sys.stderr,
    )
```

Regression test: pass `--save-reorganize-diagnostics` alone, assert
the warning is on stderr and that none of the four diagnostic files
are written.

---

## Priority Order for Opus Iteration

1. **B1** — Fix `format_noise_drop_warning` miscounting + add test
2. **B2** — Move `_load_validate_word_preservation()` call before the loop
3. **B3** — Emit warnings for all three silent no-op flag combinations
4. **B4** — Remove or document unused params in `write_diagnostic_snapshots`
5. **S1** — Extract illustration-crop block from `main()` into helper
6. **T1** — Wrap env-var tests with `try/finally` or `monkeypatch`
7. **B5/B6** — Update-check: add `?per_page=100`, set `User-Agent`
8. **S2** — Move `validate_extract_illustrations` to `ocr_to_txt.py`
9. **S3** — Unwrap full `args` namespace in `_load_layout_detector` + `setup_layout_debug_env`
10. **D1/D2/D3** — Fix stale documentation (DEVELOPMENT.md, Makefile help text, agent CLAUDE.md)
11. **U1** — Evaluate upstreaming `_text_normalize.py` to `pd-book-tools`

---

## Round 4 bugs

Fresh deep pass after B14..B16 shipped. Re-scanned end-of-batch
summary path, atomic-write semantics, signal handling, argparse type
coercion bounds, GitHub-response parsing edge cases, and Windows-
specific path crashes. Each finding is a real defect — not style.

### B17 [MINOR] Per-image exception leaves the `Processing X ...` line unterminated on stdout

**File:** `pd_ocr_cli/ocr_to_txt.py:543, 684-690`

```python
print(f"Processing {img_path} ...", end=" ", flush=True)
...
try:
    ...
    print(f"-> {out_path}{tag}")          # success branch closes the line
except Exception as e:
    print(f"ERROR processing {img_path}: {e}", file=sys.stderr)
    ...
    errors += 1
```

The `Processing X ...` header is printed with `end=" "`, so the
trailing newline is left to whichever success branch runs (`-> ...`
on stdout). The `page is None` branch was fixed in B13 with an
explicit `print()` to close the line. The bare `except Exception`
branch was missed: when a per-image try raises, the ERROR line goes
to **stderr**, leaving the stdout `Processing X ...` line still
open. The next iteration's `Processing Y ...` then concatenates
onto the same stdout line. In a 500-page batch with intermittent
errors, the `tee log.txt` output reads
``Processing a.png ... Processing b.png ... -> a.txt`` with the
`-> a.txt` belonging to a later page than its on-line predecessor —
making it impossible to attribute outputs to inputs by reading
stdout linearly.

Same family as the (fixed) B13 case; the `except` branch needs the
same single-character fix.

**Suggested fix:**

```python
except Exception as e:
    print()  # close the "Processing X ..." line on stdout
    print(f"ERROR processing {img_path}: {e}", file=sys.stderr)
    ...
```

Add a regression test: run a 2-image batch where the first image's
factory raises and the second succeeds; capture stdout and assert
that `Processing` appears exactly twice on separate lines.

---

### B18 [MAJOR] `out_path.write_text` is non-atomic — crash mid-write leaves a truncated `.txt` indistinguishable from a valid one — DONE

**File:** `pd_ocr_cli/ocr_to_txt.py:632`

```python
out_path.write_text(text, encoding="utf-8")
```

`Path.write_text` is `open(..., "w").write(text)` — it truncates
first, then writes. If the process is killed mid-write (SIGKILL,
OOM, `KeyboardInterrupt` between `open` and `write` completion, or
the disk fills with `ENOSPC` after `open` succeeded) the user is
left with an empty or partial `.txt` file at `out_path`. Worse,
because the per-image error path increments `errors` only when an
exception bubbles out of the try, a SIGKILL never increments
anything — the next batch run sees the truncated file and skips
nothing (we don't memoize completed pages), but any *external*
tooling that branches on file existence (e.g. `for f in *.png; do
[ -f ${f%.png}.txt ] || pd-ocr "$f"; done`) treats the corrupt file
as cached.

Same hazard applies to the `.json` sidecar via `doc.to_json_file`
and to the `i_<stem>_NN.jpg` crops via `cv2.imwrite` — none of the
file-write call sites use a temp+rename pattern.

**Suggested fix:** write to a sibling temp file, fsync, and
`os.replace` to the final path. `os.replace` is atomic on POSIX
and Windows for same-filesystem renames, so a crash either leaves
the *previous* `.txt` intact (re-run produces the new one) or the
new one. Sketch:

```python
def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
```

Apply at the three write sites (`out_path`, `json_path`, crop
paths). Add a regression test that monkey-patches `Path.write_text`
to raise mid-call and asserts `out_path` either does not exist or
contains the prior text — never an empty/partial result.

---

### B19 [MINOR] [DONE] `to_json_file` / diagnostic / crop failures after `out_path.write_text` succeeds leave an orphan `.txt`

**File:** `pd_ocr_cli/ocr_to_txt.py:632-677`

```python
out_path.write_text(text, encoding="utf-8")  # line 632 — succeeds

extra_paths: list[str] = []
if args.save_json:
    doc.to_json_file(json_path)              # line 636 — may raise
...
if want_diagnostic_export:
    written, notes = write_diagnostic_snapshots(...)  # line 640 — may raise
...
if args.extract_illustrations and ...:
    cv2.imwrite(str(crop_path), crop)        # line 676 — may raise
```

Once the `.txt` is on disk, any later failure inside the same
per-image try (json sidecar write, diagnostic bundle write, crop
write) is caught by the bare `except Exception`, prints `ERROR
processing <path>`, and increments `errors`. But the `.txt` is
*not* rolled back. The user sees `Done (1 error(s))`, looks at the
output directory, and finds a `.txt` for the failed page with no
`.json` sidecar despite `--save-json`. External pipelines that
key on `.txt` existence will silently consume the (post-reorganize,
ostensibly correct) text without realising the run was incomplete.

The simplest containment is to write the `.txt` *last* (after
`to_json_file`, the diagnostic snapshots, and the crop loop), so
the `.txt` only appears when every other artifact for that page
was already produced. The atomic-write change in B18 makes this
free since the `.txt` body is already in memory. Order becomes:
crops → diagnostics → json sidecar → `.txt` (last).

Alternative: on except, delete any partial outputs already written
for the failing page before re-raising. Less surgical and harder to
get right (which artifacts existed before this page started?).

---

### B20 [MAJOR] [DONE] `KeyboardInterrupt` mid-batch skips the progress summary and exit code

**File:** `pd_ocr_cli/ocr_to_txt.py:541-699`

```python
errors = 0
for img_path in images:
    ...
    try:
        ...
    except Exception as e:        # KeyboardInterrupt is BaseException, NOT caught
        ...
        errors += 1
    finally:
        clear_layout_debug_env()

if _update_thread is not None:
    _update_thread.join(timeout=3)
if errors:
    print(f"Done ({errors} error(s)).")
    sys.exit(1)
print("Done.")
```

`KeyboardInterrupt` and `SystemExit` inherit from `BaseException`,
**not** `Exception`. When a user hits Ctrl-C during a long batch —
common, since 500 pages at minutes per page is the documented
workload — the signal propagates through the `try`, runs the
`finally` (good — env vars cleaned up), then **escapes the
for-loop**. The end-of-batch summary block never runs:

- The user has no idea how many pages succeeded vs how many remain
  unprocessed (no `Done (N of M, K error(s))` line).
- The exit code is whatever Python's default SIGINT handling
  produces (typically 130 / -SIGINT), not the deterministic `0`/`1`
  the rest of the CLI surface promises.
- The pending update-notice thread is not joined, so a fast notice
  arriving microseconds before SIGINT is racing the process exit.
- The `Processing X ...` line for the in-flight page is left
  unterminated on stdout (B17 sibling).

**Suggested fix:** add a dedicated except branch that logs and
breaks out cleanly, letting the existing summary code emit a
partial-progress report:

```python
processed = 0
for img_path in images:
    ...
    try:
        ...
        processed += 1
    except KeyboardInterrupt:
        print()  # close "Processing X ..."
        print(
            f"\nInterrupted after {processed}/{len(images)} image(s); "
            f"{errors} error(s) so far.",
            file=sys.stderr,
        )
        clear_layout_debug_env()
        sys.exit(130)
    except Exception as e:
        ...
```

Or wrap the for-loop body in `try/except KeyboardInterrupt: break`
and let the existing summary pick up the partial counts. Either
way the layout-debug env cleanup must still fire, the in-flight
stdout line must close, and the exit code must signal partial
completion.

Add a regression test using `signal.raise_signal(SIGINT)` from a
side-effect monkeypatch on the document factory (or a custom
`KeyboardInterrupt`-raising factory) and assert the summary runs
plus exit is 130.

---

### B21 [MINOR] `--layout-confidence` accepts `nan`, `inf`, negative, and >1 — silently subverts the crop filter

**File:** `pd_ocr_cli/ocr_to_txt.py:348-354`, `pd_ocr_cli/_pipeline.py:319-338`

```python
p.add_argument(
    "--layout-confidence",
    type=float,
    default=0.5,
    metavar="THRESHOLD",
    help="Confidence threshold for layout detections (0..1). Default 0.5.",
)
```

`type=float` accepts `nan`, `inf`, `-inf`, negatives, and values
greater than 1 without complaint. The threshold is consumed in
`iter_crop_regions` as `region.confidence < confidence_threshold`
and inside the upstream layout backend. Two failure modes:

1. `--layout-confidence nan` — every comparison `x < nan` is False,
   so **every** region passes the filter regardless of its actual
   confidence. The crop filter is silently turned off.
2. `--layout-confidence inf` — every comparison fails, so **no**
   regions pass; `--extract-illustrations` produces zero crops with
   no warning.
3. `--layout-confidence -1` — every comparison passes, same as
   `nan` case.
4. `--layout-confidence 5` — no regions pass, same as `inf`.

The help text says "0..1" but argparse never enforces it. Users
who type a typo (`--layout-confidence 50` meaning 0.5) or who pipe
in an unvalidated config value silently get either zero crops or
all-of-them.

**Suggested fix:** custom converter that rejects nan/inf and clamps
the documented domain:

```python
def _confidence(s: str) -> float:
    v = float(s)  # raises ArgumentTypeError-equivalent on garbage
    if not math.isfinite(v) or not 0.0 <= v <= 1.0:
        raise argparse.ArgumentTypeError(
            f"--layout-confidence must be a finite number in [0, 1]; got {s!r}"
        )
    return v

p.add_argument("--layout-confidence", type=_confidence, default=0.5, ...)
```

Add tests covering each rejection case.

---

### B22 [MINOR] `_latest_stable_tag` raises on GitHub error-response bodies, swallowed silently

**File:** `pd_ocr_cli/_update_check.py:37-47, 78-82, 106-107`

```python
with urllib.request.urlopen(req, timeout=3) as resp:
    tags = json.loads(resp.read())
if not tags:
    return
latest_stable = _latest_stable_tag(tags)
...
```

When GitHub returns an error response (rate-limited, repo
temporarily unavailable, or auth required) the body is a **dict**
like `{"message": "API rate limit exceeded for ...",
"documentation_url": "..."}`, not a list of tags. `if not tags:`
short-circuits only when the dict is empty (`{}`), which it never
is — error responses always include `message`. So execution falls
through to `_latest_stable_tag(tags)`:

```python
for tag in tags:                 # iterates dict KEYS (strings)
    name = tag.get("name", "")   # AttributeError on str.get(default)
```

The `AttributeError` is swallowed by the bare `except Exception:
pass` in `check_for_update`, so the user never sees a notice and
never learns *why*. With B6's `User-Agent: pd-ocr-cli/{VERSION}`
shipped, anonymous rate limiting is the most common cause —
exactly the case where users would benefit from a clearer
diagnostic (or, at minimum, no silent swallow that masks future
bugs in this function).

**Suggested fix:** type-guard before parsing:

```python
with urllib.request.urlopen(req, timeout=3) as resp:
    payload = json.loads(resp.read())
if not isinstance(payload, list) or not payload:
    return
latest_stable = _latest_stable_tag(payload)
```

Add a regression test in `tests/test_update_check_network.py` with
a mocked `urlopen` returning the rate-limit error dict and assert
no exception (currently relies on the catch-all to mask it) and no
notice printed.

---

### B23 [MINOR] `compute_mirror_root` raises on cross-drive Windows inputs, aborting the whole batch

**File:** `pd_ocr_cli/_pipeline.py:54-66`, `pd_ocr_cli/ocr_to_txt.py:539`

```python
def compute_mirror_root(inputs, output_dir):
    if output_dir is None:
        return None
    input_dirs = [Path(i) for i in inputs if Path(i).is_dir()]
    if not input_dirs:
        return None
    return Path(os.path.commonpath([d.resolve() for d in input_dirs]))
```

`os.path.commonpath` raises `ValueError("Paths don't have the same
drive")` on Windows when the resolved input directories straddle
drive letters (e.g. `pd-ocr C:\scans D:\more_scans -o E:\out`).
The call sits at `ocr_to_txt.py:539`, **outside** the per-image
`try`, so the ValueError propagates out of `main()` as an
unhandled traceback before any image is processed. Linux users are
immune (single root); Windows users — who, given uv/pip support,
are a real install target — see a stack trace instead of a clean
diagnostic.

**Suggested fix:** catch `ValueError` and degrade to flat output:

```python
def compute_mirror_root(inputs, output_dir):
    if output_dir is None:
        return None
    input_dirs = [Path(i) for i in inputs if Path(i).is_dir()]
    if not input_dirs:
        return None
    try:
        return Path(os.path.commonpath([d.resolve() for d in input_dirs]))
    except ValueError:
        return None  # cross-drive on Windows — fall back to flat output
```

When the function returns `None`, `resolve_dest_dir` already
falls back to `output_dir` (flat) instead of mirroring. Add a
unit test that fakes the ValueError (e.g. monkeypatches
`os.path.commonpath`) and asserts the fall-through returns
`None`. Optional: emit a one-shot stderr warning so the user
knows the mirror layout was disabled.

---
