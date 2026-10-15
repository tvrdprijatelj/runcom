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

python_command() {
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'python3'
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    if python -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
      printf '%s\n' 'python'
      return 0
    fi
  fi

  return 1
}

if ! command -v curl >/dev/null 2>&1; then
  err "curl is required but not installed. Please install curl and try again."
  exit 1
fi

PYTHON="$(python_command || true)"
if [ -z "$PYTHON" ]; then
  warn "Python 3 was not found on the system."
  if ask_yes "Attempt to install Python 3 automatically? This may require elevated privileges."; then
    if command -v apt-get >/dev/null 2>&1; then
      sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
      PYTHON="python3"
    elif command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y python3 python3-venv python3-pip
      PYTHON="python3"
    elif command -v pacman >/dev/null 2>&1; then
      sudo pacman -Syu --noconfirm python python-virtualenv
      PYTHON="python"
    elif command -v brew >/dev/null 2>&1; then
      brew install python
      PYTHON="python3"
    else
      err "Automatic Python installation is not supported on this system. Please install Python 3 manually and re-run."
      exit 2
    fi
  else
    err "Python 3 is required. Install Python 3 and re-run this installer."
    exit 2
  fi
fi

info "Using Python: $($PYTHON --version 2>&1)"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
cd "$TMPDIR"

info "Querying GitHub for the latest release..."
ZIP_URL="$(curl -fsSL "$API_URL" | grep '"zipball_url"' | head -n 1 | sed -E 's/.*"([^"]+)".*/\1/' || true)"
if [ -z "$ZIP_URL" ]; then
  err "Could not find the latest release ZIP URL."
  exit 1
fi

info "Downloading release archive..."
curl -LfS "$ZIP_URL" -o release.zip

mkdir -p release_dir
if command -v unzip >/dev/null 2>&1; then
  unzip -q release.zip -d release_dir
else
  if command -v tar >/dev/null 2>&1; then
    tar -xf release.zip -C release_dir || true
  else
    err "Neither unzip nor tar is available. Please install one and retry."
    exit 1
  fi
fi

EXTRACTED_DIR="$(find release_dir -maxdepth 1 -mindepth 1 -type d | head -n 1 || true)"
if [ -z "$EXTRACTED_DIR" ]; then
  err "Extraction failed or the archive did not contain a directory."
  exit 1
fi

cd "$EXTRACTED_DIR"
info "Release extracted to: $PWD"

if [ -f requirements.txt ]; then
  warn "requirements.txt found; creating a Python virtual environment and installing dependencies."
else
  warn "No requirements.txt found in this release; creating a virtual environment anyway."
fi

$PYTHON -m venv venv
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
  # run the project entrypoint or follow the repository README
EOF

exit 0
