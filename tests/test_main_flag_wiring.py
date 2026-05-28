"""Flag-wiring tests for ocr_to_txt.main() with heavy deps mocked."""

from __future__ import annotations

from _fakes import FakePage


def test_main_no_reorg_skips_reorganize(mock_heavy_deps, run_main, single_image):
    ns = mock_heavy_deps()
    img, out = single_image

    run_main(
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
    fake_doc = ns.captured_docs[0]
    assert not fake_doc.pages[0].reorganize_page.called


def test_main_experimental_drop_layout_words_short_alias(mock_heavy_deps, run_main, single_image):
    """End-to-end: ``--edl`` alias produces the same output as the long form.

    Uses a seeded FakePage to confirm argparse routes the alias to the same
    attribute and ``main()`` passes ``drop_layout_words=True`` through to
    ``reorganize_page``, producing role-labeled layout words in the output.
    """
    img, out = single_image
    mock_heavy_deps(page=FakePage(body="BODY", layout_word="FOOTNOTE"))

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--edl",
        "-o",
        str(out),
        str(img),
    )

    text = (out / "page.txt").read_text()
    assert "[layout: FOOTNOTE]" in text  # same output as the long-form flag


def test_main_default_keeps_layout_word_in_output(mock_heavy_deps, run_main, single_image):
    """Default invocation preserves layout words in output (not relabeled).

    By default the CLI must preserve all words — layout words appear inline,
    not as [layout: ...] role-labels.
    """
    img, out = single_image
    mock_heavy_deps(page=FakePage(body="BODY", layout_word="FOOTNOTE"))

    run_main("--no-update-check", "--layout-model", "none", "-o", str(out), str(img))

    text = (out / "page.txt").read_text()
    assert "FOOTNOTE" in text
    assert "[layout: FOOTNOTE]" not in text


def test_main_edl_relabels_layout_word(mock_heavy_deps, run_main, single_image):
    """``--experimental-drop-layout-words`` relabels layout words, never drops them.

    The no-silent-drops invariant: layout words must appear as [layout: ...]
    role-labels, never silently absent from the output.
    """
    img, out = single_image
    mock_heavy_deps(page=FakePage(body="BODY", layout_word="FOOTNOTE"))

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--experimental-drop-layout-words",
        "-o",
        str(out),
        str(img),
    )

    text = (out / "page.txt").read_text()
    assert "[layout: FOOTNOTE]" in text  # role-labeled, never silently dropped


def test_main_default_emits_illustration_placeholder(mock_heavy_deps, run_main, single_image):
    """Default invocation emits [Illustration] placeholder and preserves caption.

    The placeholder block stays on by default; caption text is always preserved
    (no-silent-drops invariant).
    """
    img, out = single_image
    mock_heavy_deps(page=FakePage(body="BODY", illustration_caption="A cat"))

    run_main("--no-update-check", "--layout-model", "none", "-o", str(out), str(img))

    text = (out / "page.txt").read_text()
    assert "[Illustration]" in text
    assert "A cat" in text


def test_main_no_illustration_placeholders_keeps_caption(mock_heavy_deps, run_main, single_image):
    """``--no-illustration-placeholders`` suppresses placeholder but keeps caption.

    The flag suppresses only the [Illustration] block; caption words survive
    in the output (no-silent-drops invariant).
    """
    img, out = single_image
    mock_heavy_deps(page=FakePage(body="BODY", illustration_caption="A cat"))

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--no-illustration-placeholders",
        "-o",
        str(out),
        str(img),
    )

    text = (out / "page.txt").read_text()
    assert "[Illustration]" not in text
    assert "A cat" in text  # caption survives (no-silent-drops)
