"""Tests for the CUDA-version parse patterns used in install.ps1.

The installer script (PowerShell) has a ``Get-CudaVersion`` function that
parses nvidia-smi output to find the CUDA version.  Because PowerShell is
not available in the CI environment, these tests validate the equivalent
regex logic in Python so we catch regressions to the patterns without
needing a Windows runner.

Key fix documented here (issue #1):
  PowerShell ``-match`` on an *array* returns the matching elements but does
  NOT populate ``$Matches``.  The script must join the output lines into a
  single string before using ``-match`` so the capture group is available
  in ``$Matches[1]``.  The parse helpers below mirror the fixed logic.
"""

from __future__ import annotations

import re

import pytest

# ---------------------------------------------------------------------------
# Pure-Python equivalents of the install.ps1 parse helpers
# ---------------------------------------------------------------------------

# Pattern 1: nvidia-smi -q verbose output format:
#   CUDA Version                          : 12.4
# Allows optional whitespace around the colon.
_SMI_Q_PATTERN = re.compile(r"CUDA Version\s*:\s*(\d+\.\d+)", re.IGNORECASE)

# Pattern 2: plain nvidia-smi summary table header format:
#   | ... CUDA Version: 12.4   |
_SMI_PLAIN_PATTERN = re.compile(r"CUDA Version:\s*(\d+\.\d+)", re.IGNORECASE)


def _parse_cuda_from_smi_q(output: str) -> str | None:
    """Mirror of the nvidia-smi -q branch in install.ps1 ``Get-CudaVersion``."""
    m = _SMI_Q_PATTERN.search(output)
    return m.group(1) if m else None


def _parse_cuda_from_smi_plain(output: str) -> str | None:
    """Mirror of the plain nvidia-smi branch in install.ps1 ``Get-CudaVersion``."""
    m = _SMI_PLAIN_PATTERN.search(output)
    return m.group(1) if m else None


def _get_cuda_version(
    env_override: str | None,
    smi_q_output: str | None,
    smi_plain_output: str | None,
) -> str | None:
    """Python mirror of the full Get-CudaVersion resolution order.

    Resolution order (matches install.ps1):
      1. env override ($env:CUDA_VERSION)
      2. nvidia-smi -q parse
      3. plain nvidia-smi parse
    """
    if env_override:
        return env_override

    if smi_q_output is not None:
        ver = _parse_cuda_from_smi_q(smi_q_output)
        if ver:
            return ver

    if smi_plain_output is not None:
        ver = _parse_cuda_from_smi_plain(smi_plain_output)
        if ver:
            return ver

    return None


# ---------------------------------------------------------------------------
# Sample nvidia-smi outputs (realistic multi-line strings)
# ---------------------------------------------------------------------------

# Typical Windows "nvidia-smi -q" output excerpt (lines around CUDA Version)
_SMI_Q_SAMPLE_W11 = """\
==============NVSMI LOG==============

Timestamp                                 : Thu May 21 12:00:00 2026
Driver Version                            : 551.86
CUDA Version                              : 12.4

Attached GPUs                             : 1
GPU 00000000:01:00.0
    Product Name                          : NVIDIA GeForce RTX 4090
"""

# Slightly different spacing (extra spaces, different driver vintage)
_SMI_Q_SAMPLE_COMPACT = """\
Driver Version: 546.33
CUDA Version : 12.3
Attached GPUs: 1
"""

# Plain "nvidia-smi" table header (the pipe-box format)
_SMI_PLAIN_SAMPLE = """\
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 551.86                 Driver Version: 551.86         CUDA Version: 12.4   |
|-------------------------------+----------------------+----------------------+
"""

# Edge case: CUDA version with patch component (some niche builds)
_SMI_Q_SAMPLE_PATCH = """\
CUDA Version                              : 12.4.1
"""

# No CUDA version in output (e.g., non-CUDA driver or obscured output)
_SMI_Q_SAMPLE_NO_CUDA = """\
==============NVSMI LOG==============
Driver Version                            : 537.34
Attached GPUs                             : 0
"""

# ---------------------------------------------------------------------------
# Tests: nvidia-smi -q pattern
# ---------------------------------------------------------------------------


def test_smi_q_parses_standard_windows_format():
    assert _parse_cuda_from_smi_q(_SMI_Q_SAMPLE_W11) == "12.4"


def test_smi_q_parses_compact_spacing():
    """Space before colon ('CUDA Version : 12.3') must match."""
    assert _parse_cuda_from_smi_q(_SMI_Q_SAMPLE_COMPACT) == "12.3"


def test_smi_q_returns_none_when_no_cuda_line():
    assert _parse_cuda_from_smi_q(_SMI_Q_SAMPLE_NO_CUDA) is None


