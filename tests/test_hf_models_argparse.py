"""Argparse-adapter coverage for :mod:`pdomain_ocr_cli._hf_models`.

These exercise the partial-input validation in ``resolve_ocr_models``
and the source-descriptor formatting that backs the
"Detection model loaded: …" / "Recognition model loaded: …" CLI lines.

The HF-download path itself lives in :mod:`pdomain_book_tools.hf` and is
tested there; here we only confirm the CLI wrapper passes the right
shape through and formats output the way the user sees it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pdomain_ocr_cli import _hf_models
from pdomain_ocr_cli._hf_models import (
    DEFAULT_DET_FILENAME,
    DEFAULT_HF_REPO,
    DEFAULT_RECO_FILENAME,
    det_source_descriptor,
    reco_source_descriptor,
    resolve_layout_source,
    resolve_ocr_models,
)


def _ns(**overrides) -> SimpleNamespace:
    """Build an argparse-shaped namespace with sensible defaults."""
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


# --- resolve_ocr_models: partial-input rejection -----------------------------


def test_resolve_ocr_models_detection_without_recognition_exits(capsys):
    args = _ns(detection="det.pt")
    with pytest.raises(SystemExit) as exc_info:
        resolve_ocr_models(args)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "--detection requires its counterpart" in err


def test_resolve_ocr_models_recognition_without_detection_exits(capsys):
    args = _ns(recognition="rec.pt")
    with pytest.raises(SystemExit) as exc_info:
        resolve_ocr_models(args)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "--recognition requires its counterpart" in err


def test_resolve_ocr_models_local_pair_passes_through(monkeypatch):
    """Both local --detection and --recognition: kwargs delegate gets called."""
    captured = {}

    def fake_kwargs(**kwargs):
        captured.update(kwargs)
        return Path(kwargs["detection_path"]), Path(kwargs["recognition_path"])

    monkeypatch.setattr(_hf_models, "_resolve_ocr_models_kwargs", fake_kwargs)
    args = _ns(detection="det.pt", recognition="rec.pt")
    det, reco = resolve_ocr_models(args)
    assert det == Path("det.pt")
    assert reco == Path("rec.pt")
    # The CLI hands paths in as Path() and forwards the repo/version too.
    assert captured["detection_path"] == Path("det.pt")
    assert captured["recognition_path"] == Path("rec.pt")
    assert captured["repo"] == DEFAULT_HF_REPO


def test_resolve_ocr_models_hf_path_forwards_revision(monkeypatch):
    captured = {}

    def fake_kwargs(**kwargs):
        captured.update(kwargs)
        return Path("/cache/det.pt"), Path("/cache/rec.pt")

    monkeypatch.setattr(_hf_models, "_resolve_ocr_models_kwargs", fake_kwargs)
    args = _ns(model_version="v0.6")
    det, reco = resolve_ocr_models(args)
    assert det == Path("/cache/det.pt")
    assert reco == Path("/cache/rec.pt")
    assert captured["revision"] == "v0.6"
    assert captured["detection_path"] is None
    assert captured["recognition_path"] is None


def test_resolve_ocr_models_translates_filenotfound(monkeypatch, capsys):
    def fake_kwargs(**kwargs):
        raise FileNotFoundError("no such revision: bogus")

    monkeypatch.setattr(_hf_models, "_resolve_ocr_models_kwargs", fake_kwargs)
    args = _ns(model_version="bogus")
    with pytest.raises(SystemExit) as exc_info:
        resolve_ocr_models(args)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "no such revision: bogus" in err


# --- source descriptors ------------------------------------------------------


def test_det_descriptor_local_path_is_passthrough():
    args = _ns(detection="local/det.pt")
    assert det_source_descriptor(args, Path("local/det.pt")) == "local/det.pt"


def test_det_descriptor_hf_path_includes_repo_and_revision():
    args = _ns(model_version="v0.6")
    out = det_source_descriptor(args, Path("/cache/det.pt"))
    assert out == f"{DEFAULT_HF_REPO}/{DEFAULT_DET_FILENAME}@v0.6"


def test_det_descriptor_hf_path_default_revision_renders_as_latest():
    args = _ns()
    out = det_source_descriptor(args, Path("/cache/det.pt"))
    assert out == f"{DEFAULT_HF_REPO}/{DEFAULT_DET_FILENAME}@latest"


def test_reco_descriptor_local_path_is_passthrough():
    args = _ns(recognition="local/rec.pt")
    assert reco_source_descriptor(args, Path("local/rec.pt")) == "local/rec.pt"


def test_reco_descriptor_hf_path_with_custom_filename():
    args = _ns(reco_filename="alt/rec.pt", model_version="v0.6")
    out = reco_source_descriptor(args, Path("/cache/rec.pt"))
    assert out == f"{DEFAULT_HF_REPO}/alt/rec.pt@v0.6"


# --- resolve_layout_source ---------------------------------------------------


def test_resolve_layout_source_forwards_to_kwargs(monkeypatch):
    captured = {}

    def fake_kwargs(layout_model, layout_checkpoint):
        captured["layout_model"] = layout_model
        captured["layout_checkpoint"] = layout_checkpoint
        return ("layout/repo", "v1", "layout/repo@v1")

    monkeypatch.setattr(_hf_models, "_resolve_layout_source_kwargs", fake_kwargs)
    args = _ns(layout_model="contour", layout_checkpoint="custom/repo")
    repo, rev, descriptor = resolve_layout_source(args)
    assert repo == "layout/repo"
    assert rev == "v1"
    assert descriptor == "layout/repo@v1"
    assert captured == {"layout_model": "contour", "layout_checkpoint": "custom/repo"}
