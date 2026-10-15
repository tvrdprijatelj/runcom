#!/usr/bin/env bash
set -euo pipefail

OWNER="tvrdprijatelj"
REPO="runcom"
API_URL="https://api.github.com/repos/${OWNER}/${REPO}/releases/latest"

info() { printf '\033[1;34m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*"; }
err()  { printf '\033[1;31m%s\033[0m\n' "$*"; }

ask_yes() {
  printf "%s [y/N]: " "$1"
  read -r ans
  case "$ans" in
    [yY]|[yY][eE][sS]) return 0 ;;
    *) return 1 ;;
  esac
}

detect_python() {
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    if python -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
      printf '%s\n' "python"
      return 0
    fi
  fi

  return 1
}

if ! command -v curl >/dev/null 2>&1; then
  err "curl is required but not installed. Please install curl and try again."
  exit 1
fi

PYTHON="$(detect_python || true)"
if [ -z "$PYTHON" ]; then
  warn "Python 3 was not found on this system."
  if ask_yes "Attempt to install Python 3 automatically? This may require administrator privileges."; then
    if command -v sudo >/dev/null 2>&1; then
      if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip
        PYTHON="python3"
      elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y python3 python3-virtualenv python3-pip
        PYTHON="python3"
      elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Syu --noconfirm python python-virtualenv
        PYTHON="python"
      elif command -v brew >/dev/null 2>&1; then
        brew install python
        PYTHON="python3"
      else
        err "Automatic Python installation is not supported on this system."
        exit 2
      fi
    else
      err "sudo is required to install system packages automatically. Please install Python 3 manually and rerun this installer."
      exit 2
    fi
  else
    err "Python 3 is required. Please install Python 3 manually and rerun this installer."
    exit 2
  fi
fi

info "Using Python: $($PYTHON --version 2>&1)"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
cd "$TMPDIR"

info "Querying GitHub for the latest release..."
ZIP_URL="$(curl -fsSL -H 'Accept: application/vnd.github.v3+json' "$API_URL" | grep '"zipball_url"' | head -n 1 | sed -E 's/.*"([^"]+)".*/\1/' || true)"
if [ -z "$ZIP_URL" ]; then
  err "Could not find the latest release ZIP URL."
  exit 1
fi

info "Downloading release archive..."
curl -LfS "$ZIP_URL" -o release.zip

mkdir -p release_dir

if command -v unzip >/dev/null 2>&1; then
  unzip -q release.zip -d release_dir
elif command -v tar >/dev/null 2>&1; then
  tar -xf release.zip -C release_dir || true
else
  info "No unzip/tar available; falling back to Python zip extraction..."
  "$PYTHON" - <<'PY'
import zipfile
with zipfile.ZipFile("release.zip") as zf:
    zf.extractall("release_dir")
PY
fi

EXTRACTED_DIR="$(find release_dir -maxdepth 1 -mindepth 1 -type d | head -n 1 || true)"
if [ -z "$EXTRACTED_DIR" ]; then
  err "Extraction failed or the archive does not contain a directory."
  exit 1
fi

cd "$EXTRACTED_DIR"
info "Release extracted to: $PWD"

if [ -f requirements.txt ]; then
  warn "requirements.txt was found; creating a Python virtual environment and installing dependencies."
else
  warn "No requirements.txt file was found; creating a virtual environment anyway."
fi

"$PYTHON" -m venv venv
# shellcheck disable=SC1091
. ./venv/bin/activate

if [ -f requirements.txt ]; then
  python -m pip install --upgrade pip setuptools wheel
  python -m pip install -r requirements.txt
fi

info "Installation complete."
cat <<EOF
To use the project:
  cd "$PWD"
  source venv/bin/activate
  # then run the project entrypoint or follow the repository README
EOF

exit 0
