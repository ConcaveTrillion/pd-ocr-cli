"""Unit tests for the pure pipeline helpers in :mod:`pdomain_ocr_cli._pipeline`.

These cover the path-mirroring, text-normalization-apply, layout-debug
env scaffolding, drops-warning formatting, and illustration-region
selection logic that ``ocr_to_txt.main`` orchestrates per page.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from pdomain_ocr_cli import _pipeline
from pdomain_ocr_cli._pipeline import (
    apply_text_normalizations,
    atomic_write_bytes,
    atomic_write_text,
    clear_layout_debug_env,
    compute_mirror_root,
    diagnostic_output_paths,
    format_drops_warning,
    format_noise_drop_warning,
    illustration_crop_path,
    iter_crop_regions,
    output_paths_for,
    resolve_dest_dir,
    setup_layout_debug_env,
    validate_extract_illustrations,
    write_diagnostic_snapshots,
)


def _ns(**overrides) -> SimpleNamespace:
    base = {
        "layout_model": "pp-doclayout-plus-l",
        "extract_illustrations": False,
        "layout_debug": False,
        "layout_debug_dir": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# validate_extract_illustrations
# ---------------------------------------------------------------------------


def test_validate_extract_illustrations_ok_when_layout_enabled():
    """Combination is fine — should not raise or print to stderr."""
    args = _ns(layout_model="pp-doclayout-plus-l", extract_illustrations=True)
    validate_extract_illustrations(args)  # no exception


def test_validate_extract_illustrations_ok_when_neither_set():
    args = _ns(layout_model="none", extract_illustrations=False)
    validate_extract_illustrations(args)  # no exception


def test_validate_extract_illustrations_rejects_combo(capsys):
    args = _ns(layout_model="none", extract_illustrations=True)
    with pytest.raises(SystemExit) as exc_info:
        validate_extract_illustrations(args)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "--extract-illustrations requires a layout model" in err


# ---------------------------------------------------------------------------
# compute_mirror_root
# ---------------------------------------------------------------------------


def test_compute_mirror_root_none_when_no_output_dir(tmp_path):
    (tmp_path / "imgs").mkdir()
    assert compute_mirror_root([str(tmp_path / "imgs")], output_dir=None) is None


def test_compute_mirror_root_none_when_no_directory_inputs(tmp_path):
    (tmp_path / "page.png").write_bytes(b"")
    assert compute_mirror_root([str(tmp_path / "page.png")], output_dir=tmp_path) is None


def test_compute_mirror_root_single_dir(tmp_path):
    d = tmp_path / "imgs"
    d.mkdir()
    assert compute_mirror_root([str(d)], output_dir=tmp_path / "out") == d.resolve()


def test_compute_mirror_root_common_prefix_of_multiple_dirs(tmp_path):
    a = tmp_path / "tree" / "a"
    b = tmp_path / "tree" / "b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    out = tmp_path / "out"
    assert compute_mirror_root([str(a), str(b)], output_dir=out) == (tmp_path / "tree").resolve()


def test_compute_mirror_root_ignores_non_directory_inputs(tmp_path):
    d = tmp_path / "imgs"
    d.mkdir()
    img = tmp_path / "loose.png"
    img.write_bytes(b"")
    # "loose.png" is a file, not a dir — only `d` participates.
    assert compute_mirror_root([str(img), str(d)], output_dir=tmp_path / "out") == d.resolve()


def test_compute_mirror_root_handles_no_common_ancestor(tmp_path, monkeypatch, capsys):
    """B23: ``os.path.commonpath`` raises ``ValueError`` for inputs with no
    common ancestor — most commonly on Windows when directories live on
    different drives (``C:\\scans`` vs ``D:\\more_scans``). We can't
    reproduce a cross-drive layout on POSIX (after ``.resolve()`` every path
    starts with ``/``), so simulate it by patching ``os.path.commonpath`` to
    raise the same ``ValueError`` the real Windows stdlib raises. Before the
    fix this aborted the entire batch with an unhandled traceback before any
    image was processed; after the fix it falls back to ``None`` (flat
    output) and emits a single WARNING on stderr."""
    a = tmp_path / "scans"
    b = tmp_path / "more_scans"
    a.mkdir()
    b.mkdir()
    out = tmp_path / "out"

    def _raise(_paths):
        raise ValueError("Paths don't have the same drive")

    monkeypatch.setattr(_pipeline.os.path, "commonpath", _raise)
    result = compute_mirror_root([str(a), str(b)], output_dir=out)
    assert result is None
    err = capsys.readouterr().err
    assert "no common ancestor" in err
    # Exactly one warning, not one per image.
    assert err.count("WARNING") == 1


# ---------------------------------------------------------------------------
# resolve_dest_dir
# ---------------------------------------------------------------------------


def test_resolve_dest_dir_no_output_writes_next_to_image(tmp_path):
    img = tmp_path / "subdir" / "page.png"
    img.parent.mkdir()
    img.write_bytes(b"")
    assert resolve_dest_dir(img, output_dir=None, mirror_root=None) == img.parent


def test_resolve_dest_dir_output_only_flat(tmp_path):
    img = tmp_path / "imgs" / "deep" / "page.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"")
    out = tmp_path / "out"
    # Without a mirror root, all images land directly in `out`.
    assert resolve_dest_dir(img, output_dir=out, mirror_root=None) == out


def test_resolve_dest_dir_mirrored_under_output(tmp_path):
    root = tmp_path / "imgs"
    nested = root / "chapter1" / "scans"
    nested.mkdir(parents=True)
    img = nested / "page.png"
    img.write_bytes(b"")
    out = tmp_path / "out"

    dest = resolve_dest_dir(img, output_dir=out, mirror_root=root.resolve())
    assert dest == out / "chapter1" / "scans"


def test_resolve_dest_dir_falls_back_when_image_outside_mirror_root(tmp_path):
    """If the image isn't under mirror_root, dump flat into output_dir."""
    root = tmp_path / "imgs"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    img = elsewhere / "page.png"
    img.write_bytes(b"")
    out = tmp_path / "out"

    assert resolve_dest_dir(img, output_dir=out, mirror_root=root.resolve()) == out


