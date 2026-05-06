"""Unit tests for ``collect_images`` — the CLI's input-expansion helper.

Covers file vs directory inputs, recursion, the supported-suffix filter,
ordering guarantees, and graceful handling of missing paths.
"""

from pathlib import Path

import pytest

from pd_ocr_cli.ocr_to_txt import IMAGE_SUFFIXES, collect_images


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
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


@pytest.mark.parametrize("suffix", sorted(IMAGE_SUFFIXES))
def test_collect_accepts_each_supported_suffix(tmp_path, suffix):
    img = _touch(tmp_path / f"page{suffix}")
    assert collect_images([str(img)], recursive=False) == [img]


@pytest.mark.parametrize("suffix", [".PNG", ".JPG", ".Jpeg", ".TIFF"])
def test_collect_suffix_match_is_case_insensitive(tmp_path, suffix):
    img = _touch(tmp_path / f"page{suffix}")
    assert collect_images([str(img)], recursive=False) == [img]


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
