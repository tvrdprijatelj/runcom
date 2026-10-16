#!/usr/bin/env bash
# Compatibility entry point: use the same maintained installer.
set -euo pipefail
RUNCOM_TEMP="$(mktemp -d)"
trap 'rm -rf "$RUNCOM_TEMP"' EXIT
curl --fail --location --show-error https://raw.githubusercontent.com/tvrdprijatelj/runcom/main/install.sh -o "$RUNCOM_TEMP/install.sh"
bash "$RUNCOM_TEMP/install.sh" "$@"
