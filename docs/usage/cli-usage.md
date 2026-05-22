# Full usage options

This page covers every `pd-ocr` flag, grouped by what you'd use it for.
For the friendly walkthrough, see the [README](../../README.md). For
layout-detector specifics (the bulk of the layout flags below), see
[layout-aware-ocr.md](../architecture/layout-aware-ocr.md). `pd-ocr --help` is always
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

### Planned: output normalization (post-OCR)

Not implemented yet — tracked here so users and contributors know it's
on the roadmap.

**Motivation.** OCR on old-typesetting books (Cló Gaelach, Fraktur,
early-modern English with long-s) may emit Unicode glyphs that faithfully
reflect the page: `ſ` (long s), `ﬁ`/`ﬂ`/`ﬀ`/`ﬃ`/`ﬄ` (f-ligatures),
`ſt` (long-s+t ligature), and similar. Faithful Unicode is the right
default for archival OCR fidelity. But downstream consumers — most
notably PGDP-style proofreading flows — want ASCII-equivalent text
(`s`, `fi`, `fl`, `st`, …) so volunteers see the same characters they'd
type. The user picks per run.

**Proposed flag.**

```sh
# Default — preserve OCR glyphs exactly as recognized.
pd-ocr page.png

# Map the standard glyph set (long-s, f-ligatures, st-ligature, …) to
# their ASCII equivalents before the .txt is written.
pd-ocr --normalize-output ascii page.png
```

Flag shape: `--normalize-output {none|ascii|...}`, default `none`.
Mode names are an open extension point for future locale-specific
profiles (e.g. a `gaelic` profile that also handles dotted consonants).

**Dependency.** The actual normalization logic + glyph map live in
`pd-book-tools` as `pd_book_tools.text.normalize` (to be added). The
CLI is a thin pass-through that runs the normalizer between
reorganize and disk write. This keeps the same map reusable from
`pd-ocr-labeler` (page-scope action) and `pd-prep-for-pgdp` (export
step) without duplication.

**Cross-refs.** Mirrors decision D-025 in
[`/workspaces/ocr-container/pd-ocr-labeler-spa/specs/17-decisions.md`](/workspaces/ocr-container/pd-ocr-labeler-spa/specs/17-decisions.md).

## Model selection

By default, `pd-ocr` downloads fine-tuned weights from
`CT2534/pd-ocr-models` on Hugging Face the first time it runs, tracking
the latest revision of that repo. Pass `--model-version <tag>` to pin to
a specific release.

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
[layout-aware-ocr.md](../architecture/layout-aware-ocr.md) for the full picture.

```sh
# Skip layout detection entirely (faster, lower-quality reorg on
# pages with figures, captions, marginalia, etc.)
pd-ocr --layout-model none page.png

# Switch to the rule-based contour heuristic
pd-ocr --layout-model contour page.png

# Use a fine-tuned PP-DocLayout checkpoint (path or HF repo)
pd-ocr --layout-checkpoint ~/my-finetuned-layout/ page.png

# Tighten / loosen the confidence threshold (0..1, default 0.5).
# Values outside [0, 1] (and `nan` / `inf`) are rejected at parse time.
pd-ocr --layout-confidence 0.3 page.png

# Crop figure / decoration / table regions to i_<stem>_<n>.jpg
pd-ocr --extract-illustrations page.png

# Suppress empty figure / decoration / table placeholder blocks in the
# reorganized .txt (caption text is still preserved)
pd-ocr --no-illustration-placeholders page.png

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

### Environment variables

| Variable | Effect |
| --- | --- |
| `PD_OCR_NO_UPDATE_CHECK=1` | Skip the background GitHub-tag upgrade-notice request (same as `--no-update-check`). |
| `PD_OCR_NO_GPU_NUDGE=1` | Silence the one-line "GPU detected but installed CPU-only" message printed on startup when `nvidia-smi` is on `PATH` but the `[gpu]` extra wasn't installed. See the FAQ in [README.md](../README.md#faq) for details. |
| `PD_OCR_DEBUG=1` | On per-image processing errors, also print the full traceback to stderr. |
| `PD_OCR_REORGANIZE_STRICT=1` | Read by `pd-book-tools`'s `reorganize_page()`. When set, words dropped during reorganize raise `ReorganizeDroppedWordsError` instead of being re-added with a warning. Useful in CI to fail loudly on pipeline regressions. |
| `HF_HOME`, `HF_HUB_CACHE` | Override the Hugging Face model cache location (default `~/.cache/huggingface/hub`). Honored by the upstream `huggingface_hub` library — pd-ocr-cli does not read these directly. |

`PD_OCR_LAYOUT_DEBUG` and `PD_OCR_LAYOUT_DEBUG_FILE` are set automatically
by the CLI as an internal IPC channel to the layout backend (controlled
via `--layout-debug` / `--layout-debug-dir`) and shouldn't be overridden
manually.

### Conflicting flags / no-op combinations

When you pass a flag combination that can't take effect, `pd-ocr` emits a
`warning:` to stderr and proceeds (the redundant flag is ignored, not
fatal). The current set:

- `--no-reorg` + `--save-reorganize-diagnostics` — diagnostics are produced
  only when reorganize runs.
- `--no-reorg` + `--validate-reorg` — validation compares pre/post
  reorganize word lists.
- `--layout-model none` + `--layout-debug` — no layout model runs, so no
  debug artifact is written.
- `--no-reorg` + `--layout-debug` — the debug report is written from
  inside `reorganize_page`, which is skipped.
- `--layout-debug-dir` without `--layout-debug` — the directory is only
  used when the debug artifact is enabled.
- `--save-reorganize-diagnostics` without `--save-json` — the diagnostic
  bundle is written alongside the regular `.json` output, which requires
  `--save-json`.
- `--no-reorg` + `--experimental-drop-layout-words` — the drop is applied
  inside `reorganize_page`, which is skipped.
- `--no-reorg` + `--no-illustration-placeholders` — placeholder emission
  happens inside `reorganize_page`, which is skipped.

## Full flag table

| Flag | Short | Default | Purpose |
| --- | --- | --- | --- |
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
| `--layout-confidence THRESHOLD` | | `0.5` | Region-confidence threshold (0..1). |
| `--extract-illustrations` | | off | Crop figure / decoration / table regions. |
| `--no-illustration-placeholders` | | off | Suppress empty figure / decoration / table placeholder blocks in the reorganized output. Caption text is preserved. No effect with `--no-reorg`. |
| `--layout-debug` | | off | Write layout debug text. |
| `--layout-debug-dir DIR` | | output dir | Where layout debug text goes. |
| `--version` | | — | Print version and exit. |
