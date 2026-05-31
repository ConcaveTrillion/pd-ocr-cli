# Type Suppressions

All basedpyright warnings are resolved without suppressions (baseline.json is
empty). The three remaining `pyright: ignore` comments and the one structural
`noqa` are listed here so the rationale is auditable in one place.

## `pyright: ignore` suppressions

| File | Line | Rule | Rationale |
|------|------|------|-----------|
| `pdomain_ocr_cli/_startup_notices.py` | 53 | `reportMissingImports` | `cupy` is an optional GPU dependency not declared in `pyproject.toml`. The import is a runtime probe; the ignore lets the type checker skip the missing stub. |
| `pdomain_ocr_cli/ocr_to_txt.py` | 407 | `reportAttributeAccessIssue` | `module` is the result of `importlib.import_module("pdomain_ops.gpu.device")` cast to `object`. Basedpyright cannot resolve attributes on `object`; the `cast` on the same line completes the type for downstream callers. |
| `pdomain_ocr_cli/ocr_to_txt.py` | 430 | `reportAttributeAccessIssue` | Same pattern — `importlib.import_module("pdomain_ops.gpu.doctr_batch")` cast to `object`. The outer `cast` resolves the callable type; the suppress covers the intermediate attribute access. |

## `noqa` suppressions with structural rationale

Most `noqa` suppressions have an inline comment explaining the context. The
one that warrants extra explanation:

| File | Line | Rule | Rationale |
|------|------|------|-----------|
| `pdomain_ocr_cli/ocr_to_txt.py` | 981 | `TRY301` | `raise ValueError(...)` is inside a `try` block. TRY301 suggests abstracting the raise to an inner function, but here it is intentional: the outer `except Exception` (line 984) unifies all per-image decode failures — both the explicit ValueError and any unexpected cv2 error — through a single error-reporting path. Abstracting would require duplicating that handler. |

Other inline `noqa` suppressions (`T201` for CLI print statements, `BLE001`
for broad-except decode handlers, `S310`/`S110`/`S607` for subprocess and
URL-open patterns) are self-explanatory from their inline comments and are not
catalogued here.
