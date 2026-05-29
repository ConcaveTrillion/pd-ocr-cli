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
