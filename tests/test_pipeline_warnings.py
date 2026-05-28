"""Warning formatting tests for pdomain_ocr_cli._pipeline helpers."""

from __future__ import annotations

from pdomain_ocr_cli._pipeline import (
    format_drops_warning,
    format_noise_drop_warning,
)

# ---------------------------------------------------------------------------
# format_drops_warning
# ---------------------------------------------------------------------------


def test_format_drops_warning_empty_returns_empty_list():
    assert format_drops_warning([], "page.png") == []


def test_format_drops_warning_short_list_renders_all_lines():
    drops = ["the [10,20]", "quick [30,40]"]
    out = format_drops_warning(drops, "page.png")
    assert out == [
        "WARNING: reorganize dropped 2 word(s) in page.png:",
        "  the [10,20]",
        "  quick [30,40]",
    ]


def test_format_drops_warning_truncates_long_list():
    drops = [f"word{i}" for i in range(25)]
    out = format_drops_warning(drops, "page.png", max_lines=20)
    # 1 headline + 20 detail lines + 1 "more" tail
    assert len(out) == 22
    assert out[0] == "WARNING: reorganize dropped 25 word(s) in page.png:"
    assert out[-1] == "  ... (5 more)"


def test_format_drops_warning_exact_max_lines_no_tail():
    drops = [f"word{i}" for i in range(20)]
    out = format_drops_warning(drops, "page.png", max_lines=20)
    assert len(out) == 21  # headline + 20 details, no "more" tail
    assert "more)" not in out[-1]


# ---------------------------------------------------------------------------
# format_noise_drop_warning
# ---------------------------------------------------------------------------


class _Word:
    def __init__(self, text: str):
        self.text = text


def test_format_noise_drop_warning_empty_returns_empty_list():
    assert format_noise_drop_warning([], "page.png", "--flag") == []


def test_format_noise_drop_warning_includes_count_and_sample_and_hint():
    words = [_Word("foo"), _Word("bar"), _Word("baz")]
    out = format_noise_drop_warning(words, "page.png", "--save-reorganize-diagnostics")
    joined = "\n".join(out)
    assert "page.png" in joined
    assert "dropped 3 word(s)" in joined
    assert '"foo"' in joined
    assert '"bar"' in joined
    assert '"baz"' in joined
    assert "--save-reorganize-diagnostics" in joined


def test_format_noise_drop_warning_truncates_long_sample():
    words = [_Word(f"w{i}") for i in range(20)]
    out = format_noise_drop_warning(words, "page.png", "--flag", sample_size=5)
    joined = "\n".join(out)
    assert "dropped 20 word(s)" in joined
    assert "(+15 more)" in joined


def test_format_noise_drop_warning_handles_blank_token_text():
    words = [_Word(""), _Word("real")]
    out = format_noise_drop_warning(words, "page.png", "--flag")
    joined = "\n".join(out)
    # Blanks are skipped from the sample but still counted.
    assert "dropped 2 word(s)" in joined
    assert '"real"' in joined


def test_format_noise_drop_warning_no_phantom_more_when_blanks_within_sample():
    """All words fit within sample_size; blank-filtering must not produce
    a phantom ``(+N more)`` suffix."""
    # 2 words total, sample_size default (8). Blank gets filtered for display
    # but the entire population was already within the sample window, so
    # no "+N more" hint should appear.
    words = [_Word(""), _Word("real")]
    out = format_noise_drop_warning(words, "page.png", "--flag")
    joined = "\n".join(out)
    assert "more)" not in joined, f"phantom (+N more) suffix in: {joined!r}"


def test_format_noise_drop_warning_more_count_reflects_unseen_words():
    """When count exceeds sample_size, the suffix counts truly-unseen words,
    not a number inflated by blank-filtered display tokens."""
    # 10 words: first 5 blank, next 5 real. sample_size=5 grabs the first 5
    # (all blank). After blank-filter samples is empty. Total unseen = 5.
    words = [_Word("") for _ in range(5)] + [_Word(f"w{i}") for i in range(5)]
    out = format_noise_drop_warning(words, "page.png", "--flag", sample_size=5)
    joined = "\n".join(out)
    assert "(+5 more)" in joined, f"expected (+5 more) in: {joined!r}"
