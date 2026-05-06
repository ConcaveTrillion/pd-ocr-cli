---
name: Slow-test predictor sharing
description: How tests/test_pipeline_integration.py reuses one DocTR predictor across all 8 slow tests, and why subprocess invocation was abandoned.
type: project
---

`tests/test_pipeline_integration.py` runs the slow OCR pipeline tests in-process (not via `subprocess.run` + `python -m pd_ocr_cli.ocr_to_txt`). A session-scoped `shared_predictor` fixture builds the fine-tuned DocTR predictor exactly once; each slow test then monkeypatches `pd_ocr_cli.ocr_to_txt._load_predictor` to return that cached predictor, sets `sys.argv`, and calls `ocr_to_txt.main()` directly, catching `SystemExit` for exit-code assertions and using `capsys` for stdout/stderr.

**Why:** The original subprocess-based slow tests took ~58s for 8 tests because every test paid a fresh ~6-7s model load. After the refactor, the same 8 tests run in ~7s — one model load shared across all of them. This was option 2 of a perf cleanup (parent agent picked it).

**How to apply:**
- The `_load_predictor(det_path, reco_path)` seam is the canonical injection point. It already existed for `tests/test_main_mocked.py`. Do not add a redundant `predictor=` kwarg to `main()`.
- The slow tests do NOT mock `_load_layout_detector` / `_load_document_factory` / `resolve_ocr_models` — only `_load_predictor`. Everything else runs unmocked, against real models, so flag handling and per-image error paths still get real coverage.
- The `if __name__ == "__main__":` guard in `ocr_to_txt.py` is excluded by `[tool.coverage.report].exclude_also` in `pyproject.toml`, so no subprocess test is needed to cover it. Coverage stays at 100%.
- `COVERAGE_PROCESS_START` plumbing was removed from the slow tests (no subprocesses → no need for child-process coverage). `[tool.coverage.run].parallel` and the `multiprocessing` entry in `concurrency` were dropped from `pyproject.toml` for the same reason. `concurrency = ["thread"]` is still needed for the daemon update-check thread.
- If you ever need to test something that genuinely requires a fresh process (e.g. an env var read at module import), use `runpy.run_module(..., run_name="__main__")` rather than reintroducing `subprocess.run`.
- Predictor reuse is safe because no slow test mutates predictor internals (no `.training` toggling, no weight surgery).
