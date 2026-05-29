# pdomain-ocr-cli Review Remediation Implementation Plan

<!-- markdownlint-disable MD010 MD032 -->
<!-- This executable plan includes Makefile recipe examples and repeated task file lists. -->

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate every code, test, security, release, and architecture finding from the 2026-05-29 deep review of `pdomain-ocr-cli`.

**Architecture:** Add deep modules around the real domain seams: `RunPolicy`, `BatchPlan`, `RuntimeSession`, and `PageOutputTransaction`. Keep `ocr_to_txt.main()` as the readable CLI orchestration layer, but move policy, planning, runtime setup, and artifact lifecycle details behind focused interfaces with direct tests.

**Tech Stack:** Python 3.11-3.13, pytest, ruff, basedpyright, uv, GitHub Actions, POSIX shell, PowerShell.

---

## Non-Negotiable Execution Rules

- No deferral: every finding in the review is either fixed in this plan or explicitly proven in the final validation matrix as no longer applicable because the changed implementation removed it.
- No "follow-up issue" escape hatch.
- Use TDD for behavior changes: write the failing test, run it and confirm the expected failure, implement, then rerun.
- Preserve user-facing CLI behavior unless a review finding requires changing it. When behavior changes, update tests and docs in the same task.
- Use an isolated worktree when executing this plan.
- Commit after each task.
- Final validation must prove the implementation follows this spec, not merely that `make ci` passes.
- Package support is `>=3.11,<3.14`. CI and wheel smoke must validate 3.11, 3.12, and 3.13. Installer defaults may choose one runtime version for end users, but that default does not narrow supported Python versions.

## Files And Responsibilities

- `pdomain_ocr_cli/_policy.py`
  New. Converts parsed CLI args into effective run policy and warning messages.
- `pdomain_ocr_cli/_batch_plan.py`
  New. Expands inputs into page jobs, computes output paths, detects collisions, and validates batch size.
- `pdomain_ocr_cli/_runtime.py`
  New. Owns heavy runtime setup, image decode, batch OCR execution, and normalized startup/runtime errors.
- `pdomain_ocr_cli/_artifacts.py`
  New. Owns atomic page artifact writes: JSON, diagnostics, crops, final `.txt`, temp-file safety, cleanup, and success-line paths.
- `pdomain_ocr_cli/_model_security.py`
  New. Warns on mutable/default or user-supplied unsafe checkpoint trust boundaries.
- `pdomain_ocr_cli/_startup_notices.py`
  New. Owns update-check startup and GPU-nudge startup behavior.
- `pdomain_ocr_cli/ocr_to_txt.py`
  Modify. Keep CLI parser and high-level orchestration. Delegate policy, planning, runtime, artifacts, and notices.
- `pdomain_ocr_cli/_pipeline.py`
  Modify. Keep text normalization and warning formatting helpers. Move output planning and atomic write transaction details to new modules.
- `pdomain_ocr_cli/_hf_models.py`
  Modify. Add normalized model-resolution error surface where needed.
- `install.sh`
  Modify. Keep behavior but align with shared installer contract tests.
- `install.ps1`
  Modify. Make piped invocation self-contained and include the pdomain package index.
- `scripts/install-cuda-detect.ps1`
  Modify to keep helper behavior consistent with the self-contained `install.ps1` implementation.
- `.github/workflows/ci.yml`
  Modify. Add Python matrix and required installed-wheel smoke.
- `.github/workflows/release.yml`
  Modify. Add CI gate, pin actions/tool versions, remove direct expression interpolation in shell, and protect publishing path.
- `Makefile`
  Modify. Add explicit wheel smoke and slow/layout validation targets.
- `README.md`, `docs/usage/cli-usage.md`, `docs/architecture/layout-aware-ocr.md`, `DEVELOPMENT.md`
  Modify. Keep install, network, model trust, and release/test docs aligned with shipped behavior.
- Tests to create or modify:
  - `tests/test_policy.py`
  - `tests/test_batch_plan.py`
  - `tests/test_runtime.py`
  - `tests/test_artifacts.py`
  - `tests/test_model_security.py`
  - `tests/test_startup_notices.py`
  - `tests/test_install_sh.py`
  - `tests/test_install_ps1.py`
  - Existing `tests/test_main_*.py`
  - Existing `tests/test_pipeline_integration.py`
  - Existing `tests/test_parse_args.py`
  - Existing `tests/test_batch_pages.py`

## Spec Coverage Matrix

| Review finding | Implemented by | Validation |
|---|---|---|
| Windows `irm ... \| iex` broken | Task 1 | Task 1 tests plus installer smoke in Task 12 |
| Windows installer omits pdomain index | Task 1 | `test_install_ps1_piped_mode_is_self_contained_and_uses_pdomain_index` |
| Batch OCR failures escape handling | Task 4 | `test_main_batch_runner_error_reports_chunk_and_exits_1` |
| Batch result length mismatch crashes | Task 4 | `test_main_batch_result_count_mismatch_is_clean_error` |
| Flat output collisions overwrite | Task 3 | `test_batch_plan_rejects_flat_output_collisions` |
| Deterministic temp names unsafe | Task 5 | symlink/concurrent temp tests in `test_artifacts.py` |
| Model-resolution tracebacks | Task 4 and Task 6 | runtime/model error tests |
| Invalid `--batch-pages` silently clamps | Task 3 | parse tests for `0`, `-1`, and non-integers |
| Mutable `.pt` checkpoint trust boundary | Task 6 | model-security warning tests and docs |
| Release workflow mutable actions/test gap | Task 11 | workflow grep tests plus final spec validation |
| Local editable `pdomain-ops` reproducibility | Task 11 | release/dev docs and dependency-source validation |
| Large/numerous image DoS | Task 3 and Task 4 | batch/image limit tests |
| Default update-check outbound call | Task 7 | startup notice policy tests and docs |
| Fast CI lacks real OCR | Task 10 and Task 11 | new slow/layout workflow target |
| Default layout path untested | Task 10 | real default-layout slow test |
| Wheel/console script untested | Task 11 | wheel smoke target on Python 3.11, 3.12, and 3.13 plus CI step |
| Installer tests only helper | Task 1 and Task 2 | real shell and PowerShell tests |
| JSON contract weakly asserted | Task 5 and Task 9 | JSON envelope assertions |
| Fixture corpus too narrow | Task 10 | added fixture cases |
| Python matrix too narrow | Task 11 | CI matrix check |
| Architecture seams shallow | Tasks 3-8 | module tests and final architecture checklist |

Focused pytest commands in this plan run with `--no-cov` because the repository
enforces 100% coverage for default pytest invocations. Full coverage validation
continues to run through `make test AI=1`, `make coverage`, `make ci`, and the
final validation matrix.

---

### Task 1: Fix And Test The Windows Installer Contract

**Files:**
- Modify: `install.ps1`
- Modify: `scripts/install-cuda-detect.ps1`
- Create: `tests/test_install_ps1.py`
- Modify: `tests/test_install_ps1_cuda.py`
- Modify: `README.md`
- Modify: `docs/usage/cli-usage.md`

- [ ] **Step 1: Write failing PowerShell installer test for piped invocation**

Create `tests/test_install_ps1.py` with a test that runs the real top-level script text in a temp PowerShell process, with fake `uv`, fake `nvidia-smi`, and mocked release resolution.

```python
from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def _write_fake_exe(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_install_ps1_piped_mode_is_self_contained_and_uses_pdomain_index(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv_log = tmp_path / "uv.log"

    _write_fake_exe(
        bin_dir / "uv",
        f"""#!/bin/sh
printf '%s\\n' "$@" > {uv_log}
exit 0
""",
    )

    script = (REPO / "install.ps1").read_text(encoding="utf-8")
    harness = tmp_path / "run.ps1"
    harness.write_text(
        """
$ErrorActionPreference = "Stop"
function irm {
  param([string]$Uri)
  if ($Uri -like "*api.github.com/repos/pdomain/pdomain-ocr-cli/releases/latest*") {
    return [pscustomobject]@{
      tag_name = "v9.9.9"
      assets = @([pscustomobject]@{
        name = "pdomain_ocr_cli-9.9.9-py3-none-any.whl"
        browser_download_url = "https://example.invalid/pdomain_ocr_cli.whl"
      })
    }
  }
  if ($Uri -like "*astral.sh/uv/install.ps1*") { return "" }
  throw "unexpected irm: $Uri"
}
function Invoke-RestMethod {
  param([string]$Uri)
  return irm $Uri
}
function Invoke-WebRequest {
  param([string]$Uri, [string]$OutFile)
  Set-Content -Path $OutFile -Value "fake wheel"
}
Set-Content -Path "$env:TEMP\\install-under-test.ps1" -Value @'
"""
        + script.replace("'@", "' + \"@\"")
        + """
'@
. "$env:TEMP\\install-under-test.ps1"
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    args = uv_log.read_text(encoding="utf-8")
    assert "--extra-index-url" in args
    assert "https://pdomain.github.io/pdomain-index-pip/simple/" in args
    assert "pdomain_ocr_cli.whl" in args
```

