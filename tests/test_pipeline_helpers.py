"""Unit tests for the pure pipeline helpers in :mod:`pd_ocr_cli._pipeline`.

These cover the path-mirroring, text-normalization-apply, layout-debug
env scaffolding, drops-warning formatting, and illustration-region
selection logic that ``ocr_to_txt.main`` orchestrates per page.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_ocr_cli import _pipeline
from pd_ocr_cli._pipeline import (
    apply_text_normalizations,
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
    base = dict(
        layout_model="pp-doclayout-plus-l",
        extract_illustrations=False,
        layout_debug=False,
        layout_debug_dir=None,
    )
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
    """Minimal stand-in for pd_book_tools' Region used in selection tests."""

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
    assert '"foo"' in joined and '"bar"' in joined and '"baz"' in joined
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
