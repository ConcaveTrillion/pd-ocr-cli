"""Shared pytest configuration.

Adds a ``--run-slow`` opt-in so the heavy end-to-end OCR tests (which pull
a pinned model from Hugging Face the first time they run) stay out of the
default ``make test`` loop.
"""

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from _fakes import FakePage

from pdomain_ocr_cli import ocr_to_txt
from pdomain_ocr_cli._runtime import DefaultRuntimeSession

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TITLE_IMAGE = FIXTURES_DIR / "title_page_001.png"


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run tests marked @pytest.mark.slow (downloads a pinned model the first time).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="slow test; pass --run-slow to enable")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


@pytest.fixture
def run_main(monkeypatch):
    """Invoke ocr_to_txt.main() with the given argv (after the prog name)."""

    def _run(*argv: str) -> None:
        monkeypatch.setattr(sys, "argv", ["pd-ocr", *argv])
        ocr_to_txt.main()

    return _run


@pytest.fixture
def single_image(tmp_path):
    """Return (img_path, out_dir) — one copied fixture image + an out dir."""
    if not TITLE_IMAGE.exists():
        pytest.fail(f"missing fixture image: {TITLE_IMAGE}")
    img = tmp_path / "page.png"
    shutil.copy(TITLE_IMAGE, img)
    return img, tmp_path / "out"


@pytest.fixture
def make_images(tmp_path):
    """Factory: make_images(n) -> [path, ...] of n copied fixture images."""
    if not TITLE_IMAGE.exists():
        pytest.fail(f"missing fixture image: {TITLE_IMAGE}")

    def _make(n: int) -> list[Path]:
        imgs = []
        for i in range(n):
            img = tmp_path / f"page_{i:02d}.png"
            shutil.copy(TITLE_IMAGE, img)
            imgs.append(img)
        return imgs

    return _make


@pytest.fixture
def mock_heavy_deps(monkeypatch, tmp_path):
    """Patch every heavy dependency of main(); return a control namespace.

    Pass ``ns = mock_heavy_deps()`` to use the default single-text page, or
    ``mock_heavy_deps(page=FakePage(...))`` / ``mock_heavy_deps(texts=[...])``
    to control per-image output. Returns a SimpleNamespace with det_path,
    reco_path, predictor, page, captured_pages, captured_docs, batch_calls.
    """

    def _wire(*, page: FakePage | None = None, texts: list[str] | None = None):
        monkeypatch.setattr(ocr_to_txt, "_check_for_update", lambda: None)
        monkeypatch.setattr(ocr_to_txt, "_start_update_check_thread", lambda disabled: None)
        monkeypatch.setattr(ocr_to_txt, "_should_nudge_gpu_install", lambda: False)

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
        monkeypatch.setattr(ocr_to_txt, "_detect_torch_device", lambda: "cpu")

        fake_predictor = object()
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

        template = page if page is not None else FakePage(text="FAKE OCR TEXT")
        captured_pages: list[FakePage] = []
        batch_calls: list[dict] = []
        counter = [0]

        def _clone(template_page: FakePage) -> FakePage:
            clone = FakePage(
                template_page.text,
                list(template_page.words),
                body=template_page._body,
                layout_word=template_page._layout_word,
                illustration_caption=template_page._caption,
            )
            clone.diagnostic_pure_ocr = template_page.diagnostic_pure_ocr
            clone.diagnostic_post_noise_removal = template_page.diagnostic_post_noise_removal
            clone.diagnostic_noise_dropped_words = list(
                template_page.diagnostic_noise_dropped_words
            )
            clone.diagnostic_noise_dropped_count = template_page.diagnostic_noise_dropped_count
            return clone

        def batch_runner(images, *, predictor, device, source_identifiers):
            pages = []
            for _ in images:
                if texts is not None:
                    idx = counter[0]
                    txt = texts[idx] if idx < len(texts) else f"PAGE_{idx}"
                    clone = FakePage(text=txt)
                else:
                    clone = _clone(template)
                counter[0] += 1
                captured_pages.append(clone)
                pages.append(clone)
            batch_calls.append(
                {
                    "chunk_size": len(images),
                    "predictor": predictor,
                    "device": device,
                    "source_identifiers": source_identifiers,
                }
            )
            return pages

        runtime_session = DefaultRuntimeSession(
            predictor=fake_predictor,
            device="cpu",
            runner=batch_runner,
        )
        monkeypatch.setattr(
            ocr_to_txt, "_create_runtime_session", lambda det, reco: runtime_session
        )

        class _DocsProxy(list):
            def __getitem__(self, idx):  # type: ignore[override]
                return SimpleNamespace(pages=[captured_pages[idx]])

            def __len__(self):
                return len(captured_pages)

        return SimpleNamespace(
            det_path=fake_det,
            reco_path=fake_reco,
            predictor=fake_predictor,
            runtime_session=runtime_session,
            page=template,
            captured_pages=captured_pages,
            captured_docs=_DocsProxy(),
            batch_calls=batch_calls,
        )

    return _wire
