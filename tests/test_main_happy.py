"""Happy-path tests for ocr_to_txt.main() with heavy deps mocked."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from _fakes import FakeArray, FakePage

from pdomain_ocr_cli import ocr_to_txt

# ---------------------------------------------------------------------------
# Happy paths — output files
# ---------------------------------------------------------------------------


def test_main_writes_txt_with_layout_disabled(mock_heavy_deps, run_main, single_image):
    ns = mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    assert (out / "page.txt").read_text() == "FAKE OCR TEXT"
    assert len(ns.captured_docs) == 1


def test_main_save_json_writes_sidecar(mock_heavy_deps, run_main, single_image):
    mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--save-json",
        "-o",
        str(out),
        str(img),
    )

    assert (out / "page.txt").exists()
    payload = json.loads((out / "page.json").read_text(encoding="utf-8"))
    assert set(payload) == {"source_lib", "source_identifier", "source_path", "pages"}
    assert payload["source_lib"] == "pdomain_book_tools"
    assert payload["source_identifier"] == "page.png"
    assert payload["source_path"] == str(img)
    assert isinstance(payload["pages"], list)
    assert len(payload["pages"]) == 1


def test_main_save_reorganize_diagnostics_writes_all_six_outputs(
    mock_heavy_deps, monkeypatch, run_main, single_image
):
    """``--save-json --save-reorganize-diagnostics`` writes the post-reorg
    .txt + .json *and* both diagnostic snapshots (pure-OCR + post-noise) as
    JSON and TXT siblings — six files total per page.
    """
    mock_heavy_deps(
        page=FakePage(
            text="POST-REORG TEXT",
            pure_ocr_text="PURE OCR TEXT",
            post_noise_text="POST NOISE TEXT",
        )
    )
    img, out = single_image

    run_main(
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


def test_main_save_pre_reorg_json_alias_still_works(
    mock_heavy_deps, monkeypatch, run_main, single_image
):
    """The old ``--save-pre-reorg-json`` name maps to the same diagnostic export."""
    mock_heavy_deps(
        page=FakePage(
            pure_ocr_text="PURE",
            post_noise_text="POST",
        )
    )
    img, out = single_image

    run_main(
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


def test_main_save_diagnostics_skips_missing_snapshots(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    """When the library returns ``None`` snapshots (capture_diagnostics=False),
    the CLI must skip the pure-OCR / post-noise files and emit a clear note,
    not crash.
    """
    # No pure_ocr_text / post_noise_text → snapshots stay None.
    mock_heavy_deps(page=FakePage(text="POST-REORG"))
    img, out = single_image

    run_main(
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


def test_main_straight_quotes_normalizes(mock_heavy_deps, monkeypatch, run_main, single_image):
    mock_heavy_deps(page=FakePage(text="“hello”—world"))
    img, out = single_image

    run_main(
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
# Happy paths — validate-reorg
# ---------------------------------------------------------------------------


def test_main_validate_reorg_invokes_validator(
    mock_heavy_deps, monkeypatch, run_main, single_image
):
    mock_heavy_deps()
    img, out = single_image

    validator = MagicMock(return_value=[])
    monkeypatch.setattr(ocr_to_txt, "_load_validate_word_preservation", lambda: validator)

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--validate-reorg",
        "-o",
        str(out),
        str(img),
    )

    assert validator.called


def test_main_validate_reorg_loader_called_once_across_images(
    mock_heavy_deps, monkeypatch, run_main, make_images
):
    """The ``_load_validate_word_preservation`` loader must be invoked once
    before the per-image loop — same contract as the other ``_load_*``
    helpers — so monkeypatched test fakes are honored uniformly across all
    images in a multi-image run.
    """
    mock_heavy_deps()
    imgs = make_images(2)
    out = imgs[0].parent / "out"

    loader = MagicMock(return_value=MagicMock(return_value=[]))
    monkeypatch.setattr(ocr_to_txt, "_load_validate_word_preservation", loader)

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--validate-reorg",
        "-o",
        str(out),
        str(imgs[0]),
        str(imgs[1]),
    )

    assert loader.call_count == 1, (
        f"loader should be hoisted out of the per-image loop "
        f"(called {loader.call_count} times for 2 images)"
    )


def test_main_validate_reorg_warns_on_drops(
    mock_heavy_deps, monkeypatch, run_main, single_image, capsys
):
    mock_heavy_deps()
    img, out = single_image

    monkeypatch.setattr(
        ocr_to_txt,
        "_load_validate_word_preservation",
        lambda: MagicMock(return_value=["dropped-word [10,20]"]),
    )

    run_main(
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


def test_main_empty_page_text_warns(mock_heavy_deps, monkeypatch, run_main, single_image, capsys):
    mock_heavy_deps(page=FakePage(text=""))
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
    assert "empty text result" in err
    # The .txt is still written (empty).
    assert (out / "page.txt").read_text() == ""


def test_main_writes_recomposed_body_and_caption(mock_heavy_deps, run_main, single_image):
    img, out = single_image
    mock_heavy_deps(page=FakePage(body="The quick brown fox", illustration_caption="Fig 1"))
    run_main("--no-update-check", "--layout-model", "none", "-o", str(out), str(img))
    text = (out / "page.txt").read_text()
    assert text.startswith("The quick brown fox")
    assert "Fig 1" in text


# ---------------------------------------------------------------------------
# Happy paths — layout + illustration
# ---------------------------------------------------------------------------


def test_main_layout_enabled_with_local_checkpoint_skips_prefetch(
    mock_heavy_deps, monkeypatch, run_main, single_image
):
    """When ``resolve_layout_source`` returns ``(None, None, descriptor)``,
    the ``prefetch_layout_files`` call must be skipped — covers the False
    branch of the ``if layout_repo is not None`` gate.
    """
    mock_heavy_deps()
    img, out = single_image

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

    run_main(
        "--no-update-check",
        "--layout-model",
        "pp-doclayout-plus-l",
        "-o",
        str(out),
        str(img),
    )

    assert prefetch_calls == []  # skipped because layout_repo was None
    assert (out / "page.txt").exists()


def test_main_layout_enabled_loads_detector(mock_heavy_deps, monkeypatch, run_main, single_image):
    """With layout enabled, _load_layout_detector should be called and `detect` runs per page."""
    mock_heavy_deps()
    img, out = single_image

    fake_layout = SimpleNamespace(regions=[], inference_ms=5)
    fake_detector = MagicMock(detect=MagicMock(return_value=fake_layout))
    load_calls: list = []

    def fake_load_layout(args, device):
        load_calls.append((args.layout_model, device))
        return fake_detector

    monkeypatch.setattr(ocr_to_txt, "_load_layout_detector", fake_load_layout)

    run_main(
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


def test_main_extract_illustrations_loads_cv2_deps(
    mock_heavy_deps, monkeypatch, run_main, single_image
):
    """``--extract-illustrations`` triggers _load_illustration_deps + a layout detector."""
    mock_heavy_deps()
    img, out = single_image

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

    run_main(
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


def test_main_extract_illustrations_writes_crops(
    mock_heavy_deps, monkeypatch, run_main, single_image
):
    """When cv2.imread returns a real image array, qualifying regions get cropped.

    Two figure regions are configured: the first has positive size and is
    written; the second slices to a zero-size crop and is skipped via the
    ``if crop.size == 0: continue`` branch.
    """
    mock_heavy_deps()
    img, out = single_image

    figure_ok = SimpleNamespace(type="figure", confidence=0.9, T=0, B=10, L=0, R=10)
    figure_empty = SimpleNamespace(type="figure", confidence=0.9, T=5, B=5, L=5, R=5)
    text_region = SimpleNamespace(type="text", confidence=0.99, T=0, B=10, L=0, R=10)
    fake_layout = SimpleNamespace(regions=[figure_ok, figure_empty, text_region], inference_ms=1)

    monkeypatch.setattr(
        ocr_to_txt,
        "_load_layout_detector",
        lambda args, device: MagicMock(detect=MagicMock(return_value=fake_layout)),
    )

    fake_cv2 = MagicMock()
    fake_cv2.imread = MagicMock(return_value=FakeArray(100))

    fake_cv2.imencode = MagicMock(return_value=(True, b"\x00"))
    monkeypatch.setattr(
        ocr_to_txt,
        "_load_illustration_deps",
        lambda: (fake_cv2, {"figure"}),
    )

    run_main(
        "--no-update-check",
        "--layout-model",
        "pp-doclayout-plus-l",
        "--extract-illustrations",
        "-o",
        str(out),
        str(img),
    )

    # The empty-crop region was skipped; only one encode call ran.
    assert fake_cv2.imencode.call_count == 1
    assert (out / "i_page_01.jpg").exists()


# ---------------------------------------------------------------------------
# Happy paths — multi-image / directory / update thread
# ---------------------------------------------------------------------------


def test_main_directory_input_recursive_mirrors_to_output(
    mock_heavy_deps, monkeypatch, run_main, tmp_path
):
    import shutil
    from pathlib import Path

    fixtures_dir = Path(__file__).parent / "fixtures"
    title_image = fixtures_dir / "title_page_001.png"

    mock_heavy_deps()
    src_root = tmp_path / "src"
    nested = src_root / "ch1"
    nested.mkdir(parents=True)
    a = src_root / "page1.png"
    b = nested / "page2.png"
    shutil.copy(title_image, a)
    shutil.copy(title_image, b)
    out = tmp_path / "out"

    run_main(
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


def test_main_update_check_thread_started_when_enabled(
    mock_heavy_deps, monkeypatch, run_main, single_image
):
    """When --no-update-check is omitted, the helper is invoked with disabled=False
    and main() joins the returned thread before exiting.
    """
    mock_heavy_deps()
    img, out = single_image

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

    run_main(
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    assert calls == [False]
    assert fired == [1]  # thread ran AND was joined before main returned


def test_main_update_check_thread_disabled_via_flag(
    mock_heavy_deps, monkeypatch, run_main, single_image
):
    mock_heavy_deps()
    img, out = single_image

    calls: list[bool] = []

    def fake_starter(disabled):
        calls.append(disabled)

    monkeypatch.setattr(ocr_to_txt, "_start_update_check_thread", fake_starter)

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "-o",
        str(out),
        str(img),
    )

    assert calls == [True]


# ---------------------------------------------------------------------------
# Loader-helper smoke tests (no main() invocation needed)
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
