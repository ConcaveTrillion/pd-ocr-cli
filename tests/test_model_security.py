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
    assert not any("mutable latest OCR model revision" in warning for warning in warnings)


def test_warns_for_layout_checkpoint() -> None:
    warnings = model_security_warnings(_args(layout_checkpoint="layout.pt"))
    assert any("layout checkpoint" in warning for warning in warnings)
