#!/usr/bin/env bash
# Install the latest release into a persistent, per-user directory.
set -euo pipefail
INSTALL_DIR="${RUNCOM_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/runcom}"
PYTHON="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON" ]; then
  echo 'Python 3.8+ is required. Install Python with Tkinter and venv, then retry.' >&2
  exit 1
fi
"$PYTHON" -c 'import sys; assert sys.version_info >= (3,8), "Python 3.8+ required"'
if ! "$PYTHON" -c 'import tkinter; tkinter.Tcl()' 2>/dev/null; then
  echo 'Tkinter is missing. Ubuntu/Debian: sudo apt install python3-tk python3-venv' >&2
  echo 'Arch: sudo pacman -S python tk | Fedora: sudo dnf install python3-tkinter' >&2
  echo 'macOS: use a Python installation with Tk support from python.org.' >&2
  exit 1
fi
command -v curl >/dev/null || { echo 'Install curl and retry.' >&2; exit 1; }
RUNCOM_TEMP="$(mktemp -d)"
trap 'rm -rf "$RUNCOM_TEMP"' EXIT
curl --fail --location --silent --show-error --retry 2 \
  https://api.github.com/repos/tvrdprijatelj/runcom/releases/latest -o "$RUNCOM_TEMP/release.json"
ZIP_URL="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["zipball_url"])' "$RUNCOM_TEMP/release.json")"
curl --fail --location --show-error --retry 2 "$ZIP_URL" -o "$RUNCOM_TEMP/release.zip"
"$PYTHON" - "$RUNCOM_TEMP" <<'PY'
import pathlib, sys, zipfile
root = pathlib.Path(sys.argv[1])
with zipfile.ZipFile(root / 'release.zip') as archive:
    target = (root / 'source').resolve()
    for entry in archive.infolist():
        if target not in (target / entry.filename).resolve().parents:
            raise SystemExit('Unsafe archive path')
    archive.extractall(target)
PY
SOURCE="$(find "$RUNCOM_TEMP/source" -mindepth 1 -maxdepth 1 -type d -print -quit)"
[ -f "$SOURCE/runcom.py" ] || { echo 'Release does not contain runcom.py' >&2; exit 1; }
mkdir -p "$INSTALL_DIR"
# Validate the environment before replacing the application.
if [ ! -x "$INSTALL_DIR/venv/bin/python" ]; then
  "$PYTHON" -m venv "$INSTALL_DIR/venv" || { echo 'Install Python venv support and retry.' >&2; exit 1; }
fi
"$INSTALL_DIR/venv/bin/python" -c 'import tkinter'
if [ -f "$SOURCE/requirements.txt" ]; then
  "$INSTALL_DIR/venv/bin/python" -m pip install -r "$SOURCE/requirements.txt"
fi
cp "$SOURCE/runcom.py" "$INSTALL_DIR/runcom.py"
"$PYTHON" - "$INSTALL_DIR" <<'PY'
import pathlib, shlex, sys
folder = pathlib.Path(sys.argv[1]).resolve()
launcher = folder / 'runcom'
launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(str(folder / 'venv/bin/python')) + ' ' + shlex.quote(str(folder / 'runcom.py')) + ' "$@"\n')
launcher.chmod(0o755)
print('Installation complete. Start Runcom with:\n' + shlex.quote(str(launcher)))
PY
