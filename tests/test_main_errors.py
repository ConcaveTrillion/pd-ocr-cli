"""Error-path tests for ocr_to_txt.main() with heavy deps mocked."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from _fakes import FakeArray, FakePage

from pdomain_ocr_cli import ocr_to_txt

# ---------------------------------------------------------------------------
# Atomic-write / JSON sidecar cleanup
# ---------------------------------------------------------------------------


def test_main_save_json_failure_cleans_up_tmp_and_increments_errors(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    """If ``_SinglePageDoc.to_json_file`` fails mid-write the canonical ``.json``
    must not exist and the sibling tmp must be cleaned up. The error
    counter increments. (B18 atomic-write invariant for the JSON
    sidecar.)
    """
    mock_heavy_deps()
    img, out = single_image

    # Patch _SinglePageDoc so its to_json_file partially writes then raises.
    _orig_single_page_doc = ocr_to_txt._SinglePageDoc  # type: ignore[attr-defined]

    class _BoomSinglePageDoc(_orig_single_page_doc):
        def to_json_file(self, file_path):
            # Mimic a partial flush before crashing — the helper must
            # still leave the canonical name absent.
            Path(file_path).write_text("PARTIAL", encoding="utf-8")
            raise OSError(28, "No space left on device")

    monkeypatch.setattr(ocr_to_txt, "_SinglePageDoc", _BoomSinglePageDoc)

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            "--save-json",
            "-o",
            str(out),
            str(img),
        )
    assert exc_info.value.code == 1

    # No canonical JSON, no leftover hidden tmp.
    assert not (out / "page.json").exists()
    assert not (out / ".page.json.tmp").exists()
    err = capsys.readouterr().err
    assert "ERROR processing" in err
    assert "No space left on device" in err
    # B19: ``.txt`` is written *after* the json sidecar (and the rest
    # of the per-page artifacts) so a json failure must not leave an
    # orphan ``.txt`` for downstream pipelines that key on its
    # existence to mean "this page completed".
    assert not (out / "page.txt").exists()


def test_main_save_json_failure_with_no_tmp_swallows_unlink_error(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    """When ``_SinglePageDoc.to_json_file`` raises *before* it ever creates
    the sibling tmp, the defensive ``unlink()`` must swallow
    ``FileNotFoundError`` and re-raise the original error. Covers the
    same B18 cleanup branch when no partial tmp ever lands on disk.
    """
    mock_heavy_deps()
    img, out = single_image

    # Patch _SinglePageDoc so to_json_file raises without touching disk.
    _orig_single_page_doc = ocr_to_txt._SinglePageDoc  # type: ignore[attr-defined]

    class _ExplodeSinglePageDoc(_orig_single_page_doc):
        def to_json_file(self, file_path):
            raise RuntimeError("explode before any byte hits disk")

    monkeypatch.setattr(ocr_to_txt, "_SinglePageDoc", _ExplodeSinglePageDoc)

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            "--save-json",
            "-o",
            str(out),
            str(img),
        )
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "explode before any byte hits disk" in err
    assert not (out / "page.json").exists()


# ---------------------------------------------------------------------------
# Illustration imwrite cleanup
# ---------------------------------------------------------------------------


def test_main_extract_illustrations_imwrite_returns_false_no_tmp_swallows_unlink(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    """``cv2.imwrite`` returns False but never created the tmp file:
    the defensive cleanup must swallow ``FileNotFoundError`` and warn
    rather than crashing the batch.
    """
    mock_heavy_deps()
    img, out = single_image

    fake_layout = MagicMock()
    fake_layout.detect = MagicMock(
        return_value=SimpleNamespace(
            regions=[SimpleNamespace(L=0, R=10, T=0, B=10, type="figure", confidence=0.99)],
            inference_ms=1,
        )
    )
    monkeypatch.setattr(ocr_to_txt, "_load_layout_detector", lambda args, device: fake_layout)

    fake_cv2 = MagicMock()
    fake_cv2.imread = MagicMock(return_value=FakeArray(100))
    # Returns False without ever touching disk.
    fake_cv2.imwrite = MagicMock(return_value=False)
    monkeypatch.setattr(ocr_to_txt, "_load_illustration_deps", lambda: (fake_cv2, {"figure"}))

    run_main(
        "--no-update-check",
        "--layout-model",
        "pp-doclayout-plus-l",
        "--extract-illustrations",
        "-o",
        str(out),
        str(img),
    )
    assert (out / "page.txt").exists()
    assert not (out / "i_page_01.jpg").exists()
    assert "cv2.imwrite failed" in capsys.readouterr().err


def test_main_extract_illustrations_imwrite_failure_skips_and_cleans_tmp(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    """When ``cv2.imwrite`` returns False for a crop, the atomic-write
    branch must remove any sibling tmp it created and emit a warning,
    not crash the batch and not leave the canonical crop on disk.
    (B18 atomic-write invariant for illustration crops.)
    """
    mock_heavy_deps()
    img, out = single_image

    fake_layout = MagicMock()
    fake_layout.detect = MagicMock(
        return_value=SimpleNamespace(
            regions=[SimpleNamespace(L=0, R=10, T=0, B=10, type="figure", confidence=0.99)],
            inference_ms=1,
        )
    )
    monkeypatch.setattr(ocr_to_txt, "_load_layout_detector", lambda args, device: fake_layout)

    fake_cv2 = MagicMock()
    fake_cv2.imread = MagicMock(return_value=FakeArray(100))

    def _imwrite_returns_false(path, _crop):
        # Touch the tmp so we can verify cleanup actually unlinks it.
        Path(path).write_bytes(b"\x00")
        return False

    fake_cv2.imwrite = MagicMock(side_effect=_imwrite_returns_false)
    monkeypatch.setattr(ocr_to_txt, "_load_illustration_deps", lambda: (fake_cv2, {"figure"}))

    run_main(
        "--no-update-check",
        "--layout-model",
        "pp-doclayout-plus-l",
        "--extract-illustrations",
        "-o",
        str(out),
        str(img),
    )

    # The .txt still landed (atomic txt write succeeded).
    assert (out / "page.txt").exists()
    # The crop did not — and the tmp was unlinked.
    assert not (out / "i_page_01.jpg").exists()
    assert not list(out.glob(".i_page_01*.tmp*"))
    err = capsys.readouterr().err
    assert "cv2.imwrite failed" in err


# ---------------------------------------------------------------------------
# Per-image exception paths
# ---------------------------------------------------------------------------


def test_main_batch_runner_error_reports_chunk_and_exits_1(
    mock_heavy_deps, run_main, make_images, capsys
):
    ns = mock_heavy_deps()
    imgs = make_images(2)
    out = imgs[0].parent / "out"

    def boom_batch(images, *, predictor, device, source_identifiers):
        raise RuntimeError("batch backend exploded")

    ns.runtime_session.runner = boom_batch

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(out),
            str(imgs[0]),
            str(imgs[1]),
        )

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR processing batch" in captured.err
    assert "batch backend exploded" in captured.err
    assert "Done (2 error(s))" in captured.out
    assert not (out / f"{imgs[0].stem}.txt").exists()
    assert not (out / f"{imgs[1].stem}.txt").exists()


def test_main_batch_result_count_mismatch_is_clean_error(
    mock_heavy_deps, run_main, make_images, capsys
):
    ns = mock_heavy_deps()
    imgs = make_images(2)
    out = imgs[0].parent / "out"

    def short_batch(images, *, predictor, device, source_identifiers):
        return [FakePage(text="ONLY ONE")]

    ns.runtime_session.runner = short_batch

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(out),
            str(imgs[0]),
            str(imgs[1]),
        )

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "batch returned 1 page(s) for 2 image(s)" in captured.err
    assert "Done (2 error(s))" in captured.out


def test_main_per_image_exception_terminates_processing_stdout_line(
    mock_heavy_deps, run_main, make_images, capsys
):
    """B17: when the per-image ``try`` raises (caught by the broad
    ``except Exception``), the ``Processing X ...`` stdout line printed
    with ``end=" "`` must be terminated before the next image's
    ``Processing`` line is written. Otherwise consecutive failed images
    print as ``Processing a ... Processing b ... `` glued onto a single
    stdout line, with the corresponding ``ERROR processing`` messages
    going to stderr where they don't help readers reading stdout.

    The ``page is None`` and ``KeyboardInterrupt`` siblings already do
    this; the broad ``except Exception`` branch did not.
    """
    ns = mock_heavy_deps()
    imgs = make_images(2)
    out = imgs[0].parent / "out"

    # Both pages raise during per-page post-processing (reorganize_page).
    # This exercises the ``except Exception`` branch in the per-page loop
    # — the same branch the old per-image factory raise hit.
    call_idx = {"n": 0}

    def _boom_batch(images, *, predictor, device, source_identifiers):
        pages = []
        for _ in images:
            idx = call_idx["n"]
            call_idx["n"] += 1
            p = FakePage(text=f"PAGE_{idx}")
            p.reorganize_page = MagicMock(side_effect=RuntimeError(f"boom-img{idx}"))
            pages.append(p)
        return pages

    ns.runtime_session.runner = _boom_batch

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(out),
            str(imgs[0]),
            str(imgs[1]),
        )
    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    # The two ``Processing`` lines must each terminate before the next
    # one is printed. They are emitted with ``end=" "``; on failure,
    # the exception branch must close the line so ``Processing b`` does
    # not glue onto the prior ``Processing a ...`` line.
    assert "Processing" in captured.out
    proc_lines = [ln for ln in captured.out.splitlines() if "Processing" in ln]
    assert len(proc_lines) == 2, (
        f"expected 2 separate Processing lines (one per image), got: {captured.out!r}"
    )
    # Both errors should still land on stderr.
    assert captured.err.count("ERROR processing") == 2


def test_main_per_image_exception_increments_error_count(
    mock_heavy_deps, run_main, single_image, capsys
):
    ns = mock_heavy_deps()
    img, out = single_image

    # Raise during per-page post-processing (reorganize_page is called inside
    # the per-page try/except block), which exercises the same error path as
    # the old per-image factory raise.
    def _boom_batch(images, *, predictor, device, source_identifiers):
        p = FakePage(text="OK")
        p.reorganize_page = MagicMock(side_effect=RuntimeError("synthetic OCR failure"))
        return [p for _ in images]

    ns.runtime_session.runner = _boom_batch

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(out),
            str(img),
        )
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR processing" in captured.err
    assert "synthetic OCR failure" in captured.err
    assert "1 error(s)" in captured.out


def test_main_per_image_exception_with_debug_prints_traceback(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    """``PD_OCR_DEBUG=1`` adds a traceback to the per-image error output."""
    ns = mock_heavy_deps()
    img, out = single_image

    def _boom_batch(images, *, predictor, device, source_identifiers):
        p = FakePage(text="OK")
        p.reorganize_page = MagicMock(side_effect=RuntimeError("synthetic"))
        return [p for _ in images]

    ns.runtime_session.runner = _boom_batch
    monkeypatch.setenv("PD_OCR_DEBUG", "1")

    with pytest.raises(SystemExit):
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(out),
            str(img),
        )
    err = capsys.readouterr().err
    assert "ERROR processing" in err
    assert "Traceback" in err  # traceback.print_exc header


# ---------------------------------------------------------------------------
# Load / startup errors
# ---------------------------------------------------------------------------


def test_main_pdomain_book_tools_import_error_exits_clean(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    mock_heavy_deps()
    img, _ = single_image

    def import_boom(det, reco):
        raise ImportError("pdomain_book_tools wheel missing")

    monkeypatch.setattr(ocr_to_txt, "_create_runtime_session", import_boom)

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            str(img),
        )
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "pdomain_book_tools not importable" in err
    assert "wheel missing" in err


def test_main_predictor_returns_none_exits(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    mock_heavy_deps()
    img, _ = single_image
    monkeypatch.setattr(
        ocr_to_txt,
        "_create_runtime_session",
        lambda det, reco: (_ for _ in ()).throw(RuntimeError("failed to load models.")),
    )

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            str(img),
        )
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "failed to load models" in err


def test_main_model_resolution_error_exits_clean(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    mock_heavy_deps()
    img, _ = single_image

    def fail_model_resolution(args):
        raise RuntimeError("model repo unavailable")

    monkeypatch.setattr(ocr_to_txt, "resolve_ocr_models", fail_model_resolution)

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            str(img),
        )

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "ERROR resolving OCR model files" in err
    assert "model repo unavailable" in err


def test_main_model_resolution_system_exit_is_preserved(
    mock_heavy_deps, monkeypatch, run_main, single_image
):
    mock_heavy_deps()
    img, _ = single_image

    def exit_model_resolution(args):
        raise SystemExit(7)

    monkeypatch.setattr(ocr_to_txt, "resolve_ocr_models", exit_model_resolution)

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            str(img),
        )

    assert exc_info.value.code == 7


def test_main_layout_prefetch_error_exits_clean(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    mock_heavy_deps()
    img, _ = single_image

    def fail_prefetch(repo, revision):
        raise RuntimeError("layout repo unavailable")

    monkeypatch.setattr(ocr_to_txt, "prefetch_layout_files", fail_prefetch)

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "pp-doclayout-plus-l",
            str(img),
        )

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "ERROR resolving layout model files" in err
    assert "layout repo unavailable" in err


def test_main_layout_resolution_system_exit_is_preserved(
    mock_heavy_deps, monkeypatch, run_main, single_image
):
    mock_heavy_deps()
    img, _ = single_image

    def exit_layout_resolution(args):
        raise SystemExit(9)

    monkeypatch.setattr(ocr_to_txt, "resolve_layout_source", exit_layout_resolution)

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "pp-doclayout-plus-l",
            str(img),
        )

    assert exc_info.value.code == 9


@pytest.mark.parametrize("exc_cls", [ImportError, ValueError])
def test_main_layout_load_error_exits(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys, exc_cls
):
    mock_heavy_deps()
    img, _ = single_image

    def fail(args, device):
        raise exc_cls("layout backend missing")

    monkeypatch.setattr(ocr_to_txt, "_load_layout_detector", fail)

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "pp-doclayout-plus-l",
            str(img),
        )
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "layout backend missing" in err


def test_main_no_valid_images_exits_clean(mock_heavy_deps, monkeypatch, run_main, tmp_path, capsys):
    mock_heavy_deps()
    notes = tmp_path / "notes.txt"
    notes.write_text("not an image", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            str(notes),
        )
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "no valid image files found" in err


# ---------------------------------------------------------------------------
# None-page and per-image mkdir failures
# ---------------------------------------------------------------------------


def test_main_doc_with_no_pages_warns_increments_errors_and_exits_1(
    mock_heavy_deps, run_main, make_images, capsys
):
    """B13 regression: ``page is None`` must (1) name the image in the
    warning, (2) increment the per-image error counter so the batch
    exit code reflects the failure, and (3) terminate the
    ``Processing X ...`` line so subsequent stdout doesn't concatenate
    onto it."""
    ns = mock_heavy_deps()
    imgs = make_images(2)
    out = imgs[0].parent / "out"

    # Return None pages so the per-page ``if page is None`` branch fires.
    def empty_batch(images, *, predictor, device, source_identifiers):
        return [None for _ in images]

    ns.runtime_session.runner = empty_batch

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(out),
            str(imgs[0]),
            str(imgs[1]),
        )
    # All images yielded no pages — batch exit code MUST be non-zero so
    # shell scripts branching on $? don't think a corrupt-JPEG batch
    # succeeded.
    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    # Warning must name each image (unattributable in a 500-image batch
    # otherwise).
    assert f"no pages in result for {imgs[0]}" in captured.err
    assert f"no pages in result for {imgs[1]}" in captured.err
    # Final tally must reflect both errors.
    assert "Done (2 error(s))" in captured.out
    # ``Processing X ...`` was printed with end=" "; without an
    # explicit newline before ``continue`` the next iteration's
    # ``Processing`` concatenates onto the same line. Assert each
    # ``Processing`` starts at column zero.
    assert captured.out.count("\nProcessing ") + captured.out.startswith("Processing ") == 2


def test_main_keyboard_interrupt_mid_batch_emits_summary_and_exits_130(
    mock_heavy_deps, monkeypatch, run_main, make_images, capsys
):
    """B20 regression: Ctrl-C mid-batch must NOT escape the for-loop.

    ``KeyboardInterrupt`` derives from ``BaseException``, so the
    per-image ``except Exception`` does not catch it. Without a
    dedicated handler the signal escapes the loop, skipping the
    end-of-batch summary, the update-thread join, and the
    deterministic exit code. The fix must:

    1. close the unterminated ``Processing X ...`` stdout line,
    2. emit a partial-progress summary on stderr naming
       processed/total/error counts,
    3. join the update-notice thread (no race against process exit),
    4. exit with code 130 (SIGINT convention).
    """
    import threading

    ns = mock_heavy_deps()
    imgs = make_images(3)
    out = imgs[0].parent / "out"

    # First page processes normally (batch_pages=1 ensures each image is
    # its own batch).  The second page raises KeyboardInterrupt during
    # per-page post-processing (reorganize_page) — same point in the loop
    # as the old per-image factory raise.  The third page MUST never run.
    call_count = {"n": 0}
    third_seen = {"n": 0}

    def interrupting_batch(images, *, predictor, device, source_identifiers):
        call_count["n"] += 1
        n = call_count["n"]
        if n == 1:
            p = FakePage(text="OK")
            return [p]
        if n == 2:
            p = FakePage(text="OK")
            p.reorganize_page = MagicMock(side_effect=KeyboardInterrupt)
            return [p]
        third_seen["n"] += 1
        return [FakePage(text="OK")]

    ns.runtime_session.runner = interrupting_batch

    # Track the update-notice thread so we can assert it was joined.
    class _RecordingThread(threading.Thread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.joined = False

        def join(self, timeout=None):
            self.joined = True
            return super().join(timeout=timeout)

    started = _RecordingThread(target=lambda: None, daemon=True)
    started.start()
    monkeypatch.setattr(ocr_to_txt, "_start_update_check_thread", lambda disabled: started)

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--layout-model",
            "none",
            "--batch-pages",
            "1",  # one image per batch so the interrupt fires on the 2nd image
            "-o",
            str(out),
            str(imgs[0]),
            str(imgs[1]),
            str(imgs[2]),
        )

    # SIGINT convention: 128 + signal number.
    assert exc_info.value.code == 130
    # Loop must have broken — third image never visited.
    assert third_seen["n"] == 0
    # Update thread join must still fire (otherwise a fast notice
    # racing SIGINT can interleave with shell prompt).
    assert started.joined is True

    captured = capsys.readouterr()
    # First image's success line ran; second image's "Processing ..."
    # was unterminated by ``end=" "`` and must be closed before the
    # summary so subsequent stderr/stdout don't concatenate onto it.
    assert "Processing " in captured.out
    # Partial-progress summary on stderr names processed/total.
    assert "Interrupted after 1/3 image(s)" in captured.err
    # No "Done." (full success) and no "Done (N error(s))." (regular
    # failure) lines — KeyboardInterrupt is its own exit path.
    assert "Done." not in captured.out
    assert "Done (" not in captured.out


def test_main_layout_debug_setup_failure_recorded_per_image_not_batch_abort(
    mock_heavy_deps, monkeypatch, run_main, make_images, capsys
):
    """An unwritable ``--layout-debug-dir`` must not kill the whole batch.

    Regression for B8: ``setup_layout_debug_env`` previously ran outside the
    per-image ``try``, so a single ``mkdir`` failure aborted ``main()`` with
    an unhandled ``OSError``. The fix moves the call inside the try, so each
    image records the failure as its own per-image error and the loop keeps
    going.
    """
    mock_heavy_deps()
    imgs = make_images(2)
    out = imgs[0].parent / "out"

    # Use a *file* as the layout-debug-dir; mkdir(parents=True, exist_ok=True)
    # will raise FileExistsError because the path exists and is not a dir.
    bogus_debug = imgs[0].parent / "not-a-dir"
    bogus_debug.write_text("file, not directory", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-debug",
            "--layout-debug-dir",
            str(bogus_debug),
            "-o",
            str(out),
            str(imgs[0]),
            str(imgs[1]),
        )

    captured = capsys.readouterr()
    # Both images must be visited — the second one would never be touched if
    # the first mkdir failure aborted main() before re-entering the loop.
    assert imgs[0].name in (captured.out + captured.err)
    assert imgs[1].name in (captured.out + captured.err)
    # Both failures recorded as per-image errors, exit 1, "2 error(s)" tally.
    assert exc_info.value.code == 1
    assert "2 error(s)" in captured.out


def test_main_dest_dir_mkdir_failure_recorded_per_image_not_batch_abort(
    mock_heavy_deps, monkeypatch, run_main, make_images, capsys
):
    """A bogus ``-o`` (regular file) must not kill the whole batch.

    Regression for B14: ``dest_dir.mkdir(parents=True, exist_ok=True)``
    previously ran outside the per-image ``try``, so a single FS failure
    aborted ``main()`` with an unhandled ``FileExistsError``. The fix
    moves the mkdir inside the try, so each image records the failure as
    its own per-image error and the loop keeps going.
    """
    mock_heavy_deps()
    imgs = make_images(2)

    # ``-o`` points at a *file* — ``output_dir.mkdir(parents=True, exist_ok=True)``
    # raises FileExistsError because the path exists and is not a dir.
    bogus_out = imgs[0].parent / "out-not-a-dir"
    bogus_out.write_text("file, not directory", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(bogus_out),
            str(imgs[0]),
            str(imgs[1]),
        )

    captured = capsys.readouterr()
    # Both images must be visited — second wouldn't be touched if the first
    # mkdir failure aborted main() before re-entering the loop.
    assert imgs[0].name in (captured.out + captured.err)
    assert imgs[1].name in (captured.out + captured.err)
    assert exc_info.value.code == 1
    assert "2 error(s)" in captured.out


# ---------------------------------------------------------------------------
# CLI-side image decode failures (corrupt bytes, before batch inference)
# ---------------------------------------------------------------------------


def test_main_corrupt_image_decode_failure_reports_error_continues_batch(
    mock_heavy_deps, monkeypatch, run_main, make_images, tmp_path, capsys
):
    """A corrupt image (cv2.imdecode returns None) must be reported as a
    per-image error and must NOT abort the rest of the batch.

    This exercises the decode-failure path added in the batch loop:
    lines that catch a decode error, emit ``ERROR processing``, increment
    the error count, and continue to the next image.  The survivor image
    still runs through ``_run_doctr_batch`` and completes successfully.
    """
    mock_heavy_deps()

    # One real fixture image (decodes fine) and one corrupt image.
    good_imgs = make_images(1)
    good = good_imgs[0]

    # Corrupt image: a .png file whose bytes are not a real PNG but are long
    # enough (16+ bytes) to pass the extension-based file-type gate in
    # collect_images, yet fail cv2.imdecode (returns None).
    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"NOT A VALID PNG IMAGE AT ALL \x00\x01\x02")

    out = tmp_path / "out"

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(out),
            str(corrupt),
            str(good),
        )

    captured = capsys.readouterr()
    # Corrupt image must appear in ERROR line on stderr.
    assert "ERROR processing" in captured.err
    assert "corrupt.png" in captured.err
    # Exit 1 because of the one decode error.
    assert exc_info.value.code == 1
    # Summary must name exactly 1 error.
    assert "1 error(s)" in captured.out
    # Good image must have produced a .txt output (stem of fixture = "page_00").
    assert (out / f"{good.stem}.txt").exists()


def test_main_all_images_corrupt_skips_batch_exits_1(mock_heavy_deps, run_main, tmp_path, capsys):
    """When every image in a chunk fails to decode, the batch call must be
    skipped entirely (``if not survivor_arrays: continue``), and the final
    exit code must be 1.
    """
    ns = mock_heavy_deps()

    # Two corrupt images — long enough to pass the extension gate (16+ bytes)
    # but not valid images, so cv2.imdecode returns None for each.
    c1 = tmp_path / "bad1.png"
    c2 = tmp_path / "bad2.png"
    c1.write_bytes(b"GARBAGE_IMAGE_1_CORRUPT_DATA_HERE")
    c2.write_bytes(b"GARBAGE_IMAGE_2_CORRUPT_DATA_HERE")

    out = tmp_path / "out"

    # Track whether _run_doctr_batch was ever called — it must NOT be.
    batch_called: list[int] = []

    def _spy_batch(images, *, predictor, device, source_identifiers):
        batch_called.append(1)
        return []

    ns.runtime_session.runner = _spy_batch

    with pytest.raises(SystemExit) as exc_info:
        run_main(
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(out),
            str(c1),
            str(c2),
        )

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "ERROR processing" in captured.err
    assert "2 error(s)" in captured.out
    # _run_doctr_batch must have been skipped entirely.
    assert batch_called == [], "batch must not be called when all images fail to decode"
