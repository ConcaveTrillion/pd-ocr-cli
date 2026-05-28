# Test-suite reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the `pdomain-ocr-cli` test suite so every test has a clear correct-state oracle, shared scaffolding is extracted once, the two oversized files are split, behavior gaps are closed in the fast suite, and `install.ps1` is exercised through real `pwsh` — all under the existing 100% branch-coverage gate.

**Architecture:** Phased refactor. Phases 0–2 preserve behavior (restructuring only — existing assertions keep passing). Phase 3 is TDD (new failing assertion first). Phase 4 extracts the PowerShell CUDA-detection helpers into a dot-sourceable lib and tests them through `pwsh`. Phase 5 reconciles coverage by testing, not exclusion. Each task ends with a local commit; `make ci` stays green between phases.

**Tech Stack:** pytest, pytest-xdist, pytest-cov (branch, `fail_under=100`), `unittest.mock`, PowerShell (`pwsh`) for the install-script tests.

**Definition of done (non-negotiable):** No `skip`/`skipif` added to dodge an environment gap. No `# pragma: no cover` over reachable behavior (pragma only for genuinely unexecutable lines, each with a one-line reason). All behavior gaps closed in this effort. `make ci` and `make test-slow` both green; coverage stays 100% by testing.

---

## File Structure

### New files

- `tests/_fakes.py` — importable fakes + namespace builders. One canonical `FakePage` (with a real `reorganize_page` side effect), `FakeSnapshot`, `FakeWord`, `FakeDoc`, `FakeArray`, `pipeline_args()`, `hf_args()`.
- `tests/test_main_happy.py` — happy-path `main()` tests (split from `test_main_mocked.py`).
- `tests/test_main_errors.py` — SystemExit / atomic-write / KeyboardInterrupt cluster.
- `tests/test_main_flag_wiring.py` — flag→output behavior tests (formerly call-args).
- `tests/test_main_warnings.py` — silent-no-op stderr warnings (parametrized).
- `tests/test_pipeline_paths.py` — path-mirroring + diagnostic-path helpers.
- `tests/test_pipeline_warnings.py` — drops/noise warning formatting.
- `tests/test_pipeline_atomic_write.py` — `atomic_write_*` invariants.
- `tests/test_install_ps1_cuda.py` — real-`pwsh` tests of the CUDA-detection lib (replaces `test_install_ps1_cuda_parse.py`).
- `scripts/install-cuda-detect.ps1` — extracted pure PowerShell helpers (`Get-CudaVersion`, `Get-CudaTag`, `Get-BookToolsExtras`).

### Modified files

- `tests/conftest.py` — add `mock_heavy_deps`, `run_main`, `single_image`, `make_images` fixtures.
- `tests/test_batch_pages.py`, `tests/test_collect_images.py`, `tests/test_gpu_nudge.py`, `tests/test_hf_models_argparse.py`, `tests/test_parse_args.py`, `tests/test_text_normalize.py`, `tests/test_torch_device.py`, `tests/test_update_check_*.py`, `tests/test_pipeline_integration.py` — migrate onto shared scaffolding where they currently duplicate it.
- `install.ps1` — dot-source `scripts/install-cuda-detect.ps1`; remove the inlined detection/tag/extras logic.
- `.devcontainer/Dockerfile` (workspace-shared — handle with care) — install `pwsh`.

### Deleted files

- `tests/test_install_ps1_cuda_parse.py` (replaced).
- `tests/test_main_mocked.py`, `tests/test_pipeline_helpers.py` (after their tests move to the split files).

---

## Phase 0 — Shared scaffolding foundation (behavior-preserving)

### Task 1: Create `tests/_fakes.py`

**Files:**

- Create: `tests/_fakes.py`

- [ ] **Step 1: Write the fakes module**

The canonical `FakePage.reorganize_page` is a `MagicMock` whose `side_effect` recomposes `self.text` from seed parts, so the same object serves *both* the call-recording tests (Phase 2/old wiring) and the new behavior tests (Phase 3). Seed parts model the no-silent-drops invariant: a "layout word" is never deleted — under `drop_layout_words=True` it is re-emitted with a role label.

