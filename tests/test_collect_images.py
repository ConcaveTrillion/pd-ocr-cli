"""Unit tests for ``collect_images`` — the CLI's input-expansion helper.

Covers file vs directory inputs, recursion, the supported-suffix filter,
ordering guarantees, and graceful handling of missing paths.
"""

import logging
from pathlib import Path

import pytest
from pdomain_book_tools.image_processing.formats import SUPPORTED_IMAGE_SUFFIXES

from pdomain_ocr_cli.ocr_to_txt import collect_images

# Minimal magic-byte headers (>= 16 bytes after padding) for the formats
# pdomain-book-tools' is_image_file recognises. Used by _touch to lay down
# fixtures that pass the gate without involving real image encoders.
_MAGIC_BY_SUFFIX: dict[str, bytes] = {
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff\xe0",
    ".jpeg": b"\xff\xd8\xff\xe0",
    ".tif": b"II*\x00",
    ".tiff": b"II*\x00",
    ".bmp": b"BM",
    ".webp": b"RIFF\x00\x00\x00\x00WEBP",
    ".jp2": b"\x00\x00\x00\x0cjP  \r\n\x87\n",
    ".j2k": b"\xff\x4f\xff\x51",
    ".jpf": b"\x00\x00\x00\x0cjP  \r\n\x87\n",
    ".jpx": b"\x00\x00\x00\x0cjP  \r\n\x87\n",
    ".gif": b"GIF89a",
    ".ppm": b"P6\n",
    ".pgm": b"P5\n",
    ".pbm": b"P4\n",
    ".pnm": b"P6\n",
    # HEIF / AVIF — ISO BMFF ftyp box. The 4-byte size field is unused by
    # the sniff; brand at offset 8.
    ".heic": b"\x00\x00\x00\x20ftypheic",
    ".heif": b"\x00\x00\x00\x20ftypheic",
    ".avif": b"\x00\x00\x00\x20ftypavif",
}


def _magic_for(suffix: str) -> bytes:
    """Pad the suffix's magic bytes to 16 so is_image_file accepts it."""
    suffix = suffix.lower()
    head = _MAGIC_BY_SUFFIX.get(suffix, b"")
    if len(head) < 16:
        head = head + b"\x00" * (16 - len(head))
    return head


def _touch(p: Path) -> Path:
    """Create *p* with a minimal valid header for its suffix (or empty
    if the suffix is not an image — e.g. ``.txt``, ``.md``)."""
    p.parent.mkdir(parents=True, exist_ok=True)
    suffix = p.suffix.lower()
    if suffix in _MAGIC_BY_SUFFIX:
        p.write_bytes(_magic_for(suffix))
    else:
        p.write_bytes(b"")
    return p


def test_collect_single_image_file(tmp_path):
    img = _touch(tmp_path / "page.png")
    assert collect_images([str(img)], recursive=False) == [img]


def test_collect_skips_non_image_file(tmp_path, capsys):
    txt = _touch(tmp_path / "notes.txt")
    assert collect_images([str(txt)], recursive=False) == []
    err = capsys.readouterr().err
    assert "skipping non-image file" in err
    assert str(txt) in err


def test_collect_warns_on_missing_path(tmp_path, capsys):
    missing = tmp_path / "does-not-exist.png"
    assert collect_images([str(missing)], recursive=False) == []
    err = capsys.readouterr().err
    assert "skipping missing path" in err


def test_collect_directory_non_recursive(tmp_path):
    a = _touch(tmp_path / "a.png")
    b = _touch(tmp_path / "b.jpg")
    _touch(tmp_path / "sub" / "c.png")  # ignored without recursion
    _touch(tmp_path / "ignored.txt")

    result = collect_images([str(tmp_path)], recursive=False)
    assert result == [a, b]


def test_collect_directory_recursive(tmp_path):
    a = _touch(tmp_path / "a.png")
    nested = _touch(tmp_path / "sub" / "deep" / "b.png")
    _touch(tmp_path / "sub" / "ignore.md")

    result = collect_images([str(tmp_path)], recursive=True)
    assert set(result) == {a, nested}


def test_collect_directory_results_sorted(tmp_path):
    files = [_touch(tmp_path / name) for name in ("c.png", "a.png", "b.png")]
    result = collect_images([str(tmp_path)], recursive=False)
    assert result == sorted(files)


def test_collect_preserves_input_order_for_multiple_files(tmp_path):
    a = _touch(tmp_path / "a.png")
    b = _touch(tmp_path / "b.png")
    c = _touch(tmp_path / "c.png")
    # Order is the order the user passed them on the CLI.
    result = collect_images([str(b), str(a), str(c)], recursive=False)
    assert result == [b, a, c]


