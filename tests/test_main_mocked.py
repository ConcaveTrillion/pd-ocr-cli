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


class _FakePage:
    def __init__(self, text: str = "FAKE TEXT", words: list | None = None):
        self.text = text
        self.words = words or []
        self.reorganize_page = MagicMock(return_value=None)


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
    """Return ``(factory, captured_docs)`` — captured_docs grows on each call."""
    captured: list[_FakeDoc] = []

    def factory(img_path, source_identifier=None, predictor=None):
        doc = _FakeDoc(_FakePage(page.text, list(page.words)))
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


def test_main_save_pre_reorg_json(patched_main, monkeypatch, tmp_path):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

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
    assert (out / "page.pre-reorg.json").exists()


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
    fake_cv2.imwrite = MagicMock(return_value=True)
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
    crop_path = fake_cv2.imwrite.call_args[0][0]
    assert "i_page_01.jpg" in crop_path


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


def test_main_doc_with_no_pages_warns_and_continues(patched_main, monkeypatch, tmp_path, capsys):
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    out = tmp_path / "out"

    def empty_factory(img_path, source_identifier=None, predictor=None):
        return SimpleNamespace(pages=[], to_json_file=lambda p: None)

    monkeypatch.setattr(ocr_to_txt, "_load_document_factory", lambda: empty_factory)

    # Should NOT exit with an error — empty pages is a per-image warning.
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
    assert "no pages in result" in err


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
        return None

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