```python
"""Importable test fakes shared across the pdomain-ocr-cli test suite.

The single source of truth for the ``main()`` fast-path fakes. ``FakePage``
exposes a ``reorganize_page`` MagicMock (so call-recording still works) whose
side effect deterministically recomposes ``self.text`` from the seeded parts.
That lets a test assert on the written ``.txt`` content, not just that a mock
was called.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


class FakeSnapshot:
    """Diagnostic Page snapshot stand-in — exposes ``text`` + ``to_dict``."""

    def __init__(self, text: str) -> None:
        self.text = text

    def to_dict(self) -> dict:
        return {"type": "Page", "text": self.text}


class FakeWord:
    def __init__(self, text: str) -> None:
        self.text = text


class FakePage:
    """Fake OCR page whose ``reorganize_page`` transforms ``text`` per flags.

    Seed parts:
      - ``body``: ordinary body text, always present.
      - ``layout_word``: a word the layout pass would route out of the body
        (e.g. a footnote). Never dropped silently: under
        ``drop_layout_words=True`` it is re-emitted as ``[layout: <word>]``.
      - ``illustration_caption``: caption text, always preserved.

    Output composition (after ``reorganize_page``):
      - base = ``body`` + (`` `` + layout_word if not dropped else
        ``\\n[layout: <layout_word>]``)
      - + ``\\n[Illustration]`` line when ``emit_illustration_placeholders``
      - + ``\\n`` + caption when a caption is set.

    With no seed parts beyond ``text`` the page behaves like the legacy
    fake: ``reorganize_page`` leaves ``text`` unchanged.
    """

    def __init__(
        self,
        text: str = "FAKE TEXT",
        words: list | None = None,
        *,
        body: str | None = None,
        layout_word: str | None = None,
        illustration_caption: str | None = None,
        pure_ocr_text: str | None = None,
        post_noise_text: str | None = None,
        dropped_word_texts: list[str] | None = None,
    ) -> None:
        self.text = text
        self.words = words or []
        self._body = body
        self._layout_word = layout_word
        self._caption = illustration_caption
        self.reorganize_page = MagicMock(side_effect=self._reorganize)
        self.diagnostic_pure_ocr = (
            FakeSnapshot(pure_ocr_text) if pure_ocr_text is not None else None
        )
        self.diagnostic_post_noise_removal = (
            FakeSnapshot(post_noise_text) if post_noise_text is not None else None
        )
        self.diagnostic_noise_dropped_words = [FakeWord(t) for t in (dropped_word_texts or [])]
        self.diagnostic_noise_dropped_count = len(self.diagnostic_noise_dropped_words)

    def _reorganize(self, *, drop_layout_words: bool = False,
                    emit_illustration_placeholders: bool = True, **_: object) -> None:
        if self._body is None:
            return  # legacy behavior: leave text untouched
        parts = [self._body]
        if self._layout_word is not None:
            parts.append(
                f"[layout: {self._layout_word}]" if drop_layout_words else self._layout_word
            )
        if emit_illustration_placeholders:
            parts.append("[Illustration]")
        if self._caption is not None:
            parts.append(self._caption)
        self.text = "\n".join(parts) if (drop_layout_words or emit_illustration_placeholders
                                         or self._caption) else " ".join(parts)


class FakeDoc:
    """Minimal Document stand-in wrapping one page."""

    def __init__(self, page: FakePage) -> None:
        self.pages = [page]
        self.json_writes: list[Path] = []

    def to_json_file(self, path) -> None:
        p = Path(path)
        p.write_text("{}", encoding="utf-8")
        self.json_writes.append(p)


class FakeArray:
    """cv2-style array fake supporting slicing (for crop-region tests)."""

    def __init__(self, shape: tuple[int, ...] = (100, 100, 3)) -> None:
        self.shape = shape

    def __getitem__(self, _key) -> "FakeArray":
        return self


def pipeline_args(**overrides) -> SimpleNamespace:
    """Argparse-shaped namespace with `_pipeline` defaults."""
    base = {
        "layout_model": "pp-doclayout-plus-l",
        "extract_illustrations": False,
        "layout_debug": False,
        "layout_debug_dir": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def hf_args(**overrides) -> SimpleNamespace:
    """Argparse-shaped namespace with `_hf_models` defaults."""
    from pdomain_ocr_cli._hf_models import (
        DEFAULT_DET_FILENAME,
        DEFAULT_HF_REPO,
        DEFAULT_RECO_FILENAME,
    )

    base = {
        "hf_repo": DEFAULT_HF_REPO,
        "model_version": None,
        "det_filename": DEFAULT_DET_FILENAME,
        "reco_filename": DEFAULT_RECO_FILENAME,
        "detection": None,
        "recognition": None,
        "layout_model": "pp-doclayout-plus-l",
        "layout_checkpoint": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)
```

- [ ] **Step 2: Verify it imports**

Run: `uv run python -c "import tests._fakes as f; print(f.FakePage().text)"`
Expected: prints `FAKE TEXT`, no error.

- [ ] **Step 3: Commit**

```bash
git add tests/_fakes.py
git commit -m "test: add shared fakes module (FakePage with behavior side effect)"
```

### Task 2: Add shared fixtures to `tests/conftest.py`

**Files:**

- Modify: `tests/conftest.py`

- [ ] **Step 1: Append the fixtures**

Add to `tests/conftest.py` (keep the existing `--run-slow` hooks). `mock_heavy_deps` is the single wiring fixture replacing both `patched_main` and `_patch_common`. It accepts an optional `page` so callers can inject a seeded `FakePage`.

