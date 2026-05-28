"""Atomic write and text normalization tests for pdomain_ocr_cli._pipeline helpers."""

from __future__ import annotations

import os

import pytest

from pdomain_ocr_cli._pipeline import (
    apply_text_normalizations,
    atomic_write_bytes,
    atomic_write_text,
)

# ---------------------------------------------------------------------------
# apply_text_normalizations
# ---------------------------------------------------------------------------


def test_apply_text_normalizations_default_passthrough():
    src = "“hello” world—done"
    assert (
        apply_text_normalizations(src, straight_quotes=False, em_dash_to_double_hyphen=False) == src
    )


def test_apply_text_normalizations_straight_quotes_only():
    out = apply_text_normalizations(
        "“hi”—there", straight_quotes=True, em_dash_to_double_hyphen=False
    )
    assert out == '"hi"—there'


def test_apply_text_normalizations_em_dash_only():
    out = apply_text_normalizations(
        "“hi”—there", straight_quotes=False, em_dash_to_double_hyphen=True
    )
    assert out == "“hi”--there"


def test_apply_text_normalizations_both():
    out = apply_text_normalizations(
        "“hi”—there", straight_quotes=True, em_dash_to_double_hyphen=True
    )
    assert out == '"hi"--there'


@pytest.mark.parametrize("falsy", [None, ""])
def test_apply_text_normalizations_none_or_empty_returns_empty(falsy):
    assert (
        apply_text_normalizations(falsy, straight_quotes=True, em_dash_to_double_hyphen=True) == ""
    )


# ---------------------------------------------------------------------------
# atomic_write_text / atomic_write_bytes
# ---------------------------------------------------------------------------


def test_atomic_write_text_basic_roundtrip(tmp_path):
    """Happy path: file ends up at the canonical name with the new text."""
    target = tmp_path / "page.txt"
    atomic_write_text(target, "hello\n")
    assert target.read_text(encoding="utf-8") == "hello\n"
    # No leftover sibling temp.
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_text_overwrites_existing(tmp_path):
    target = tmp_path / "page.txt"
    target.write_text("OLD CONTENT", encoding="utf-8")
    atomic_write_text(target, "NEW")
    assert target.read_text(encoding="utf-8") == "NEW"


def test_atomic_write_text_failure_preserves_prior_file(tmp_path, monkeypatch):
    """If the temp write blows up, the canonical path keeps its prior bytes
    and no partial sibling is left behind. This is the B18 invariant: a
    crash mid-write must never leave a truncated ``.txt`` at the final
    path that downstream tools would mistake for a successful export.
    """
    target = tmp_path / "page.txt"
    target.write_text("PRIOR GOOD CONTENT", encoding="utf-8")

    real_write = os.write

    def boom(fd, data):
        # Simulate ENOSPC mid-write: write a partial chunk so the temp
        # file is non-empty on disk, then explode.
        real_write(fd, b"PARTIAL")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("pdomain_ocr_cli._pipeline.os.write", boom)

    with pytest.raises(OSError):
        atomic_write_text(target, "NEW CONTENT")

    # Canonical path is untouched — prior content intact, no partial.
    assert target.read_text(encoding="utf-8") == "PRIOR GOOD CONTENT"
    # Partial sibling was cleaned up.
    siblings = [p.name for p in tmp_path.iterdir()]
    assert siblings == ["page.txt"], siblings


def test_atomic_write_text_failure_with_no_prior_file_leaves_no_partial(tmp_path, monkeypatch):
    """Same invariant when the canonical path didn't yet exist: a failed
    write must not leave a half-written file at the canonical name.
    """
    target = tmp_path / "page.txt"

    real_write = os.write

    def boom(fd, data):
        real_write(fd, b"PARTIAL")
        raise RuntimeError("simulated SIGKILL between truncate and full flush")

    monkeypatch.setattr("pdomain_ocr_cli._pipeline.os.write", boom)

    with pytest.raises(RuntimeError):
        atomic_write_text(target, "NEW CONTENT")

    # Canonical path never appeared.
    assert not target.exists()
    # Partial sibling cleaned up.
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_text_failure_with_no_tmp_created_swallows_unlink(tmp_path, monkeypatch):
    """If ``os.open`` itself raises before the temp file appears on disk,
    nothing is left behind and the original error propagates. (No
    defensive unlink runs in this path; ``os.open`` failing means the
    temp never existed.)
    """
    target = tmp_path / "page.txt"

    def boom(*args, **kwargs):
        raise RuntimeError("blew up before any byte hit disk")

    monkeypatch.setattr("pdomain_ocr_cli._pipeline.os.open", boom)
    with pytest.raises(RuntimeError, match="blew up"):
        atomic_write_text(target, "x")
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_bytes_failure_with_no_tmp_created_swallows_unlink(tmp_path, monkeypatch):
    target = tmp_path / "page.bin"

    def boom(*args, **kwargs):
        raise RuntimeError("blew up before any byte hit disk")

    monkeypatch.setattr("pdomain_ocr_cli._pipeline.os.open", boom)
    with pytest.raises(RuntimeError, match="blew up"):
        atomic_write_bytes(target, b"x")
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_bytes_roundtrip_and_failure(tmp_path, monkeypatch):
    target = tmp_path / "page.bin"
    atomic_write_bytes(target, b"\x00\x01\x02")
    assert target.read_bytes() == b"\x00\x01\x02"

    real_write = os.write

    def boom(fd, data):
        real_write(fd, b"PARTIAL")
        raise OSError("disk full")

    monkeypatch.setattr("pdomain_ocr_cli._pipeline.os.write", boom)

    with pytest.raises(OSError):
        atomic_write_bytes(target, b"\xff\xff")

    # Original bytes preserved, no leftover temp.
    assert target.read_bytes() == b"\x00\x01\x02"
    assert list(tmp_path.iterdir()) == [target]


