# Lint-rule Deviations — pd-ocr-cli

Standing suppressions and per-file rule overrides in this repo.
Each entry records: the rule, the tool, the file(s) affected, and
the justification. Update this file whenever a new suppression is added.

This catalogue covers both the project-wide `[tool.ruff.lint]` `ignore`
list / `per-file-ignores` and every inline `# noqa` / `# pyright: ignore`
comment in the source tree.

Reference implementation: `pd-book-tools/docs/conventions/lint-deviations.md`.

---

## Project-wide ruff `ignore`

These rules are disabled repo-wide in `pyproject.toml` → `[tool.ruff.lint]`
`ignore`. Each carries an inline rationale at the suppression point as well.

### 1. `E501` — line-too-long

Many long docstrings, error messages, and URLs. Enforcing 88/100-char
wrapping everywhere adds noise without improving readability. The ruff
formatter still wraps code; this only relaxes the lint check.

### 2. `D203` / `D212` — pydocstyle pair conflicts

`D203` (1-blank-before-class-docstring) conflicts with `D211`
(no-blank-before-class-docstring); `D212` (multi-line-summary-first-line)
conflicts with `D213` (multi-line-summary-second-line). One of each pair
must be disabled — this repo keeps `D211` + `D213`.

### 3. `D100` / `D104` / `D107` — missing docstrings

Missing docstrings on public modules / packages / `__init__` methods.
Tracked as an incremental backlog rather than a hard gate.

### 4. `D105` — missing docstring in magic method

Magic methods are self-documenting; add docstrings incrementally.

### 5. `D205` — 1-blank-line-between-summary-and-description

Too noisy for the docstring style used here.

### 6. `PLR0913` — too-many-arguments

CLI entry points and pipeline functions legitimately take many params
(model paths, device, layout flags, rotation options, etc.).

### 7. `PLR2004` — magic-value-comparison

Common in CLI argument defaults and threshold comparisons.

### 8. `PLR0911` / `PLR0912` / `PLR0915` — function complexity

`main()` orchestrates the full OCR pipeline and legitimately has high
branch / return / statement counts. Splitting it further would scatter
sequential pipeline logic without improving clarity.

### 9. `PLC0415` — import-not-at-top-level

Deferred imports are an intentional pattern: they break circular deps and
avoid loading optional-heavy modules (torch, cv2, cupy) until needed.
Several are also monkeypatch seams for tests.

### 10. `TRY003` — long-message-outside-exception-class

Too noisy for a CLI that uses f-string error messages everywhere.

### 11. `COM812` — missing-trailing-comma

Conflicts with the ruff formatter's auto-style; the formatter owns commas.

### 12. `ANN401` — dynamically-typed-expressions (`Any`)

Some helpers legitimately accept/return `Any` — monkeypatch seams and
word-object helpers that operate on heterogeneous pd-book-tools objects.

---

## Per-file ruff ignores

From `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml`.

### 13. `tests/**/*.py`

Ignored: `S101`, `S105`, `S106`, `S311`, `T201`, `ANN`, `D`, `PLR2004`,
`PT011`, `S108`, `PLR0133`, `PLW2901`, `PERF401`.

`assert` is the test idiom (`S101`); hardcoded passwords / random are test
fixtures (`S105`/`S106`/`S311`); `print()` is fine in tests (`T201`); tests
need no annotations or docstrings (`ANN`/`D`); magic numbers are common
(`PLR2004`); `pytest.raises(match=)` is not required on every test
(`PT011`); `/tmp` paths are fine (`S108`); trivial self-comparisons can be
intentional (`PLR0133`); loop-var reassignment is an accepted test pattern
(`PLW2901`); list-building loops in tests are fine (`PERF401`).

### 14. `scripts/*.py`

Ignored: `T201`, `D`, `S607`.

`print()` is the output mechanism for scripts; no docstrings required;
`S607` partial executable path is idiomatic when invoking system tools
(`uv`, `git`, etc.) that are always on `PATH`.

### 15. `**/__init__.py`

Ignored: `D104`, `F401`, `TC`.

Re-export modules with no docstrings; `F401` unused-import is the public
API-surface pattern; `TC` type-checking import moves do not apply.

### 16. `**/_*.py`

Ignored: `D`.

Private modules follow internal convention and need no docstrings.

---

## Inline `# noqa` suppressions

### 17. `T201` — print-found (ruff)

**Files:** `pd_ocr_cli/ocr_to_txt.py` (~45 occurrences), `_pipeline.py`,
`_hf_models.py`, `_update_check.py`.