- [ ] **Step 2: Run the failing test**

Run: `uv run pytest --no-cov tests/test_install_ps1.py::test_install_ps1_piped_mode_is_self_contained_and_uses_pdomain_index -v`

Expected before implementation: FAIL because `install.ps1` dot-sources a missing helper or omits the pdomain index.

- [ ] **Step 3: Make `install.ps1` self-contained**

Modify `install.ps1` so CUDA helper functions are defined in the script when `scripts/install-cuda-detect.ps1` is not available.

```powershell
function Get-CudaTag {
    param([string]$CudaVersion)
    return "cu$($CudaVersion -replace '\.', '')"
}

function Get-BookToolsExtras {
    param([string]$CudaVersion)
    try {
        $Version = [version]$CudaVersion
    } catch {
        return ""
    }
    if ($Version.Major -gt 12 -or ($Version.Major -eq 12 -and $Version.Minor -ge 4)) {
        return "[gpu]"
    }
    return ""
}

function Get-CudaVersion {
    if ($env:CUDA_VERSION) {
        return $env:CUDA_VERSION
    }
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $smi) {
        return $null
    }
    $query = & nvidia-smi -q 2>$null | Out-String
    if ($query -match 'CUDA Version\s*:\s*([0-9]+\.[0-9]+)') {
        return $Matches[1]
    }
    $plain = & nvidia-smi 2>$null | Out-String
    if ($plain -match 'CUDA Version:\s*([0-9]+\.[0-9]+)') {
        return $Matches[1]
    }
    return $null
}
```

Keep dot-sourcing as a checked-out development override:

```powershell
$HelperPath = Join-Path $PSScriptRoot "scripts/install-cuda-detect.ps1"
if ($PSScriptRoot -and (Test-Path $HelperPath)) {
    . $HelperPath
}
```

- [ ] **Step 4: Add pdomain index and wheel release install to `install.ps1`**

Define:

```powershell
$PdIndexUrl = "https://pdomain.github.io/pdomain-index-pip/simple/"
$Repo = "pdomain/pdomain-ocr-cli"
```

Build `uv` arguments so the pdomain index is always present:

```powershell
$PythonVersion = if ($env:PD_OCR_INSTALL_PYTHON) { $env:PD_OCR_INSTALL_PYTHON } else { "3.13" }
$UvArgs = @("tool", "install", "--python", $PythonVersion, "--reinstall", $WheelFile, "--extra-index-url", $PdIndexUrl)
if ($BookToolsExtras) {
    $UvArgs += @("--with", "pdomain-book-tools$BookToolsExtras")
}
if ($ExtraIndex) {
    $UvArgs += @("--extra-index-url", $ExtraIndex)
}
& uv @UvArgs
```

Resolve and download the latest release wheel instead of installing from a git ref, matching `install.sh`.

- [ ] **Step 5: Run installer tests**

Run: `uv run pytest --no-cov tests/test_install_ps1.py tests/test_install_ps1_cuda.py -v`

Expected: PASS.

- [ ] **Step 6: Update install docs**

Update `README.md` and `docs/usage/cli-usage.md` to state both installers install the release wheel and always pass the pdomain package index.

- [ ] **Step 7: Commit**

```bash
git add install.ps1 scripts/install-cuda-detect.ps1 tests/test_install_ps1.py tests/test_install_ps1_cuda.py README.md docs/usage/cli-usage.md
git commit -m "fix: make Windows installer self-contained"
```

### Task 2: Add Real POSIX Installer Contract Tests

**Files:**
- Create: `tests/test_install_sh.py`
- Modify: `install.sh`
- Modify: `Makefile`

- [ ] **Step 1: Write failing test for `install.sh` uv command contract**

Create `tests/test_install_sh.py`.

```python
from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_install_sh_uses_release_wheel_and_pdomain_index(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv_log = tmp_path / "uv.log"
    wheel_path_log = tmp_path / "curl-output.log"

    (bin_dir / "uv").write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {uv_log}\nexit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "uv").chmod(0o755)
    (bin_dir / "curl").write_text(
        f"""#!/bin/sh
out=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then shift; out="$1"; fi
  shift || true
done
if [ -n "$out" ]; then
  printf 'fake wheel' > "$out"
  printf '%s\\n' "$out" > {wheel_path_log}
else
  cat <<'JSON'
{{"tag_name":"v9.9.9","assets":[{{"browser_download_url":"https://example.invalid/pdomain_ocr_cli-9.9.9-py3-none-any.whl"}}]}}
JSON
fi
exit 0
""",
        encoding="utf-8",
    )
    (bin_dir / "curl").chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        ["sh", str(REPO / "install.sh")],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    args = uv_log.read_text(encoding="utf-8")
    assert "--extra-index-url" in args
    assert "https://pdomain.github.io/pdomain-index-pip/simple/" in args
    assert "pdomain_ocr_cli-9.9.9-py3-none-any.whl" in args
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest --no-cov tests/test_install_sh.py -v`

Expected: PASS if `install.sh` already conforms. If it fails, change `install.sh` to keep the contract tested above.

- [ ] **Step 3: Add installer tests to CI path**

Modify `Makefile`:

```make
installer-test: ## Run real installer contract tests with fake uv/curl/gh
	PYTEST_ADDOPTS=--no-cov uv run pytest tests/test_install_sh.py tests/test_install_ps1.py tests/test_install_ps1_cuda.py -v
```

Add `installer-test` to `ci` after `coverage`.

- [ ] **Step 4: Commit**

```bash
git add install.sh tests/test_install_sh.py Makefile
git commit -m "test: cover installer command contracts"
```

### Task 3: Add RunPolicy And BatchPlan

**Files:**
- Create: `pdomain_ocr_cli/_policy.py`
- Create: `pdomain_ocr_cli/_batch_plan.py`
- Create: `tests/test_policy.py`
- Create: `tests/test_batch_plan.py`
- Modify: `pdomain_ocr_cli/ocr_to_txt.py`
- Modify: `pdomain_ocr_cli/_pipeline.py`
- Modify: `tests/test_parse_args.py`
- Modify: `tests/test_batch_pages.py`
- Modify: `docs/usage/cli-usage.md`

- [ ] **Step 1: Write failing `RunPolicy` tests**

Create `tests/test_policy.py`.

```python
from __future__ import annotations

from types import SimpleNamespace

from pdomain_ocr_cli._policy import RunPolicy, build_run_policy


def _args(**overrides: object) -> SimpleNamespace:
    values = {
        "no_reorg": False,
        "save_json": False,
        "save_reorganize_diagnostics": False,
        "validate_reorg": False,
        "experimental_drop_layout_words": False,
        "extract_illustrations": False,
        "no_illustration_placeholders": False,
        "layout_debug": False,
        "layout_debug_dir": None,
        "layout_model": "pp-doclayout-plus-l",
        "no_update_check": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_policy_skips_layout_for_plain_no_reorg() -> None:
    policy = build_run_policy(_args(no_reorg=True))
    assert policy.do_reorg is False
    assert policy.layout_needed is False
    assert policy.layout_debug_announced is False


def test_policy_keeps_layout_for_no_reorg_extract_illustrations() -> None:
    policy = build_run_policy(_args(no_reorg=True, extract_illustrations=True))
    assert policy.do_reorg is False
    assert policy.layout_needed is True


def test_policy_diagnostic_export_requires_reorg_save_json_and_flag() -> None:
    policy = build_run_policy(
        _args(save_json=True, save_reorganize_diagnostics=True, no_reorg=False)
    )
    assert policy.want_diagnostic_export is True


def test_policy_emits_current_noop_warnings() -> None:
    policy = build_run_policy(
        _args(
            no_reorg=True,
            save_reorganize_diagnostics=True,
            validate_reorg=True,
            experimental_drop_layout_words=True,
            no_illustration_placeholders=True,
            layout_debug=True,
            layout_debug_dir="debug",
        )
    )
    joined = "\n".join(policy.warnings)
    assert "--save-reorganize-diagnostics has no effect with --no-reorg" in joined
    assert "--validate-reorg has no effect with --no-reorg" in joined
    assert "--layout-debug has no effect with --no-reorg" in joined
    assert "--experimental-drop-layout-words has no effect with --no-reorg" in joined
    assert "--no-illustration-placeholders has no effect with --no-reorg" in joined
```

