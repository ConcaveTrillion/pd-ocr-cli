# pdomain-ocr-cli Review Remediation Validation

Date: 2026-05-29

## Commands

- `uv run pytest --no-cov ... focused suite`: PASS, 41 passed.
- `make ci AI=1`: PASS.
- `make ci-slow AI=1`: PASS.
- `make installer-test AI=1`: PASS.
- `make wheel-smoke AI=1`: PASS on Python 3.11, 3.12, and 3.13; each ran `pd-ocr 0.7.2.dev45+ga4ebb146c`.
- deterministic temp scan: PASS; production code has no deterministic artifact temp names, and hits are tests that assert legacy names are absent.
- workflow action pin scan: PASS.
- `make check-release-deps`: EXPECTED FAIL while `pdomain-ops` is path-sourced; release is blocked until it resolves from `pdomain-index-pip`.

## Spec Coverage

| Finding | Evidence |
|---|---|
| Windows piped installer works | `tests/test_install_ps1.py::test_install_ps1_piped_mode_is_self_contained_and_uses_release_wheel` |
| Windows pdomain index included | same test plus `install.ps1` uv args |
| Batch OCR exceptions cleanly handled | `tests/test_main_errors.py::test_main_batch_runner_error_reports_chunk_and_exits_1` |
| Batch count mismatch cleanly handled | `tests/test_main_errors.py::test_main_batch_result_count_mismatch_is_clean_error` |
| Flat output collisions rejected | `tests/test_batch_plan.py::test_batch_plan_rejects_flat_output_collisions` |
| Temp files are unique and symlink-safe | `tests/test_artifacts.py` |
| Model trust boundary surfaced | `tests/test_model_security.py` and README section |
| Release gated by tests | `tests/test_workflows_static.py::test_release_runs_ci_before_build` |
| Default layout integration covered | `tests/test_pipeline_integration.py::test_ocr_default_layout_model_runs_successfully` |
| Wheel console script covered | `make wheel-smoke AI=1` across Python 3.11, 3.12, and 3.13 |
| JSON sidecar contract covered | fast and slow JSON tests |
| Python version matrix declared | `tests/test_workflows_static.py::test_ci_declares_supported_python_matrix` |
| Path-sourced release dependency blocked | `make check-release-deps` and `tests/test_workflows_static.py::test_release_checks_dependency_sources_before_build` |

## Architecture Compliance

- `RunPolicy` owns effective flag behavior.
- `BatchPlan` owns image expansion and output collision preflight.
- `RuntimeSession` owns the heavy runtime seam.
- `PageOutputTransaction` / artifact helpers own atomic artifact writes.
- Startup notices and model trust warnings are isolated behind `_startup_notices.py` and `_model_security.py`.
- `ocr_to_txt.main()` remains orchestration, not detailed policy or artifact implementation.
