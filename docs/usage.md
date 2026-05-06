# Full usage options

This page covers every `pd-ocr` flag, grouped by what you'd use it for.
For the friendly walkthrough, see the [README](../README.md). For
layout-detector specifics (the bulk of the layout flags below), see
[layout-aware-ocr.md](layout-aware-ocr.md). `pd-ocr --help` is always
authoritative.

## Inputs and outputs

```sh
# Single image — output written alongside as page.txt
pd-ocr page.png

# Multiple images (any mix of files / directories)
pd-ocr page1.png page2.png images/

# All images in a directory (non-recursive)
pd-ocr images/

# Recurse into subdirectories
pd-ocr --recursive images/        # also: -r, -R

# Write outputs into a specific directory.
# When inputs include directories, structure is mirrored under -o.
pd-ocr -o output/ page.png
pd-ocr -r images/ -o output/      # output/ mirrors images/'s tree

# Also save the reorganized OCR document as JSON next to the .txt
pd-ocr --save-json page.png
```

Recognized image suffixes: `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`,
`.bmp`, `.webp`. Other files in a directory are skipped with a
warning.

## Text normalization

```sh
# Curly → straight quotes ('hi' "hi" → 'hi' "hi")
pd-ocr --straight-quotes page.png        # also: -sq

# Em dash → ASCII double hyphen (— → --)
pd-ocr --em-dash-to-double-hyphen page.png   # also: -ed
```

`--straight-quotes` covers the eight common curly variants
(`‘-‟`). Prime symbols (`′`, `″`) are intentionally left
alone — they're meaningful in measurements and citations.

## Model selection

By default, `pd-ocr` downloads pinned, fine-tuned weights from
`CT2534/pd-ocr-models` on Hugging Face the first time it runs.

```sh
# Pin to a specific model version (HF Hub revision / tag)
pd-ocr --model-version v1.2.0 page.png

# Use a different HF Hub repo
pd-ocr --hf-repo myorg/my-ocr-models page.png

# Override the filenames within the repo
pd-ocr --det-filename detection/custom.pt \
       --reco-filename recognition/custom.pt page.png

# Use local .pt files instead of downloading.
# Both flags must be provided together.
pd-ocr -d ./detection.pt -g ./recognition.pt page.png
```

Local `.pt` files are loaded as-is. If sibling `.arch` / `.vocab`
files exist next to them, they're picked up automatically.

## Layout detection

Layout detection runs by default and feeds the reorganize step. See
[layout-aware-ocr.md](layout-aware-ocr.md) for the full picture.

```sh
# Skip layout detection entirely (faster, lower-quality reorg on
# pages with figures, captions, marginalia, etc.)
pd-ocr --layout-model none page.png

# Switch to the rule-based contour heuristic
pd-ocr --layout-model contour page.png

# Use a fine-tuned PP-DocLayout checkpoint (path or HF repo)
pd-ocr --layout-checkpoint ~/my-finetuned-layout/ page.png

# Tighten / loosen the confidence threshold (0..1, default 0.5)
pd-ocr --layout-confidence 0.3 page.png

# Crop figure / decoration / table regions to i_<stem>_<n>.jpg
pd-ocr --extract-illustrations page.png

# Per-step layout debug text (see layout-aware-ocr.md)
pd-ocr --layout-debug page.png
pd-ocr --layout-debug --layout-debug-dir debug/ page.png
```

`--extract-illustrations` requires a layout model — combining it with
`--layout-model none` is rejected.

## Reorganize controls

`Page.reorganize_page()` from `pd-book-tools` turns the raw OCR block
tree into reading-order text. These flags let you skip it, snapshot
it, or audit it.

```sh
# Skip reorganize entirely — emit raw OCR
pd-ocr --no-reorg page.png

# With --save-json: also write the full diagnostic bundle alongside
# the regular .txt/.json — six files per page in total:
#   <image>.txt + <image>.json                   (post-reorganize)
#   <image>.pure-ocr.txt + <image>.pure-ocr.json (literal OCR output)
#   <image>.post-noise.txt + <image>.post-noise.json
#                                                (after figure-noise
#                                                 removal, before reorg)
# Useful for auditing what reorganize preserved, dropped, or rearranged.
# The old name --save-pre-reorg-json is still accepted as a back-compat alias.
pd-ocr --save-json --save-reorganize-diagnostics page.png

# Warn (don't fail) if reorganize drops any words
pd-ocr --validate-reorg page.png

# [experimental] Enable drop of figure-internal OCR words during
# reorganize. Two steps are gated by this flag:
#   * Step Layout-2b — lines fully inside detected figure regions
#     with no body-text overlap.
#   * Step B2 — figure-internal heuristic noise.
# Default keeps all words. Footnote / header / footer / abandoned
# regions are NEVER dropped, regardless of this flag.
pd-ocr --experimental-drop-layout-words page.png   # also: --edl
```