```python
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from pdomain_ocr_cli import ocr_to_txt
from tests._fakes import FakePage

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TITLE_IMAGE = FIXTURES_DIR / "title_page_001.png"


@pytest.fixture
def run_main(monkeypatch):
    """Invoke ocr_to_txt.main() with the given argv (after the prog name)."""

    def _run(*argv: str) -> None:
        monkeypatch.setattr(sys, "argv", ["pd-ocr", *argv])
        ocr_to_txt.main()

    return _run


@pytest.fixture
def single_image(tmp_path):
    """Return (img_path, out_dir) — one copied fixture image + an out dir."""
    if not TITLE_IMAGE.exists():
        pytest.fail(f"missing fixture image: {TITLE_IMAGE}")
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    return img, tmp_path / "out"


@pytest.fixture
def make_images(tmp_path):
    """Factory: make_images(n) -> [path, ...] of n copied fixture images."""
    if not TITLE_IMAGE.exists():
        pytest.fail(f"missing fixture image: {TITLE_IMAGE}")

    def _make(n: int) -> list[Path]:
        imgs = []
        for i in range(n):
            img = tmp_path / f"page_{i:02d}.png"
            shutil.copy(TITLE_IMAGE, img)
            imgs.append(img)
        return imgs

    return _make


@pytest.fixture
def mock_heavy_deps(monkeypatch, tmp_path):
    """Patch every heavy dependency of main(); return a control namespace.

    Pass ``ns = mock_heavy_deps()`` to use the default single-text page, or
    ``mock_heavy_deps(page=FakePage(...))`` / ``mock_heavy_deps(texts=[...])``
    to control per-image output. Returns a SimpleNamespace with det_path,
    reco_path, predictor, page, captured_pages, captured_docs, batch_calls.
    """

    def _wire(*, page: FakePage | None = None, texts: list[str] | None = None):
        monkeypatch.setattr(ocr_to_txt, "_check_for_update", lambda: None)
        monkeypatch.setattr(ocr_to_txt, "_start_update_check_thread", lambda disabled: None)
        monkeypatch.setattr(ocr_to_txt, "_should_nudge_gpu_install", lambda: False)

        fake_det = tmp_path / "fake-det.pt"
        fake_reco = tmp_path / "fake-reco.pt"
        fake_det.write_bytes(b"")
        fake_reco.write_bytes(b"")
        monkeypatch.setattr(ocr_to_txt, "resolve_ocr_models", lambda args: (fake_det, fake_reco))
        monkeypatch.setattr(
            ocr_to_txt, "resolve_layout_source",
            lambda args: ("fake/layout-repo", "v0", "fake/layout-repo@v0"),
        )
        monkeypatch.setattr(ocr_to_txt, "prefetch_layout_files", lambda repo, rev: None)
        monkeypatch.setattr(ocr_to_txt, "_detect_torch_device", lambda: "cpu")
        monkeypatch.setattr(ocr_to_txt, "_pick_device", lambda: "cpu")

        fake_predictor = object()
        monkeypatch.setattr(ocr_to_txt, "_load_predictor", lambda det, reco: fake_predictor)
        monkeypatch.setattr(
            ocr_to_txt, "_load_layout_detector",
            lambda args, device: MagicMock(
                detect=MagicMock(return_value=SimpleNamespace(regions=[], inference_ms=1))
            ),
        )
        monkeypatch.setattr(
            ocr_to_txt, "_load_validate_word_preservation",
            lambda: MagicMock(return_value=[]),
        )

        template = page if page is not None else FakePage(text="FAKE OCR TEXT")
        captured_pages: list[FakePage] = []
        batch_calls: list[dict] = []
        counter = [0]

        def _clone(template_page: FakePage) -> FakePage:
            clone = FakePage(
                template_page.text, list(template_page.words),
                body=template_page._body, layout_word=template_page._layout_word,
                illustration_caption=template_page._caption,
            )
            clone.diagnostic_pure_ocr = template_page.diagnostic_pure_ocr
            clone.diagnostic_post_noise_removal = template_page.diagnostic_post_noise_removal
            clone.diagnostic_noise_dropped_words = list(template_page.diagnostic_noise_dropped_words)
            clone.diagnostic_noise_dropped_count = template_page.diagnostic_noise_dropped_count
            return clone

        def batch_runner(images, *, predictor, device, build_smaller=None,
                         source_identifiers=None):
            pages = []
            for _ in images:
                if texts is not None:
                    idx = counter[0]
                    txt = texts[idx] if idx < len(texts) else f"PAGE_{idx}"
                    clone = FakePage(text=txt)
                else:
                    clone = _clone(template)
                counter[0] += 1
                captured_pages.append(clone)
                pages.append(clone)
            batch_calls.append({
                "chunk_size": len(images), "predictor": predictor,
                "device": device, "source_identifiers": source_identifiers,
            })
            return pages

        monkeypatch.setattr(ocr_to_txt, "_run_doctr_batch", batch_runner)

        class _DocsProxy(list):
            def __getitem__(self, idx):  # type: ignore[override]
                return SimpleNamespace(pages=[captured_pages[idx]])

            def __len__(self):
                return len(captured_pages)

        return SimpleNamespace(
            det_path=fake_det, reco_path=fake_reco, predictor=fake_predictor,
            page=template, captured_pages=captured_pages,
            captured_docs=_DocsProxy(), batch_calls=batch_calls,
        )

    return _wire
```

- [ ] **Step 2: Verify fixtures load (collection only)**

Run: `uv run pytest tests/ --collect-only -q 2>&1 | tail -5`
Expected: collection succeeds, no fixture/import errors.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add shared mock_heavy_deps/run_main/single_image fixtures"
```

### Task 3: Migrate `test_batch_pages.py` onto shared scaffolding

**Files:**

- Modify: `tests/test_batch_pages.py`

- [ ] **Step 1: Replace local fakes/helpers with fixtures**

Delete the module-level `_FakePage`, `_patch_common`, `_run_main`, and the `FIXTURES_DIR`/`TITLE_IMAGE`/`shutil`/`sys` imports. Convert each test to take `mock_heavy_deps`, `run_main`, `make_images`. Use `texts=` to control per-image output. Example transform for the chunking test:

```python
def test_batch_pages_chunking_calls_run_doctr_batch_with_correct_chunk_sizes(
    mock_heavy_deps, run_main, make_images, tmp_path
):
    imgs = make_images(5)
    out = tmp_path / "out"
    texts = [f"TEXT_{i}" for i in range(5)]
    ns = mock_heavy_deps(texts=texts)

    run_main("--no-update-check", "--layout-model", "none",
             "--batch-pages", "2", "-o", str(out), *[str(i) for i in imgs])

    assert [c["chunk_size"] for c in ns.batch_calls] == [2, 2, 1]
    for i, img in enumerate(imgs):
        assert (out / f"{img.stem}.txt").read_text() == f"TEXT_{i}"
