#!/usr/bin/env bash
set -eu

RELEASE_REPO="pdomain/pdomain-ocr-cli"

. "$(dirname "$0")/release-common.sh"
pd_release_main "$@"
