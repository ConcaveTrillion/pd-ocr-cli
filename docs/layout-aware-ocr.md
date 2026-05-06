# Layout-aware OCR

`pd-ocr` runs document-layout detection on every page by default. The
detected regions feed `Page.reorganize_page()` as a hint, which:

- Wraps figure captions so they emit as `[Illustration: ...]` blocks
  rather than getting folded into surrounding paragraphs.
- Strips high-confidence headers and footers (running titles, page
  numbers) from the body text.
- Tags tables and figures so downstream consumers can route them
  separately.
- Drops marginalia (sidenotes, abandoned regions) from the main flow.

The default detector is
[`PaddlePaddle/PP-DocLayout_plus-L`](https://huggingface.co/CT2534/PP-DocLayout_plus-L)
(via `pd-book-tools`), Apache-2.0 licensed, ~132 MB downloaded on first
run.

## Flags

| Flag | Purpose |
|---|---|
| `--layout-model {none,contour,pp-doclayout-plus-l}` | Detector backend. `none` skips layout entirely. Default `pp-doclayout-plus-l`. |
| `--layout-checkpoint PATH_OR_REPO` | Use a fine-tuned PP-DocLayout checkpoint instead of the default weights. |
| `--layout-confidence THRESHOLD` | Minimum region confidence (0..1). Default 0.5. |
| `--extract-illustrations` | Crop figure/decoration/table regions into `i_<stem>_<n>.jpg`. Requires a layout model. |
| `--layout-debug` | Write per-step layout debug text alongside outputs. |
| `--layout-debug-dir DIR` | Where to put the debug text files (default: alongside each image's output). |

## Examples

```sh
# Skip layout detection entirely (faster; reorganize falls back to
# heuristics, which can fold captions into paragraphs and leave page
# numbers in the body text).
pd-ocr --layout-model none page.png

# Crop figure / decoration / table regions to i_<stem>_<n>.jpg files
# alongside the .txt output.
pd-ocr --extract-illustrations page.png

# Use a fine-tuned PP-DocLayout checkpoint (path or HF repo).
pd-ocr --layout-checkpoint ~/my-finetuned-layout/ page.png

# Lower confidence threshold for noisier scans.
pd-ocr --layout-confidence 0.3 page.png

# Per-step layout diagnostics for tuning the reorganize pipeline.
pd-ocr --layout-debug page.png
```

## Page rotation

Page rotation is handled automatically by the underlying OCR layer: if
upright recognition confidence is low, the image is re-OCR'd at
90° / 180° / 270° and the best orientation wins. Detected layout
regions are reported in the rotated frame, so figure crops and
caption tagging still line up.

## Performance notes

- The layout detector loads once at startup (auto-detects CUDA / MPS /
  CPU, mirroring the OCR predictor) and is reused for every page in the
  batch.
- Per-page layout inference is reported on the processing line:
  `layout: N regions (M ms)`.
- If a page returns `0 regions`, that's plausible for plain-text pages
  but can also indicate the confidence threshold filtered everything
  out — try `--layout-confidence 0.3` to verify.

## Related flags

These aren't layout-specific but interact with the reorganize step that
consumes layout output:

- `--no-reorg` — skip `reorganize_page()` entirely; emit raw OCR. The
  layout detector still runs (for `--extract-illustrations`) but its
  hints aren't applied.
- `--save-reorganize-diagnostics` — with `--save-json`, also writes
  `<image>.pure-ocr.json` + `.txt` (literal OCR output) and
  `<image>.post-noise.json` + `.txt` (state after figure-noise removal,
  before reorg). Six files per page in total when combined with the
  regular `--save-json` post-reorganize pair. Old alias:
  `--save-pre-reorg-json`. Useful when comparing pipeline output to raw
  OCR or auditing the noise-drop step.
- `--validate-reorg` — warn (don't fail) if reorganize drops any words.
- (always on) — when reorganize drops figure-internal noise words, the CLI
  prints a warning to stderr
  identifying the page, count, sample tokens, and the re-run hint for
  the full diagnostic bundle.
- `--experimental-drop-layout-words` (alias: `--edl`) — gates BOTH
  figure-internal drop steps (Layout-2b and B2). Default OFF preserves
  every OCR word; the always-on warning's count is then 0 and the
  warning does not fire. Footnote / header / footer / abandoned
  regions are NEVER dropped, regardless of this flag.
