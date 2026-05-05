"""Tests for ``_detect_torch_device`` — the device picker for the layout model.

The function gracefully degrades when torch isn't importable, prefers CUDA,
falls back to MPS on Apple Silicon, and otherwise returns ``"cpu"``. Each
branch is small but the function runs on every CLI invocation, so we cover
all four paths.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from pd_ocr_cli.ocr_to_txt import _detect_torch_device


def test_detect_returns_cpu_when_torch_missing(monkeypatch):
    """Setting ``sys.modules["torch"] = None`` makes ``import torch`` raise."""
    monkeypatch.setitem(sys.modules, "torch", None)
    assert _detect_torch_device() == "cpu"


def test_detect_returns_cuda_when_available(monkeypatch):
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True),
        backends=SimpleNamespace(mps=None),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert _detect_torch_device() == "cuda"


def test_detect_returns_mps_when_only_mps_available(monkeypatch):
    fake_mps = SimpleNamespace(is_available=lambda: True)
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=fake_mps),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert _detect_torch_device() == "mps"


def test_detect_returns_cpu_when_neither_cuda_nor_mps(monkeypatch):
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=None),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert _detect_torch_device() == "cpu"


def test_detect_returns_cpu_when_mps_present_but_unavailable(monkeypatch):
    """``backends.mps`` exists but ``is_available()`` is False — fall to CPU."""
    fake_mps = SimpleNamespace(is_available=lambda: False)
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=fake_mps),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert _detect_torch_device() == "cpu"


def test_detect_handles_torch_backends_without_mps_attr(monkeypatch):
    """Older torch builds may not expose ``torch.backends.mps`` at all."""
    # backends namespace deliberately has no `mps` attr.
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert _detect_torch_device() == "cpu"
