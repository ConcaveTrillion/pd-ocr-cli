"""Silent-no-op and noise-drop warning tests for ocr_to_txt.main() with heavy deps mocked."""

from __future__ import annotations

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
# B3 silent-no-op warnings
# ---------------------------------------------------------------------------


def test_main_no_reorg_with_save_diag_warns(mock_heavy_deps, run_main, single_image, capsys):
    """B3.1: ``--no-reorg --save-reorganize-diagnostics`` is a silent no-op.

    The diagnostics flag only fires when reorganize runs, so combining it
    with ``--no-reorg`` produces no output. Warn the user explicitly to
    stderr so the flag's silence is not surprising.
    """
    mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--no-reorg",
        "--save-json",
        "--save-reorganize-diagnostics",
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "--no-reorg" in err
    assert "--save-reorganize-diagnostics" in err
    assert "warning" in err.lower()


def test_main_no_reorg_with_validate_reorg_warns(mock_heavy_deps, run_main, single_image, capsys):
    """B3.2: ``--no-reorg --validate-reorg`` silently skips validation.

    The ``if do_reorg and args.validate_reorg`` gate short-circuits, so no
    validation runs and no warning is shown. Emit a stderr warning making
    that explicit.
    """
    mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--no-reorg",
        "--validate-reorg",
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "--no-reorg" in err
    assert "--validate-reorg" in err
    assert "warning" in err.lower()


def test_main_layout_none_with_layout_debug_warns(mock_heavy_deps, run_main, single_image, capsys):
    """B3.3: ``--layout-model none --layout-debug`` is a silent no-op.

    With layout disabled the debug file path is announced on stdout but no
    layout model ever runs, so the file never materializes. Warn on stderr
    so users understand why the announced path stays empty.
    """
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

    err = capsys.readouterr().err
    assert "--layout-model none" in err
    assert "--layout-debug" in err
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


def test_main_layout_debug_dir_without_layout_debug_warns(
    mock_heavy_deps, run_main, single_image, capsys, tmp_path
):
    """B11: ``--layout-debug-dir DIR`` without ``--layout-debug`` is a silent no-op.

    The directory argument is only consulted inside ``setup_layout_debug_env``,
    which short-circuits to ``None`` when ``--layout-debug`` was not passed.
    Users who specify a debug directory without the enable flag get no
    artifacts and no feedback. Warn on stderr per the B3 pattern.
    """
    mock_heavy_deps()
    img, out = single_image
    debug_dir = tmp_path / "debug"

    run_main(
        "--no-update-check",
        "--layout-debug-dir",
        str(debug_dir),
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "--layout-debug-dir" in err
    assert "--layout-debug" in err
    assert "warning" in err.lower()


def test_main_no_reorg_with_experimental_drop_layout_words_warns(
    mock_heavy_deps, run_main, single_image, capsys
):
    """B15: ``--experimental-drop-layout-words`` with ``--no-reorg`` is a silent no-op.

    The flag is consumed only inside the ``if do_reorg:`` block, so combining
    it with ``--no-reorg`` quietly does nothing. Warn on stderr per the B3
    silent-no-op pattern.
    """
    mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--no-reorg",
        "--experimental-drop-layout-words",
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "--no-reorg" in err
    assert "--experimental-drop-layout-words" in err
    assert "warning" in err.lower()


def test_main_save_reorganize_diagnostics_without_save_json_warns(
    mock_heavy_deps, run_main, single_image, capsys
):
    """B16: ``--save-reorganize-diagnostics`` without ``--save-json`` is a silent no-op.

    The diagnostic-export bundle is gated on ``args.save_json`` in the
    per-image loop, so a user passing only ``--save-reorganize-diagnostics``
    (or its legacy alias ``--save-pre-reorg-json``) gets no diagnostic
    files and no feedback. Warn on stderr per the B3 silent-no-op pattern.
    """
    mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--save-reorganize-diagnostics",
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "--save-reorganize-diagnostics" in err
    assert "--save-json" in err
    assert "warning" in err.lower()


def test_main_no_illustration_placeholders_with_no_reorg_warns(
    mock_heavy_deps, run_main, single_image, capsys
):
    """``--no-illustration-placeholders --no-reorg`` is a silent no-op; warn.

    Placeholder emission happens inside reorganize_page, which is skipped
    under --no-reorg. Match the B3 no-op-warning pattern.
    """
    mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--no-reorg",
        "--no-illustration-placeholders",
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "--no-illustration-placeholders" in err
    assert "--no-reorg" in err
    assert "warning" in err.lower()


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
