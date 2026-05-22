"""Fast end-to-end ``main()`` tests with every heavy item mocked.

These exercise the ``ocr_to_txt.main`` orchestration without loading torch,
DocTR, pd_book_tools, or cv2 — the ``_load_*`` indirection helpers and
``_check_for_update`` are monkeypatched to return fakes so the fast suite
(``make ci``) covers the same flow paths the slow integration tests
exercise via subprocess + real models.

The patching strategy:
- ``_check_for_update`` and the update thread are stubbed out so no
  network call ever fires.
- ``resolve_ocr_models`` and ``resolve_layout_source`` return fake paths /
  descriptors so HF download is skipped.
- ``_load_predictor``, ``_load_layout_detector``, ``_load_document_factory``,
  ``_load_validate_word_preservation``, ``_load_illustration_deps`` return
  test fakes so no real models load.
- The fake ``Document`` factory yields a fake page whose ``.text`` /
  ``.words`` / ``.reorganize_page`` are stubs — that lets the per-image
  loop write a deterministic .txt sidecar.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pd_ocr_cli import ocr_to_txt

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TITLE_IMAGE = FIXTURES_DIR / "title_page_001.png"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSnapshot:
    """Stand-in for the diagnostic Page snapshots — exposes ``text`` + ``to_dict``."""

    def __init__(self, text: str):
        self.text = text

    def to_dict(self):
        return {"type": "Page", "text": self.text}


class _FakeWord:
    def __init__(self, text: str):
        self.text = text


class _FakePage:
    def __init__(
        self,
        text: str = "FAKE TEXT",
        words: list | None = None,
        *,
        pure_ocr_text: str | None = None,
        post_noise_text: str | None = None,
        dropped_word_texts: list[str] | None = None,
    ):
        self.text = text
        self.words = words or []
        self.reorganize_page = MagicMock(return_value=None)
        # The library populates these on real pages after reorganize_page
        # runs. The fake mirrors that contract so the CLI's diagnostic
        # warning + export branches can be tested without the heavy
        # dependency.
        self.diagnostic_pure_ocr = (
            _FakeSnapshot(pure_ocr_text) if pure_ocr_text is not None else None
        )
        self.diagnostic_post_noise_removal = (
            _FakeSnapshot(post_noise_text) if post_noise_text is not None else None
        )
        self.diagnostic_noise_dropped_words = [_FakeWord(t) for t in (dropped_word_texts or [])]
        self.diagnostic_noise_dropped_count = len(self.diagnostic_noise_dropped_words)


class _FakeDoc:
    """Minimal ``Document`` stand-in for the test factory."""

    def __init__(self, page: _FakePage):
        self.pages = [page]
        self.json_writes: list[Path] = []

    def to_json_file(self, path) -> None:  # pragma: no cover - exercised via assert
        p = Path(path)
        p.write_text("{}", encoding="utf-8")
        self.json_writes.append(p)


def _make_factory(page: _FakePage) -> tuple[callable, list[_FakeDoc]]:
    """Return ``(factory, captured_docs)`` — captured_docs grows on each call.

    Each call rebuilds a fresh ``_FakePage`` mirroring the template's
    ``text``, ``words``, and diagnostic attributes so per-page assertions
    don't see state from a previous call.
    """
    captured: list[_FakeDoc] = []

    def factory(img_path, source_identifier=None, predictor=None):
        clone = _FakePage(page.text, list(page.words))
        clone.diagnostic_pure_ocr = page.diagnostic_pure_ocr
        clone.diagnostic_post_noise_removal = page.diagnostic_post_noise_removal
        clone.diagnostic_noise_dropped_words = list(page.diagnostic_noise_dropped_words)
        clone.diagnostic_noise_dropped_count = page.diagnostic_noise_dropped_count
        doc = _FakeDoc(clone)
        captured.append(doc)
        return doc

    return factory, captured


# ---------------------------------------------------------------------------
# Patch fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_main(monkeypatch, tmp_path):
    """Wires up sane defaults for every heavy item; tests override per case.

    Returns a ``SimpleNamespace`` with the configurable knobs and the
    captured fakes so tests can assert against what main() did.
    """
    if not TITLE_IMAGE.exists():
        pytest.skip(f"missing fixture image: {TITLE_IMAGE}")

    # Disable real update check unconditionally (cheap belt-and-braces — main()
    # also gates on --no-update-check).
    monkeypatch.setattr(ocr_to_txt, "_check_for_update", lambda: None)
    monkeypatch.setattr(ocr_to_txt, "_start_update_check_thread", lambda disabled: None)

    # Suppress the GPU-install nudge in the fast-test fixture so individual
    # tests don't have to assert against unrelated stderr noise. The nudge
    # itself is exercised by tests/test_gpu_nudge.py against
    # ``_should_nudge_gpu_install`` directly.
    monkeypatch.setattr(ocr_to_txt, "_should_nudge_gpu_install", lambda: False)

    # Fake model files (just need paths that exist for descriptor formatting).
    fake_det = tmp_path / "fake-det.pt"
    fake_reco = tmp_path / "fake-reco.pt"
    fake_det.write_bytes(b"")
    fake_reco.write_bytes(b"")

    monkeypatch.setattr(ocr_to_txt, "resolve_ocr_models", lambda args: (fake_det, fake_reco))
    monkeypatch.setattr(
        ocr_to_txt,
        "resolve_layout_source",
        lambda args: ("fake/layout-repo", "v0", "fake/layout-repo@v0"),
    )
    monkeypatch.setattr(ocr_to_txt, "prefetch_layout_files", lambda repo, rev: None)

    # No real torch + DocTR + cv2 loads.
    monkeypatch.setattr(ocr_to_txt, "_detect_torch_device", lambda: "cpu")

    fake_predictor = object()
    monkeypatch.setattr(ocr_to_txt, "_load_predictor", lambda det, reco: fake_predictor)

    page = _FakePage(text="FAKE OCR TEXT")
    factory, captured_docs = _make_factory(page)
    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: factory)

    # Default: layout detection mocked off (main() still picks "none" via
    # --layout-model none in the test argv); override per-test if needed.
    monkeypatch.setattr(
        ocr_to_txt,
        "_load_layout_detector",
        lambda args, device: MagicMock(
            detect=MagicMock(return_value=SimpleNamespace(regions=[], inference_ms=1))
        ),
    )

    monkeypatch.setattr(
        ocr_to_txt,
        "_load_validate_word_preservation",
        lambda: MagicMock(return_value=[]),
    )

    return SimpleNamespace(
        det_path=fake_det,
        reco_path=fake_reco,
        predictor=fake_predictor,
        page=page,
        captured_docs=captured_docs,
        factory=factory,
    )


def _run_main(monkeypatch, *argv: str) -> None:
    monkeypatch.setattr(sys, "argv", ["pd-ocr", *argv])
    ocr_to_txt.main()


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_main_writes_txt_with_layout_disabled(patched_main, monkeypatch, tmp_path):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    assert (out / "page.txt").read_text() == "FAKE OCR TEXT"
    assert len(patched_main.captured_docs) == 1


def test_main_save_json_writes_sidecar(patched_main, monkeypatch, tmp_path):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--save-json",
        "-o",
        str(out),
        str(img),
    )

    assert (out / "page.txt").exists()
    assert (out / "page.json").exists()


def test_main_save_json_failure_cleans_up_tmp_and_increments_errors(
    patched_main, monkeypatch, tmp_path, capsys
):
    """If ``doc.to_json_file`` fails mid-write the canonical ``.json``
    must not exist and the sibling tmp must be cleaned up. The error
    counter increments. (B18 atomic-write invariant for the JSON
    sidecar.)
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    page = _FakePage(text="OK")
    captured: list = []

    def factory(img_path, source_identifier=None, predictor=None):
        clone = _FakePage(page.text, list(page.words))
        doc = _FakeDoc(clone)

        def _boom_to_json_file(p):
            # Mimic a partial flush before crashing — the helper must
            # still leave the canonical name absent.
            Path(p).write_text("PARTIAL", encoding="utf-8")
            raise OSError(28, "No space left on device")

        doc.to_json_file = _boom_to_json_file
        captured.append(doc)
        return doc

    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: factory)

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
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