# ---------------------------------------------------------------------------
# output_paths_for / illustration_crop_path
# ---------------------------------------------------------------------------


def test_output_paths_for_pairs_txt_and_json(tmp_path):
    img = Path("/some/where/page-001.png")
    out = tmp_path / "out"
    txt, json_ = output_paths_for(img, out)
    assert txt == out / "page-001.txt"
    assert json_ == out / "page-001.json"


def test_illustration_crop_path_zero_pads_index(tmp_path):
    out = tmp_path / "out"
    assert illustration_crop_path(out, "page-001", 1) == out / "i_page-001_01.jpg"
    assert illustration_crop_path(out, "page-001", 12) == out / "i_page-001_12.jpg"


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
# layout-debug env scaffolding
# ---------------------------------------------------------------------------


def test_setup_layout_debug_env_returns_none_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("PD_OCR_LAYOUT_DEBUG", raising=False)
    monkeypatch.delenv("PD_OCR_LAYOUT_DEBUG_FILE", raising=False)
    args = _ns(layout_debug=False)
    assert setup_layout_debug_env(args, tmp_path, "page") is None
    assert "PD_OCR_LAYOUT_DEBUG" not in os.environ
    assert "PD_OCR_LAYOUT_DEBUG_FILE" not in os.environ


def test_setup_layout_debug_env_writes_into_dest_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("PD_OCR_LAYOUT_DEBUG", raising=False)
    monkeypatch.delenv("PD_OCR_LAYOUT_DEBUG_FILE", raising=False)
    dest = tmp_path / "out"
    dest.mkdir()
    args = _ns(layout_debug=True, layout_debug_dir=None)

    debug_file = setup_layout_debug_env(args, dest, "page-001")
    assert debug_file == dest / "page-001.layout-debug.txt"
    assert os.environ["PD_OCR_LAYOUT_DEBUG"] == "1"
    assert os.environ["PD_OCR_LAYOUT_DEBUG_FILE"] == str(debug_file)
    clear_layout_debug_env()
    assert "PD_OCR_LAYOUT_DEBUG" not in os.environ
    assert "PD_OCR_LAYOUT_DEBUG_FILE" not in os.environ