- [ ] **Step 2: Run policy tests and confirm failure**

Run: `uv run pytest --no-cov tests/test_policy.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'pdomain_ocr_cli._policy'`.

- [ ] **Step 3: Implement `RunPolicy`**

Create `pdomain_ocr_cli/_policy.py`.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RunPolicyArgs(Protocol):
    no_reorg: bool
    save_json: bool
    save_reorganize_diagnostics: bool
    validate_reorg: bool
    experimental_drop_layout_words: bool
    extract_illustrations: bool
    no_illustration_placeholders: bool
    layout_debug: bool
    layout_debug_dir: str | None
    layout_model: str
    no_update_check: bool


@dataclass(frozen=True)
class RunPolicy:
    do_reorg: bool
    layout_configured: bool
    layout_needed: bool
    want_diagnostic_export: bool
    validate_reorg: bool
    drop_layout_words: bool
    emit_illustration_placeholders: bool
    layout_debug_announced: bool
    warnings: tuple[str, ...]


def build_run_policy(args: RunPolicyArgs) -> RunPolicy:
    do_reorg = not args.no_reorg
    layout_configured = args.layout_model != "none"
    layout_needed = layout_configured and (do_reorg or args.extract_illustrations)
    warnings: list[str] = []

    if args.no_reorg and args.save_reorganize_diagnostics:
        warnings.append(
            "warning: --save-reorganize-diagnostics has no effect with --no-reorg "
            "(diagnostics are produced only when reorganize runs); ignoring."
        )
    if args.no_reorg and args.validate_reorg:
        warnings.append(
            "warning: --validate-reorg has no effect with --no-reorg "
            "(validation compares pre/post reorganize word lists); ignoring."
        )
    if not layout_configured and args.layout_debug:
        warnings.append(
            "warning: --layout-debug has no effect with --layout-model none "
            "(no layout model runs, so no debug artifact is written); ignoring."
        )
    if args.no_reorg and args.layout_debug:
        warnings.append(
            "warning: --layout-debug has no effect with --no-reorg "
            "(the debug report is written from inside reorganize_page, which is skipped); ignoring."
        )
    if args.layout_debug_dir and not args.layout_debug:
        warnings.append(
            "warning: --layout-debug-dir has no effect without --layout-debug "
            "(the directory is only used when the debug artifact is enabled); ignoring."
        )
    if args.save_reorganize_diagnostics and not args.save_json:
        warnings.append(
            "warning: --save-reorganize-diagnostics has no effect without --save-json "
            "(the diagnostic bundle is written alongside the regular .json output, which requires --save-json); ignoring."
        )
    if args.no_reorg and args.experimental_drop_layout_words:
        warnings.append(
            "warning: --experimental-drop-layout-words has no effect with --no-reorg "
            "(the drop is applied inside reorganize_page, which is skipped); ignoring."
        )
    if args.no_reorg and args.no_illustration_placeholders:
        warnings.append(
            "warning: --no-illustration-placeholders has no effect with --no-reorg "
            "(placeholder emission happens inside reorganize_page, which is skipped); ignoring."
        )

    return RunPolicy(
        do_reorg=do_reorg,
        layout_configured=layout_configured,
        layout_needed=layout_needed,
        want_diagnostic_export=do_reorg and args.save_json and args.save_reorganize_diagnostics,
        validate_reorg=do_reorg and args.validate_reorg,
        drop_layout_words=do_reorg and args.experimental_drop_layout_words,
        emit_illustration_placeholders=not args.no_illustration_placeholders,
        layout_debug_announced=args.layout_debug and do_reorg,
        warnings=tuple(warnings),
    )
```

- [ ] **Step 4: Write failing `BatchPlan` tests**

Create `tests/test_batch_plan.py`.

```python
from __future__ import annotations

from pathlib import Path

import pytest

from pdomain_ocr_cli._batch_plan import BatchPlanError, build_batch_plan, positive_int


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def test_positive_int_rejects_zero_and_negative() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        positive_int("0")
    with pytest.raises(ValueError, match="positive integer"):
        positive_int("-1")
    assert positive_int("2") == 2


def test_batch_plan_rejects_flat_output_collisions(tmp_path: Path) -> None:
    a = tmp_path / "a" / "page.png"
    b = tmp_path / "b" / "page.png"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_bytes(b"png")
    b.write_bytes(b"png")

    with pytest.raises(BatchPlanError, match="output path collision"):
        build_batch_plan(
            inputs=[str(a), str(b)],
            recursive=False,
            output_dir=tmp_path / "out",
            is_image_file=_is_image,
            batch_pages=4,
        )


def test_batch_plan_precomputes_mirrored_jobs(tmp_path: Path) -> None:
    root = tmp_path / "images"
    nested = root / "ch1"
    nested.mkdir(parents=True)
    img = nested / "page.png"
    img.write_bytes(b"png")
    out = tmp_path / "out"

    plan = build_batch_plan(
        inputs=[str(root)],
        recursive=True,
        output_dir=out,
        is_image_file=_is_image,
        batch_pages=2,
    )

    assert len(plan.jobs) == 1
    assert plan.jobs[0].txt_path == out / "ch1" / "page.txt"
    assert plan.chunk_size == 2
```

- [ ] **Step 5: Run batch-plan tests and confirm failure**

Run: `uv run pytest --no-cov tests/test_batch_plan.py -v`

Expected: FAIL with missing module.

- [ ] **Step 6: Implement `BatchPlan`**

Create `pdomain_ocr_cli/_batch_plan.py` with:

```python
from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class BatchPlanError(ValueError):
    pass


@dataclass(frozen=True)
class PageJob:
    image_path: Path
    dest_dir: Path
    txt_path: Path
    json_path: Path


@dataclass(frozen=True)
class BatchPlan:
    jobs: tuple[PageJob, ...]
    mirror_root: Path | None
    chunk_size: int


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"expected a positive integer; got {value!r}") from exc
    if parsed < 1:
        raise ValueError(f"expected a positive integer; got {value!r}")
    return parsed


def collect_images(
    inputs: list[str],
    recursive: bool,
    *,
    is_image_file: Callable[[Path], bool],
) -> list[Path]:
    images: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            images.append(path)

    for raw in inputs:
        path = Path(raw)
        if path.is_file():
            if is_image_file(path):
                add(path)
            else:
                print(f"WARNING: skipping non-image file: {path}", file=sys.stderr)  # noqa: T201
        elif path.is_dir():
            pattern = "**/*" if recursive else "*"
            for child in sorted(path.glob(pattern)):
                if child.is_file() and is_image_file(child):
                    add(child)
        else:
            print(f"WARNING: skipping missing path: {path}", file=sys.stderr)  # noqa: T201
    return images


def compute_mirror_root(inputs: list[str], output_dir: Path | None) -> Path | None:
    if output_dir is None:
        return None
    dirs = [Path(raw).resolve() for raw in inputs if Path(raw).is_dir()]
    if not dirs:
        return None
    try:
        return Path(os.path.commonpath(dirs))
    except ValueError:
        print(
            "WARNING: input directories have no common ancestor; writing outputs flat under --output-dir instead of mirroring.",
            file=sys.stderr,
        )  # noqa: T201
        return None