def test_main_per_image_exception_terminates_processing_stdout_line(
    patched_main, monkeypatch, tmp_path, capsys
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
    img_a = tmp_path / "a.png"
    img_b = tmp_path / "b.png"
    shutil.copy(TITLE_IMAGE, img_a)
    shutil.copy(TITLE_IMAGE, img_b)
    out = tmp_path / "out"

    def factory(img_path, source_identifier=None, predictor=None):
        raise RuntimeError(f"boom-{Path(img_path).stem}")

    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: factory)

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(out),
            str(img_a),
            str(img_b),
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


def test_main_save_json_failure_with_no_tmp_swallows_unlink_error(
    patched_main, monkeypatch, tmp_path, capsys
):
    """When ``doc.to_json_file`` raises *before* it ever creates the
    sibling tmp, the defensive ``unlink()`` must swallow
    ``FileNotFoundError`` and re-raise the original error. Covers the
    same B18 cleanup branch when no partial tmp ever lands on disk.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    def factory(img_path, source_identifier=None, predictor=None):
        clone = _FakePage("OK", [])
        doc = _FakeDoc(clone)

        def _explode(_p):
            raise RuntimeError("explode before any byte hits disk")

        doc.to_json_file = _explode
        return doc

    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: factory)

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
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


def test_main_extract_illustrations_imwrite_returns_false_no_tmp_swallows_unlink(
    patched_main, monkeypatch, tmp_path, capsys
):
    """``cv2.imwrite`` returns False but never created the tmp file:
    the defensive cleanup must swallow ``FileNotFoundError`` and warn
    rather than crashing the batch.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    fake_layout = MagicMock()
    fake_layout.detect = MagicMock(
        return_value=SimpleNamespace(
            regions=[SimpleNamespace(L=0, R=10, T=0, B=10, type="figure", confidence=0.99)],
            inference_ms=1,
        )
    )
    monkeypatch.setattr(ocr_to_txt, "_load_layout_detector", lambda args, device: fake_layout)

    class _FakeArray:
        def __init__(self, extent: int):
            self.size = extent

        def __getitem__(self, slc):
            row, col = slc
            extent = max(0, row.stop - row.start) * max(0, col.stop - col.start)
            return _FakeArray(extent)

    fake_cv2 = MagicMock()
    fake_cv2.imread = MagicMock(return_value=_FakeArray(100))
    # Returns False without ever touching disk.
    fake_cv2.imwrite = MagicMock(return_value=False)
    monkeypatch.setattr(ocr_to_txt, "_load_illustration_deps", lambda: (fake_cv2, {"figure"}))

    _run_main(
        monkeypatch,
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
    patched_main, monkeypatch, tmp_path, capsys
):
    """When ``cv2.imwrite`` returns False for a crop, the atomic-write
    branch must remove any sibling tmp it created and emit a warning,
    not crash the batch and not leave the canonical crop on disk.
    (B18 atomic-write invariant for illustration crops.)
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    fake_layout = MagicMock()
    fake_layout.detect = MagicMock(
        return_value=SimpleNamespace(
            regions=[SimpleNamespace(L=0, R=10, T=0, B=10, type="figure", confidence=0.99)],
            inference_ms=1,
        )
    )
    monkeypatch.setattr(ocr_to_txt, "_load_layout_detector", lambda args, device: fake_layout)

    class _FakeArray:
        def __init__(self, extent: int):
            self.size = extent

        def __getitem__(self, slc):
            row, col = slc
            extent = max(0, row.stop - row.start) * max(0, col.stop - col.start)
            return _FakeArray(extent)

    fake_cv2 = MagicMock()
    fake_cv2.imread = MagicMock(return_value=_FakeArray(100))

    def _imwrite_returns_false(path, _crop):
        # Touch the tmp so we can verify cleanup actually unlinks it.
        Path(path).write_bytes(b"\x00")
        return False

    fake_cv2.imwrite = MagicMock(side_effect=_imwrite_returns_false)
    monkeypatch.setattr(ocr_to_txt, "_load_illustration_deps", lambda: (fake_cv2, {"figure"}))

    _run_main(
        monkeypatch,
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


def test_main_save_reorganize_diagnostics_writes_all_six_outputs(
    patched_main, monkeypatch, tmp_path
):
    """``--save-json --save-reorganize-diagnostics`` writes the post-reorg
    .txt + .json *and* both diagnostic snapshots (pure-OCR + post-noise) as
    JSON and TXT siblings — six files total per page.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    factory, _ = _make_factory(
        _FakePage(
            text="POST-REORG TEXT",
            pure_ocr_text="PURE OCR TEXT",
            post_noise_text="POST NOISE TEXT",
        )
    )
    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: factory)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--save-json",
        "--save-reorganize-diagnostics",
        "-o",
        str(out),
        str(img),
    )

    # Post-reorganize pair (existing behavior).
    assert (out / "page.txt").read_text() == "POST-REORG TEXT"
    assert (out / "page.json").exists()
    # Pure-OCR snapshot pair (new).
    assert (out / "page.pure-ocr.json").exists()
    assert (out / "page.pure-ocr.txt").read_text() == "PURE OCR TEXT"
    # Post-noise-removal snapshot pair (new).
    assert (out / "page.post-noise.json").exists()
    assert (out / "page.post-noise.txt").read_text() == "POST NOISE TEXT"


