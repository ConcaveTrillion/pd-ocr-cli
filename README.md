# pd-ocr-cli

Turn scanned book pages into clean `.txt` files. No setup required —
just install and point it at an image.

## What pd-ocr does

Point it at a page scan (or a folder of them) and it writes a `.txt`
file next to each image. Two things make the output more useful than
plain OCR:

- **Layout-aware reorganization.** Before reading the words, `pd-ocr`
  looks at the whole page and figures out what each part is — the body
  text, the figures, the captions underneath them, the running title at
  the top, the page number at the bottom, any sidenotes in the margin.
  It uses that map to put the text together in the right order:
  captions stay with their figures, running titles and page numbers are
  kept at the top, and sidenotes don't get mashed into the paragraphs
  they sit next to. By default no OCR words are dropped; opt-in
  `--experimental-drop-layout-words` (`--edl`) allows for
  noise inside of figures to be dropped, and a warning is always emitted
  if this happens. More in
  [docs/architecture/layout-aware-ocr.md](docs/architecture/layout-aware-ocr.md).
- **Auto-rotation.** If a page was scanned sideways or upside down,
  `pd-ocr` re-runs the OCR at 90° / 180° / 270° and keeps the
  orientation that reads best.

The first time you run it, it downloads the models it needs
(roughly 150 MB total). After that it works offline — no account or
sign-up. For specifics on what the tool downloads and from where, see
[Technical details](#technical-details) at the bottom.

---

## GPU acceleration (optional)

`pd-ocr` works fine on CPU. Add an NVIDIA GPU and it goes faster — worth
it when you're running through a whole book rather than one page.

> ⚠️ **Heads up — disk space.** The NVIDIA path pulls in the CUDA
> Toolkit and CUDA-flavored PyTorch wheels — roughly 10 GB total. CPU
> mode is a fine starting point if that's tight.

- **NVIDIA on Linux/Windows** — install the [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads) (12.4 or newer), then run the install script; it auto-detects CUDA.
- **Apple Silicon Mac** — kicks in automatically, nothing to install. *(Unverified — feedback welcome.)*
- **No GPU** — nothing to do; CPU is the default.

Already installed without a GPU? Just re-run the install script — it
swaps the install in place. See the [FAQ](#faq) for switching to GPU,
the "GPU detected but installed CPU-only" nudge, troubleshooting, and
when a GPU is (or isn't) worth it.

---

## Install

**Linux / macOS:**

```sh
curl -sSL https://raw.githubusercontent.com/ConcaveTrillion/pd-ocr-cli/main/install.sh | sh
```

**Windows (PowerShell):** *(untested — feedback welcome)*

```powershell
irm https://raw.githubusercontent.com/ConcaveTrillion/pd-ocr-cli/main/install.ps1 | iex
```

Both scripts detect NVIDIA CUDA automatically and select the correct PyTorch build.

---

## Usage

```sh
# OCR a single image (output written alongside as page.txt)
pd-ocr page.png

# Multiple images
pd-ocr page1.png page2.png page3.png

# Process all images in a directory
pd-ocr images/

# Process a directory tree recursively, mirroring structure into output/
pd-ocr -r images/ -o output/

# Also save the reorganized OCR document as JSON
pd-ocr --save-json page.png

# Print the installed version
pd-ocr --version
```

Full flag reference — quote / em-dash normalization, model pinning,
layout-detector options, illustration extraction, debug output — in
[docs/usage/cli-usage.md](docs/usage/cli-usage.md). `pd-ocr --help` lists everything
authoritatively.

---

## FAQ

### How do I switch from CPU-only to GPU?

Re-run the install script. It re-detects `nvidia-smi` on every run,
picks the matching `cuXXX` PyTorch wheels, and (when CUDA ≥ 12.4)
opts into the `pd-book-tools[gpu]` extra (CuPy + opencv-cuda).
`uv tool install --reinstall` swaps the existing install in place.

```sh
# Linux / macOS
curl -sSL https://raw.githubusercontent.com/ConcaveTrillion/pd-ocr-cli/main/install.sh | sh
```

```powershell
# Windows
irm https://raw.githubusercontent.com/ConcaveTrillion/pd-ocr-cli/main/install.ps1 | iex
```

CUDA 11.x or 12.0–12.3 still gets the GPU PyTorch wheels, but the
heavier CuPy stack is skipped (CuPy itself requires CUDA ≥ 12.4).

### Why am I seeing a "GPU detected but installed CPU-only" message?

On startup, `pd-ocr` does a cheap check: if your host has an NVIDIA GPU
(`nvidia-smi` on `PATH`, exits 0) but pd-ocr was installed without the
`[gpu]` extra (CuPy isn't importable), it prints a one-line nudge to
stderr suggesting the reinstall command. The probe is fail-soft — any
error is swallowed and the OCR run proceeds normally.

To silence it persistently (e.g. you've decided CPU-only is right for
this host):

```sh
export PD_OCR_NO_GPU_NUDGE=1
```

### Is a GPU worth it for my workload?

For one-off pages, most of the time goes into loading the models, not
reading the words — CPU feels about the same. The GPU pays off when
you're processing tens or hundreds of pages in a single run.

### The GPU isn't being used — what's wrong?

A few things to check:

- **`nvidia-smi` not found** — NVIDIA driver / toolkit isn't
  available in your environment. Install the [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads).
- **Running in Docker / devcontainer** — make sure the container was
  started with `--gpus all` and the NVIDIA Container Toolkit is
  configured on the host (see
  [Running in a Container](#running-in-a-container-with-nvidia-gpu)).
- **GPU still not used after that** — re-run the install script; it
  re-detects on each run.

For the deep mechanics — `cuXXX` wheel selection, what the install
script does, disk / VRAM budgets — see
[Technical details](#technical-details).

### Why is the first run so slow?

That's the one-time model download (~150 MB) and initialization.
Later runs reuse the cache.

### Where are the models cached?

`~/.cache/huggingface/hub` by default; override with `$HF_HOME` or
`$HF_HUB_CACHE`. See [Network calls](#network-calls-the-tool-makes)
for what's downloaded and from where, and [Uninstall](#uninstall) for
how to remove the cache.

---

## Running in a Container with NVIDIA GPU

You'll need the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) configured on your host and the container run with `--gpus all`. Then install as normal inside the container.

---

## Uninstall

```sh
uv tool uninstall pd-ocr-cli
```

To also remove the cached models, check your `HF_HOME` environment variable for the cache location:

```sh
echo $HF_HOME   # custom location if set
# Default location:
rm -rf ~/.cache/huggingface/hub/models--CT2534--pd-ocr-models
```

---

## Technical details

### What's under the hood

- **Text recognition:** [DocTR](https://github.com/mindee/doctr)
  (detection + recognition), with weights fine-tuned on
  public-domain book scans.
- **Layout detection:** [PP-DocLayout_plus-L](https://github.com/PaddlePaddle/PaddleOCR)
  (RT-DETR-based), Apache-2.0 licensed.
- **Pipeline glue:** [pd-book-tools](https://github.com/ConcaveTrillion/pd-book-tools)
  — owns the OCR predictor wrapper, layout adapter, and the
  `reorganize_page()` step that turns OCR output into reading-order
  text.

### Network calls the tool makes

`pd-ocr` does not collect telemetry or call home with usage data. It
makes exactly these outbound requests:

1. **Model downloads** (first run only, then cached):
   - OCR weights from
     [`CT2534/pd-ocr-models`](https://huggingface.co/CT2534/pd-ocr-models)
     on `huggingface.co`.
   - Layout weights from
     [`CT2534/PP-DocLayout_plus-L`](https://huggingface.co/CT2534/PP-DocLayout_plus-L)
     on `huggingface.co`.
   - No Hugging Face account required.
   - Cached at `~/.cache/huggingface/hub` by default; override with
     `$HF_HOME` or `$HF_HUB_CACHE`.
2. **Version check** (every run, in the background):
   - `GET https://api.github.com/repos/ConcaveTrillion/pd-ocr-cli/tags`
   - 3-second timeout; if a newer release tag exists, prints a one-line
     upgrade notice to stderr.
   - Best-effort — silently suppressed on any network or parse error,
     and never blocks startup.
   - Bypass entirely with `--no-update-check`, or persistently via
     the `PD_OCR_NO_UPDATE_CHECK=1` env var (e.g. offline runs or
     locked-down networks).

If you need to run fully offline after the first install, both of
these are cache-friendly: once models are cached and the update check
is suppressed (`--no-update-check` or `PD_OCR_NO_UPDATE_CHECK=1`), no
further network access is required.

### The install script

`install.sh` / `install.ps1` are bootstrap helpers — re-run them any
time to upgrade or to switch between CPU and GPU. They:

- Install [uv](https://docs.astral.sh/uv/) if it isn't already on PATH.
- Resolve the latest non-prerelease GitHub Release via the GitHub API
  (or `gh` if authenticated) and download the published `.whl` asset.
- Detect NVIDIA CUDA via `nvidia-smi`, pick the matching `cuXXX` PyTorch
  wheel index, and — when CUDA ≥ 12.4 — add `--with 'pd-book-tools[gpu]'`
  for CuPy + opencv-cuda.
- Run `uv tool install --reinstall <wheel>` with `--extra-index-url`
  pointing at the self-hosted `pd-index-pip` (for `pd-book-tools`) and at
  PyTorch's CUDA index when applicable.

Once installed, `pd-ocr` itself only does the two outbound requests
listed above.

### Manual install

If you'd rather not pipe `curl | sh`, you can run the install yourself
with [uv](https://docs.astral.sh/uv/). The install script just wraps
`uv tool install` against the wheel asset on the latest GitHub Release —
nothing here uses `pip`.

Install uv first:

```sh
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

CPU install (uses the self-hosted `pd-index-pip` PEP 503 index for
`pd-book-tools`):

```sh
uv tool install git+https://github.com/ConcaveTrillion/pd-ocr-cli \
    --extra-index-url https://concavetrillion.github.io/pd-index-pip/simple/
```

NVIDIA GPU install — replace `cuXXX` with your CUDA version (e.g.
`cu124`, `cu130`; **CUDA 12.4 or later required** for the `[gpu]`
extra):

```sh
uv tool install git+https://github.com/ConcaveTrillion/pd-ocr-cli \
    --with 'pd-book-tools[gpu]' \
    --extra-index-url https://concavetrillion.github.io/pd-index-pip/simple/ \
    --extra-index-url https://download.pytorch.org/whl/cuXXX
```

The `[gpu]` extra on `pd-book-tools` opts into `cupy-cuda12x` and
`opencv-cuda`. Use `nvidia-smi` to read your CUDA version, or the
[PyTorch install selector](https://pytorch.org/get-started/locally/).
Disk / VRAM budgets are below in
[GPU acceleration mechanics](#gpu-acceleration-mechanics).

In practice, just re-running the install script is simpler — it does
the detection and assembles these flags for you.

### GPU acceleration mechanics

How the pieces fit together when you opt in:

- **`pd-ocr-cli`** — the app.
- **CUDA Toolkit** — NVIDIA's runtime that lets programs talk to
  your GPU. Required on Linux / Windows for the CUDA path; the
  Apple Silicon path uses Metal via PyTorch's MPS backend instead.
- **CUDA-enabled PyTorch wheels** — the same PyTorch you'd install
  on CPU, compiled to call into CUDA. The install script chooses
  the wheel matching your installed CUDA: `cu124` for CUDA 12.4,
  `cu130` for 13.0, etc. (CUDA 12.4 or newer required.)
- **OCR / layout model weights** — downloaded on first run; not
  GPU-specific.

If you'd rather pick the PyTorch wheel manually, the
[PyTorch install selector](https://pytorch.org/get-started/locally/)
walks you through it.

Rough disk + memory budget for the NVIDIA path:

- CUDA Toolkit: ~2–4 GB download, ~5–12 GB installed (depends on
  the components you select).
- CUDA-enabled PyTorch wheels: ~1–3 GB on top.
- Runtime VRAM with both OCR + layout models loaded: a few GB —
  fits comfortably on any modern dedicated NVIDIA card.

---

## Development

Working on `pd-ocr-cli` itself? See [`DEVELOPMENT.md`](DEVELOPMENT.md) for the full
developer guide — covers `make setup`, the editable side-by-side workflow with
`pd-book-tools` (`make local-setup`, `make run-local ARGS="…"`), the project
layout, and the release process.

Quick start:

```sh
git clone https://github.com/ConcaveTrillion/pd-ocr-cli
cd pd-ocr-cli
make setup            # regular dev setup against the pinned pd-book-tools tag
# — or —
make local-setup      # also clones ../pd-book-tools and links it editable
```