def resolve_dest_dir(image_path: Path, output_dir: Path | None, mirror_root: Path | None) -> Path:
    if output_dir is not None and mirror_root is not None:
        try:
            rel = image_path.resolve().relative_to(mirror_root)
            return output_dir / rel.parent
        except ValueError:
            return output_dir
    if output_dir is not None:
        return output_dir
    return image_path.parent


def build_batch_plan(
    *,
    inputs: list[str],
    recursive: bool,
    output_dir: Path | None,
    is_image_file: Callable[[Path], bool],
    batch_pages: int,
) -> BatchPlan:
    if batch_pages < 1:
        raise BatchPlanError(f"--batch-pages must be >= 1; got {batch_pages}")
    images = collect_images(inputs, recursive, is_image_file=is_image_file)
    if not images:
        raise BatchPlanError("no valid image files found.")
    mirror_root = compute_mirror_root(inputs, output_dir)
    jobs: list[PageJob] = []
    seen_outputs: dict[Path, Path] = {}
    collisions: list[str] = []

    for image_path in images:
        dest_dir = resolve_dest_dir(image_path, output_dir, mirror_root)
        txt_path = dest_dir / image_path.with_suffix(".txt").name
        json_path = dest_dir / image_path.with_suffix(".json").name
        for artifact in (txt_path, json_path):
            previous = seen_outputs.get(artifact)
            if previous is not None and previous.resolve() != image_path.resolve():
                collisions.append(f"{artifact} from {previous} and {image_path}")
            seen_outputs[artifact] = image_path
        jobs.append(PageJob(image_path=image_path, dest_dir=dest_dir, txt_path=txt_path, json_path=json_path))

    if collisions:
        details = "; ".join(collisions)
        raise BatchPlanError(f"output path collision: {details}")

    return BatchPlan(jobs=tuple(jobs), mirror_root=mirror_root, chunk_size=batch_pages)
```

- [ ] **Step 7: Wire `positive_int` into argparse**

In `ocr_to_txt.py`, import `positive_int` and change `--batch-pages`:

```python
_ = p.add_argument(
    "--batch-pages",
    type=lambda s: positive_int(s),
    default=4,
    metavar="N",
    help="Number of pages to send to the OCR engine in a single batch call. Must be >= 1. Default: 4.",
)
```

Use this local wrapper so argparse errors are rendered cleanly:

```python
def _positive_batch_pages(s: str) -> int:
    try:
        return positive_int(s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
```

- [ ] **Step 8: Wire `RunPolicy` and `BatchPlan` into `main()`**

At the start of `main()` after coercing args:

```python
policy = build_run_policy(args)
for warning in policy.warnings:
    print(warning, file=sys.stderr)  # noqa: T201
```

Replace `layout_enabled` checks with `policy.layout_needed` for resolving/loading/detecting layout. Build the batch plan before resolving model files:

```python
try:
    batch_plan = build_batch_plan(
        inputs=args.inputs,
        recursive=args.recursive,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        is_image_file=_IS_IMAGE_FILE,
        batch_pages=args.batch_pages,
    )
except BatchPlanError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)  # noqa: T201
    sys.exit(1)
```

Use `batch_plan.jobs` in the processing loop, and `job.dest_dir`, `job.txt_path`, `job.json_path` instead of recomputing.

- [ ] **Step 9: Keep compatibility wrappers during the split**

Keep wrappers in `_pipeline.py` for `collect_images`, `compute_mirror_root`, `resolve_dest_dir`, and `output_paths_for`. Each wrapper calls the implementation in `_batch_plan.py`, so existing imports keep working while the deeper module becomes the source of truth.

- [ ] **Step 10: Run focused tests**

Run:

```bash
uv run pytest --no-cov tests/test_policy.py tests/test_batch_plan.py tests/test_parse_args.py tests/test_batch_pages.py tests/test_main_warnings.py -v
```

Expected: PASS.

- [ ] **Step 11: Update docs for `--batch-pages` and `--no-reorg` layout behavior**

Document that `--batch-pages` must be `>=1`, and that plain `--no-reorg` skips layout unless `--extract-illustrations` requires it.

- [ ] **Step 12: Commit**

```bash
git add pdomain_ocr_cli/_policy.py pdomain_ocr_cli/_batch_plan.py pdomain_ocr_cli/ocr_to_txt.py pdomain_ocr_cli/_pipeline.py tests/test_policy.py tests/test_batch_plan.py tests/test_parse_args.py tests/test_batch_pages.py tests/test_main_warnings.py docs/usage/cli-usage.md
git commit -m "refactor: add run policy and batch planning"
```

### Task 4: Add RuntimeSession And Normalize Runtime Errors

**Files:**
- Create: `pdomain_ocr_cli/_runtime.py`
- Create: `tests/test_runtime.py`
- Modify: `pdomain_ocr_cli/ocr_to_txt.py`
- Modify: `tests/test_main_errors.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing tests for batch runner exceptions and result mismatch**

Add to `tests/test_main_errors.py`:

```python
def test_main_batch_runner_error_reports_chunk_and_exits_1(
    mock_heavy_deps, monkeypatch, run_main, make_images, capsys
):
    mock_heavy_deps()
    imgs = make_images(2)
    out = imgs[0].parent / "out"

    def boom_batch(images, *, predictor, device, build_smaller=None, source_identifiers=None):
        raise RuntimeError("batch backend exploded")

    monkeypatch.setattr(ocr_to_txt, "_run_doctr_batch", boom_batch)

    with pytest.raises(SystemExit) as exc_info:
        run_main("--no-update-check", "--layout-model", "none", "-o", str(out), str(imgs[0]), str(imgs[1]))

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR processing batch" in captured.err
    assert "batch backend exploded" in captured.err
    assert "Done (2 error(s))" in captured.out
    assert not (out / f"{imgs[0].stem}.txt").exists()
    assert not (out / f"{imgs[1].stem}.txt").exists()


def test_main_batch_result_count_mismatch_is_clean_error(
    mock_heavy_deps, monkeypatch, run_main, make_images, capsys
):
    mock_heavy_deps()
    imgs = make_images(2)
    out = imgs[0].parent / "out"

    def short_batch(images, *, predictor, device, build_smaller=None, source_identifiers=None):
        return [FakePage(text="ONLY ONE")]

    monkeypatch.setattr(ocr_to_txt, "_run_doctr_batch", short_batch)

    with pytest.raises(SystemExit) as exc_info:
        run_main("--no-update-check", "--layout-model", "none", "-o", str(out), str(imgs[0]), str(imgs[1]))

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "batch returned 1 page(s) for 2 image(s)" in captured.err
    assert "Done (2 error(s))" in captured.out
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest --no-cov tests/test_main_errors.py::test_main_batch_runner_error_reports_chunk_and_exits_1 tests/test_main_errors.py::test_main_batch_result_count_mismatch_is_clean_error -v`

Expected: FAIL with unhandled exception or missing clean error.

- [ ] **Step 3: Implement runtime error types**

Create `pdomain_ocr_cli/_runtime.py`.

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class RuntimeSetupError(RuntimeError):
    pass


class BatchRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class DecodedImage:
    path: Path
    array: object
    source_identifier: str


class BatchRunner(Protocol):
    def __call__(self, images: list[object], **kwargs: object) -> list[object | None]: ...


def validate_batch_result_count(pages: list[object | None], expected: int) -> None:
    if len(pages) != expected:
        raise BatchRuntimeError(f"batch returned {len(pages)} page(s) for {expected} image(s)")


def run_batch_checked(
    runner: BatchRunner,
    images: list[object],
    *,
    predictor: object,
    device: str,
    source_identifiers: list[str],
) -> list[object | None]:
    try:
        pages = runner(
            images,
            predictor=predictor,
            device=device,
            source_identifiers=source_identifiers,
        )
    except Exception as exc:
        raise BatchRuntimeError(str(exc)) from exc
    validate_batch_result_count(pages, len(images))
    return pages
```

- [ ] **Step 4: Wire checked batch execution into `main()`**

Replace direct `_run_doctr_batch(...)` call with:

```python
try:
    chunk_pages = run_batch_checked(
        _run_doctr_batch,
        survivor_arrays,
        predictor=predictor,
        device=ops_device,
        source_identifiers=survivor_ids,
    )