def test_setup_layout_debug_env_uses_explicit_debug_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("PD_OCR_LAYOUT_DEBUG", raising=False)
    monkeypatch.delenv("PD_OCR_LAYOUT_DEBUG_FILE", raising=False)
    dest = tmp_path / "out"
    dest.mkdir()
    debug_dir = tmp_path / "dbg"  # does not exist yet
    args = _ns(layout_debug=True, layout_debug_dir=str(debug_dir))

    debug_file = setup_layout_debug_env(args, dest, "page-001")
    assert debug_file == debug_dir / "page-001.layout-debug.txt"
    assert debug_dir.is_dir()  # was created
    clear_layout_debug_env()


def test_clear_layout_debug_env_idempotent(monkeypatch):
    monkeypatch.delenv("PD_OCR_LAYOUT_DEBUG", raising=False)
    monkeypatch.delenv("PD_OCR_LAYOUT_DEBUG_FILE", raising=False)
    # No-op when nothing was set; should not raise.
    clear_layout_debug_env()
    clear_layout_debug_env()


# ---------------------------------------------------------------------------
# format_drops_warning
# ---------------------------------------------------------------------------


def test_format_drops_warning_empty_returns_empty_list():
    assert format_drops_warning([], "page.png") == []


def test_format_drops_warning_short_list_renders_all_lines():
    drops = ["the [10,20]", "quick [30,40]"]
    out = format_drops_warning(drops, "page.png")
    assert out == [
        "WARNING: reorganize dropped 2 word(s) in page.png:",
        "  the [10,20]",
        "  quick [30,40]",
    ]


def test_format_drops_warning_truncates_long_list():
    drops = [f"word{i}" for i in range(25)]
    out = format_drops_warning(drops, "page.png", max_lines=20)
    # 1 headline + 20 detail lines + 1 "more" tail
    assert len(out) == 22
    assert out[0] == "WARNING: reorganize dropped 25 word(s) in page.png:"
    assert out[-1] == "  ... (5 more)"


def test_format_drops_warning_exact_max_lines_no_tail():
    drops = [f"word{i}" for i in range(20)]
    out = format_drops_warning(drops, "page.png", max_lines=20)
    assert len(out) == 21  # headline + 20 details, no "more" tail
    assert "more)" not in out[-1]


# ---------------------------------------------------------------------------
# iter_crop_regions
# ---------------------------------------------------------------------------


class _Region:
    """Minimal stand-in for pdomain_book_tools' Region used in selection tests."""

    def __init__(self, type_, confidence):
        self.type = type_
        self.confidence = confidence


def test_iter_crop_regions_filters_by_type_and_confidence():
    regions = [
        _Region("figure", 0.9),  # kept
        _Region("text", 0.99),  # wrong type
        _Region("figure", 0.4),  # too low
        _Region("table", 0.6),  # kept
        _Region("decoration", 0.55),  # kept
    ]
    crop_types = {"figure", "decoration", "table"}
    out = list(iter_crop_regions(regions, confidence_threshold=0.5, crop_types=crop_types))
    assert [(idx, r.type, r.confidence) for idx, r in out] == [
        (1, "figure", 0.9),
        (2, "table", 0.6),
        (3, "decoration", 0.55),
    ]


def test_iter_crop_regions_indices_are_one_based_consecutive():
    regions = [_Region("figure", 0.8) for _ in range(4)]
    out = list(iter_crop_regions(regions, 0.5, {"figure"}))
    assert [idx for idx, _ in out] == [1, 2, 3, 4]


def test_iter_crop_regions_empty_when_nothing_matches():
    regions = [_Region("text", 0.99), _Region("figure", 0.1)]
    out = list(iter_crop_regions(regions, 0.5, {"figure"}))
    assert out == []


def test_iter_crop_regions_module_constants_present():
    """Regression guard: env-var names are part of the layout-debug contract."""
    assert _pipeline._LAYOUT_DEBUG_ENV == "PD_OCR_LAYOUT_DEBUG"
    assert _pipeline._LAYOUT_DEBUG_FILE_ENV == "PD_OCR_LAYOUT_DEBUG_FILE"


# ---------------------------------------------------------------------------
# format_noise_drop_warning
# ---------------------------------------------------------------------------


