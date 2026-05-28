"""Flag-wiring tests for ocr_to_txt.main() with heavy deps mocked."""

from __future__ import annotations


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
    """End-to-end: ``--edl`` alias flips the same wiring as the long form.

    Mirrors ``test_main_experimental_drop_layout_words_passes_true_to_reorganize``
    but uses ``--edl`` to confirm argparse routes the alias to the same
    attribute and ``main()`` passes ``drop_layout_words=True`` through
    to ``reorganize_page``.
    """
    ns = mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--edl",
        "-o",
        str(out),
        str(img),
    )

    fake_doc = ns.captured_docs[0]
    fake_doc.pages[0].reorganize_page.assert_called_once()
    _, kwargs = fake_doc.pages[0].reorganize_page.call_args
    assert kwargs.get("drop_layout_words") is True


def test_main_default_passes_drop_layout_words_false_to_reorganize(
    mock_heavy_deps, run_main, single_image
):
    """Default invocation must call reorganize_page(drop_layout_words=False).

    This is the user-visible footnote-loss fix: by default the CLI must
    match the new pdomain-book-tools library default and preserve all words.
    """
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

    fake_doc = ns.captured_docs[0]
    fake_doc.pages[0].reorganize_page.assert_called_once()
    _, kwargs = fake_doc.pages[0].reorganize_page.call_args
    assert kwargs.get("drop_layout_words") is False


def test_main_experimental_drop_layout_words_passes_true_to_reorganize(
    mock_heavy_deps, run_main, single_image
):
    """``--experimental-drop-layout-words`` opts into legacy drop behavior.

    Verifies the flag is wired through the call site at
    ``pdomain_ocr_cli/ocr_to_txt.py`` so users who still want the pre-fix
    behavior can request it explicitly.
    """
    ns = mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--experimental-drop-layout-words",
        "-o",
        str(out),
        str(img),
    )

    fake_doc = ns.captured_docs[0]
    fake_doc.pages[0].reorganize_page.assert_called_once()
    _, kwargs = fake_doc.pages[0].reorganize_page.call_args
    assert kwargs.get("drop_layout_words") is True


def test_main_default_emits_illustration_placeholders(mock_heavy_deps, run_main, single_image):
    """Default invocation forwards emit_illustration_placeholders=True.

    The placeholder block stays on by default so pdomain-prep-for-pgdp can
    anchor [Illustration: ...] serialisation.
    """
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

    fake_doc = ns.captured_docs[0]
    fake_doc.pages[0].reorganize_page.assert_called_once()
    _, kwargs = fake_doc.pages[0].reorganize_page.call_args
    assert kwargs.get("emit_illustration_placeholders") is True


def test_main_no_illustration_placeholders_passes_false_to_reorganize(
    mock_heavy_deps, run_main, single_image
):
    """``--no-illustration-placeholders`` forwards emit_illustration_placeholders=False.

    Suppresses only the placeholder block; caption words are preserved by
    the library (no-silent-drops invariant).
    """
    ns = mock_heavy_deps()
    img, out = single_image

    run_main(
        "--no-update-check",
        "--layout-model",
        "none",
        "--no-illustration-placeholders",
        "-o",
        str(out),
        str(img),
    )

    fake_doc = ns.captured_docs[0]
    fake_doc.pages[0].reorganize_page.assert_called_once()
    _, kwargs = fake_doc.pages[0].reorganize_page.call_args
    assert kwargs.get("emit_illustration_placeholders") is False