except BatchRuntimeError as exc:
    print(f"ERROR processing batch {chunk_start // chunk_size + 1}: {exc}", file=sys.stderr)  # noqa: T201
    errors += len(survivor_paths)
    continue
```

Import `BatchRuntimeError` and `run_batch_checked`.

- [ ] **Step 5: Normalize model-resolution and layout-prefetch errors**

Wrap model resolution and layout prefetch:

```python
try:
    det_path, reco_path = resolve_ocr_models(args)
except Exception as exc:
    print(f"ERROR resolving OCR model files: {exc}", file=sys.stderr)  # noqa: T201
    sys.exit(1)

if policy.layout_needed:
    try:
        layout_repo, layout_revision, layout_descriptor = resolve_layout_source(args)
        if layout_repo is not None:
            _ = prefetch_layout_files(layout_repo, layout_revision)
    except Exception as exc:
        print(f"ERROR resolving layout model files: {exc}", file=sys.stderr)  # noqa: T201
        sys.exit(1)
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest --no-cov tests/test_runtime.py tests/test_main_errors.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pdomain_ocr_cli/_runtime.py pdomain_ocr_cli/ocr_to_txt.py tests/test_runtime.py tests/test_main_errors.py tests/conftest.py
git commit -m "fix: normalize batch runtime errors"
```

### Task 5: Add PageOutputTransaction And Secure Atomic Artifacts

**Files:**
- Create: `pdomain_ocr_cli/_artifacts.py`
- Create: `tests/test_artifacts.py`
- Modify: `pdomain_ocr_cli/ocr_to_txt.py`
- Modify: `pdomain_ocr_cli/_pipeline.py`
- Modify: `tests/test_pipeline_atomic_write.py`
- Modify: `tests/test_main_happy.py`
- Modify: `tests/test_main_errors.py`

- [ ] **Step 1: Write failing secure temp tests**

Create `tests/test_artifacts.py`.

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pdomain_ocr_cli._artifacts import atomic_write_bytes, atomic_write_text


def test_atomic_write_rejects_preexisting_symlink_temp_target(tmp_path: Path) -> None:
    target = tmp_path / "page.txt"
    outside = tmp_path / "outside.txt"
    outside.write_text("safe", encoding="utf-8")
    legacy_tmp = tmp_path / ".page.txt.tmp"
    legacy_tmp.symlink_to(outside)

    atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    assert outside.read_text(encoding="utf-8") == "safe"
    assert legacy_tmp.is_symlink()


def test_atomic_write_uses_unique_temp_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "page.txt"
    opened: list[str] = []
    real_open = os.open

    def tracking_open(path, flags, mode=0o777):
        opened.append(str(path))
        return real_open(path, flags, mode)

    monkeypatch.setattr("pdomain_ocr_cli._artifacts.os.open", tracking_open)
    atomic_write_text(target, "hello")

    assert target.read_text(encoding="utf-8") == "hello"
    assert all(name != str(tmp_path / ".page.txt.tmp") for name in opened)
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest --no-cov tests/test_artifacts.py -v`

Expected: FAIL because `_artifacts.py` does not exist.

- [ ] **Step 3: Implement unique-temp atomic helpers**

Create `pdomain_ocr_cli/_artifacts.py`.

```python
from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


def _fsync_parent_dir(path: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        _fsync_parent_dir(path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


class JsonDocumentLike(Protocol):
    def to_json_file(self, file_path: str | Path) -> None: ...


def atomic_write_json_document(path: Path, doc: JsonDocumentLike) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    os.close(fd)
    try:
        doc.to_json_file(tmp)
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_parent_dir(path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise
```

- [ ] **Step 4: Move existing atomic imports**

Update `_pipeline.py` to import and re-export `atomic_write_text` and `atomic_write_bytes` from `_artifacts.py` until all callers move.

```python
from pdomain_ocr_cli._artifacts import atomic_write_bytes, atomic_write_text
```

Remove old deterministic `_atomic_tmp_path` and `_atomic_write_raw` from `_pipeline.py`. Keep compatibility imports for public helper names by importing the unique-temp implementations from `_artifacts.py`.

- [ ] **Step 5: Update JSON and crop writes**

In `ocr_to_txt.py`, replace manual JSON temp:

```python
atomic_write_json_document(json_path, doc)
```

For crops, encode to bytes and write through the unique-temp atomic helper:

```python
ok, encoded = cv2_module.imencode(".jpg", crop)
if not ok:
    print(f"WARNING: cv2.imencode failed for {crop_path}", file=sys.stderr)  # noqa: T201
    continue
atomic_write_bytes(crop_path, bytes(encoded))
```

Update `_Cv2Like` protocol with `imencode`.

- [ ] **Step 6: Add PageOutputTransaction skeleton**

In `_artifacts.py`, add `PageOutputTransaction` to own artifact ordering:

```python
@dataclass
class PageOutputTransaction:
    txt_path: Path
    json_path: Path
    extra_paths: list[str]

    def write_text_last(self, text: str) -> None:
        atomic_write_text(self.txt_path, text)
```

Move more artifact methods into this class only after existing tests pass.

- [ ] **Step 7: Strengthen JSON envelope tests**

In `tests/test_main_happy.py`, change JSON existence assertion:

```python
import json

payload = json.loads((out / "page.json").read_text(encoding="utf-8"))
assert payload["source_lib"] == "pdomain_book_tools"
assert payload["source_identifier"] == "page.png"
assert payload["source_path"] == str(img)
assert isinstance(payload["pages"], list)
assert len(payload["pages"]) == 1
```

- [ ] **Step 8: Run focused tests**

Run:

```bash
uv run pytest --no-cov tests/test_artifacts.py tests/test_pipeline_atomic_write.py tests/test_main_happy.py tests/test_main_errors.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add pdomain_ocr_cli/_artifacts.py pdomain_ocr_cli/_pipeline.py pdomain_ocr_cli/ocr_to_txt.py tests/test_artifacts.py tests/test_pipeline_atomic_write.py tests/test_main_happy.py tests/test_main_errors.py
git commit -m "fix: secure page artifact writes"
```

### Task 6: Add Model Trust Boundary Warnings

**Files:**
- Create: `pdomain_ocr_cli/_model_security.py`
- Create: `tests/test_model_security.py`
- Modify: `pdomain_ocr_cli/ocr_to_txt.py`
- Modify: `README.md`
- Modify: `docs/usage/cli-usage.md`

- [ ] **Step 1: Write failing tests for model warnings**

Create `tests/test_model_security.py`.

```python
from __future__ import annotations

from types import SimpleNamespace

from pdomain_ocr_cli._model_security import model_security_warnings


def _args(**overrides: object) -> SimpleNamespace:
    values = {
        "hf_repo": "CT2534/pd-ocr-models",
        "model_version": None,
        "detection": None,
        "recognition": None,
        "layout_checkpoint": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_warns_when_default_model_revision_is_mutable() -> None:
    warnings = model_security_warnings(_args())
    assert any("mutable latest OCR model revision" in warning for warning in warnings)


def test_warns_for_custom_hf_repo() -> None:
    warnings = model_security_warnings(_args(hf_repo="someone/model"))
    assert any("custom Hugging Face OCR repo" in warning for warning in warnings)


def test_warns_for_local_pt_paths() -> None:
    warnings = model_security_warnings(_args(detection="det.pt", recognition="reco.pt"))
    assert any("local PyTorch checkpoint" in warning for warning in warnings)


def test_warns_for_layout_checkpoint() -> None:
    warnings = model_security_warnings(_args(layout_checkpoint="layout.pt"))
    assert any("layout checkpoint" in warning for warning in warnings)
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest --no-cov tests/test_model_security.py -v`

Expected: FAIL with missing module.

- [ ] **Step 3: Implement warnings**

Create `pdomain_ocr_cli/_model_security.py`.

