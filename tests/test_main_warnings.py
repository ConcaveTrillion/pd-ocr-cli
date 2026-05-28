"""Silent-no-op and noise-drop warning tests for ocr_to_txt.main() with heavy deps mocked."""

from __future__ import annotations

import pytest
from _fakes import FakePage

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


def test_main_noise_drop_warning_skipped_when_no_drops(
    mock_heavy_deps, run_main, single_image, capsys
):
    mock_heavy_deps()
    img, out = single_image

    # Default _FakePage has no dropped words.
    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "dropped" not in err.lower() or "look like figure-internal noise" not in err


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
    assert "look like figure-internal noise" not in err
    assert "dropped 0 word(s)" not in err
    assert "--save-reorganize-diagnostics to write the full" not in err
    assert (out / "page.txt").read_text() == "POST-REORG TEXT"


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
    mock_heavy_deps, run_main, single_image, capsys
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

    run_main(
        "--no-update-check",
        "--no-reorg",
        "--layout-debug",
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


def test_main_layout_debug_writes_debug_file(mock_heavy_deps, run_main, single_image):
    mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--layout-debug",
        "-o",
        str(out),
        str(img),
    )

    # The env-var setup helper makes the debug dir; the loop never writes the
    # actual file (pdomain_book_tools does that), but the path is announced in the
    # "extra paths" line on stdout.
    assert (out / "page.txt").exists()
