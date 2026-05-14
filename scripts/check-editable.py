#!/usr/bin/env python3
"""Verify pd-book-tools resolves to the sibling editable checkout.

Used by the `check-local-editable` Make target. Exits 0 if the imported
`pd_book_tools` module lives inside the directory passed as argv[1]
(the resolved peer-repo path), otherwise exits 1. Diagnostic info is
printed to stdout in either case so callers can see which copy was
picked up.
"""

from __future__ import annotations

import importlib.metadata as md
import inspect
import os
import sys

import pd_book_tools

if len(sys.argv) != 2:
    print("usage: check-editable.py <expected-peer-path>", file=sys.stderr)  # CLI output
    sys.exit(2)

expected_peer = os.path.realpath(sys.argv[1])
module_file = os.path.realpath(inspect.getfile(pd_book_tools))
is_local = module_file == expected_peer or module_file.startswith(expected_peer + os.sep)

print("module_file=", module_file)  # CLI output
print("expected_peer=", expected_peer)  # CLI output
print("dist_version=", md.version("pd-book-tools"))  # CLI output

sys.exit(0 if is_local else 1)
