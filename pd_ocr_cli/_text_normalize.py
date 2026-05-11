"""Post-OCR text-cleanup helpers (curly quotes, em dash)."""

# Keys use \uXXXX escapes so that ERA001's comment-as-code heuristic does not
# mis-classify the inline comment text as commented-out Python.
_CURLY_TO_STRAIGHT_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",  # LEFT SINGLE QUOTATION MARK
        "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK / apostrophe
        "\u201a": "'",  # SINGLE LOW-9 QUOTATION MARK
        "\u201b": "'",  # SINGLE HIGH-REVERSED-9 QUOTATION MARK
        "\u201c": '"',  # LEFT DOUBLE QUOTATION MARK
        "\u201d": '"',  # RIGHT DOUBLE QUOTATION MARK
        "\u201e": '"',  # DOUBLE LOW-9 QUOTATION MARK
        "\u201f": '"',  # DOUBLE HIGH-REVERSED-9 QUOTATION MARK
    }
)


def normalize_curly_quotes(text: str) -> str:
    """Convert common curly quote variants to straight ASCII quotes."""
    return text.translate(_CURLY_TO_STRAIGHT_TRANSLATION)


def normalize_em_dash(text: str) -> str:
    """Convert em dash to ASCII double hyphen."""
    return text.replace("\u2014", "--")