def test_main_save_pre_reorg_json_alias_still_works(patched_main, monkeypatch, tmp_path):
    """The old ``--save-pre-reorg-json`` name maps to the same diagnostic export."""
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    factory, _ = _make_factory(
        _FakePage(
            pure_ocr_text="PURE",
            post_noise_text="POST",
        )
    )
    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: factory)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--save-json",
        "--save-pre-reorg-json",
        "-o",
        str(out),
        str(img),
    )

    assert (out / "page.json").exists()
    assert (out / "page.pure-ocr.json").exists()
    assert (out / "page.post-noise.json").exists()


def test_main_save_diagnostics_skips_missing_snapshots(patched_main, monkeypatch, tmp_path, capsys):
    """When the library returns ``None`` snapshots (capture_diagnostics=False),
    the CLI must skip the pure-OCR / post-noise files and emit a clear note,
    not crash.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    # No pure_ocr_text / post_noise_text → snapshots stay None.
    factory, _ = _make_factory(_FakePage(text="POST-REORG"))
    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: factory)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--save-json",
        "--save-reorganize-diagnostics",
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "diagnostic_pure_ocr unavailable" in err
    assert "diagnostic_post_noise_removal unavailable" in err
    assert (out / "page.json").exists()
    assert not (out / "page.pure-ocr.json").exists()
    assert not (out / "page.post-noise.json").exists()


def test_main_noise_drop_warning_always_fires(patched_main, monkeypatch, tmp_path, capsys):
    """When the library reports any dropped words, stderr gets a warning
    that includes the count, a quoted token sample, and the re-run hint —
    regardless of whether --save-json / diagnostics are passed.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    factory, _ = _make_factory(
        _FakePage(
            text="POST-REORG TEXT",
            dropped_word_texts=["foo", "bar", "baz"],
        )
    )
    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: factory)

    _run_main(
        monkeypatch,
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


def test_main_noise_drop_warning_skipped_when_no_drops(patched_main, monkeypatch, tmp_path, capsys):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    # Default _FakePage has no dropped words.
    _run_main(
        monkeypatch,
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
    patched_main, monkeypatch, tmp_path, capsys
):
    """Mirror of ``test_main_noise_drop_warning_always_fires`` — when the
    library reports ``diagnostic_noise_dropped_count == 0`` (which is the
    new default-flag-off behavior after the upstream library tightening),
    the always-on warning must NOT fire and stderr must contain neither
    the count line nor the "look like figure-internal noise" phrase nor
    the diagnostic re-run hint.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    # Build a page whose diagnostic snapshots are populated but whose
    # dropped list is empty — i.e. reorganize ran with drop_layout_words=False
    # and preserved every word.
    factory, _ = _make_factory(
        _FakePage(
            text="POST-REORG TEXT",
            pure_ocr_text="PURE OCR TEXT",
            post_noise_text="POST NOISE TEXT",
            dropped_word_texts=[],  # explicit empty list
        )
    )
    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: factory)

    _run_main(
        monkeypatch,
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


def test_main_experimental_drop_layout_words_short_alias(patched_main, monkeypatch, tmp_path):
    """End-to-end: ``--edl`` alias flips the same wiring as the long form.

    Mirrors ``test_main_experimental_drop_layout_words_passes_true_to_reorganize``
    but uses ``--edl`` to confirm argparse routes the alias to the same
    attribute and ``main()`` passes ``drop_layout_words=True`` through
    to ``reorganize_page``.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--edl",
        "-o",
        str(out),
        str(img),
    )

    fake_doc = patched_main.captured_docs[0]
    fake_doc.pages[0].reorganize_page.assert_called_once()
    _, kwargs = fake_doc.pages[0].reorganize_page.call_args
    assert kwargs.get("drop_layout_words") is True