```

Apply the same pattern to `test_batch_pages_predictor_passed_through`, `test_batch_pages_reorganize_called_per_page`, `test_batch_pages_equivalence_different_sizes`, `test_batch_pages_default_is_4`. For the `reorganize_called_per_page` test, read `ns.captured_pages` instead of re-wrapping the runner (each captured page's `reorganize_page.assert_called_once()`).

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/test_batch_pages.py -v -n auto`
Expected: all 5 pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_batch_pages.py
git commit -m "test: migrate test_batch_pages onto shared fixtures"
```

### Task 4: Migrate the `_ns()` users (`test_pipeline_helpers.py`, `test_hf_models_argparse.py`)

**Files:**

- Modify: `tests/test_pipeline_helpers.py`, `tests/test_hf_models_argparse.py`

- [ ] **Step 1: Replace local `_ns` with shared builders**

In `test_pipeline_helpers.py`: delete the local `_ns` (lines 36–44) and replace every `_ns(` call with `pipeline_args(`; add `from tests._fakes import pipeline_args`. In `test_hf_models_argparse.py`: delete the local `_ns` (lines 31–44) and replace every `_ns(` with `hf_args(`; add `from tests._fakes import hf_args`.

- [ ] **Step 2: Run both files**

Run: `uv run pytest tests/test_pipeline_helpers.py tests/test_hf_models_argparse.py -n auto`
Expected: all pass (55 + 11).

- [ ] **Step 3: Commit**

```bash
git add tests/test_pipeline_helpers.py tests/test_hf_models_argparse.py
git commit -m "test: use shared pipeline_args/hf_args namespace builders"
```

### Task 5: Replace duplicate `FakeArray` definitions in `test_pipeline_helpers.py`

**Files:**

- Modify: `tests/test_pipeline_helpers.py`

- [ ] **Step 1: Hoist to shared fake**

Find the three local cv2-slice array fakes (around lines 467, 518, 1403 in the original file) and replace each with `from tests._fakes import FakeArray` + `FakeArray(shape=...)`. Keep any test-specific `shape` values.

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/test_pipeline_helpers.py -n auto`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pipeline_helpers.py
git commit -m "test: use shared FakeArray fake"
```

---

## Phase 1 — Split the giants

### Task 6: Split `test_main_mocked.py` into four files

**Files:**

- Create: `tests/test_main_happy.py`, `tests/test_main_errors.py`, `tests/test_main_flag_wiring.py`, `tests/test_main_warnings.py`
- Delete: `tests/test_main_mocked.py`

This is a move-and-rewire, not a rewrite. Each moved test drops its local `_run_main`/`shutil.copy` boilerplate and takes `mock_heavy_deps`, `run_main`, `single_image`. The old `patched_main` fixture is gone; tests call `ns = mock_heavy_deps()` explicitly.

- [ ] **Step 1: Create the four files with a shared header**

Each file starts with:

```python
"""<scope> tests for ocr_to_txt.main() with heavy deps mocked."""

from __future__ import annotations

import pytest

from pdomain_ocr_cli import ocr_to_txt
from tests._fakes import FakePage
```

Distribute the existing tests:

- **`test_main_happy.py`**: the "Happy paths" section (`test_main_writes_txt_with_layout_disabled`, `test_main_save_json_writes_sidecar`, and other non-error happy cases).
- **`test_main_errors.py`**: `test_main_save_json_failure_cleans_up_tmp_and_increments_errors` and the rest of the SystemExit / atomicity / per-image-exception / KeyboardInterrupt cluster, plus `test_main_layout_load_error_exits` (already parametrized).
- **`test_main_flag_wiring.py`**: `test_main_no_reorg_skips_reorganize`, `test_main_experimental_drop_layout_words_short_alias`, `test_main_default_passes_drop_layout_words_false_to_reorganize`, `test_main_experimental_drop_layout_words_passes_true_to_reorganize`, `test_main_default_emits_illustration_placeholders`, `test_main_no_illustration_placeholders_passes_false_to_reorganize`. (These get *strengthened* in Phase 3 — move them as-is for now so the split stays behavior-preserving.)
- **`test_main_warnings.py`**: the B3 silent-no-op family (`test_main_no_reorg_with_save_diag_warns`, `_no_reorg_with_validate_reorg_warns`, `_layout_none_with_layout_debug_warns`, `_no_reorg_with_layout_debug_warns_and_suppresses_success_path`, `_layout_debug_dir_without_layout_debug_warns`, `_no_reorg_with_experimental_drop_layout_words_warns`, `_save_reorganize_diagnostics_without_save_json_warns`, `_no_illustration_placeholders_with_no_reorg_warns`) plus `test_main_layout_debug_writes_debug_file` and `test_main_noise_drop_warning_skipped_when_no_drops` (these two get fixed/deleted in Phase 3). (Parametrize comes in Phase 2.)

Mechanical per-test rewrite pattern (example):

```python
# BEFORE (in test_main_mocked.py):
def test_main_writes_txt_with_layout_disabled(patched_main, monkeypatch, tmp_path):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"
    _run_main(monkeypatch, "--no-update-check", "--layout-model", "none",
              "-o", str(out), str(img))
    assert (out / "page.txt").read_text() == "FAKE OCR TEXT"
    assert len(patched_main.captured_docs) == 1

# AFTER (in test_main_happy.py):
def test_main_writes_txt_with_layout_disabled(mock_heavy_deps, run_main, single_image):
    img, out = single_image
    ns = mock_heavy_deps()
    run_main("--no-update-check", "--layout-model", "none", "-o", str(out), str(img))
    assert (out / "page.txt").read_text() == "FAKE OCR TEXT"
    assert len(ns.captured_pages) == 1
```

For multi-image tests use `make_images(n)`; for tests that need a custom page, pass `mock_heavy_deps(page=FakePage(...))`.

- [ ] **Step 2: Delete the old file**

```bash
git rm tests/test_main_mocked.py
```

- [ ] **Step 3: Run the four new files**

Run: `uv run pytest tests/test_main_happy.py tests/test_main_errors.py tests/test_main_flag_wiring.py tests/test_main_warnings.py -n auto`
Expected: same total count as the old 52, all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_main_happy.py tests/test_main_errors.py tests/test_main_flag_wiring.py tests/test_main_warnings.py
git commit -m "test: split test_main_mocked into happy/errors/flag-wiring/warnings"
```

### Task 7: Split `test_pipeline_helpers.py` into three files

**Files:**

- Create: `tests/test_pipeline_paths.py`, `tests/test_pipeline_warnings.py`, `tests/test_pipeline_atomic_write.py`
- Delete: `tests/test_pipeline_helpers.py`

- [ ] **Step 1: Distribute tests by helper group**

Each file imports only the helpers it uses from `pdomain_ocr_cli._pipeline` and `from tests._fakes import pipeline_args, FakeArray` as needed.

- **`test_pipeline_paths.py`**: `compute_mirror_root`, `resolve_dest_dir`, `output_paths_for`, `diagnostic_output_paths`, `illustration_crop_path`, `iter_crop_regions`, `validate_extract_illustrations`, `validate_extract_illustrations`-related, `setup_layout_debug_env`/`clear_layout_debug_env`, `write_diagnostic_snapshots`.
- **`test_pipeline_warnings.py`**: `format_drops_warning`, `format_noise_drop_warning`.
- **`test_pipeline_atomic_write.py`**: `atomic_write_text`, `atomic_write_bytes`, `apply_text_normalizations`.

- [ ] **Step 2: Convert env tests to monkeypatch (no manual teardown)**

In `test_pipeline_paths.py`, rewrite the `setup_layout_debug_env`/`clear_layout_debug_env` tests so they take `monkeypatch` and use `monkeypatch.setenv`/`monkeypatch.delenv(..., raising=False)` instead of mutating `os.environ` directly with a manual `clear_layout_debug_env()` call at the end. This prevents env leakage on mid-test assertion failure. Example:

```python
def test_setup_layout_debug_env_sets_vars(monkeypatch, tmp_path):
    monkeypatch.delenv("LAYOUT_DEBUG", raising=False)
    args = pipeline_args(layout_debug=True, layout_debug_dir=str(tmp_path))
    result = setup_layout_debug_env(args)
    assert result is not None
    # assert on the env vars the helper sets ...
```

(Keep at least one test that exercises `clear_layout_debug_env` directly so its body stays covered.)

- [ ] **Step 3: Delete the old file**

```bash
git rm tests/test_pipeline_helpers.py
```

- [ ] **Step 4: Run the three new files**

Run: `uv run pytest tests/test_pipeline_paths.py tests/test_pipeline_warnings.py tests/test_pipeline_atomic_write.py -n auto`
Expected: same total as the old 55, all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline_paths.py tests/test_pipeline_warnings.py tests/test_pipeline_atomic_write.py
git commit -m "test: split test_pipeline_helpers by helper group; monkeypatch env tests"
```

---

## Phase 2 — Parametrize

### Task 8: Parametrize the silent-no-op warning family

**Files:**

- Modify: `tests/test_main_warnings.py`

- [ ] **Step 1: Replace the 8 near-identical warning tests with one parametrized test**

Each case is `(id, extra_flags, expected_substrings)`. Keep `test_main_no_reorg_with_layout_debug_warns_and_suppresses_success_path` separate (it also asserts on stdout), but the other warning tests collapse:

```python
import pytest

_WARN_CASES = [
    ("no_reorg+save_diag",
     ["--no-reorg", "--save-json", "--save-reorganize-diagnostics"],
     ["--no-reorg", "--save-reorganize-diagnostics"]),
    ("no_reorg+validate_reorg",
     ["--no-reorg", "--validate-reorg"],
     ["--no-reorg", "--validate-reorg"]),
    ("layout_none+layout_debug",
     ["--layout-debug"],
     ["--layout-model none", "--layout-debug"]),
    ("layout_debug_dir_without_enable",
     ["--layout-debug-dir", "DEBUG_DIR"],
     ["--layout-debug-dir", "--layout-debug"]),
    ("no_reorg+edl",
     ["--no-reorg", "--experimental-drop-layout-words"],
     ["--no-reorg", "--experimental-drop-layout-words"]),
    ("save_diag_without_save_json",
     ["--save-reorganize-diagnostics"],
     ["--save-reorganize-diagnostics", "--save-json"]),
    ("no_illustration_placeholders+no_reorg",
     ["--no-reorg", "--no-illustration-placeholders"],
     ["--no-reorg", "--no-illustration-placeholders"]),
]


@pytest.mark.parametrize("flags,expected", [(f, e) for _, f, e in _WARN_CASES],
                         ids=[c[0] for c in _WARN_CASES])
def test_main_silent_no_op_warns(mock_heavy_deps, run_main, single_image, capsys,
                                 tmp_path, flags, expected):
    img, out = single_image
    # the layout_debug_dir case needs a real dir path
    flags = [str(tmp_path / "debug") if f == "DEBUG_DIR" else f for f in flags]
    mock_heavy_deps()
    base = ["--no-update-check", "--layout-model", "none"]
    run_main(*base, *flags, "-o", str(out), str(img))
    err = capsys.readouterr().err
    for sub in expected:
        assert sub in err
    assert "warning" in err.lower()
```

Note: the `layout_none+layout_debug` and `layout_debug_dir` cases include/omit `--layout-model none` deliberately — match the originals (the `no_reorg+layout_debug` original omits `--layout-model none`; that one stays as the separate stdout-asserting test). Verify each migrated case keeps the exact flag set of its original.

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/test_main_warnings.py -v -n auto`
Expected: parametrized cases + the two kept-separate tests all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_main_warnings.py
git commit -m "test: parametrize silent-no-op warning family"
```

### Task 9: Parametrize the `resolve_ocr_models` partial-input pair

**Files:**

- Modify: `tests/test_hf_models_argparse.py`

- [ ] **Step 1: Collapse the detection/recognition-without-counterpart pair**

```python
@pytest.mark.parametrize(
    "kwargs,expected_msg",
    [
        ({"detection": "det.pt"}, "--detection requires its counterpart"),
        ({"recognition": "rec.pt"}, "--recognition requires its counterpart"),
    ],
    ids=["detection_only", "recognition_only"],
)
def test_resolve_ocr_models_partial_input_exits(capsys, kwargs, expected_msg):
    with pytest.raises(SystemExit) as exc_info:
        resolve_ocr_models(hf_args(**kwargs))
    assert exc_info.value.code == 1
    assert expected_msg in capsys.readouterr().err
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/test_hf_models_argparse.py -v -n auto`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_hf_models_argparse.py
git commit -m "test: parametrize resolve_ocr_models partial-input pair"
```

---

## Phase 3 — Strengthen, fix, delete (TDD)

### Task 10: Turn flag-wiring tests into output-behavior tests

**Files:**

- Modify: `tests/test_main_flag_wiring.py`

- [ ] **Step 1: Write the failing behavior tests**

Replace the call-args assertions with assertions on the written `.txt`, using a seeded `FakePage`. Write these first and watch them fail (the default fixture page has no seed parts, so output won't change yet — you must pass a seeded page).

```python
def test_main_default_keeps_layout_word_in_output(mock_heavy_deps, run_main, single_image):
    img, out = single_image
    page = FakePage(body="BODY", layout_word="FOOTNOTE")
    mock_heavy_deps(page=page)
    run_main("--no-update-check", "--layout-model", "none", "-o", str(out), str(img))
    text = (out / "page.txt").read_text()
    assert "FOOTNOTE" in text
    assert "[layout: FOOTNOTE]" not in text


def test_main_edl_relabels_layout_word(mock_heavy_deps, run_main, single_image):
    img, out = single_image
    page = FakePage(body="BODY", layout_word="FOOTNOTE")
    mock_heavy_deps(page=page)
    run_main("--no-update-check", "--layout-model", "none",
             "--experimental-drop-layout-words", "-o", str(out), str(img))
    text = (out / "page.txt").read_text()
    assert "[layout: FOOTNOTE]" in text   # role-labeled, never silently dropped


def test_main_default_emits_illustration_placeholder(mock_heavy_deps, run_main, single_image):
    img, out = single_image
    page = FakePage(body="BODY", illustration_caption="A cat")
    mock_heavy_deps(page=page)
    run_main("--no-update-check", "--layout-model", "none", "-o", str(out), str(img))
    text = (out / "page.txt").read_text()
    assert "[Illustration]" in text
    assert "A cat" in text


def test_main_no_illustration_placeholders_keeps_caption(mock_heavy_deps, run_main, single_image):
    img, out = single_image
    page = FakePage(body="BODY", illustration_caption="A cat")
    mock_heavy_deps(page=page)
    run_main("--no-update-check", "--layout-model", "none",
             "--no-illustration-placeholders", "-o", str(out), str(img))
    text = (out / "page.txt").read_text()
    assert "[Illustration]" not in text
    assert "A cat" in text   # caption survives (no-silent-drops)
```

Keep `test_main_no_reorg_skips_reorganize` and the `--edl` alias-routes-the-same test (one call-args assertion is legitimate for proving the alias maps to the same attribute — but prefer asserting output parity with the long form). Delete the four pure call-args tests these replace.

- [ ] **Step 2: Run to verify the new tests pass and old ones are gone**

Run: `uv run pytest tests/test_main_flag_wiring.py -v -n auto`
Expected: new behavior tests PASS; no `call_args` assertions remain (`grep -L call_args tests/test_main_flag_wiring.py` returns the file).

- [ ] **Step 3: Commit**

```bash
git add tests/test_main_flag_wiring.py
git commit -m "test: assert flag effects on output text, not mock call-args"
```

### Task 11: Add a fast-suite happy-path content test

**Files:**

- Modify: `tests/test_main_happy.py`

- [ ] **Step 1: Add a content-shape assertion using a seeded page**

```python
def test_main_writes_recomposed_body_and_caption(mock_heavy_deps, run_main, single_image):
    img, out = single_image
    page = FakePage(body="The quick brown fox", illustration_caption="Fig 1")
    mock_heavy_deps(page=page)
    run_main("--no-update-check", "--layout-model", "none", "-o", str(out), str(img))
    text = (out / "page.txt").read_text()
    assert text.startswith("The quick brown fox")
    assert "Fig 1" in text
```

- [ ] **Step 2: Run**

Run: `uv run pytest tests/test_main_happy.py -v -n auto`
Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_main_happy.py
git commit -m "test: assert recomposed happy-path output content in fast suite"
```

### Task 12: Fix the misnamed test and delete the weak-oracle test

**Files:**

- Modify: `tests/test_main_warnings.py`

- [ ] **Step 1: Delete `test_main_noise_drop_warning_skipped_when_no_drops`**

It uses an `or`-of-negatives oracle (`"dropped" not in err.lower() or "..." not in err`) that passes trivially. Its rigorous sibling (`test_main_noise_drop_warning_silent_with_zero_count`, in the noise-warning area) already covers the case. Remove it. (Ensure the sibling moved into one of the split files; if it lived in `test_main_mocked.py` it is now in `test_main_happy.py` or `test_main_warnings.py` — locate and keep it.)

- [ ] **Step 2: Fix `test_main_layout_debug_writes_debug_file`**

It currently asserts only that `page.txt` exists (the comment concedes the debug file is never written by the loop). Either (a) make it assert the real behavior — that under `--layout-debug` with layout enabled the debug artifact path is announced on stdout — or (b) if no observable behavior exists at this seam, delete it (the warning case already covers the no-op path). Choose (a) if the success line emits a `layout-debug:` segment; otherwise delete and note why in the commit message.

```python
def test_main_layout_debug_announces_artifact_on_success_line(
    mock_heavy_deps, run_main, single_image, capsys, tmp_path
):
    img, out = single_image
    mock_heavy_deps()
    run_main("--no-update-check", "--layout-debug",
             "--layout-debug-dir", str(tmp_path / "dbg"), "-o", str(out), str(img))
    captured = capsys.readouterr()
    assert "layout-debug:" in captured.out
```

(If the layout detector mock makes this seam unreachable, delete the test instead — do not keep a no-oracle test.)

- [ ] **Step 3: Run**

Run: `uv run pytest tests/test_main_warnings.py tests/test_main_happy.py -v -n auto`
Expected: pass; the weak test is gone.

- [ ] **Step 4: Commit**

```bash
git add tests/test_main_warnings.py tests/test_main_happy.py
git commit -m "test: fix misnamed layout-debug test; drop weak noise-warning oracle"
```

### Task 13: Replace the KeyboardInterrupt class-level flag with an instance flag

**Files:**

- Modify: `tests/test_main_errors.py`

- [ ] **Step 1: Make the recording thread use an instance attribute**

In the KeyboardInterrupt test, change the `_RecordingThread` helper so `joined` is set in `__init__` (`self.joined = False`) and flipped on the instance in `join`, rather than mutating a class attribute. This removes cross-instance shared state.

- [ ] **Step 2: Run**

Run: `uv run pytest tests/test_main_errors.py -v -n auto`
Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_main_errors.py
git commit -m "test: use instance flag in KeyboardInterrupt recording thread"
```

---

## Phase 4 — Real-pwsh install-script tests

### Task 14: Extract CUDA-detection helpers into a dot-sourceable lib

**Files:**

- Create: `scripts/install-cuda-detect.ps1`
- Modify: `install.ps1`

- [ ] **Step 1: Create `scripts/install-cuda-detect.ps1`**

Move `Get-CudaVersion` verbatim and add two pure helpers extracted from the current inline logic (lines 92 and 100 of `install.ps1`). This file contains ONLY function definitions — no side effects — so tests can dot-source it safely.

```powershell
# Pure CUDA-detection helpers for install.ps1.
# Dot-sourced by install.ps1 and by tests/test_install_ps1_cuda.py.
# Contains NO top-level side effects.

function Get-CudaVersion {
    if ($env:CUDA_VERSION) {
        Write-Host "Using CUDA_VERSION override: $($env:CUDA_VERSION)"
        return $env:CUDA_VERSION
    }
    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        return $null
    }
    try {
        $qOut = & nvidia-smi -q 2>$null
        $qStr = ($qOut -join "`n")
        if ($qStr -match "CUDA Version\s*:\s*(\d+\.\d+)") {
            return $Matches[1]
        }
    } catch {}
    try {
        $smiOut = & nvidia-smi 2>$null
        $smiStr = ($smiOut -join "`n")
        if ($smiStr -match "CUDA Version:\s*(\d+\.\d+)") {
            return $Matches[1]
        }
    } catch {}
    return $null
}

function Get-CudaTag {
    param([Parameter(Mandatory = $true)][string]$CudaVer)
    return "cu" + ($CudaVer -replace "\.", "")
}

function Get-BookToolsExtras {
    param([Parameter(Mandatory = $true)][string]$CudaVer)
    # CuPy (cupy-cuda12x) requires CUDA >= 12.4.
    if ([version]$CudaVer -ge [version]"12.4") { return "[gpu]" }
    return ""
}
```

- [ ] **Step 2: Rewire `install.ps1` to dot-source the lib**

Add near the top (after `$ErrorActionPreference`): `. "$PSScriptRoot/scripts/install-cuda-detect.ps1"`. Delete the inline `function Get-CudaVersion { ... }` (lines 49–86) and replace the inline tag/extras construction (lines 92, 100–105) with `Get-CudaTag $CudaVer` and `Get-BookToolsExtras $CudaVer`. Behavior is unchanged.

- [ ] **Step 3: Smoke-check the script still parses**

Run: `pwsh -NoProfile -Command "& { \$ErrorActionPreference='Stop'; . ./scripts/install-cuda-detect.ps1; Write-Output (Get-CudaTag '12.4'); Write-Output (Get-BookToolsExtras '12.4'); Write-Output (Get-BookToolsExtras '12.1') }"`
Expected output lines: `cu124`, `[gpu]`, `` (empty).

- [ ] **Step 4: Commit**

```bash
git add scripts/install-cuda-detect.ps1 install.ps1
git commit -m "refactor(install): extract CUDA-detection helpers into dot-sourceable lib"
```

### Task 15: Add real-pwsh tests; delete the reimplementation file

**Files:**

- Create: `tests/test_install_ps1_cuda.py`
- Delete: `tests/test_install_ps1_cuda_parse.py`

These run the REAL functions via `pwsh` subprocess. No `skipif` — a missing `pwsh` is a hard failure (DoD). `pwsh` is preinstalled on GitHub `ubuntu-latest`; the devcontainer gets it in Task 17.

- [ ] **Step 1: Write the tests**

```python
"""Real-pwsh tests for scripts/install-cuda-detect.ps1.

Invokes the actual PowerShell helpers via a pwsh subprocess so edits to the
real script are caught. pwsh is required (no skip) — CI and devcontainer both
provide it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

LIB = Path(__file__).parents[1] / "scripts" / "install-cuda-detect.ps1"


def _pwsh(body: str) -> subprocess.CompletedProcess:
    script = f". '{LIB}'\n{body}"
    return subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, check=True,
    )


def test_get_cuda_tag_strips_dot():
    out = _pwsh("Get-CudaTag '12.4'").stdout.strip()
    assert out == "cu124"


def test_get_book_tools_extras_gpu_at_or_above_124():
    assert _pwsh("Get-BookToolsExtras '12.4'").stdout.strip() == "[gpu]"
    assert _pwsh("Get-BookToolsExtras '12.8'").stdout.strip() == "[gpu]"


def test_get_book_tools_extras_empty_below_124():
    assert _pwsh("Get-BookToolsExtras '12.1'").stdout.strip() == ""


def test_get_cuda_version_env_override():
    out = _pwsh("$env:CUDA_VERSION='12.6'; Get-CudaVersion").stdout
    assert "12.6" in out


def test_get_cuda_version_parses_smi_q_output():
    # Stub nvidia-smi as a pwsh function so Get-Command finds it and the -q
    # branch's regex runs against canned verbose output.
    body = (
        "$env:CUDA_VERSION=$null\n"
        "function nvidia-smi { 'CUDA Version                          : 12.4' }\n"
        "Get-CudaVersion"
    )
    assert _pwsh(body).stdout.strip().endswith("12.4")


def test_get_cuda_version_parses_plain_smi_header():
    body = (
        "$env:CUDA_VERSION=$null\n"
        "function nvidia-smi { if ($args -contains '-q') { '' } "
        "else { '| NVIDIA-SMI ... CUDA Version: 12.2   |' } }\n"
        "Get-CudaVersion"
    )
    assert _pwsh(body).stdout.strip().endswith("12.2")


def test_get_cuda_version_null_when_no_smi():
    body = (
        "$env:CUDA_VERSION=$null\n"
        "Get-CudaVersion | ForEach-Object { 'GOT:' + $_ }"
    )
    # No nvidia-smi on the runner -> returns $null -> no GOT: line.
    assert "GOT:" not in _pwsh(body).stdout
```

(Note: `test_get_cuda_version_null_when_no_smi` assumes the runner has no real `nvidia-smi`. CI sets `CUDA_VISIBLE_DEVICES=""` and ubuntu-latest has no GPU/driver, so `nvidia-smi` is absent. If a local dev machine HAS nvidia-smi, define a shadowing function returning empty in the body to keep it deterministic — add `function nvidia-smi { '' }`.)

To stay deterministic everywhere, prefer shadowing in that last test:

```python
def test_get_cuda_version_null_when_smi_gives_nothing():
    body = (
        "$env:CUDA_VERSION=$null\n"
        "function nvidia-smi { '' }\n"
        "Get-CudaVersion | ForEach-Object { 'GOT:' + $_ }"
    )
    assert "GOT:" not in _pwsh(body).stdout
```

Use this shadowing variant (drop the runner-dependent one).

- [ ] **Step 2: Delete the old reimplementation file**

```bash
git rm tests/test_install_ps1_cuda_parse.py
```

- [ ] **Step 3: Run the new tests**

Run: `uv run pytest tests/test_install_ps1_cuda.py -v -n auto`
Expected: all pass (requires `pwsh` on PATH).

- [ ] **Step 4: Commit**

```bash
git add tests/test_install_ps1_cuda.py
git commit -m "test: drive real install.ps1 CUDA helpers via pwsh; drop python reimpl"
```

### Task 16: Update the coverage `omit`/`exclude` for the .ps1 boundary

**Files:**

- Modify: `pyproject.toml`

- [ ] **Step 1: Confirm no Python coverage impact**

The `.ps1` files are not Python, so they never appear in coverage. No `exclude_also` change is needed for them. Verify the deleted `test_install_ps1_cuda_parse.py` removed no Python lines that were the *only* cover for a `pdomain_ocr_cli` line (it tested a local Python reimplementation, not package code — so it covered nothing in `pdomain_ocr_cli`). This task is a verification checkpoint, not an edit, unless Step 2 of the coverage run (Task 19) shows a gap.

- [ ] **Step 2: No commit unless an edit was required.**

### Task 17: Install `pwsh` in the devcontainer

**Files:**

- Modify: `.devcontainer/Dockerfile` (workspace-shared — coordinate; this affects all repos in the container)

- [ ] **Step 1: Add PowerShell to the image**

Add an apt/Microsoft-repo install of `powershell` so `pwsh` is on PATH for local `make test`. (The Dockerfile is already modified in the working tree per `git status`; append the pwsh layer alongside existing tooling, following the file's existing install pattern.) Because this is a shared workspace file, flag the change to CT before merging — it is the one cross-repo touch in this plan.

- [ ] **Step 2: Verify locally**

Run: `pwsh --version`
Expected: prints a PowerShell version (after rebuilding/repackaging the devcontainer, or installing pwsh in the running container for the session).

- [ ] **Step 3: Commit (workspace-root commit, separate from the repo commits)**

```bash
git -C /workspaces/ocr-container add .devcontainer/Dockerfile
git -C /workspaces/ocr-container commit -m "chore(devcontainer): install pwsh for pdomain-ocr-cli install-script tests"
```

---

## Phase 5 — Coverage reconciliation & final gate

### Task 18: Reconcile coverage by testing (no pragma over reachable lines)

**Files:**

- Modify: any test file flagged by the coverage report; `pyproject.toml` only if a genuinely unexecutable line needs a justified pragma.

- [ ] **Step 1: Run coverage and read the missing-lines report**

Run: `uv run pytest tests/ --cov=pdomain_ocr_cli --cov-branch --cov-report=term-missing -n auto`
Expected: identify any line now uncovered after the deletions/rewrites.

- [ ] **Step 2: Cover each gap with a real behavior test**

For every reported missing line in `pdomain_ocr_cli/*`, add or extend a test that exercises it through real behavior. Do NOT add `# pragma: no cover` to a reachable line. Only if a line is genuinely unexecutable from a test (e.g. a defensive branch that the type system makes unreachable) add `# pragma: no cover  # <one-line reason>`.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: restore 100% coverage via real behavior tests after reorg"
```

### Task 19: Full green gate

**Files:** none (verification).

- [ ] **Step 1: Fast CI**

Run: `make ci AI=1`
Expected: `✅`, coverage == 100%.

- [ ] **Step 2: Slow suite (real model)**

Run: `make test-slow AI=1`
Expected: integration tests pass (downloads pinned model on first run).

- [ ] **Step 3: Confirm no stragglers**

Run: `grep -rn "patched_main\|_patch_common\|def _run_main\|def _ns(\|class _FakePage" tests/ || echo "clean"`
Expected: `clean` (all local duplicates removed).

Run: `ls tests/test_main_mocked.py tests/test_pipeline_helpers.py tests/test_install_ps1_cuda_parse.py 2>&1`
Expected: all three report "No such file".

- [ ] **Step 4: Final commit if anything was touched in Step 3 cleanup.**

---

## Self-Review

- **Spec coverage:** Phase 0 ↔ spec "shared scaffolding" (Tasks 1–5). Phase 1 ↔ "split the giants" (Tasks 6–7). Phase 2 ↔ "parametrize" (Tasks 8–9). Phase 3 ↔ "strengthen/fix/delete" + behavior gaps + env-leak + class-flag (Tasks 10–13). Phase 4 ↔ "install.ps1 real pwsh" + devcontainer (Tasks 14–17). Phase 5 ↔ "coverage reconciliation" + DoD gate (Tasks 18–19). All spec sections map to tasks.
- **Placeholder scan:** No "TBD"/"handle edge cases"/"similar to". Every code step shows real code. The two conditional steps (Task 12 fix-or-delete, Task 16 verify-or-edit) state the explicit decision criterion rather than deferring.
- **Type consistency:** `FakePage` ctor params (`body`, `layout_word`, `illustration_caption`) used consistently in `_fakes.py`, `mock_heavy_deps` `_clone`, and Tasks 10–11. `mock_heavy_deps(page=, texts=)` signature consistent across Tasks 3, 6, 10, 11. `Get-CudaTag`/`Get-BookToolsExtras`/`Get-CudaVersion` names consistent across Tasks 14–15.
- **FastAPI + SPA check:** N/A — `pdomain-ocr-cli` is a CLI, not a FastAPI+SPA app. No browser-verification milestone required.
