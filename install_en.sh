#!/usr/bin/env bash
# Download the installer, then install Runcom in the selected language.
set -euo pipefail
RUNCOM_INSTALLER_TEMP="$(mktemp -d)"
trap 'rm -rf "$RUNCOM_INSTALLER_TEMP"' EXIT
curl -fL https://raw.githubusercontent.com/tvrdprijatelj/runcom/main/install.sh -o "$RUNCOM_INSTALLER_TEMP/install.sh"
bash "$RUNCOM_INSTALLER_TEMP/install.sh" --ref main "$@" --lang en