def test_main_no_reorg_skips_reorganize(patched_main, monkeypatch, tmp_path):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--no-reorg",
        "-o",
        str(out),
        str(img),
    )

    # The fake page's reorganize_page must NOT have been called.
    assert (out / "page.txt").exists()
    fake_doc = patched_main.captured_docs[0]
    assert not fake_doc.pages[0].reorganize_page.called


def test_main_no_reorg_with_save_diag_warns(patched_main, monkeypatch, tmp_path, capsys):
    """B3.1: ``--no-reorg --save-reorganize-diagnostics`` is a silent no-op.

    The diagnostics flag only fires when reorganize runs, so combining it
    with ``--no-reorg`` produces no output. Warn the user explicitly to
    stderr so the flag's silence is not surprising.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
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


def test_main_no_reorg_with_validate_reorg_warns(patched_main, monkeypatch, tmp_path, capsys):
    """B3.2: ``--no-reorg --validate-reorg`` silently skips validation.

    The ``if do_reorg and args.validate_reorg`` gate short-circuits, so no
    validation runs and no warning is shown. Emit a stderr warning making
    that explicit.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
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


def test_main_layout_none_with_layout_debug_warns(patched_main, monkeypatch, tmp_path, capsys):
    """B3.3: ``--layout-model none --layout-debug`` is a silent no-op.

    With layout disabled the debug file path is announced on stdout but no
    layout model ever runs, so the file never materializes. Warn on stderr
    so users understand why the announced path stays empty.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
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
    patched_main, monkeypatch, tmp_path, capsys
):
    """B9: ``--no-reorg --layout-debug`` is a silent no-op.

    The layout-debug report is written from inside ``Page.reorganize_page``,
    which never runs under ``--no-reorg``. The CLI must (a) emit a stderr
    warning so users understand the flag is ignored, and (b) suppress the
    misleading ``layout-debug: <path>`` segment on the success line that
    points at a file that was never written.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
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
    patched_main, monkeypatch, tmp_path, capsys
):
    """B11: ``--layout-debug-dir DIR`` without ``--layout-debug`` is a silent no-op.

    The directory argument is only consulted inside ``setup_layout_debug_env``,
    which short-circuits to ``None`` when ``--layout-debug`` was not passed.
    Users who specify a debug directory without the enable flag get no
    artifacts and no feedback. Warn on stderr per the B3 pattern.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"
    debug_dir = tmp_path / "debug"

    _run_main(
        monkeypatch,
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
    patched_main, monkeypatch, tmp_path, capsys
):
    """B15: ``--experimental-drop-layout-words`` with ``--no-reorg`` is a silent no-op.

    The flag is consumed only inside the ``if do_reorg:`` block, so combining
    it with ``--no-reorg`` quietly does nothing. Warn on stderr per the B3
    silent-no-op pattern.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
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
    patched_main, monkeypatch, tmp_path, capsys
):
    """B16: ``--save-reorganize-diagnostics`` without ``--save-json`` is a silent no-op.

    The diagnostic-export bundle is gated on ``args.save_json`` in the
    per-image loop, so a user passing only ``--save-reorganize-diagnostics``
    (or its legacy alias ``--save-pre-reorg-json``) gets no diagnostic
    files and no feedback. Warn on stderr per the B3 silent-no-op pattern.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
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


def test_main_default_passes_drop_layout_words_false_to_reorganize(
    patched_main, monkeypatch, tmp_path
):
    """Default invocation must call reorganize_page(drop_layout_words=False).

    This is the user-visible footnote-loss fix: by default the CLI must
    match the new pd-book-tools library default and preserve all words.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    fake_doc = patched_main.captured_docs[0]
    fake_doc.pages[0].reorganize_page.assert_called_once()
    _, kwargs = fake_doc.pages[0].reorganize_page.call_args
    assert kwargs.get("drop_layout_words") is False


