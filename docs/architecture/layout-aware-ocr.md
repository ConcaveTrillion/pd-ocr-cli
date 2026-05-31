# Layout-aware OCR

`pdomain-ocr` runs document-layout detection on every page by default. The
detected regions feed `Page.reorganize_page()` as a hint, which:

- Detects high-confidence running titles and page numbers, role-labels
  them as page headers / footers, and weaves them back into the page
  at the boundaries (header band at the front, footer band at the
  back) so they don't bleed into body paragraphs. Words are preserved,
  not dropped.
- Tags tables and figures so downstream consumers can route them
  separately.
- Routes marginalia (sidenotes, abandoned regions) so they don't fold
  into the main reading flow — left-margin notes sort before the body,
  right-margin notes after. The words remain on the page.

The default detector is
[`PaddlePaddle/PP-DocLayout_plus-L`](https://huggingface.co/CT2534/PP-DocLayout_plus-L)
(via `pdomain-book-tools`), Apache-2.0 licensed, ~132 MB downloaded on first
run.

Plain `--no-reorg` skips both `Page.reorganize_page()` and layout
detection. The only exception is `--extract-illustrations`, which still
requires layout regions to discover crop boxes.

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
pdomain-ocr --layout-model none page.png

# Crop figure / decoration / table regions to i_<stem>_<n>.jpg files
# alongside the .txt output.
pdomain-ocr --extract-illustrations page.png

# Use a fine-tuned PP-DocLayout checkpoint (path or HF repo).
pdomain-ocr --layout-checkpoint ~/my-finetuned-layout/ page.png

# Lower confidence threshold for noisier scans.
pdomain-ocr --layout-confidence 0.3 page.png

# Per-step layout diagnostics for tuning the reorganize pipeline.
pdomain-ocr --layout-debug page.png
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

## Artifact lifecycle

Page artifacts are written transactionally. JSON sidecars, diagnostic
snapshots, layout-debug reports, and illustration crops are written through
unique temporary files and atomically replaced into place. The final `.txt`
file is written last, so the presence of `<image>.txt` means that page's
artifact set completed.

## Test coverage

The slow integration suite exercises the real OCR path, the default
`pp-doclayout-plus-l` layout path, layout-debug report writing, JSON
sidecars, corrupt-image handling, and the fixture corpus under
`tests/fixtures/`. Run it with:

```sh
make test-integration
make test-layout-integration
```

## Related flags

These aren't layout-specific but interact with the reorganize step that
consumes layout output:

- `--no-reorg` — skip `reorganize_page()` entirely; emit raw OCR. Layout
  detection is skipped too unless `--extract-illustrations` needs it for
  crop discovery.
- `--save-reorganize-diagnostics` — with `--save-json`, also writes
  `<image>.pure-ocr.json` + `.txt` (literal OCR output) and
  `<image>.post-noise.json` + `.txt` (state after figure-noise removal,
  before reorg). Six files per page in total when combined with the
  regular `--save-json` post-reorganize pair. Old alias:
  `--save-pre-reorg-json`. Useful when comparing pipeline output to raw
  OCR or auditing the noise-drop step.
- `--validate-reorg` — warn (don't fail) if reorganize drops any words.
- _Always-on noise-drop warning_ — when reorganize drops figure-internal
  noise words, the CLI prints a warning to stderr identifying the page,
  the count, a sample of the dropped tokens, and a re-run hint pointing
  at `--save-json --save-reorganize-diagnostics` for the full diagnostic
  bundle. There is no flag to silence it.
- `--experimental-drop-layout-words` (alias: `--edl`) — gates BOTH
  figure-internal drop steps (Layout-2b and B2). Default OFF preserves
  every OCR word; the always-on warning's count is then 0 and the
  warning does not fire. Footnote / header / footer / abandoned
  regions are NEVER dropped, regardless of this flag.