class _Word:
    def __init__(self, text: str):
        self.text = text


def test_format_noise_drop_warning_empty_returns_empty_list():
    assert format_noise_drop_warning([], "page.png", "--flag") == []


def test_format_noise_drop_warning_includes_count_and_sample_and_hint():
    words = [_Word("foo"), _Word("bar"), _Word("baz")]
    out = format_noise_drop_warning(words, "page.png", "--save-reorganize-diagnostics")
    joined = "\n".join(out)
    assert "page.png" in joined
    assert "dropped 3 word(s)" in joined
    assert '"foo"' in joined
    assert '"bar"' in joined
    assert '"baz"' in joined
    assert "--save-reorganize-diagnostics" in joined


def test_format_noise_drop_warning_truncates_long_sample():
    words = [_Word(f"w{i}") for i in range(20)]
    out = format_noise_drop_warning(words, "page.png", "--flag", sample_size=5)
    joined = "\n".join(out)
    assert "dropped 20 word(s)" in joined
    assert "(+15 more)" in joined


def test_format_noise_drop_warning_handles_blank_token_text():
    words = [_Word(""), _Word("real")]
    out = format_noise_drop_warning(words, "page.png", "--flag")
    joined = "\n".join(out)
    # Blanks are skipped from the sample but still counted.
    assert "dropped 2 word(s)" in joined
    assert '"real"' in joined


def test_format_noise_drop_warning_no_phantom_more_when_blanks_within_sample():
    """All words fit within sample_size; blank-filtering must not produce
    a phantom ``(+N more)`` suffix."""
    # 2 words total, sample_size default (8). Blank gets filtered for display
    # but the entire population was already within the sample window, so
    # no "+N more" hint should appear.
    words = [_Word(""), _Word("real")]
    out = format_noise_drop_warning(words, "page.png", "--flag")
    joined = "\n".join(out)
    assert "more)" not in joined, f"phantom (+N more) suffix in: {joined!r}"


def test_format_noise_drop_warning_more_count_reflects_unseen_words():
    """When count exceeds sample_size, the suffix counts truly-unseen words,
    not a number inflated by blank-filtered display tokens."""
    # 10 words: first 5 blank, next 5 real. sample_size=5 grabs the first 5
    # (all blank). After blank-filter samples is empty. Total unseen = 5.
    words = [_Word("") for _ in range(5)] + [_Word(f"w{i}") for i in range(5)]
    out = format_noise_drop_warning(words, "page.png", "--flag", sample_size=5)
    joined = "\n".join(out)
    assert "(+5 more)" in joined, f"expected (+5 more) in: {joined!r}"


# ---------------------------------------------------------------------------
# diagnostic_output_paths
# ---------------------------------------------------------------------------


def test_diagnostic_output_paths_pairs_pure_and_post_noise(tmp_path):
    json_p = tmp_path / "page-001.json"
    txt_p = tmp_path / "page-001.txt"
    paths = diagnostic_output_paths(json_p, txt_p)
    assert paths["pure_ocr_json"] == tmp_path / "page-001.pure-ocr.json"
    assert paths["pure_ocr_txt"] == tmp_path / "page-001.pure-ocr.txt"
    assert paths["post_noise_json"] == tmp_path / "page-001.post-noise.json"
    assert paths["post_noise_txt"] == tmp_path / "page-001.post-noise.txt"


def test_diagnostic_output_paths_preserves_multi_dot_stem(tmp_path):
    """Regression test for B7: image stems with embedded dots
    (e.g. ``page.001.png`` → ``page.001.txt``) must not collapse into a
    shared diagnostic filename. Previously ``Path.with_suffix`` stripped
    ``.001`` from ``page.001`` and every ``page.NNN.png`` overwrote the
    same diagnostic files.
    """
    json_p = tmp_path / "page.001.json"
    txt_p = tmp_path / "page.001.txt"
    paths = diagnostic_output_paths(json_p, txt_p)
    assert paths["pure_ocr_json"] == tmp_path / "page.001.pure-ocr.json"
    assert paths["pure_ocr_txt"] == tmp_path / "page.001.pure-ocr.txt"
    assert paths["post_noise_json"] == tmp_path / "page.001.post-noise.json"
    assert paths["post_noise_txt"] == tmp_path / "page.001.post-noise.txt"

    # And the collision: page.001 vs page.002 must yield distinct diag paths.
    paths2 = diagnostic_output_paths(tmp_path / "page.002.json", tmp_path / "page.002.txt")
    assert paths["pure_ocr_txt"] != paths2["pure_ocr_txt"]
    assert paths["post_noise_json"] != paths2["post_noise_json"]


