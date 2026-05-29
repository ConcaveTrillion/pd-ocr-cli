"""Silent-no-op and noise-drop warning tests for ocr_to_txt.main() with heavy deps mocked."""

from __future__ import annotations

import pytest
from _fakes import FakePage

from pdomain_ocr_cli import ocr_to_txt

# ---------------------------------------------------------------------------
# Noise-drop warnings
# ---------------------------------------------------------------------------


def test_main_noise_drop_warning_always_fires(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    """When the library reports any dropped words, stderr gets a warning
    that includes the count, a quoted token sample, and the re-run hint —
    regardless of whether --save-json / diagnostics are passed.
    """
    mock_heavy_deps(
        page=FakePage(
            text="POST-REORG TEXT",
            dropped_word_texts=["foo", "bar", "baz"],
        )
    )
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "page.png" in err
    assert "dropped 3 word(s)" in err
    assert '"foo"' in err
    assert '"bar"' in err
    assert '"baz"' in err
    # Hint references the current flag name (plus --save-json which it requires).
    assert "--save-reorganize-diagnostics" in err


def test_main_noise_drop_warning_silent_with_zero_count(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    """Mirror of ``test_main_noise_drop_warning_always_fires`` — when the
    library reports ``diagnostic_noise_dropped_count == 0`` (which is the
    new default-flag-off behavior after the upstream library tightening),
    the always-on warning must NOT fire and stderr must contain neither
    the count line nor the "look like figure-internal noise" phrase nor
    the diagnostic re-run hint.
    """
    # Build a page whose diagnostic snapshots are populated but whose
    # dropped list is empty — i.e. reorganize ran with drop_layout_words=False
    # and preserved every word.
    mock_heavy_deps(
        page=FakePage(
            text="POST-REORG TEXT",
            pure_ocr_text="PURE OCR TEXT",
            post_noise_text="POST NOISE TEXT",
            dropped_word_texts=[],  # explicit empty list
        )
    )
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "mutable latest OCR model revision" in err
    assert "look like figure-internal noise" not in err
    assert "dropped 0 word(s)" not in err
    assert "--save-reorganize-diagnostics to write the full" not in err
    assert (out / "page.txt").read_text() == "POST-REORG TEXT"


def test_main_prints_default_model_trust_warning_once(
    mock_heavy_deps, run_main, single_image, capsys
):
    mock_heavy_deps()
    img, out = single_image

    run_main("--no-update-check", "--layout-model", "none", "-o", str(out), str(img))

    err = capsys.readouterr().err
    assert err.count("mutable latest OCR model revision") == 1


# ---------------------------------------------------------------------------
# B3 silent-no-op warnings — parametrized family
# ---------------------------------------------------------------------------

# Each tuple: (id, extra_flags, expected_substrings)
# "DEBUG_DIR" sentinel is replaced with str(tmp_path / "debug") at runtime.
# Cases that did NOT use --layout-model none in the original include it in
# their own flags list; cases that did omit it also omit it here.
_WARN_CASES = [
    (
        "no_reorg+save_diag",  # B3.1
        ["--layout-model", "none", "--no-reorg", "--save-json", "--save-reorganize-diagnostics"],
        ["--no-reorg", "--save-reorganize-diagnostics"],
    ),
    (
        "no_reorg+validate_reorg",  # B3.2
        ["--layout-model", "none", "--no-reorg", "--validate-reorg"],
        ["--no-reorg", "--validate-reorg"],
    ),
    (
        "layout_none+layout_debug",  # B3.3
        ["--layout-model", "none", "--layout-debug"],
        ["--layout-model none", "--layout-debug"],
    ),
    (
        "layout_debug_dir_without_layout_debug",  # B11 — original omitted --layout-model none
        ["--layout-debug-dir", "DEBUG_DIR"],
        ["--layout-debug-dir", "--layout-debug"],
    ),
    (
        "no_reorg+experimental_drop_layout_words",  # B15
        ["--layout-model", "none", "--no-reorg", "--experimental-drop-layout-words"],
        ["--no-reorg", "--experimental-drop-layout-words"],
    ),
    (
        "save_reorg_diag_without_save_json",  # B16
        ["--layout-model", "none", "--save-reorganize-diagnostics"],
        ["--save-reorganize-diagnostics", "--save-json"],
    ),
    (
        "no_illustration_placeholders+no_reorg",  # original omitted --layout-model none
        ["--no-reorg", "--no-illustration-placeholders"],
        ["--no-illustration-placeholders", "--no-reorg"],
    ),
]


@pytest.mark.parametrize(
    ("flags", "expected"),
    [(f, e) for _, f, e in _WARN_CASES],
    ids=[c[0] for c in _WARN_CASES],
)
def test_main_silent_no_op_warns(
    mock_heavy_deps, run_main, single_image, capsys, tmp_path, flags, expected
):
    """Parametrized: each silent-no-op flag combo must emit a stderr warning."""
    img, out = single_image
    flags = [str(tmp_path / "debug") if f == "DEBUG_DIR" else f for f in flags]
    mock_heavy_deps()
    run_main("--no-update-check", *flags, "-o", str(out), str(img))
    err = capsys.readouterr().err
    for sub in expected:
        assert sub in err
    assert "warning" in err.lower()


def test_main_no_reorg_with_layout_debug_warns_and_suppresses_success_path(
    mock_heavy_deps, run_main, single_image, capsys, tmp_path
):
    """B9: ``--no-reorg --layout-debug`` is a silent no-op.

    The layout-debug report is written from inside ``Page.reorganize_page``,
    which never runs under ``--no-reorg``. The CLI must (a) emit a stderr
    warning so users understand the flag is ignored, and (b) suppress the
    misleading ``layout-debug: <path>`` segment on the success line that
    points at a file that was never written.
    """
    mock_heavy_deps()
    img, out = single_image
    debug_dir_file = tmp_path / "not-a-debug-dir"
    debug_dir_file.write_text("file, not directory", encoding="utf-8")

    run_main(
        "--no-update-check",
        "--no-reorg",
        "--layout-debug",
        "--layout-debug-dir",
        str(debug_dir_file),
        "-o",
        str(out),
        str(img),
    )

    captured = capsys.readouterr()
    err = captured.err
    assert "--no-reorg" in err
    assert "--layout-debug" in err
    assert "warning" in err.lower()
    # Success line must not falsely advertise a layout-debug artifact.
    assert "layout-debug:" not in captured.out
    assert debug_dir_file.is_file()


def test_main_layout_debug_announces_artifact_on_success_line(
    mock_heavy_deps, run_main, single_image, capsys
):
    """With layout enabled (not ``--layout-model none``) and ``--layout-debug``,
    the success line must include a ``layout-debug: <path>`` segment.

    ``setup_layout_debug_env`` sets the env vars and returns a non-None path;
    ``ocr_to_txt.py`` appends it to ``extra_paths`` when
    ``args.layout_debug and debug_file is not None and do_reorg`` all hold.
    The mock layout detector (installed by ``mock_heavy_deps``) returns empty
    regions, so ``reorganize_page`` still runs — the announcement fires.
    """
    mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-debug",
        "-o",
        str(out),
        str(img),
    )

    captured = capsys.readouterr()
    assert "layout-debug:" in captured.out


def test_main_plain_no_reorg_skips_default_layout_loading(
    mock_heavy_deps, monkeypatch, run_main, single_image
):
    mock_heavy_deps()
    img, out = single_image

    def fail_layout_load(args, device):
        raise AssertionError("layout should not load for plain --no-reorg")

    monkeypatch.setattr(ocr_to_txt, "_load_layout_detector", fail_layout_load)

    run_main("--no-update-check", "--no-reorg", "-o", str(out), str(img))

    assert (out / "page.txt").read_text() == "FAKE OCR TEXT"
