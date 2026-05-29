from __future__ import annotations

from types import SimpleNamespace

import pytest

from pdomain_ocr_cli import ocr_to_txt
from pdomain_ocr_cli._runtime import (
    BatchRuntimeError,
    DefaultRuntimeSession,
    run_batch_checked,
    validate_batch_result_count,
)


def test_run_batch_checked_converts_runner_exception() -> None:
    def runner(images, *, predictor, device, source_identifiers):
        raise RuntimeError("batch backend exploded")

    with pytest.raises(BatchRuntimeError) as exc_info:
        run_batch_checked(
            runner,
            [object()],
            predictor="predictor",
            device="cpu",
            source_identifiers=["a.png"],
        )

    assert "batch backend exploded" in str(exc_info.value)


def test_validate_batch_result_count_rejects_wrong_length() -> None:
    with pytest.raises(BatchRuntimeError) as exc_info:
        validate_batch_result_count([object()], expected=2)

    assert "batch returned 1 page(s) for 2 image(s)" in str(exc_info.value)


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


def test_create_runtime_session_loads_predictor_device_and_runner(monkeypatch, tmp_path) -> None:
    predictor = object()
    det_path = tmp_path / "det.pt"
    reco_path = tmp_path / "reco.pt"

    monkeypatch.setattr(ocr_to_txt, "_load_predictor", lambda det, reco: predictor)
    monkeypatch.setattr(ocr_to_txt, "_pick_device", lambda: "cpu")

    def runner(images, *, predictor, device, build_smaller=None, source_identifiers=None):
        return [SimpleNamespace(text="OK")]

    monkeypatch.setattr(ocr_to_txt, "_run_doctr_batch", runner)

    session = ocr_to_txt._create_runtime_session(det_path, reco_path)

    assert session.predictor is predictor
    assert session.device == "cpu"
    pages = session.run_batch([object()], source_identifiers=["page.png"])
    assert pages[0].text == "OK"


def test_create_runtime_session_rejects_none_predictor(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ocr_to_txt, "_load_predictor", lambda det, reco: None)

    with pytest.raises(RuntimeError, match="failed to load models"):
        ocr_to_txt._create_runtime_session(tmp_path / "det.pt", tmp_path / "reco.pt")