def test_main_experimental_drop_layout_words_passes_true_to_reorganize(
    patched_main, monkeypatch, tmp_path
):
    """``--experimental-drop-layout-words`` opts into legacy drop behavior.

    Verifies the flag is wired through the call site at
    ``pd_ocr_cli/ocr_to_txt.py`` so users who still want the pre-fix
    behavior can request it explicitly.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--experimental-drop-layout-words",
        "-o",
        str(out),
        str(img),
    )

    fake_doc = patched_main.captured_docs[0]
    fake_doc.pages[0].reorganize_page.assert_called_once()
    _, kwargs = fake_doc.pages[0].reorganize_page.call_args
    assert kwargs.get("drop_layout_words") is True


def test_main_default_emits_illustration_placeholders(patched_main, monkeypatch, tmp_path):
    """Default invocation forwards emit_illustration_placeholders=True.

    The placeholder block stays on by default so pd-prep-for-pgdp can
    anchor [Illustration: ...] serialisation.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    fake_doc = patched_main.captured_docs[0]
    fake_doc.pages[0].reorganize_page.assert_called_once()
    _, kwargs = fake_doc.pages[0].reorganize_page.call_args
    assert kwargs.get("emit_illustration_placeholders") is True


def test_main_no_illustration_placeholders_passes_false_to_reorganize(
    patched_main, monkeypatch, tmp_path
):
    """``--no-illustration-placeholders`` forwards emit_illustration_placeholders=False.

    Suppresses only the placeholder block; caption words are preserved by
    the library (no-silent-drops invariant).
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--no-illustration-placeholders",
        "-o",
        str(out),
        str(img),
    )

    fake_doc = patched_main.captured_docs[0]
    fake_doc.pages[0].reorganize_page.assert_called_once()
    _, kwargs = fake_doc.pages[0].reorganize_page.call_args
    assert kwargs.get("emit_illustration_placeholders") is False


def test_main_no_illustration_placeholders_with_no_reorg_warns(
    patched_main, monkeypatch, tmp_path, capsys
):
    """``--no-illustration-placeholders --no-reorg`` is a silent no-op; warn.

    Placeholder emission happens inside reorganize_page, which is skipped
    under --no-reorg. Match the B3 no-op-warning pattern.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
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


def test_main_validate_reorg_invokes_validator(patched_main, monkeypatch, tmp_path):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    validator = MagicMock(return_value=[])
    monkeypatch.setattr(ocr_to_txt, "_load_validate_word_preservation", lambda: validator)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--validate-reorg",
        "-o",
        str(out),
        str(img),
    )

    assert validator.called


def test_main_validate_reorg_loader_called_once_across_images(patched_main, monkeypatch, tmp_path):
    """The ``_load_validate_word_preservation`` loader must be invoked once
    before the per-image loop — same contract as the other ``_load_*``
    helpers — so monkeypatched test fakes are honored uniformly across all
    images in a multi-image run.
    """
    img1 = tmp_path / "page1.png"
    img2 = tmp_path / "page2.png"
    shutil.copy(TITLE_IMAGE, img1)
    shutil.copy(TITLE_IMAGE, img2)
    out = tmp_path / "out"

    loader = MagicMock(return_value=MagicMock(return_value=[]))
    monkeypatch.setattr(ocr_to_txt, "_load_validate_word_preservation", loader)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--validate-reorg",
        "-o",
        str(out),
        str(img1),
        str(img2),
    )

    assert loader.call_count == 1, (
        f"loader should be hoisted out of the per-image loop "
        f"(called {loader.call_count} times for 2 images)"
    )


def test_main_validate_reorg_warns_on_drops(patched_main, monkeypatch, tmp_path, capsys):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    monkeypatch.setattr(
        ocr_to_txt,
        "_load_validate_word_preservation",
        lambda: MagicMock(return_value=["dropped-word [10,20]"]),
    )

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--validate-reorg",
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "reorganize dropped 1 word(s)" in err
    assert "dropped-word [10,20]" in err


def test_main_empty_page_text_warns(patched_main, monkeypatch, tmp_path, capsys):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    # Make the document factory return a page with no text.
    factory, _ = _make_factory(_FakePage(text=""))
    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: factory)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    err = capsys.readouterr().err
    assert "empty text result" in err
    # The .txt is still written (empty).
    assert (out / "page.txt").read_text() == ""


