"""Unit tests for the post-OCR text normalization helpers.

These exercise :mod:`pdomain_ocr_cli._text_normalize`, the module behind the
``--straight-quotes`` and ``--em-dash-to-double-hyphen`` CLI flags.

String literals that contain curly quotes or em dashes use \\uXXXX escapes
to avoid ERA001 false-positives (ERA001's comment-as-code parser extracts
fragments of string literals containing Unicode quotes and reports
invalid-syntax when it cannot parse them as Python code).
"""

import pytest

from pdomain_ocr_cli._text_normalize import normalize_curly_quotes, normalize_em_dash

# Unicode code point constants for the characters under test.
# U+2018 LEFT SINGLE QUOTATION MARK
# U+2019 RIGHT SINGLE QUOTATION MARK
# U+201A SINGLE LOW-9 QUOTATION MARK
# U+201B SINGLE HIGH-REVERSED-9 QUOTATION MARK
# U+201C LEFT DOUBLE QUOTATION MARK
# U+201D RIGHT DOUBLE QUOTATION MARK
# U+201E DOUBLE LOW-9 QUOTATION MARK
# U+201F DOUBLE HIGH-REVERSED-9 QUOTATION MARK
# U+2013 EN DASH
# U+2014 EM DASH


@pytest.mark.parametrize(
    "src",
    ["\u2018", "\u2019", "\u201a", "\u201b"],  # U+2018/9/201A/B curly single quotes
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
    # U+201C Hello, U+201D she said, U+201C it U+2019 s fine. U+201D
    src = "\u201cHello,\u201d she said, \u201cit\u2019s fine.\u201d"
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
    # U+2013 en dash is intentionally left alone (only U+2014 em dash is replaced).
    src = "no dashes here, just hyphens - and en-dashes \u2013"  # U+2013 EN DASH
    assert normalize_em_dash(src) == src


def test_normalize_em_dash_empty():
    assert normalize_em_dash("") == ""


def test_normalizers_compose():
    """The two transforms are independent and order does not matter."""
    # U+201C wait U+2014 really? U+201D
    src = "“wait—really?”"
    expected = '"wait--really?"'
    assert normalize_em_dash(normalize_curly_quotes(src)) == expected
    assert normalize_curly_quotes(normalize_em_dash(src)) == expected
