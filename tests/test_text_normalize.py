"""Unit tests for the post-OCR text normalization helpers.

These exercise :mod:`pd_ocr_cli._text_normalize`, the module behind the
``--straight-quotes`` and ``--em-dash-to-double-hyphen`` CLI flags.
"""

import pytest

from pd_ocr_cli._text_normalize import normalize_curly_quotes, normalize_em_dash


@pytest.mark.parametrize(
    "src",
    ["‘", "’", "‚", "‛"],
)
def test_normalize_curly_single_quotes(src):
    assert normalize_curly_quotes(src) == "'"


@pytest.mark.parametrize(
    "src",
    ["“", "”", "„", "‟"],
)
def test_normalize_curly_double_quotes(src):
    assert normalize_curly_quotes(src) == '"'


def test_normalize_curly_quotes_in_sentence():
    src = "“Hello,” she said, “it’s fine.”"
    assert normalize_curly_quotes(src) == '"Hello," she said, "it\'s fine."'


def test_normalize_curly_quotes_passthrough():
    src = "plain ASCII \"quotes\" and 'apostrophes' unchanged"
    assert normalize_curly_quotes(src) == src


def test_normalize_curly_quotes_empty():
    assert normalize_curly_quotes("") == ""


def test_normalize_em_dash_basic():
    assert normalize_em_dash("foo—bar") == "foo--bar"


def test_normalize_em_dash_multiple():
    assert normalize_em_dash("a—b—c") == "a--b--c"


def test_normalize_em_dash_no_dash():
    src = "no dashes here, just hyphens - and en-dashes –"
    # En dash (U+2013) is intentionally left alone.
    assert normalize_em_dash(src) == src


def test_normalize_em_dash_empty():
    assert normalize_em_dash("") == ""


def test_normalizers_compose():
    """The two transforms are independent and order does not matter."""
    src = "“wait—really?”"
    expected = '"wait--really?"'
    assert normalize_em_dash(normalize_curly_quotes(src)) == expected
    assert normalize_curly_quotes(normalize_em_dash(src)) == expected
