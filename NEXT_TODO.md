# NEXT_TODO — clean up Makefile tab-completion

## Symptom

Running `make <TAB>` in the pd-ocr-cli repo shows a list of "targets"
that includes junk like:

```
"❌    "||    1)"    (echo    else    if    is    is_local    not    pd-book-tools    sys.exit(0
```

These are not real make targets — running them fails with
`make: *** No rule to make target '...'`. They're noise polluting an
otherwise useful UX.

## Cause

Bash's `make` tab-completion is a regex scraper, not a grammar parser.
It walks the Makefile and extracts anything that looks vaguely
target-shaped, including tokens inside multi-line shell snippets and
recipe bodies. It does **not** call `make -pn` to ask make for the
real target list.

Two recipes in our Makefile feed it the most junk:

1. `check-local-editable` embeds a Python one-liner:
   ```makefile
   @env -u VIRTUAL_ENV UV_NO_SYNC=1 uv run python -c "import inspect, os, sys, importlib.metadata as md, pd_book_tools; \
   module_file = os.path.realpath(inspect.getfile(pd_book_tools)); \
   peer = os.path.realpath('$(PEER_BOOK_TOOLS)'); \
   is_local = module_file.startswith(peer + os.sep) or module_file == peer; \
   ...
   sys.exit(0 if is_local else 1)" || (echo "❌ pd-book-tools is not local/editable. Run: make dev-local" >&2; exit 1)
   ```
   This contributes `is_local`, `is`, `not`, `else`, `sys.exit(0`,
   `pd-book-tools`, `(echo`, `"❌`, `||`, `1)"`.

2. The `_resolve_gpu_index` and `_maybe_install_cuda_torch`
   `define`/`endef` blocks contain shell `if`/`else`/`fi`, `case`,
   and quoted echos that contribute `if`, `else`, and similar tokens.

## Fix

Extract the embedded code into proper script files, then call them
from one-line recipes. The completion scraper only sees the call,
not the implementation.

### Step 1 — extract the editable check

Create `scripts/check-editable.py`:

```python
#!/usr/bin/env python3
"""Verify pd-book-tools resolves to the sibling editable checkout."""
from __future__ import annotations

import importlib.metadata as md
import inspect
import os
import sys

import pd_book_tools

if len(sys.argv) != 2:
    print("usage: check-editable.py <expected-peer-path>", file=sys.stderr)
    sys.exit(2)

expected_peer = os.path.realpath(sys.argv[1])
module_file = os.path.realpath(inspect.getfile(pd_book_tools))
is_local = module_file == expected_peer or module_file.startswith(
    expected_peer + os.sep
)

print(f"module_file= {module_file}")
print(f"expected_peer= {expected_peer}")
print(f"dist_version= {md.version('pd-book-tools')}")

sys.exit(0 if is_local else 1)
```

Replace the recipe body with:

```makefile
check-local-editable: ## [local-dev] Verify pd-book-tools resolves to ../pd-book-tools (not the pinned tag)
	$(call _require_peer_book_tools)
	@env -u VIRTUAL_ENV UV_NO_SYNC=1 uv run python scripts/check-editable.py "$(PEER_BOOK_TOOLS)" \
		|| (echo "❌ pd-book-tools is not local/editable. Run: make dev-local" >&2; exit 1)
	@echo "✅ pd-book-tools resolves to local editable copy."
```

That's still one shell-level `|| (echo …; exit 1)` chain, but it
contributes far less noise than the inlined Python.

### Step 2 — extract GPU detection

Move the bodies of `_resolve_gpu_index` and `_maybe_install_cuda_torch`
into `scripts/resolve-gpu-index.sh` and `scripts/maybe-install-cuda-torch.sh`
respectively. Each becomes a single-purpose shell script. Replace the
`define`/`endef` blocks with simple invocations:

```makefile
setup: ## Set up dev environment ...
	@echo "📦 Installing dependencies..."
	uv sync --group all-dev
	@echo "🌐 Installing Playwright Chromium browser and system dependencies..."
	uv run playwright install --with-deps chromium
	@echo "🪝 Setting up pre-commit hooks..."
	uv run pre-commit install
	@./scripts/maybe-install-cuda-torch.sh
	@$(MAKE) --no-print-directory prefetch-models
	@echo "✅ Setup complete!"
```

Same behavior, no inline shell logic, no `if`/`else`/`fi` lines for
the completion scraper to mistake for targets.

### Step 3 — verify

After the refactor:

```bash
# Real target list (clean)
make -pRrq : 2>/dev/null | awk '/^[a-zA-Z_-][a-zA-Z0-9_.-]*:/ {sub(":.*","",$0); print}' | sort -u

# Tab completion
make <TAB>
```

Both should match — only real targets, no shell tokens.

## Why bother

- A clean `make <TAB>` saves time when discovering targets.
- New contributors don't get confused by `make sys.exit(0` not working.
- Extracted scripts are also easier to test in isolation
  (`bash -x scripts/resolve-gpu-index.sh` is a normal debug loop;
  `make -n` against a `define` block is awkward).

## Cross-reference

This pattern was identified during pd-ocr-synth's M01 dev-tooling
work. The pd-ocr-synth Makefile deliberately avoids embedded shell
and Python in recipes precisely to keep tab-completion clean.
See `pd-ocr-synth/Makefile` for the reference layout.

## Scope

Mechanical refactor; no behavior change. Suggested sizing: half a
session, including writing one or two regression tests against
`make help` output to catch regressions.