```python
from __future__ import annotations

from typing import Protocol

from pdomain_ocr_cli._hf_models import DEFAULT_HF_REPO


class ModelSecurityArgs(Protocol):
    hf_repo: str
    model_version: str | None
    detection: str | None
    recognition: str | None
    layout_checkpoint: str | None


def model_security_warnings(args: ModelSecurityArgs) -> tuple[str, ...]:
    warnings: list[str] = []
    if args.hf_repo == DEFAULT_HF_REPO and args.model_version is None:
        warnings.append(
            "warning: using mutable latest OCR model revision; for reproducible and safer runs, pass --model-version pinned to a trusted tag or commit."
        )
    if args.hf_repo != DEFAULT_HF_REPO:
        warnings.append(
            "warning: custom Hugging Face OCR repo is a model trust boundary; only use repos you trust because PyTorch checkpoint loading can execute code."
        )
    if args.detection or args.recognition:
        warnings.append(
            "warning: local PyTorch checkpoint paths are trusted executable inputs; only pass .pt files from trusted sources."
        )
    if args.layout_checkpoint:
        warnings.append(
            "warning: layout checkpoint is a model trust boundary; only use trusted local paths or Hugging Face repos."
        )
    return tuple(warnings)
```

- [ ] **Step 4: Print warnings once during startup**

In `main()`, after no-op warnings and before resolving models:

```python
for warning in model_security_warnings(args):
    print(warning, file=sys.stderr)  # noqa: T201
```

- [ ] **Step 5: Add docs**

Add a "Model trust boundary" section to `README.md` and `docs/usage/cli-usage.md`:

```markdown
### Model trust boundary

OCR and layout model checkpoints are trusted inputs. The default model source is maintained by this project, but mutable latest revisions can change. For reproducible runs, pass `--model-version` pinned to a tag or commit. Custom `--hf-repo`, local `--detection` / `--recognition`, and `--layout-checkpoint` values should only come from sources you trust.
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest --no-cov tests/test_model_security.py tests/test_main_warnings.py -v
```

Expected: PASS. Update any stderr assertions in `tests/test_main_warnings.py` in this task so the new model-security warnings are asserted deliberately.

- [ ] **Step 7: Commit**

```bash
git add pdomain_ocr_cli/_model_security.py pdomain_ocr_cli/ocr_to_txt.py tests/test_model_security.py tests/test_main_warnings.py README.md docs/usage/cli-usage.md
git commit -m "feat: warn on model trust boundaries"
```

### Task 7: Extract Startup Notices

**Files:**
- Create: `pdomain_ocr_cli/_startup_notices.py`
- Create: `tests/test_startup_notices.py`
- Modify: `pdomain_ocr_cli/ocr_to_txt.py`
- Modify: `tests/test_update_check_bypass.py`
- Modify: `tests/test_gpu_nudge.py`

- [ ] **Step 1: Write failing startup-notice tests**

Create `tests/test_startup_notices.py`.

```python
from __future__ import annotations

from types import SimpleNamespace

from pdomain_ocr_cli._startup_notices import update_check_disabled


def test_update_check_disabled_by_flag(monkeypatch) -> None:
    monkeypatch.delenv("PD_OCR_NO_UPDATE_CHECK", raising=False)
    assert update_check_disabled(SimpleNamespace(no_update_check=True)) is True


def test_update_check_disabled_by_env(monkeypatch) -> None:
    monkeypatch.setenv("PD_OCR_NO_UPDATE_CHECK", "1")
    assert update_check_disabled(SimpleNamespace(no_update_check=False)) is True


def test_update_check_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PD_OCR_NO_UPDATE_CHECK", raising=False)
    assert update_check_disabled(SimpleNamespace(no_update_check=False)) is False
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest --no-cov tests/test_startup_notices.py -v`

Expected: FAIL with missing module.

- [ ] **Step 3: Implement startup notices**

Create `pdomain_ocr_cli/_startup_notices.py`.

```python
from __future__ import annotations

import os
import threading
from typing import Callable, Protocol


class UpdateArgs(Protocol):
    no_update_check: bool


def env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def update_check_disabled(args: UpdateArgs) -> bool:
    return args.no_update_check or env_truthy("PD_OCR_NO_UPDATE_CHECK")


def start_update_check_thread(
    *,
    disabled: bool,
    check_for_update: Callable[[], None],
) -> threading.Thread | None:
    if disabled:
        return None
    thread = threading.Thread(target=check_for_update, daemon=True)
    thread.start()
    return thread
```

Move GPU nudge helpers into this module: `_should_nudge_gpu_install`, `_maybe_print_gpu_nudge`, and the process cache. Keep same function names exported from `ocr_to_txt.py` as compatibility aliases to the new module so existing tests continue to patch stable names.

- [ ] **Step 4: Add main integration test for env gate**

In `tests/test_update_check_bypass.py`, add:

```python
def test_main_env_var_disables_update_check(mock_heavy_deps, monkeypatch, run_main, single_image):
    mock_heavy_deps()
    img, out = single_image
    monkeypatch.setenv("PD_OCR_NO_UPDATE_CHECK", "1")
    calls: list[bool] = []
    monkeypatch.setattr(ocr_to_txt, "_start_update_check_thread", lambda disabled: calls.append(disabled))

    run_main("--layout-model", "none", "-o", str(out), str(img))

    assert calls == [True]
```

- [ ] **Step 5: Wire module into `main()`**

Replace inline gate:

```python
update_thread = _start_update_check_thread(disabled=update_check_disabled(args))
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest --no-cov tests/test_startup_notices.py tests/test_update_check_bypass.py tests/test_gpu_nudge.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pdomain_ocr_cli/_startup_notices.py pdomain_ocr_cli/ocr_to_txt.py tests/test_startup_notices.py tests/test_update_check_bypass.py tests/test_gpu_nudge.py
git commit -m "refactor: extract startup notice policy"
```

### Task 8: Introduce RuntimeSession Test Adapter

**Files:**
- Modify: `pdomain_ocr_cli/_runtime.py`
- Modify: `pdomain_ocr_cli/ocr_to_txt.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_runtime.py`

- [ ] **Step 1: Add failing test for one runtime adapter seam**

In `tests/test_runtime.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

from pdomain_ocr_cli._runtime import DefaultRuntimeSession

def test_default_runtime_session_runs_checked_batch() -> None:
    pages = [SimpleNamespace(text="A"), SimpleNamespace(text="B")]

    def runner(images, *, predictor, device, source_identifiers):
        assert predictor == "predictor"
        assert device == "cpu"
        assert source_identifiers == ["a.png", "b.png"]
        return pages

    session = DefaultRuntimeSession(predictor="predictor", device="cpu", runner=runner)
    result = session.run_batch([object(), object()], source_identifiers=["a.png", "b.png"])
    assert [page.text for page in result] == ["A", "B"]
```

- [ ] **Step 2: Implement runtime session class**

In `_runtime.py`:

```python
class RuntimeSession(Protocol):
    predictor: object
    device: str

    def run_batch(
        self,
        images: list[object],
        *,
        source_identifiers: list[str],
    ) -> list[object | None]: ...


@dataclass
class DefaultRuntimeSession:
    predictor: object
    device: str
    runner: BatchRunner

    def run_batch(self, images: list[object], *, source_identifiers: list[str]) -> list[object | None]:
        return run_batch_checked(
            self.runner,
            images,
            predictor=self.predictor,
            device=self.device,
            source_identifiers=source_identifiers,
        )
```

- [ ] **Step 3: Update tests to patch one runtime adapter**