# ---------------------------------------------------------------------------
# write_diagnostic_snapshots
# ---------------------------------------------------------------------------


class _Snapshot:
    def __init__(self, text: str, payload: dict | None = None):
        self.text = text
        self._payload = payload or {"text": text}

    def to_dict(self):
        return self._payload


class _PageWithDiagnostics:
    def __init__(self, pure: _Snapshot | None, post: _Snapshot | None):
        self.diagnostic_pure_ocr = pure
        self.diagnostic_post_noise_removal = post


def test_write_diagnostic_snapshots_writes_all_four_when_present(tmp_path):
    page = _PageWithDiagnostics(
        pure=_Snapshot("pure text", {"type": "Page", "n": 1}),
        post=_Snapshot("post text", {"type": "Page", "n": 2}),
    )
    written, notes = write_diagnostic_snapshots(
        page,
        pure_ocr_json=tmp_path / "page.pure-ocr.json",
        pure_ocr_txt=tmp_path / "page.pure-ocr.txt",
        post_noise_json=tmp_path / "page.post-noise.json",
        post_noise_txt=tmp_path / "page.post-noise.txt",
    )
    assert notes == []
    assert (tmp_path / "page.pure-ocr.txt").read_text() == "pure text"
    assert (tmp_path / "page.post-noise.txt").read_text() == "post text"
    # JSON files are non-empty and parse.
    import json as _json

    assert _json.loads((tmp_path / "page.pure-ocr.json").read_text())["n"] == 1
    assert _json.loads((tmp_path / "page.post-noise.json").read_text())["n"] == 2
    assert len(written) == 4


def test_write_diagnostic_snapshots_skips_missing_with_note(tmp_path):
    page = _PageWithDiagnostics(pure=None, post=None)
    written, notes = write_diagnostic_snapshots(
        page,
        pure_ocr_json=tmp_path / "page.pure-ocr.json",
        pure_ocr_txt=tmp_path / "page.pure-ocr.txt",
        post_noise_json=tmp_path / "page.post-noise.json",
        post_noise_txt=tmp_path / "page.post-noise.txt",
    )
    assert written == []
    assert any("diagnostic_pure_ocr unavailable" in n for n in notes)
    assert any("diagnostic_post_noise_removal unavailable" in n for n in notes)
    assert not (tmp_path / "page.pure-ocr.json").exists()
    assert not (tmp_path / "page.post-noise.json").exists()


def test_write_diagnostic_snapshots_signature_has_no_unused_path_params():
    """B4: ``json_path`` / ``txt_path`` were accepted but silently ignored.

    They've been removed from the signature so callers can't mistake them
    for inputs the helper writes to.
    """
    import inspect

    params = inspect.signature(write_diagnostic_snapshots).parameters
    assert "json_path" not in params
    assert "txt_path" not in params


def test_write_diagnostic_snapshots_partial_one_missing(tmp_path):
    """Only one snapshot present — the other is reported as unavailable."""
    page = _PageWithDiagnostics(
        pure=_Snapshot("only pure", {"x": 1}),
        post=None,
    )
    written, notes = write_diagnostic_snapshots(
        page,
        pure_ocr_json=tmp_path / "page.pure-ocr.json",
        pure_ocr_txt=tmp_path / "page.pure-ocr.txt",
        post_noise_json=tmp_path / "page.post-noise.json",
        post_noise_txt=tmp_path / "page.post-noise.txt",
    )
    assert (tmp_path / "page.pure-ocr.json").exists()
    assert not (tmp_path / "page.post-noise.json").exists()
    assert len(written) == 2  # pure pair only
    assert any("post_noise_removal unavailable" in n for n in notes)


# ---------------------------------------------------------------------------
# atomic_write_text / atomic_write_bytes (B18)  # noqa: ERA001  # section header, not dead code
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
