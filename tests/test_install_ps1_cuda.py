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
        capture_output=True,
        text=True,
        check=True,
    )


def test_get_cuda_tag_strips_dot():
    assert _pwsh("Get-CudaTag '12.4'").stdout.strip() == "cu124"


def test_get_book_tools_extras_gpu_at_or_above_124():
    assert _pwsh("Get-BookToolsExtras '12.4'").stdout.strip() == "[gpu]"
    assert _pwsh("Get-BookToolsExtras '12.8'").stdout.strip() == "[gpu]"


def test_get_book_tools_extras_empty_below_124():
    assert _pwsh("Get-BookToolsExtras '12.1'").stdout.strip() == ""


def test_get_cuda_version_env_override():
    assert _pwsh("$env:CUDA_VERSION='12.6'; Get-CudaVersion").stdout.strip() == "12.6"


def test_get_cuda_version_parses_smi_q_output():
    body = (
        "$env:CUDA_VERSION=$null\n"
        "function nvidia-smi { 'CUDA Version                          : 12.4' }\n"
        "Get-CudaVersion"
    )
    # The shadowed function ignores $args, so both the -q and plain calls return
    # the same string; the -q regex matches first and returns "12.4".
    assert _pwsh(body).stdout.strip() == "12.4"


def test_get_cuda_version_parses_plain_smi_header():
    body = (
        "$env:CUDA_VERSION=$null\n"
        "function nvidia-smi { if ($args -contains '-q') { '' } "
        "else { '| NVIDIA-SMI ... CUDA Version: 12.2   |' } }\n"
        "Get-CudaVersion"
    )
    # -q branch returns '' (no match); plain branch returns the header with 12.2.
    assert _pwsh(body).stdout.strip() == "12.2"


def test_get_cuda_version_null_when_smi_gives_nothing():
    body = "$env:CUDA_VERSION=$null\nfunction nvidia-smi { '' }\nGet-CudaVersion"
    # Both -q and plain branches get '' — neither regex matches — function returns
    # $null. PowerShell writes nothing to stdout for a $null return value.
    assert _pwsh(body).stdout.strip() == ""
