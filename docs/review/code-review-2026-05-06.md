# pd-ocr-cli Code Review — 2026-05-06

Full architectural review of all source modules. Each finding is tagged with
severity (`[CRITICAL]`, `[MAJOR]`, `[MINOR]`, `[NIT]`) and a file:line citation.
Intended for Opus iteration: work top-to-bottom, mark each item done as you go.

---

## Next item

**B11** — `--layout-debug-dir DIR` without `--layout-debug` is
silently ignored: same silent-no-op family as B3, just an additional
flag combination missed at the time. User passes a directory path,
no warning, no artifacts. Add a stderr warning at the top-of-`main`
arg-validation block.

### Done

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

### B11 [MINOR] `--layout-debug-dir DIR` without `--layout-debug` is silently ignored

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

### B12 [MINOR] `collect_images` does not deduplicate, double-processing files passed both directly and via a parent dir

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