### Always-on noise-drop warning

When reorganize removes any words it considered figure-internal noise
(via Step Layout-2b or Step B2 inside `pd-book-tools`), the CLI emits a
warning to stderr — independent of any flag. The warning includes:

- the page filename and the count of dropped words;
- a quoted sample of the first few dropped tokens;
- a hint pointing at `--save-json --save-reorganize-diagnostics` so you
  can re-run and inspect the full pure-OCR / post-noise / post-reorg
  bundle.

This is intentionally always-on so quiet figure-noise drops don't slip
past unnoticed. There is no quiet flag — file an issue if you need one.

## Misc

```sh
# Print the installed version
pd-ocr --version

# Skip the background GitHub-tag check (offline runs, locked-down
# networks, or just to silence the upgrade notice).
# Can also be set persistently: export PD_OCR_NO_UPDATE_CHECK=1
pd-ocr --no-update-check page.png

# Built-in help — authoritative listing of every flag
pd-ocr --help
```

## Full flag table

| Flag | Short | Default | Purpose |
|---|---|---|---|
| `--hf-repo REPO_ID` | | `CT2534/pd-ocr-models` | HF Hub repo for OCR models. |
| `--model-version TAG` | | latest | HF revision / tag. |
| `--det-filename PATH` | | `detection/pd-all-detection-model-finetuned.pt` | Detection-model path within the HF repo. |
| `--reco-filename PATH` | | `recognition/pd-all-recognition-model-finetuned.pt` | Recognition-model path within the HF repo. |
| `--detection PT_FILE` | `-d` | — | Local detection `.pt`; requires `--recognition` too. |
| `--recognition PT_FILE` | `-g` | — | Local recognition `.pt`; requires `--detection` too. |
| `--output-dir DIR` | `-o` | input's dir | Where `.txt` (and `.json`, crops) are written. |
| `--recursive` | `-r`, `-R` | off | Recurse into subdirectories of input dirs. |
| `--save-json` | | off | Write the reorganized doc as `<image>.json`. |
| `--no-reorg` | | off | Skip `reorganize_page()`; emit raw OCR. |
| `--save-reorganize-diagnostics` | | off | With `--save-json`: also write the pure-OCR + post-noise diagnostic snapshots as JSON+TXT siblings. Old alias: `--save-pre-reorg-json`. |
| `--validate-reorg` | | off | Warn if reorganize drops any OCR words. |
| `--experimental-drop-layout-words` | `--edl` | off | [experimental] Enable drop of figure-internal OCR words during reorganize: Step Layout-2b (lines fully inside figure regions with no body-text overlap) and Step B2 (figure-internal heuristic noise). Footnote / header / footer / abandoned regions are NEVER dropped, regardless of this flag. |
| `--straight-quotes` | `-sq` | off | Curly → straight ASCII quotes. |
| `--em-dash-to-double-hyphen` | `-ed` | off | Em dash → `--`. |
| `--no-update-check` | | off | Skip the background GitHub-tag upgrade-notice request. Also via `PD_OCR_NO_UPDATE_CHECK=1`. |
| `--layout-model {none,contour,pp-doclayout-plus-l}` | | `pp-doclayout-plus-l` | Layout backend. |
| `--layout-checkpoint PATH_OR_REPO` | | — | Fine-tuned PP-DocLayout checkpoint. |
| `--layout-confidence FLOAT` | | `0.5` | Region-confidence threshold (0..1). |
| `--extract-illustrations` | | off | Crop figure / decoration / table regions. |
| `--layout-debug` | | off | Write layout debug text. |
| `--layout-debug-dir DIR` | | output dir | Where layout debug text goes. |
| `--version` | | — | Print version and exit. |
