"""Tests for the GPU-install nudge helpers in ``ocr_to_txt``.

The nudge fires on hosts that have an NVIDIA GPU (``nvidia-smi`` present
and exiting 0) but were installed CPU-only (CuPy not importable). It is
opt-out via ``PD_OCR_NO_GPU_NUDGE=1`` and must NEVER raise — a bug in a
printing helper must not break ``pdomain-ocr`` itself.
"""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

from pdomain_ocr_cli import ocr_to_txt


@pytest.fixture(autouse=True)
def _reset_nudge_cache(monkeypatch):
    """Clear the process-level cache between tests so each one starts fresh."""
    monkeypatch.setattr(ocr_to_txt, "_GPU_NUDGE_CACHE", {})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_fake_cupy(monkeypatch):
    """Make ``import cupy`` succeed (in-process) for one test."""
    monkeypatch.setitem(sys.modules, "cupy", SimpleNamespace(__name__="cupy"))


def _uninstall_fake_cupy(monkeypatch):
    """Ensure ``import cupy`` raises ``ImportError`` for the test."""
    # delitem is safe even if absent — pop with default first.
    sys.modules.pop("cupy", None)

    real_import = __import__

    def _import(name, *a, **kw):
        if name == "cupy" or name.startswith("cupy."):
            raise ImportError("no cupy in this test")
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", _import)


# ---------------------------------------------------------------------------
# _should_nudge_gpu_install
# ---------------------------------------------------------------------------


