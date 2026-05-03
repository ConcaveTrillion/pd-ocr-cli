# pd-ocr-cli

OCR public domain book images to `.txt` files using fine-tuned DocTR detection and recognition models.
Models are downloaded automatically on first run — no setup required.

## GPU Setup (Optional — Recommended)

GPU acceleration is detected automatically — NVIDIA CUDA and Apple Silicon (MPS) are both supported. Without a GPU, OCR will still work but will be significantly slower on large batches.

**NVIDIA GPUs:** Install the [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads) for your OS and driver version. After installation, verify with:

```sh
nvidia-smi
```

The output should show your GPU and a `CUDA Version` in the top-right corner. The install script reads this version to select the correct PyTorch build automatically.

**Apple Silicon (M1/M2/M3/M4):** No extra setup needed — MPS acceleration should be used automatically. *(Note: this has not been tested.)*

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

NVIDIA GPU install — replace `cuXXX` with your CUDA version (e.g. `cu118`, `cu121`, `cu124`). Check `nvidia-smi` for your version, or use the [PyTorch install selector](https://pytorch.org/get-started/locally/):

```sh
uv tool install git+https://github.com/ConcaveTrillion/pd-ocr-cli \
    --extra-index-url https://download.pytorch.org/whl/cu124
```

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