**Suppression form:** `# noqa: T201  # CLI output` inline.

**Justification.** `pd-ocr-cli` is a user-facing CLI; `print()` to stdout
and `print(..., file=sys.stderr)` are the intended output mechanism.
`T201` is relaxed repo-wide for `tests/**` and `scripts/**`, but library
modules under `pd_ocr_cli/` keep the rule on and suppress per-call so any
*accidental* debug `print` still gets flagged in review.

### 18. `BLE001` — blind-except (ruff)

**Files:** `pd_ocr_cli/ocr_to_txt.py` (lines ~223, 253, 278, 874),
`_update_check.py` (line ~118).

**Suppression form:** `# noqa: BLE001` (sometimes `# noqa: BLE001 S110`)
inline, each with a trailing rationale.

**Justification.** Three distinct best-effort boundaries:

- The CuPy GPU probe and the GPU-install nudge helper must never crash
  `pd-ocr` — a broken native CuPy can even segfault, so the catch is
  intentionally `BaseException` and silent.
- The update-check is best-effort; any network/parse failure is safe to
  swallow.
- The per-image loop in `main()` catches all errors, reports them, and
  continues the batch rather than aborting on one bad scan.

### 19. `S110` — try-except-pass (ruff)

**Files:** `pd_ocr_cli/ocr_to_txt.py` (line ~278), `_update_check.py`
(line ~118). Always paired with `BLE001`.

**Justification.** Same best-effort boundaries as entry 18 — a silent
`pass` is the correct behaviour for the GPU nudge and the update check;
neither must ever surface an error to the user.

### 20. `S310` — suspicious-url-open (ruff)

**Files:** `pd_ocr_cli/_update_check.py` (lines ~74, 81).

**Suppression form:** `# noqa: S310` inline.

**Justification.** `urllib.request.Request` / `urlopen` are called only
with a hardcoded `https://` PyPI URL — there is no `file://` or
attacker-controlled scheme risk.

### 21. `S607` — start-process-with-partial-path (ruff)

**Files:** `pd_ocr_cli/ocr_to_txt.py` (line ~239).

**Suppression form:** `# noqa: S607` inline.

**Justification.** `nvidia-smi` is invoked by bare name; when an NVIDIA
driver is present the binary is always on `PATH`. Hardcoding an absolute
path would be wrong across distros. (`scripts/*.py` get this via
per-file-ignores; this one site is in a library module so it is suppressed
inline.)

### 22. `F401` — unused-import (ruff)

**Files:** `pd_ocr_cli/ocr_to_txt.py` (line ~219).

**Suppression form:** `# noqa: F401` inline.

**Justification.** `import cupy` here is an import-only probe — success of
the import is what is being tested, the name is never used. Paired with
`# pyright: ignore[reportMissingImports]` (see entry 24).

### 23. `ERA001` — commented-out-code (ruff)

**Files:** `tests/test_update_check_bypass.py` (line ~56),
`tests/test_pipeline_helpers.py` (line ~573).

**Suppression form:** `# noqa: ERA001` inline.

**Justification.** Both are intentional: one is a documented reference
copy of the bypass-condition expression kept alongside the test it
exercises; the other is a section-header comment, not dead code. (Tests
get `ERA001` via per-file-ignores in many repos, but it is not in this
repo's `tests/**` ignore list, so these are suppressed inline.)

---

## Inline `# pyright: ignore` suppressions

### 24. `reportMissingImports` — basedpyright

**Files:** `pd_ocr_cli/ocr_to_txt.py` (line ~219).

**Suppression form:** `# pyright: ignore[reportMissingImports]` inline on
the `import cupy` probe line.

**Justification.** `cupy` is an optional `[gpu]`-extra dependency, absent
on CPU-only installs. The import sits inside a guarded `try` whose only
purpose is to detect whether the GPU stack is active. basedpyright cannot
see the optional dependency, so the named suppression is required. It is
the only basedpyright suppression in the repo; `failOnWarnings` is
deferred (see the note in `pyproject.toml` `[tool.basedpyright]`).

---

## Notes

- No `# type: ignore[...]` (mypy-style) suppressions exist in this repo —
  basedpyright is the type checker and `# pyright: ignore[...]` with the
  tool-native rule code is the correct form.
- `failOnWarnings` is intentionally not yet enabled for basedpyright;
  `recommended` mode surfaces warnings from optional stubs (cupy, DocTR)
  that lag the runtime. Enable incrementally as stub coverage improves.
- Every inline suppression in the tree already carries a trailing
  rationale comment; this file is the consolidated catalogue.