def test_nudge_skipped_when_cupy_importable(monkeypatch):
    """If CuPy imports cleanly, the GPU stack is already wired up."""
    _install_fake_cupy(monkeypatch)
    # Pretend nvidia-smi exists too so the only reason for False is CuPy.
    monkeypatch.setattr(ocr_to_txt.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.delenv("PD_OCR_NO_GPU_NUDGE", raising=False)

    assert ocr_to_txt._should_nudge_gpu_install() is False


def test_nudge_skipped_when_no_nvidia_smi(monkeypatch):
    """No GPU on the host → no nudge (cheap short-circuit)."""
    _uninstall_fake_cupy(monkeypatch)
    monkeypatch.setattr(ocr_to_txt.shutil, "which", lambda name: None)
    monkeypatch.delenv("PD_OCR_NO_GPU_NUDGE", raising=False)

    # subprocess.run must NOT be called when nvidia-smi is absent — verify
    # by raising if the test accidentally invokes it.
    def _no_subprocess(*a, **kw):
        raise AssertionError("subprocess.run must not be called when nvidia-smi is absent")

    monkeypatch.setattr(ocr_to_txt.subprocess, "run", _no_subprocess)

    assert ocr_to_txt._should_nudge_gpu_install() is False


def test_nudge_fires_when_gpu_present_and_cupy_missing(monkeypatch):
    """nvidia-smi present + CuPy missing + opt-in not disabled → nudge."""
    _uninstall_fake_cupy(monkeypatch)
    monkeypatch.setattr(ocr_to_txt.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.delenv("PD_OCR_NO_GPU_NUDGE", raising=False)

    def _ok_subprocess(*a, **kw):
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ocr_to_txt.subprocess, "run", _ok_subprocess)

    assert ocr_to_txt._should_nudge_gpu_install() is True


def test_nudge_skipped_when_env_opt_out(monkeypatch):
    """``PD_OCR_NO_GPU_NUDGE=1`` short-circuits everything."""
    _uninstall_fake_cupy(monkeypatch)
    monkeypatch.setattr(ocr_to_txt.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.setenv("PD_OCR_NO_GPU_NUDGE", "1")

    def _no_subprocess(*a, **kw):
        raise AssertionError("subprocess.run must not be called when env opt-out is set")

    monkeypatch.setattr(ocr_to_txt.subprocess, "run", _no_subprocess)

    assert ocr_to_txt._should_nudge_gpu_install() is False


def test_nudge_skipped_when_subprocess_fails(monkeypatch):
    """nvidia-smi exits non-zero (driver broken) → no nudge."""
    _uninstall_fake_cupy(monkeypatch)
    monkeypatch.setattr(ocr_to_txt.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.delenv("PD_OCR_NO_GPU_NUDGE", raising=False)

    monkeypatch.setattr(
        ocr_to_txt.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=9),
    )

    assert ocr_to_txt._should_nudge_gpu_install() is False


def test_nudge_skipped_when_subprocess_raises(monkeypatch):
    """A subprocess error (TimeoutExpired, OSError) is treated as "no GPU"."""
    _uninstall_fake_cupy(monkeypatch)
    monkeypatch.setattr(ocr_to_txt.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.delenv("PD_OCR_NO_GPU_NUDGE", raising=False)

    def _raise(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=2)

    monkeypatch.setattr(ocr_to_txt.subprocess, "run", _raise)

    assert ocr_to_txt._should_nudge_gpu_install() is False


def test_nudge_skipped_when_subprocess_raises_oserror(monkeypatch):
    """An OSError from subprocess.run (e.g. ENOENT under a race) is also swallowed."""
    _uninstall_fake_cupy(monkeypatch)
    monkeypatch.setattr(ocr_to_txt.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.delenv("PD_OCR_NO_GPU_NUDGE", raising=False)

    def _raise(*a, **kw):
        raise OSError(2, "race lost: nvidia-smi vanished")

    monkeypatch.setattr(ocr_to_txt.subprocess, "run", _raise)

    assert ocr_to_txt._should_nudge_gpu_install() is False


def test_nudge_skipped_when_cupy_import_explodes(monkeypatch):
    """A non-ImportError raised by ``import cupy`` is swallowed (broken install)."""
    sys.modules.pop("cupy", None)
    real_import = __import__

    def _import(name, *a, **kw):
        if name == "cupy":
            raise RuntimeError("cupy installed but its native lib segfaults on import")
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", _import)
    monkeypatch.setattr(ocr_to_txt.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.delenv("PD_OCR_NO_GPU_NUDGE", raising=False)

    assert ocr_to_txt._should_nudge_gpu_install() is False


def test_nudge_result_cached_across_calls(monkeypatch):
    """The probe runs at most once per process — second call uses the cache."""
    _uninstall_fake_cupy(monkeypatch)
    monkeypatch.setattr(ocr_to_txt.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.delenv("PD_OCR_NO_GPU_NUDGE", raising=False)

    call_count = {"n": 0}

    def _counting_run(*a, **kw):
        call_count["n"] += 1
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ocr_to_txt.subprocess, "run", _counting_run)

    assert ocr_to_txt._should_nudge_gpu_install() is True
    assert ocr_to_txt._should_nudge_gpu_install() is True
    assert call_count["n"] == 1, "second call must hit the cache, not re-spawn nvidia-smi"


def test_nudge_outer_guard_swallows_unexpected_exception(monkeypatch):
    """If ``shutil.which`` itself raises (extremely unusual), the helper still returns False."""
    _uninstall_fake_cupy(monkeypatch)

    def _boom(name):
        raise RuntimeError("PATH is on fire")

    monkeypatch.setattr(ocr_to_txt.shutil, "which", _boom)
    monkeypatch.delenv("PD_OCR_NO_GPU_NUDGE", raising=False)

    assert ocr_to_txt._should_nudge_gpu_install() is False


# ---------------------------------------------------------------------------
# _maybe_print_gpu_nudge
# ---------------------------------------------------------------------------


def test_maybe_print_emits_to_stderr_when_nudging(monkeypatch, capsys):
    monkeypatch.setattr(ocr_to_txt, "_should_nudge_gpu_install", lambda: True)

    ocr_to_txt._maybe_print_gpu_nudge()

    err = capsys.readouterr().err
    assert "NVIDIA GPU detected" in err
    # The canonical install path is the install script (not pip); the
    # nudge points the user at re-running install.sh to swap CPU→GPU.
    assert "install.sh" in err
    assert "PD_OCR_NO_GPU_NUDGE" in err


def test_maybe_print_silent_when_not_nudging(monkeypatch, capsys):
    monkeypatch.setattr(ocr_to_txt, "_should_nudge_gpu_install", lambda: False)

    ocr_to_txt._maybe_print_gpu_nudge()

    assert capsys.readouterr().err == ""


def test_maybe_print_swallows_helper_exceptions(monkeypatch, capsys):
    """A bug in ``_should_nudge_gpu_install`` must not break ``pdomain-ocr``."""

    def _broken():
        raise RuntimeError("nudge helper bug")

    monkeypatch.setattr(ocr_to_txt, "_should_nudge_gpu_install", _broken)

    # Must not raise.
    ocr_to_txt._maybe_print_gpu_nudge()
    assert capsys.readouterr().err == ""
