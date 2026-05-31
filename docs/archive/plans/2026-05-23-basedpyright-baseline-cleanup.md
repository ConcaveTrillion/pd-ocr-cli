# Basedpyright Baseline Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the production-code diagnostics currently grandfathered in `.basedpyright/baseline.json`.

**Architecture:** Work is split by module so each branch owns a disjoint write scope. Worker branches should fix code diagnostics only; the baseline file is regenerated once after merge to avoid generated-file conflicts.

**Tech Stack:** Python 3.10+, `basedpyright`, `uv`, `pytest-xdist`, `ruff`.

---

## Baseline Inventory

Run from the repo root:

```bash
uv run basedpyright pdomain_ocr_cli --baselinefile /tmp/no-baseline-pdomain-ocr-cli.json --outputjson
```

Current production baseline:

- `pdomain_ocr_cli/ocr_to_txt.py`: 155 warnings.
- `pdomain_ocr_cli/_hf_models.py`: 36 warnings.
- `pdomain_ocr_cli/_pipeline.py`: 31 warnings.
- `pdomain_ocr_cli/_update_check.py`: 6 warnings.

Do not edit `.basedpyright/baseline.json` in worker branches. Regenerate it only after the branches are merged.

### Workstream 1: Hugging Face Argparse Adapters

**Branch/worktree:** `agent/bpy-hf-models` at `.worktree/bpy-hf-models`

**Files:**

- Modify: `pdomain_ocr_cli/_hf_models.py`
- Optional test touch: `tests/test_hf_models_argparse.py`

- [ ] Replace `argparse.Namespace` parameters with narrow protocols for the model-resolution args.
- [ ] Type the attributes consumed by `resolve_ocr_models`, `det_source_descriptor`, `reco_source_descriptor`, and `resolve_layout_source`.
- [ ] Contain untyped `pdomain_book_tools.hf` imports at the module boundary with precise aliases or casts.
- [ ] Verify:

```bash
uv run basedpyright pdomain_ocr_cli/_hf_models.py --baselinefile /tmp/bpy-hf-empty.json
uv run pytest -n auto tests/test_hf_models_argparse.py
uv run ruff check pdomain_ocr_cli/_hf_models.py tests/test_hf_models_argparse.py
```

### Workstream 2: Pipeline Helper Protocols

**Branch/worktree:** `agent/bpy-pipeline` at `.worktree/bpy-pipeline`

**Files:**

- Modify: `pdomain_ocr_cli/_pipeline.py`
- Optional test touch: `tests/test_pipeline_helpers.py`, `tests/test_main_mocked.py`

- [ ] Add narrow protocols for layout args, word-like values, diagnostic page snapshots, and crop regions.
- [ ] Replace explicit `Any` in helper signatures where `object`, `Protocol`, or concrete containers are sufficient.
- [ ] Assign intentionally ignored `os.environ.pop` results to `_`.
- [ ] Replace implicit string concatenation in warning/note strings.
- [ ] Verify:

```bash
uv run basedpyright pdomain_ocr_cli/_pipeline.py --baselinefile /tmp/bpy-pipeline-empty.json
uv run pytest -n auto tests/test_pipeline_helpers.py tests/test_main_mocked.py
uv run ruff check pdomain_ocr_cli/_pipeline.py tests/test_pipeline_helpers.py tests/test_main_mocked.py
```

### Workstream 3: Update Check JSON Boundary

**Branch/worktree:** `agent/bpy-update-check` at `.worktree/bpy-update-check`

**Files:**

- Modify: `pdomain_ocr_cli/_update_check.py`
- Optional test touch: `tests/test_update_check_bypass.py`, `tests/test_update_check_network.py`, `tests/test_update_check_parsers.py`

- [ ] Treat `json.loads` as `object` and validate the GitHub tags payload before passing it to `_latest_stable_tag`.
- [ ] Add a small typed boundary for tag dictionaries.
- [ ] Preserve the existing best-effort network failure behavior.
- [ ] Replace the implicit notice-string concatenation.
- [ ] Verify:

```bash
uv run basedpyright pdomain_ocr_cli/_update_check.py --baselinefile /tmp/bpy-update-empty.json
uv run pytest -n auto tests/test_update_check_bypass.py tests/test_update_check_network.py tests/test_update_check_parsers.py
uv run ruff check pdomain_ocr_cli/_update_check.py tests/test_update_check_*.py
```

### Workstream 4: CLI Driver Boundary Types

**Branch/worktree:** `agent/bpy-ocr-to-txt` at `.worktree/bpy-ocr-to-txt`

**Files:**

- Modify: `pdomain_ocr_cli/ocr_to_txt.py`
- Optional test touch: `tests/test_parse_args.py`, `tests/test_main_mocked.py`, `tests/test_collect_images.py`, `tests/test_gpu_nudge.py`, `tests/test_torch_device.py`

- [ ] Add narrow protocols for parsed CLI args, predictor/document/page/layout detector/cv2-like dependencies, and crop regions.
- [ ] Replace loader return `Any` types with typed callable aliases or protocols.
- [ ] Fix optional import probe diagnostics while preserving import-only behavior.
- [ ] Assign argparse action return values to `_`.
- [ ] Replace implicit string concatenation in help and error text.
- [ ] Type main-loop interactions at external-library boundaries with narrow casts, not broad ignores.
- [ ] Verify:

```bash
uv run basedpyright pdomain_ocr_cli/ocr_to_txt.py --baselinefile /tmp/bpy-ocr-empty.json
uv run pytest -n auto tests/test_parse_args.py tests/test_main_mocked.py tests/test_collect_images.py tests/test_gpu_nudge.py tests/test_torch_device.py
uv run ruff check pdomain_ocr_cli/ocr_to_txt.py tests/test_parse_args.py tests/test_main_mocked.py tests/test_collect_images.py tests/test_gpu_nudge.py tests/test_torch_device.py
```

## Merge-Back Checklist

- [ ] Review each worker branch diff.
- [ ] Merge branches into one integration branch.
- [ ] Run `uv run basedpyright pdomain_ocr_cli --baselinefile /tmp/no-baseline-pdomain-ocr-cli.json` to confirm production warnings are gone.
- [ ] Regenerate `.basedpyright/baseline.json` once with the final merged state if tests remain included in project-wide type checking.
- [ ] Run `make test AI=1`, `make lint AI=1`, and finally `make ci AI=1`.