@pytest.mark.parametrize("suffix", sorted(SUPPORTED_IMAGE_SUFFIXES))
def test_collect_accepts_each_supported_suffix(tmp_path, suffix):
    img = _touch(tmp_path / f"page{suffix}")
    assert collect_images([str(img)], recursive=False) == [img]


@pytest.mark.parametrize("suffix", [".PNG", ".JPG", ".Jpeg", ".TIFF", ".JP2"])
def test_collect_suffix_match_is_case_insensitive(tmp_path, suffix):
    # Magic bytes lookup is keyed on the lowercased suffix (handled inside
    # _touch); is_image_file lowercases the suffix internally too.
    img = _touch(tmp_path / f"page{suffix}")
    assert collect_images([str(img)], recursive=False) == [img]


def test_collect_accepts_jp2_with_real_magic_bytes(tmp_path):
    """A real-world ``.jp2`` book scan must pass the input gate.

    Regression: prior IMAGE_SUFFIXES allowlist hardcoded only PNG/JPEG/
    TIFF/BMP/WebP, so JPEG 2000 scans were rejected as "non-image".
    pdomain-book-tools' is_image_file now decides via extension OR magic.
    """
    jp2 = tmp_path / "scan.jp2"
    # Real JP2 box-format header (12 bytes) + zero padding to clear the
    # 16-byte head buffer is_image_file reads.
    jp2.write_bytes(b"\x00\x00\x00\x0cjP  \r\n\x87\n" + b"\x00" * 8)
    assert collect_images([str(jp2)], recursive=False) == [jp2]


def test_collect_accepts_mislabeled_png_with_jp2_bytes_and_warns(tmp_path, capsys, caplog):
    """A file named ``.png`` whose bytes are JPEG 2000 must (1) still be
    accepted (it IS a real image, just mislabeled) and (2) produce a
    visible WARNING so the user knows the extension is wrong.

    The warning is emitted by pdomain-book-tools'
    ``pdomain_book_tools.image_processing.formats`` module logger; pdomain-ocr-cli's
    own logging configuration must not silence it.
    """
    fake_png = tmp_path / "mislabeled.png"
    # JP2 box magic + padding; 12 + 8 = 20 bytes total.
    fake_png.write_bytes(b"\x00\x00\x00\x0cjP  \r\n\x87\n" + b"\x00" * 8)

    with caplog.at_level(logging.WARNING, logger="pdomain_book_tools.image_processing.formats"):
        result = collect_images([str(fake_png)], recursive=False)

    assert result == [fake_png], "mislabeled-but-real image must be accepted"
    # The mismatch warning names the path and identifies the actual format.
    assert any(
        "jpeg2000" in rec.getMessage() and str(fake_png) in rec.getMessage()
        for rec in caplog.records
    ), f"expected mismatch warning, got: {[r.getMessage() for r in caplog.records]}"
    # And the user-facing "skipping non-image file" warning must NOT fire,
    # because the file is accepted.
    err = capsys.readouterr().err
    assert "skipping non-image file" not in err


def test_collect_mixed_file_and_directory(tmp_path):
    standalone = _touch(tmp_path / "standalone.png")
    dir_a = tmp_path / "d"
    inside = _touch(dir_a / "inner.png")

    result = collect_images([str(standalone), str(dir_a)], recursive=False)
    assert result == [standalone, inside]


def test_collect_returns_empty_for_empty_directory(tmp_path):
    (tmp_path / "empty").mkdir()
    assert collect_images([str(tmp_path / "empty")], recursive=False) == []


def test_collect_dedupes_file_also_inside_passed_directory(tmp_path):
    """B12: passing both a directory and a file inside it must not OCR the
    file twice. Dedup on resolved path; preserve first-seen order."""
    a = _touch(tmp_path / "a.png")
    b = _touch(tmp_path / "b.png")

    # User passes the file explicitly first, then the parent dir.
    result = collect_images([str(b), str(tmp_path)], recursive=False)
    assert result == [b, a]

    # And the reverse: dir first, then a file already covered by the dir.
    result2 = collect_images([str(tmp_path), str(a)], recursive=False)
    assert result2 == [a, b]


def test_collect_dedupes_same_file_passed_twice(tmp_path):
    """B12: same file path repeated on the CLI should still OCR once."""
    a = _touch(tmp_path / "a.png")
    assert collect_images([str(a), str(a)], recursive=False) == [a]


def test_collect_dedupes_overlapping_directories(tmp_path):
    """B12: overlapping dir trees must not double-process shared images."""
    inner = _touch(tmp_path / "sub" / "x.png")
    result = collect_images([str(tmp_path), str(tmp_path / "sub")], recursive=True)
    assert result == [inner]
