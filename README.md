# pd-ocr-cli

OCR public domain book images to `.txt` files using fine-tuned DocTR detection and recognition models.
Models are downloaded automatically on first run — no setup required.

## GPU Setup (Optional — Recommended)

GPU acceleration is detected automatically — NVIDIA CUDA and Apple Silicon (MPS) are both supported. Without a GPU, OCR should still work but will be significantly slower on large batches.

**Apple Silicon (M1/M2/M3/M4, macOS only):** No extra setup needed — MPS acceleration should be used automatically. This path is only useful on macOS Apple Silicon systems. *(Note: this has not been tested.)*

Important: NVIDIA CUDA acceleration only works if your computer has an NVIDIA GPU. Installing CUDA alone does not add GPU support on systems without NVIDIA hardware. In practice, this path is mainly useful on Windows/Linux machines with NVIDIA GPUs.

What GPU acceleration changes in practice:

- Best gains are on large/high-resolution page batches.
- Small one-off pages may feel similar on CPU because startup/load overhead dominates.
- GPU mostly speeds up model inference (the expensive OCR step), not file I/O.

**NVIDIA GPUs:** First check whether CUDA is already available:

```sh
nvidia-smi
```

The output should show your GPU and a `CUDA Version` in the top-right corner. The install script reads this version to select the correct PyTorch build automatically.

If `nvidia-smi` is missing, or no CUDA version is shown, install the [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads) for your OS/driver and run `nvidia-smi` again.

`cuXXX` cheat sheet for install commands:

- `cu118` = CUDA 11.8
- `cu121` = CUDA 12.1
- `cu124` = CUDA 12.4
- `cu130` = CUDA 13.0

Example: if `nvidia-smi` reports CUDA 12.4, use `cu124`.

ELI5: what all this installing is for

- `pd-ocr-cli` is the app itself.
- `CUDA Toolkit` is the NVIDIA "bridge" that lets programs talk to your GPU.
- CUDA-enabled `PyTorch` wheels are the OCR engine parts compiled to run on that GPU.
- OCR models are the learned data files downloaded on first run.

If you skip GPU setup, `pd-ocr-cli` still works on CPU; GPU setup is mainly for speed.

NVIDIA GPU dependency size estimate:

- CUDA Toolkit itself is typically a multi-GB install (roughly 2-4 GB download, often 5-12 GB on disk, depending on OS/components).
- CUDA-enabled PyTorch wheels are also large: expect roughly 1-3 GB of downloads for a fresh GPU install, plus additional disk space after installation.

Manual NVIDIA GPU install with `uv` (replace `cuXXX` with your CUDA version, for example `cu118`, `cu121`, or `cu124`):

```sh
uv tool install git+https://github.com/ConcaveTrillion/pd-ocr-cli \
    --extra-index-url https://download.pytorch.org/whl/cu124
```

Use `nvidia-smi` for your CUDA version, or the [PyTorch install selector](https://pytorch.org/get-started/locally/).

Quick troubleshooting:

- `nvidia-smi` not found: NVIDIA driver/toolkit is not available in your current environment.
- Running in Docker/devcontainer: confirm the container was started with GPU access (`--gpus all`) and NVIDIA Container Toolkit is configured on the host.
- Very slow first run: model download and initialization happen once; later runs use cache.
- GPU still not used: reinstall with the matching `cuXXX` extra index and retry.

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
# OCR a single image (output written alongside the image as .txt)
pd-ocr page.png

# Multiple images
pd-ocr page1.png page2.png page3.png

# Process all images in a directory
pd-ocr images/

# Process a directory tree recursively, mirroring structure into output/
pd-ocr --recursive images/ -o output/

# Short recursive flags are also supported
pd-ocr -r images/ -o output/

# Write output to a specific directory
pd-ocr -o output/ page.png

# Also save the reorganized OCR document as JSON
pd-ocr --save-json page.png

# Check the installed version
pd-ocr --version

# Pin to a specific model version from Hugging Face
pd-ocr --model-version v1.2.0 page.png

# Use a custom Hugging Face model repo
pd-ocr --hf-repo myorg/my-ocr-models page.png
```

---

## Manual Install

Requires [uv](https://docs.astral.sh/uv/). To install uv:

```sh
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

CPU install:

```sh
uv tool install git+https://github.com/ConcaveTrillion/pd-ocr-cli
```

NVIDIA GPU install (replace `cuXXX` with your CUDA version, for example `cu118`, `cu121`, or `cu124`):

```sh
uv tool install git+https://github.com/ConcaveTrillion/pd-ocr-cli \
    --extra-index-url https://download.pytorch.org/whl/cuXXX
```

Use `nvidia-smi` for your CUDA version, or the [PyTorch install selector](https://pytorch.org/get-started/locally/). Size estimates are listed in **GPU Setup (Optional — Recommended)** above.

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

## Notes

- Models are downloaded from [CT2534/pd-ocr-models](https://huggingface.co/CT2534/pd-ocr-models) on first run and cached locally (default: `~/.cache/huggingface/hub`, or the path in `$HF_HOME` if set).
- No Hugging Face account required.
- Subsequent runs use the cached models with no download (they still need to be loaded in to memory).
- OCR powered by [DocTR](https://github.com/mindee/doctr) with fine-tuned detection and recognition models.

---

## Appendix: Development Setup (from cloned repo)

If you've cloned this repository and want to run or develop the tool locally:

**Prerequisites:** [uv](https://docs.astral.sh/uv/) must be installed.

```sh
git clone https://github.com/ConcaveTrillion/pd-ocr-cli
cd pd-ocr-cli
make setup
```

This installs the dev dependencies and sets up pre-commit hooks.

To run the CLI directly from the local source (without installing as a tool):

```sh
uv run pd-ocr page.png
```

To install it as a local tool (picks up changes after each reinstall):

```sh
uv tool install --editable .
```

To run linting and formatting checks:

```sh
make lint      # ruff check + import sort
make format    # ruff format + lint
```

To run the full CI pipeline (setup + pre-commit + build):

```sh
make ci
```