Change `mock_heavy_deps` to keep its existing return namespace but patch one runtime factory instead of patching `_run_doctr_batch`, `_pick_device`, and `_load_predictor` separately. The fixture must expose `batch_calls`, `predictor`, and `captured_pages` exactly as it does now.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest --no-cov tests/test_runtime.py tests/test_main_happy.py tests/test_main_errors.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pdomain_ocr_cli/_runtime.py pdomain_ocr_cli/ocr_to_txt.py tests/conftest.py tests/test_runtime.py
git commit -m "refactor: introduce runtime session seam"
```

### Task 9: Strengthen JSON And Artifact Contract Tests

**Files:**
- Modify: `tests/test_main_happy.py`
- Modify: `tests/test_pipeline_integration.py`
- Modify: `tests/test_artifacts.py`
- Modify: `docs/usage/cli-usage.md`

- [ ] **Step 1: Add fast JSON envelope assertions**

In `tests/test_main_happy.py`, assert the full envelope for `--save-json`:

```python
payload = json.loads((out / "page.json").read_text(encoding="utf-8"))
assert set(payload) == {"source_lib", "source_identifier", "source_path", "pages"}
assert payload["source_lib"] == "pdomain_book_tools"
assert payload["source_identifier"] == "page.png"
assert payload["source_path"] == str(img)
assert len(payload["pages"]) == 1
```

- [ ] **Step 2: Add slow JSON envelope assertions**

In `tests/test_pipeline_integration.py::test_ocr_save_json_writes_sidecar`, parse JSON and assert:

```python
payload = json.loads(out_json.read_text(encoding="utf-8"))
assert payload["source_lib"] == "pdomain_book_tools"
assert payload["source_identifier"] == title_image_path.name
assert payload["source_path"] == str(title_image_path)
assert len(payload["pages"]) == 1
```

- [ ] **Step 3: Run tests**

Run:

```bash
uv run pytest --no-cov tests/test_main_happy.py::test_main_save_json_writes_sidecar tests/test_pipeline_integration.py::test_ocr_save_json_writes_sidecar --run-slow -v
```

Expected: PASS.

- [ ] **Step 4: Document JSON contract**

In `docs/usage/cli-usage.md`, add the exact top-level JSON keys and note that downstream tools can rely on them.

- [ ] **Step 5: Commit**

```bash
git add tests/test_main_happy.py tests/test_pipeline_integration.py tests/test_artifacts.py docs/usage/cli-usage.md
git commit -m "test: assert JSON sidecar contract"
```

### Task 10: Add Required Real OCR And Layout Coverage

**Files:**
- Modify: `tests/test_pipeline_integration.py`
- Add fixtures under: `tests/fixtures/`
- Modify: `Makefile`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add default-layout slow test**

In `tests/test_pipeline_integration.py`, add a helper that does not force `--layout-model none`:

```python
def _invoke_main_default_layout(monkeypatch, shared_predictor, image: Path, output_dir: Path, *extra_args: str) -> int:
    monkeypatch.setattr(ocr_to_txt, "_load_predictor", lambda det, reco: shared_predictor)
    argv = [
        "pd-ocr",
        "--no-update-check",
        "--model-version",
        PINNED_MODEL_REVISION,
        "--output-dir",
        str(output_dir),
        *extra_args,
        str(image),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    try:
        ocr_to_txt.main()
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 1
    return 0
```

Add test:

```python
def test_ocr_default_layout_model_runs_successfully(
    title_image_path: Path, tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    rc = _invoke_main_default_layout(monkeypatch, shared_predictor, title_image_path, tmp_path)
    captured = capsys.readouterr()
    assert rc == 0, captured.out + captured.err
    assert "Layout model loaded:" in captured.out
    assert "layout:" in captured.out
    assert (tmp_path / "title_page_001.txt").exists()
```

- [ ] **Step 2: Add default-layout debug test**

```python
def test_ocr_default_layout_debug_writes_report(
    title_image_path: Path, tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    debug_dir = tmp_path / "debug"
    rc = _invoke_main_default_layout(
        monkeypatch,
        shared_predictor,
        title_image_path,
        tmp_path,
        "--layout-debug",
        "--layout-debug-dir",
        str(debug_dir),
    )
    captured = capsys.readouterr()
    assert rc == 0, captured.out + captured.err
    assert "layout-debug:" in captured.out
    assert (debug_dir / "title_page_001.layout-debug.txt").exists()
```

- [ ] **Step 3: Add fixture corpus tests**

Add at least:
- `tests/fixtures/blank_page.png`
- `tests/fixtures/two_column_page.png`
- `tests/fixtures/rotated_page.png`
- `tests/fixtures/illustrated_page.png`

Add token/structure tests using non-exact assertions:

```python
@pytest.mark.parametrize(
    ("fixture_name", "expected_tokens"),
    [
        ("title_page_001.png", ["french", "furniture", "decoration"]),
        ("two_column_page.png", ["left", "right"]),
        ("rotated_page.png", ["rotated"]),
    ],
)
def test_ocr_fixture_corpus_recovers_expected_tokens(
    fixture_name: str, expected_tokens: list[str], tmp_path: Path, shared_predictor, monkeypatch, capsys
):
    image = FIXTURES_DIR / fixture_name
    if not image.exists():
        pytest.fail(f"missing required fixture: {image}")
    rc = _invoke_main(monkeypatch, shared_predictor, image, tmp_path)
    captured = capsys.readouterr()
    assert rc == 0, captured.out + captured.err
    text = (tmp_path / image.with_suffix(".txt").name).read_text(encoding="utf-8").lower()
    for token in expected_tokens:
        assert token in text
```

- [ ] **Step 4: Add Make targets**

In `Makefile`:

```make
test-integration: ## Run real OCR integration tests
	uv run pytest --no-cov tests/test_pipeline_integration.py -v --run-slow

test-layout-integration: ## Run real default-layout integration tests
	uv run pytest --no-cov tests/test_pipeline_integration.py -v --run-slow -k "default_layout"
```

- [ ] **Step 5: Run slow tests**

Run:

```bash
uv run pytest --no-cov tests/test_pipeline_integration.py -v --run-slow
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_pipeline_integration.py tests/fixtures Makefile .github/workflows/ci.yml
git commit -m "test: cover real OCR and default layout"
```

### Task 11: Harden CI, Release, Wheel Smoke, And Dependency Reproducibility

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `Makefile`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `DEVELOPMENT.md`
- Modify: `README.md`
- Create: `tests/test_workflows_static.py`

- [ ] **Step 1: Add wheel smoke target**

Modify `Makefile`:

```make
PYTHON_VERSIONS ?= 3.11 3.12 3.13

wheel-smoke: build ## Install built wheel into isolated envs for every supported Python and run console script
	@for py in $(PYTHON_VERSIONS); do \
		echo "wheel-smoke: Python $$py"; \
		tmpdir=$$(mktemp -d); \
		trap 'rm -rf "$$tmpdir"' EXIT; \
		uv venv "$$tmpdir/venv" --python "$$py"; \
		UV_PROJECT_ENVIRONMENT="$$tmpdir/venv" uv pip install dist/*.whl --extra-index-url https://pdomain.github.io/pdomain-index-pip/simple/; \
		"$$tmpdir/venv/bin/pd-ocr" --version; \
		rm -rf "$$tmpdir"; \
	done

wheel-smoke-one: build ## Install built wheel for one Python version; set PYTHON_VERSION=3.11/3.12/3.13
	@test -n "$(PYTHON_VERSION)" || (echo "PYTHON_VERSION is required"; exit 2)
	tmpdir=$$(mktemp -d); \
	trap 'rm -rf "$$tmpdir"' EXIT; \
	uv venv "$$tmpdir/venv" --python "$(PYTHON_VERSION)"; \
	UV_PROJECT_ENVIRONMENT="$$tmpdir/venv" uv pip install dist/*.whl --extra-index-url https://pdomain.github.io/pdomain-index-pip/simple/; \
	"$$tmpdir/venv/bin/pd-ocr" --version
```

Add `wheel-smoke` to `ci`.

- [ ] **Step 2: Add CI Python matrix**

In `.github/workflows/ci.yml`, replace single Python env with matrix:

```yaml
strategy:
  fail-fast: false
  matrix:
    python-version: ["3.11", "3.12", "3.13"]
env:
  UV_PYTHON: ${{ matrix.python-version }}
  CUDA_VISIBLE_DEVICES: ""
steps:
  - uses: actions/checkout@<pinned-sha>
    with:
      fetch-depth: 0
      persist-credentials: false
  - uses: astral-sh/setup-uv@<pinned-sha>
    with:
      version: "0.9.17"
  - run: make ci PYTHON_VERSIONS="${{ matrix.python-version }}"
```

Use actual current full commit SHAs when editing.

- [ ] **Step 3: Add release test gate**

In `.github/workflows/release.yml`, insert before `uv build`:

```yaml
- name: Run release CI gate
  run: make ci-slow
```

Pin all actions by full commit SHA and set `persist-credentials: false` on checkout.

- [ ] **Step 4: Remove shell interpolation for tag in dispatch**

Change:

```yaml
env:
  GH_TOKEN: ${{ secrets.PDOMAIN_INDEX_DISPATCH_TOKEN }}
  RELEASE_TAG: ${{ github.ref_name }}
run: |
  gh api -X POST /repos/pdomain/pdomain-index-pip/dispatches \
    -f event_type=pd-release-published \
    -F 'client_payload[repo]=pdomain-ocr-cli' \
    -F "client_payload[tag]=$RELEASE_TAG" || \
    echo "::warning::pdomain-index-pip dispatch failed; index will catch up via 15-min cron"
```

- [ ] **Step 5: Resolve `pdomain-ops` reproducibility**

Release `pdomain-ops` to `pdomain-index-pip`, then change `pyproject.toml`:

```toml
pdomain-ops = { index = "pdomain-index-pip" }
```

Publish `pdomain-ops` to `pdomain-index-pip`, then change the source mapping to the package index. Add a release-blocking check in `Makefile` so the repo cannot release while `pdomain-ops` is path-sourced:

```make
check-release-deps:
	@uv run python -c 'import tomllib; p=tomllib.load(open("pyproject.toml","rb")); src=p.get("tool",{}).get("uv",{}).get("sources",{}).get("pdomain-ops",{}); raise SystemExit("pdomain-ops must not be path-sourced for release") if "path" in src else 0'
```

Add `check-release-deps` to the release CI gate. The release path must fail until `pdomain-ops` resolves from the package index.

- [ ] **Step 6: Add static workflow tests**

Create `tests/test_workflows_static.py`:

```python
from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_release_runs_ci_before_build() -> None:
    text = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "make ci-slow" in text
    assert text.index("make ci-slow") < text.index("uv build")


def test_release_uses_env_for_ref_name_in_shell() -> None:
    text = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
    run_blocks = [line for line in text.splitlines() if "client_payload[tag]" in line]
    assert all("${{ github.ref_name }}" not in line for line in run_blocks)
    assert "RELEASE_TAG: ${{ github.ref_name }}" in text


def test_ci_declares_supported_python_matrix() -> None:
    text = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert '"3.11"' in text
    assert '"3.12"' in text
    assert '"3.13"' in text


def test_makefile_wheel_smoke_covers_supported_python_versions() -> None:
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "PYTHON_VERSIONS ?= 3.11 3.12 3.13" in text
    assert "wheel-smoke:" in text
```

- [ ] **Step 7: Run workflow tests**

Run: `uv run pytest --no-cov tests/test_workflows_static.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/release.yml Makefile pyproject.toml uv.lock DEVELOPMENT.md README.md tests/test_workflows_static.py
git commit -m "ci: harden release and wheel verification"
```

### Task 12: Documentation Pass

**Files:**
- Modify: `README.md`
- Modify: `docs/usage/cli-usage.md`
- Modify: `docs/architecture/layout-aware-ocr.md`
- Modify: `DEVELOPMENT.md`
- Modify: `docs/plans/roadmap.md`

- [ ] **Step 1: Update README install and security details**

Ensure README states:
- Windows installer is self-contained when piped.
- Both installers use the release wheel and pdomain package index.
- Custom model checkpoints are trusted inputs.
- `--no-update-check` disables GitHub network access.
- Plain `--no-reorg` skips layout unless illustration extraction requires it.

- [ ] **Step 2: Update CLI usage docs**

Ensure `docs/usage/cli-usage.md` contains:
- `--batch-pages N` requires `N >= 1`.
- JSON sidecar top-level keys.
- Model trust boundary.
- Update-check network behavior.

- [ ] **Step 3: Update architecture docs**

Ensure `docs/architecture/layout-aware-ocr.md` reflects:
- Default layout integration is covered by slow tests.
- `--no-reorg` layout behavior.
- Artifact transaction invariant: final `.txt` means page completed.

- [ ] **Step 4: Update development docs**

Ensure `DEVELOPMENT.md` states:
- `make ci` includes wheel smoke and installer contract tests.
- `make ci-slow` is release-required.
- Supported Python versions are exercised in CI.
- Release cannot proceed with path-sourced runtime dependencies.

- [ ] **Step 5: Run docs/static checks**

Run:

```bash
uv run pre-commit run --all-files
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/usage/cli-usage.md docs/architecture/layout-aware-ocr.md DEVELOPMENT.md docs/plans/roadmap.md
git commit -m "docs: align review remediation behavior"
```

### Task 13: Final Spec Compliance Validation

**Files:**
- Create: `docs/research/2026-05-29-pdomain-ocr-cli-review-remediation-validation.md`

- [ ] **Step 1: Run focused suite**

Run:

```bash
uv run pytest --no-cov \
  tests/test_policy.py \
  tests/test_batch_plan.py \
  tests/test_runtime.py \
  tests/test_artifacts.py \
  tests/test_model_security.py \
  tests/test_startup_notices.py \
  tests/test_install_sh.py \
  tests/test_install_ps1.py \
  tests/test_workflows_static.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run full fast CI**

Run:

```bash
make ci AI=1
```

Expected: PASS.

- [ ] **Step 3: Run full slow CI**

Run:

```bash
make ci-slow AI=1
```

Expected: PASS.

- [ ] **Step 4: Run explicit installer contracts**

Run:

```bash
make installer-test AI=1
```

Expected: PASS.

- [ ] **Step 5: Run explicit wheel smoke**

Run:

```bash
make wheel-smoke AI=1
```

Expected: PASS and output includes one `pd-ocr <version>` run for Python 3.11, one for Python 3.12, and one for Python 3.13.

- [ ] **Step 6: Validate no legacy deterministic temps remain**

Run:

```bash
rg -n '"\\.[^"]+\\.tmp"|with_name\\(f"\\.|\\.tmp\\.jpg|\\.json\\.tmp|\\.txt\\.tmp' pdomain_ocr_cli tests
```

Expected: no production hits that create deterministic artifact temp names. Test fixtures may mention legacy names only to assert they are not used.

- [ ] **Step 7: Validate no release workflow mutable action refs remain**

Run:

```bash
uv run python - <<'PY'
from pathlib import Path
import re
for path in [Path(".github/workflows/ci.yml"), Path(".github/workflows/release.yml")]:
    text = path.read_text()
    refs = re.findall(r"uses:\\s*([^\\s]+)", text)
    bad = [ref for ref in refs if "@" in ref and not re.search(r"@[0-9a-f]{40}$", ref)]
    if bad:
        raise SystemExit(f"{path}: mutable action refs: {bad}")
PY
```

Expected: no output, exit 0.

- [ ] **Step 8: Validate spec coverage matrix**

Create `docs/research/2026-05-29-pdomain-ocr-cli-review-remediation-validation.md` with this exact structure filled in:

```markdown
# pdomain-ocr-cli Review Remediation Validation

Date: 2026-05-29

## Commands

- `uv run pytest --no-cov ... focused suite`: PASS
- `make ci AI=1`: PASS
- `make ci-slow AI=1`: PASS
- `make installer-test AI=1`: PASS
- `make wheel-smoke AI=1`: PASS on Python 3.11, 3.12, and 3.13
- deterministic temp scan: PASS
- workflow action pin scan: PASS

## Spec Coverage

| Finding | Evidence |
|---|---|
| Windows piped installer works | `tests/test_install_ps1.py::test_install_ps1_piped_mode_is_self_contained_and_uses_pdomain_index` |
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

## Architecture Compliance

- `RunPolicy` owns effective flag behavior.
- `BatchPlan` owns image expansion and output collision preflight.
- `RuntimeSession` owns the heavy runtime seam.
- `PageOutputTransaction` / artifact helpers own atomic artifact writes.
- `ocr_to_txt.main()` remains orchestration, not detailed policy or artifact implementation.
```

- [ ] **Step 9: Commit validation report**

```bash
git add docs/research/2026-05-29-pdomain-ocr-cli-review-remediation-validation.md
git commit -m "docs: validate review remediation"
```

---

## Self-Review Checklist For This Plan

- [x] Covers every code review finding.
- [x] Covers every test review finding.
- [x] Covers every security review finding.
- [x] Covers every architecture recommendation that should be implemented now.
- [x] Includes tests before implementation for each behavior change.
- [x] Includes installer, wheel, slow OCR, default layout, release, and workflow validation.
- [x] Includes explicit validation that the built work follows the spec.
- [x] Contains no "later", "TBD", or follow-up escape hatches.