def test_main_layout_enabled_with_local_checkpoint_skips_prefetch(
    patched_main, monkeypatch, tmp_path
):
    """When ``resolve_layout_source`` returns ``(None, None, descriptor)``,
    the ``prefetch_layout_files`` call must be skipped — covers the False
    branch of the ``if layout_repo is not None`` gate.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    monkeypatch.setattr(
        ocr_to_txt,
        "resolve_layout_source",
        lambda args: (None, None, "local-checkpoint.pt"),
    )
    prefetch_calls: list = []
    monkeypatch.setattr(
        ocr_to_txt,
        "prefetch_layout_files",
        lambda repo, rev: prefetch_calls.append((repo, rev)),
    )

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "pp-doclayout-plus-l",
        "-o",
        str(out),
        str(img),
    )

    assert prefetch_calls == []  # skipped because layout_repo was None
    assert (out / "page.txt").exists()


def test_main_layout_enabled_loads_detector(patched_main, monkeypatch, tmp_path):
    """With layout enabled, _load_layout_detector should be called and `detect` runs per page."""
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    fake_layout = SimpleNamespace(regions=[], inference_ms=5)
    fake_detector = MagicMock(detect=MagicMock(return_value=fake_layout))
    load_calls: list = []

    def fake_load_layout(args, device):
        load_calls.append((args.layout_model, device))
        return fake_detector

    monkeypatch.setattr(ocr_to_txt, "_load_layout_detector", fake_load_layout)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "pp-doclayout-plus-l",
        "-o",
        str(out),
        str(img),
    )

    assert load_calls == [("pp-doclayout-plus-l", "cpu")]
    assert fake_detector.detect.called
    assert (out / "page.txt").exists()


def test_main_extract_illustrations_loads_cv2_deps(patched_main, monkeypatch, tmp_path):
    """``--extract-illustrations`` triggers _load_illustration_deps + a layout detector."""
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    fake_layout = SimpleNamespace(regions=[], inference_ms=1)
    monkeypatch.setattr(
        ocr_to_txt,
        "_load_layout_detector",
        lambda args, device: MagicMock(detect=MagicMock(return_value=fake_layout)),
    )

    fake_cv2 = MagicMock()
    fake_cv2.imread = MagicMock(return_value=None)  # warns but doesn't crash
    fake_crop_types: set = {"figure"}
    monkeypatch.setattr(ocr_to_txt, "_load_illustration_deps", lambda: (fake_cv2, fake_crop_types))

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "pp-doclayout-plus-l",
        "--extract-illustrations",
        "-o",
        str(out),
        str(img),
    )

    assert fake_cv2.imread.called
    assert (out / "page.txt").exists()


def test_main_extract_illustrations_writes_crops(patched_main, monkeypatch, tmp_path):
    """When cv2.imread returns a real image array, qualifying regions get cropped.

    Two figure regions are configured: the first has positive size and is
    written; the second slices to a zero-size crop and is skipped via the
    ``if crop.size == 0: continue`` branch.
    """
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    figure_ok = SimpleNamespace(type="figure", confidence=0.9, T=0, B=10, L=0, R=10)
    figure_empty = SimpleNamespace(type="figure", confidence=0.9, T=5, B=5, L=5, R=5)
    text_region = SimpleNamespace(type="text", confidence=0.99, T=0, B=10, L=0, R=10)
    fake_layout = SimpleNamespace(regions=[figure_ok, figure_empty, text_region], inference_ms=1)

    monkeypatch.setattr(
        ocr_to_txt,
        "_load_layout_detector",
        lambda args, device: MagicMock(detect=MagicMock(return_value=fake_layout)),
    )

    # NumPy-like fake whose slice size depends on slice extents.
    class _FakeArray:
        def __init__(self, size: int = 100):
            self.size = size

        def __getitem__(self, slc):
            # `slc` is a tuple of two slices: (rows, cols).
            row, col = slc
            extent = max(0, row.stop - row.start) * max(0, col.stop - col.start)
            return _FakeArray(extent)

    fake_cv2 = MagicMock()
    fake_cv2.imread = MagicMock(return_value=_FakeArray(100))

    def _fake_imwrite(path, _crop):
        # The atomic-write path (B18) writes to a sibling tmp file then
        # ``os.replace`` onto the canonical name, so the mock must
        # actually create the file the rename will move.
        Path(path).write_bytes(b"\x00")
        return True

    fake_cv2.imwrite = MagicMock(side_effect=_fake_imwrite)
    monkeypatch.setattr(
        ocr_to_txt,
        "_load_illustration_deps",
        lambda: (fake_cv2, {"figure"}),
    )

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "pp-doclayout-plus-l",
        "--extract-illustrations",
        "-o",
        str(out),
        str(img),
    )

    # The empty-crop region was skipped; only one imwrite call ran.
    assert fake_cv2.imwrite.call_count == 1
    # ``imwrite`` is called against the sibling atomic-tmp path; after
    # ``os.replace`` the final crop lands at ``i_page_01.jpg`` in the
    # output dir. (B18.)
    tmp_call_path = fake_cv2.imwrite.call_args[0][0]
    assert tmp_call_path.endswith(".jpg")
    assert ".i_page_01.tmp" in tmp_call_path
    assert (out / "i_page_01.jpg").exists()


def test_main_layout_debug_writes_debug_file(patched_main, monkeypatch, tmp_path):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--layout-debug",
        "-o",
        str(out),
        str(img),
    )

    # The env-var setup helper makes the debug dir; the loop never writes the
    # actual file (pd_book_tools does that), but the path is announced in the
    # "extra paths" line on stdout.
    assert (out / "page.txt").exists()


def test_main_layout_debug_setup_failure_recorded_per_image_not_batch_abort(
    patched_main, monkeypatch, tmp_path, capsys
):
    """An unwritable ``--layout-debug-dir`` must not kill the whole batch.

    Regression for B8: ``setup_layout_debug_env`` previously ran outside the
    per-image ``try``, so a single ``mkdir`` failure aborted ``main()`` with
    an unhandled ``OSError``. The fix moves the call inside the try, so each
    image records the failure as its own per-image error and the loop keeps
    going.
    """
    img1 = tmp_path / "page-001.png"
    img2 = tmp_path / "page-002.png"
    shutil.copy(TITLE_IMAGE, img1)
    shutil.copy(TITLE_IMAGE, img2)
    out = tmp_path / "out"

    # Use a *file* as the layout-debug-dir; mkdir(parents=True, exist_ok=True)
    # will raise FileExistsError because the path exists and is not a dir.
    bogus_debug = tmp_path / "not-a-dir"
    bogus_debug.write_text("file, not directory", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            "--no-update-check",
            "--layout-model",
            "none",
            "--layout-debug",
            "--layout-debug-dir",
            str(bogus_debug),
            "-o",
            str(out),
            str(img1),
            str(img2),
        )

    captured = capsys.readouterr()
    # Both images must be visited — the second one would never be touched if
    # the first mkdir failure aborted main() before re-entering the loop.
    assert "page-001.png" in (captured.out + captured.err)
    assert "page-002.png" in (captured.out + captured.err)
    # Both failures recorded as per-image errors, exit 1, "2 error(s)" tally.
    assert exc_info.value.code == 1
    assert "2 error(s)" in captured.out


def test_main_dest_dir_mkdir_failure_recorded_per_image_not_batch_abort(
    patched_main, monkeypatch, tmp_path, capsys
):
    """A bogus ``-o`` (regular file) must not kill the whole batch.

    Regression for B14: ``dest_dir.mkdir(parents=True, exist_ok=True)``
    previously ran outside the per-image ``try``, so a single FS failure
    aborted ``main()`` with an unhandled ``FileExistsError``. The fix
    moves the mkdir inside the try, so each image records the failure as
    its own per-image error and the loop keeps going.
    """
    img1 = tmp_path / "page-001.png"
    img2 = tmp_path / "page-002.png"
    shutil.copy(TITLE_IMAGE, img1)
    shutil.copy(TITLE_IMAGE, img2)

    # ``-o`` points at a *file* — ``output_dir.mkdir(parents=True, exist_ok=True)``
    # raises FileExistsError because the path exists and is not a dir.
    bogus_out = tmp_path / "out-not-a-dir"
    bogus_out.write_text("file, not directory", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(bogus_out),
            str(img1),
            str(img2),
        )

    captured = capsys.readouterr()
    # Both images must be visited — second wouldn't be touched if the first
    # mkdir failure aborted main() before re-entering the loop.
    assert "page-001.png" in (captured.out + captured.err)
    assert "page-002.png" in (captured.out + captured.err)
    assert exc_info.value.code == 1
    assert "2 error(s)" in captured.out


def test_main_straight_quotes_normalizes(patched_main, monkeypatch, tmp_path):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    factory, _ = _make_factory(_FakePage(text="“hello”—world"))
    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: factory)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--straight-quotes",
        "--em-dash-to-double-hyphen",
        "-o",
        str(out),
        str(img),
    )

    assert (out / "page.txt").read_text() == '"hello"--world'


# ---------------------------------------------------------------------------
# Error paths in main()
# ---------------------------------------------------------------------------


def test_main_per_image_exception_increments_error_count(
    patched_main, monkeypatch, tmp_path, capsys
):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    def boom(*a, **kw):
        raise RuntimeError("synthetic OCR failure")

    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: boom)

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
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
    patched_main, monkeypatch, tmp_path, capsys
):
    """``PD_OCR_DEBUG=1`` adds a traceback to the per-image error output."""
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    def boom(*a, **kw):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: boom)
    monkeypatch.setenv("PD_OCR_DEBUG", "1")

    with pytest.raises(SystemExit):
        _run_main(
            monkeypatch,
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


def test_main_pd_book_tools_import_error_exits_clean(patched_main, monkeypatch, tmp_path, capsys):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)

    def import_boom(det, reco):
        raise ImportError("pd_book_tools wheel missing")

    monkeypatch.setattr(ocr_to_txt, "_load_predictor", import_boom)

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            "--no-update-check",
            "--layout-model",
            "none",
            str(img),
        )
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "pd_book_tools not importable" in err
    assert "wheel missing" in err


def test_main_predictor_returns_none_exits(patched_main, monkeypatch, tmp_path, capsys):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    monkeypatch.setattr(ocr_to_txt, "_load_predictor", lambda det, reco: None)

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            "--no-update-check",
            "--layout-model",
            "none",
            str(img),
        )
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "failed to load models" in err


@pytest.mark.parametrize("exc_cls", [ImportError, ValueError])
def test_main_layout_load_error_exits(patched_main, monkeypatch, tmp_path, capsys, exc_cls):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)

    def fail(args, device):
        raise exc_cls("layout backend missing")

    monkeypatch.setattr(ocr_to_txt, "_load_layout_detector", fail)

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            "--no-update-check",
            "--layout-model",
            "pp-doclayout-plus-l",
            str(img),
        )
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "layout backend missing" in err


def test_main_no_valid_images_exits_clean(patched_main, monkeypatch, tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.write_text("not an image", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            "--no-update-check",
            "--layout-model",
            "none",
            str(notes),
        )
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "no valid image files found" in err


def test_main_doc_with_no_pages_warns_increments_errors_and_exits_1(
    patched_main, monkeypatch, tmp_path, capsys
):
    """B13 regression: ``page is None`` must (1) name the image in the
    warning, (2) increment the per-image error counter so the batch
    exit code reflects the failure, and (3) terminate the
    ``Processing X ...`` line so subsequent stdout doesn't concatenate
    onto it."""
    img_a = tmp_path / "page_a.png"
    img_b = tmp_path / "page_b.png"
    shutil.copy(TITLE_IMAGE, img_a)
    shutil.copy(TITLE_IMAGE, img_b)
    out = tmp_path / "out"

    def empty_factory(img_path, source_identifier=None, predictor=None):
        return SimpleNamespace(pages=[], to_json_file=lambda p: None)

    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: empty_factory)

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            "--no-update-check",
            "--layout-model",
            "none",
            "-o",
            str(out),
            str(img_a),
            str(img_b),
        )
    # All images yielded no pages — batch exit code MUST be non-zero so
    # shell scripts branching on $? don't think a corrupt-JPEG batch
    # succeeded.
    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    # Warning must name each image (unattributable in a 500-image batch
    # otherwise).
    assert f"no pages in result for {img_a}" in captured.err
    assert f"no pages in result for {img_b}" in captured.err
    # Final tally must reflect both errors.
    assert "Done (2 error(s))" in captured.out
    # ``Processing X ...`` was printed with end=" "; without an
    # explicit newline before ``continue`` the next iteration's
    # ``Processing`` concatenates onto the same line. Assert each
    # ``Processing`` starts at column zero.
    assert captured.out.count("\nProcessing ") + captured.out.startswith("Processing ") == 2


def test_main_keyboard_interrupt_mid_batch_emits_summary_and_exits_130(
    patched_main, monkeypatch, tmp_path, capsys
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
    img_a = tmp_path / "page_a.png"
    img_b = tmp_path / "page_b.png"
    img_c = tmp_path / "page_c.png"
    for img in (img_a, img_b, img_c):
        shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    # First call returns a normal page; second call raises
    # KeyboardInterrupt (simulating Ctrl-C while OCR'ing the second
    # image); third call MUST never run.
    call_count = {"n": 0}
    third_seen = {"n": 0}

    def interrupting_factory(img_path, source_identifier=None, predictor=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return SimpleNamespace(
                pages=[_FakePage(text="OK")],
                to_json_file=lambda p: None,
            )
        if call_count["n"] == 2:
            raise KeyboardInterrupt
        third_seen["n"] += 1
        return SimpleNamespace(pages=[_FakePage(text="OK")], to_json_file=lambda p: None)

    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: interrupting_factory)

    # Track the update-notice thread so we can assert it was joined.
    import threading

    class _RecordingThread(threading.Thread):
        joined = False

        def join(self, timeout=None):
            type(self).joined = True
            return super().join(timeout=timeout)

    started = _RecordingThread(target=lambda: None, daemon=True)
    started.start()
    monkeypatch.setattr(ocr_to_txt, "_start_update_check_thread", lambda disabled: started)

    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            "--layout-model",
            "none",
            "-o",
            str(out),
            str(img_a),
            str(img_b),
            str(img_c),
        )

    # SIGINT convention: 128 + signal number.
    assert exc_info.value.code == 130
    # Loop must have broken — third image never visited.
    assert third_seen["n"] == 0
    # Update thread join must still fire (otherwise a fast notice
    # racing SIGINT can interleave with shell prompt).
    assert _RecordingThread.joined is True

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


# ---------------------------------------------------------------------------
# Multi-image / mirroring behavior
# ---------------------------------------------------------------------------


def test_main_directory_input_recursive_mirrors_to_output(patched_main, monkeypatch, tmp_path):
    src_root = tmp_path / "src"
    nested = src_root / "ch1"
    nested.mkdir(parents=True)
    a = src_root / "page1.png"
    b = nested / "page2.png"
    shutil.copy(TITLE_IMAGE, a)
    shutil.copy(TITLE_IMAGE, b)
    out = tmp_path / "out"

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "--recursive",
        "-o",
        str(out),
        str(src_root),
    )

    assert (out / "page1.txt").read_text() == "FAKE OCR TEXT"
    assert (out / "ch1" / "page2.txt").read_text() == "FAKE OCR TEXT"


def test_main_update_check_thread_started_when_enabled(patched_main, monkeypatch, tmp_path):
    """When --no-update-check is omitted, the helper is invoked with disabled=False
    and main() joins the returned thread before exiting.
    """
    import threading

    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    calls: list[bool] = []
    fired: list[int] = []

    def fake_starter(disabled):
        calls.append(disabled)
        # Return a real (no-op) thread so main()'s `_update_thread.join(...)`
        # branch actually runs — that's the line we want to cover.
        thread = threading.Thread(target=lambda: fired.append(1))
        thread.start()
        return thread

    monkeypatch.setattr(ocr_to_txt, "_start_update_check_thread", fake_starter)

    _run_main(
        monkeypatch,
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    assert calls == [False]
    assert fired == [1]  # thread ran AND was joined before main returned


def test_main_update_check_thread_disabled_via_flag(patched_main, monkeypatch, tmp_path):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    calls: list[bool] = []

    def fake_starter(disabled):
        calls.append(disabled)

    monkeypatch.setattr(ocr_to_txt, "_start_update_check_thread", fake_starter)

    _run_main(
        monkeypatch,
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    assert calls == [True]


# ---------------------------------------------------------------------------
# Tests for the loader helpers themselves (small smoke tests)
# ---------------------------------------------------------------------------


def test_start_update_check_thread_returns_none_when_disabled():
    assert ocr_to_txt._start_update_check_thread(disabled=True) is None


def test_start_update_check_thread_spawns_when_enabled(monkeypatch):
    """Verify the helper actually spawns a daemon thread targeting _check_for_update."""
    fired = []
    monkeypatch.setattr(ocr_to_txt, "_check_for_update", lambda: fired.append(1))
    t = ocr_to_txt._start_update_check_thread(disabled=False)
    assert t is not None
    assert t.daemon is True
    t.join(timeout=2)
    assert fired == [1]
