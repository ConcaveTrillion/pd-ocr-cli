from __future__ import annotations

import os
from pathlib import Path

import pytest

from pdomain_ocr_cli._artifacts import (
    PageOutputTransaction,
    atomic_write_json_document,
    atomic_write_text,
)


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


def test_atomic_write_uses_unique_temp_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_atomic_write_preserves_shared_readable_mode(tmp_path: Path) -> None:
    target = tmp_path / "page.txt"

    atomic_write_text(target, "hello")

    assert target.stat().st_mode & 0o777 == 0o644


def test_atomic_write_json_document_uses_unique_temp_and_cleans_failure(
    tmp_path: Path,
) -> None:
    class BrokenDoc:
        def to_json_file(self, file_path: str | Path) -> None:
            Path(file_path).write_text("partial", encoding="utf-8")
            raise RuntimeError("boom")

    target = tmp_path / "page.json"

    with pytest.raises(RuntimeError, match="boom"):
        atomic_write_json_document(target, BrokenDoc())

    assert not target.exists()
    assert not list(tmp_path.glob(".page.json.*.tmp"))


def test_atomic_write_json_document_preserves_shared_readable_mode(
    tmp_path: Path,
) -> None:
    class Doc:
        def to_json_file(self, file_path: str | Path) -> None:
            Path(file_path).write_text("{}", encoding="utf-8")

    target = tmp_path / "page.json"

    atomic_write_json_document(target, Doc())

    assert target.stat().st_mode & 0o777 == 0o644


def test_page_output_transaction_writes_text_last(tmp_path: Path) -> None:
    tx = PageOutputTransaction(txt_path=tmp_path / "page.txt", json_path=tmp_path / "page.json")

    tx.write_text_last("done")

    assert tx.txt_path.read_text(encoding="utf-8") == "done"