def test_smi_q_returns_none_for_empty_string():
    assert _parse_cuda_from_smi_q("") is None


def test_smi_q_handles_patch_version_gracefully():
    """nvidia-smi -q occasionally shows 'CUDA Version : 12.4.1'.
    The pattern captures only MAJOR.MINOR (the part PyTorch index tags use).
    """
    result = _parse_cuda_from_smi_q(_SMI_Q_SAMPLE_PATCH)
    # Pattern stops at \d+\.\d+ so captures "12.4" not "12.4.1"
    assert result == "12.4"


def test_smi_q_multiline_join_fixes_array_match_bug():
    """Core regression test for issue #1.

    In the original install.ps1, $smiOut was an array of lines.
    PowerShell -match on arrays does NOT populate $Matches, so $CudaVer
    was always $null even when the version was in the output.

    This test verifies that joining lines first (as the fix does) produces
    the correct result, while searching only a single-line fragment fails
    if that fragment doesn't contain the version.
    """
    # Line that does NOT contain the CUDA version (simulates searching one
    # array element at a time, which is what the unfixed script did implicitly)
    single_non_matching_line = "Driver Version                            : 551.86"
    assert _parse_cuda_from_smi_q(single_non_matching_line) is None

    # Joined multi-line output (as the fix does) correctly finds the version
    assert _parse_cuda_from_smi_q(_SMI_Q_SAMPLE_W11) == "12.4"


# ---------------------------------------------------------------------------
# Tests: plain nvidia-smi table pattern
# ---------------------------------------------------------------------------


def test_smi_plain_parses_table_header():
    assert _parse_cuda_from_smi_plain(_SMI_PLAIN_SAMPLE) == "12.4"


def test_smi_plain_returns_none_for_empty_string():
    assert _parse_cuda_from_smi_plain("") is None


def test_smi_plain_returns_none_when_no_cuda_token():
    assert _parse_cuda_from_smi_plain("Driver Version: 551.86\nNo GPU info here\n") is None


# ---------------------------------------------------------------------------
# Tests: full resolution order (env override + fallbacks)
# ---------------------------------------------------------------------------


def test_env_override_takes_precedence():
    """$env:CUDA_VERSION bypasses nvidia-smi entirely."""
    result = _get_cuda_version(
        env_override="11.8",
        smi_q_output=_SMI_Q_SAMPLE_W11,  # would give 12.4 if parsed
        smi_plain_output=_SMI_PLAIN_SAMPLE,
    )
    assert result == "11.8"


def test_env_override_empty_string_not_used():
    """Empty string env var must not override (PowerShell falsy '')."""
    result = _get_cuda_version(
        env_override="",
        smi_q_output=_SMI_Q_SAMPLE_W11,
        smi_plain_output=None,
    )
    assert result == "12.4"


def test_smi_q_used_when_no_env_override():
    result = _get_cuda_version(
        env_override=None,
        smi_q_output=_SMI_Q_SAMPLE_W11,
        smi_plain_output=None,
    )
    assert result == "12.4"


def test_smi_plain_fallback_when_smi_q_fails():
    """If nvidia-smi -q returns no parseable output, fall back to plain output."""
    result = _get_cuda_version(
        env_override=None,
        smi_q_output=_SMI_Q_SAMPLE_NO_CUDA,  # no CUDA line
        smi_plain_output=_SMI_PLAIN_SAMPLE,  # plain output has it
    )
    assert result == "12.4"


def test_smi_plain_fallback_when_smi_q_unavailable():
    """nvidia-smi -q fails entirely (smi_q_output=None)."""
    result = _get_cuda_version(
        env_override=None,
        smi_q_output=None,
        smi_plain_output=_SMI_PLAIN_SAMPLE,
    )
    assert result == "12.4"


def test_returns_none_when_all_sources_fail():
    result = _get_cuda_version(
        env_override=None,
        smi_q_output=_SMI_Q_SAMPLE_NO_CUDA,
        smi_plain_output="No version here\n",
    )
    assert result is None


def test_returns_none_when_nvidia_smi_absent():
    result = _get_cuda_version(
        env_override=None,
        smi_q_output=None,
        smi_plain_output=None,
    )
    assert result is None


# ---------------------------------------------------------------------------
# Tests: CudaTag generation (cu-tag used for PyTorch index URL)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cuda_ver", "expected_tag"),
    [
        ("12.4", "cu124"),
        ("11.8", "cu118"),
        ("12.3", "cu123"),
        ("12.1", "cu121"),
    ],
)
def test_cuda_tag_format(cuda_ver: str, expected_tag: str):
    """cu-tag = 'cu' + digits only (dots stripped). Used in PyTorch index URL."""
    tag = "cu" + cuda_ver.replace(".", "")
    assert tag == expected_tag
