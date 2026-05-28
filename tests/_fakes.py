"""Importable test fakes shared across the pdomain-ocr-cli test suite.

The single source of truth for the ``main()`` fast-path fakes. ``FakePage``
exposes a ``reorganize_page`` MagicMock (so call-recording still works) whose
side effect deterministically recomposes ``self.text`` from the seeded parts.
That lets a test assert on the written ``.txt`` content, not just that a mock
was called.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


class FakeSnapshot:
    """Diagnostic Page snapshot stand-in — exposes ``text`` + ``to_dict``."""

    def __init__(self, text: str) -> None:
        self.text = text

    def to_dict(self) -> dict:
        return {"type": "Page", "text": self.text}


class FakeWord:
    def __init__(self, text: str) -> None:
        self.text = text


class FakePage:
    """Fake OCR page whose ``reorganize_page`` transforms ``text`` per flags.

    Seed parts:
      - ``body``: ordinary body text, always present.
      - ``layout_word``: a word the layout pass would route out of the body
        (e.g. a footnote). Never dropped silently: under
        ``drop_layout_words=True`` it is re-emitted as ``[layout: <word>]``.
      - ``illustration_caption``: caption text, always preserved.

    Output composition (after ``reorganize_page``):
      - base = ``body`` + (`` `` + layout_word if not dropped else
        ``\\n[layout: <layout_word>]``)
      - + ``\\n[Illustration]`` line when ``emit_illustration_placeholders``
      - + ``\\n`` + caption when a caption is set.

    With no seed parts beyond ``text`` the page behaves like the legacy
    fake: ``reorganize_page`` leaves ``text`` unchanged.
    """

    def __init__(
        self,
        text: str = "FAKE TEXT",
        words: list | None = None,
        *,
        body: str | None = None,
        layout_word: str | None = None,
        illustration_caption: str | None = None,
        pure_ocr_text: str | None = None,
        post_noise_text: str | None = None,
        dropped_word_texts: list[str] | None = None,
    ) -> None:
        self.text = text
        self.words = words or []
        self._body = body
        self._layout_word = layout_word
        self._caption = illustration_caption
        self.reorganize_page = MagicMock(side_effect=self._reorganize)
        self.diagnostic_pure_ocr = (
            FakeSnapshot(pure_ocr_text) if pure_ocr_text is not None else None
        )
        self.diagnostic_post_noise_removal = (
            FakeSnapshot(post_noise_text) if post_noise_text is not None else None
        )
        self.diagnostic_noise_dropped_words = [FakeWord(t) for t in (dropped_word_texts or [])]
        self.diagnostic_noise_dropped_count = len(self.diagnostic_noise_dropped_words)

    def _reorganize(
        self,
        *,
        drop_layout_words: bool = False,
        emit_illustration_placeholders: bool = True,
        **_: object,
    ) -> None:
        if self._body is None:
            return  # legacy behavior: leave text untouched
        parts = [self._body]
        if self._layout_word is not None:
            parts.append(
                f"[layout: {self._layout_word}]" if drop_layout_words else self._layout_word
            )
        if emit_illustration_placeholders:
            parts.append("[Illustration]")
        if self._caption is not None:
            parts.append(self._caption)
        self.text = (
            "\n".join(parts)
            if (drop_layout_words or emit_illustration_placeholders or self._caption)
            else " ".join(parts)
        )


class FakeDoc:
    """Minimal Document stand-in wrapping one page."""

    def __init__(self, page: FakePage) -> None:
        self.pages = [page]
        self.json_writes: list[Path] = []

    def to_json_file(self, path) -> None:
        p = Path(path)
        p.write_text("{}", encoding="utf-8")
        self.json_writes.append(p)


class FakeArray:
    """cv2-style image fake for illustration-crop tests.

    ``size`` is the pixel-area extent; slicing with ``arr[row_slice,
    col_slice]`` returns a new ``FakeArray`` whose ``size`` is the area of the
    requested crop. Mirrors the only ndarray behavior the CLI's crop path
    touches (``crop.size`` to decide whether a region is empty).
    """

    def __init__(self, extent: int = 100) -> None:
        self.size = extent

    def __getitem__(self, slc) -> FakeArray:
        row, col = slc
        extent = max(0, row.stop - row.start) * max(0, col.stop - col.start)
        return FakeArray(extent)


def pipeline_args(**overrides) -> SimpleNamespace:
    """Argparse-shaped namespace with `_pipeline` defaults."""
    base = {
        "layout_model": "pp-doclayout-plus-l",
        "extract_illustrations": False,
        "layout_debug": False,
        "layout_debug_dir": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def hf_args(**overrides) -> SimpleNamespace:
    """Argparse-shaped namespace with `_hf_models` defaults."""
    from pdomain_ocr_cli._hf_models import (
        DEFAULT_DET_FILENAME,
        DEFAULT_HF_REPO,
        DEFAULT_RECO_FILENAME,
    )

    base = {
        "hf_repo": DEFAULT_HF_REPO,
        "model_version": None,
        "det_filename": DEFAULT_DET_FILENAME,
        "reco_filename": DEFAULT_RECO_FILENAME,
        "detection": None,
        "recognition": None,
        "layout_model": "pp-doclayout-plus-l",
        "layout_checkpoint": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)