# B24: durability — fsync the temp fd before close, fsync the parent dir
# after replace. Without these, ``os.replace`` is metadata-atomic only
# and the data + rename can be lost on power loss / kernel panic.


def test_atomic_write_text_fsyncs_temp_fd_and_parent_dir(tmp_path, monkeypatch):
    """``atomic_write_text`` must call ``os.fsync`` on the temp fd before
    close and on the parent directory fd after ``os.replace``. Right-
    reason failure before the fix: ``fsync`` was never called, so this
    asserts the call list explicitly.
    """
    target = tmp_path / "page.txt"

    fsynced_fds: list[int] = []
    real_fsync = os.fsync

    def tracking_fsync(fd):
        fsynced_fds.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr("pdomain_ocr_cli._pipeline.os.fsync", tracking_fsync)

    atomic_write_text(target, "durable\n")

    # At least two fsyncs happened: one on the file fd before close, one
    # on the parent directory fd after replace. (On Windows the parent-
    # dir fsync is skipped — but POSIX, where the test runs in CI, must
    # do both.)
    assert len(fsynced_fds) >= 2, fsynced_fds
    assert target.read_text(encoding="utf-8") == "durable\n"


def test_atomic_write_bytes_fsyncs_temp_fd_and_parent_dir(tmp_path, monkeypatch):
    target = tmp_path / "page.bin"

    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def tracking_fsync(fd):
        fsync_calls.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr("pdomain_ocr_cli._pipeline.os.fsync", tracking_fsync)

    atomic_write_bytes(target, b"\xde\xad\xbe\xef")

    assert len(fsync_calls) >= 2, fsync_calls
    assert target.read_bytes() == b"\xde\xad\xbe\xef"


def test_atomic_write_swallows_filenotfound_on_cleanup(tmp_path, monkeypatch):
    """If the temp file vanishes between ``os.open`` and the cleanup
    branch (e.g. another process unlinked it), the helper's defensive
    ``unlink()`` must swallow ``FileNotFoundError`` and re-raise the
    original write error rather than masking it.
    """
    target = tmp_path / "page.txt"

    def vanishing_write(fd, data):
        # Unlink the temp file so the subsequent unlink() in the helper
        # raises FileNotFoundError, then explode with the "real" error.
        for entry in tmp_path.iterdir():
            if entry.name.endswith(".tmp"):
                entry.unlink()
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("pdomain_ocr_cli._pipeline.os.write", vanishing_write)

    with pytest.raises(OSError, match="No space left"):
        atomic_write_text(target, "x")
    # Nothing left behind, no spurious FileNotFoundError surfaced.
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_parent_dir_fsync_skipped_on_windows(tmp_path, monkeypatch):
    """On ``os.name == "nt"`` the helper must skip the directory fsync
    (Windows can't open a directory for fsync). Only the temp fd is
    fsynced there; NTFS journals the rename itself.
    """
    target = tmp_path / "page.txt"

    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def tracking_fsync(fd):
        fsync_calls.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr("pdomain_ocr_cli._pipeline.os.fsync", tracking_fsync)
    monkeypatch.setattr("pdomain_ocr_cli._pipeline.os.name", "nt")

    atomic_write_text(target, "x")

    # Only the temp fd fsync — no parent-dir fsync on the Windows branch.
    assert len(fsync_calls) == 1, fsync_calls
    assert target.read_text(encoding="utf-8") == "x"
