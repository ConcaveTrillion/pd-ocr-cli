"""Post-OCR text-cleanup helpers (curly quotes, em dash)."""

_CURLY_TO_STRAIGHT_TRANSLATION = str.maketrans(
    {
        "‘": "'",  # left single quote
        "’": "'",  # right single quote / apostrophe
        "‚": "'",  # single low-9 quote
        "‛": "'",  # single high-reversed-9 quote
        "“": '"',  # left double quote
        "”": '"',  # right double quote
        "„": '"',  # double low-9 quote
        "‟": '"',  # double high-reversed-9 quote
    }
)


def normalize_curly_quotes(text: str) -> str:
    """Convert common curly quote variants to straight ASCII quotes."""
    return text.translate(_CURLY_TO_STRAIGHT_TRANSLATION)


def normalize_em_dash(text: str) -> str:
    """Convert em dash to ASCII double hyphen."""
    return text.replace("—", "--")
