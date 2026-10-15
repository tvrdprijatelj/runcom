#!/usr/bin/env bash
set -euo pipefail

# runcom installer script (POSIX shell)
# This script downloads the latest release of runcom from GitHub,
# creates a Python virtual environment and installs dependencies.
# It does NOT automatically install system Python without asking.

OWNER="tvrdprijatelj"
REPO="runcom"

echo "runcom installer — fetching latest release from GitHub for ${OWNER}/${REPO}"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT
cd "$TMPDIR"

# Try to get the latest zipball URL from the GitHub API
ZIP_URL=$(curl -fsSL "https://api.github.com/repos/${OWNER}/${REPO}/releases/latest" \
  | grep '"zipball_url"' \
  | head -n1 \
  | sed -E 's/.*"([^\"]+)".*/\1/')

if [ -z "$ZIP_URL" ]; then
  echo "Could not determine latest release URL. Exiting."
  exit 1
fi

echo "Latest release (zip): $ZIP_URL"

# Download the zip
echo "Downloading release..."
if ! curl -LfS "$ZIP_URL" -o release.zip; then
  echo "Download failed. Exiting."
  exit 1
fi

# Extract
mkdir -p release_dir
echo "Extracting..."
if command -v unzip >/dev/null 2>&1; then
  unzip -q release.zip -d release_dir
else
  # try busybox/unzip fallback for some systems
  if command -v tar >/dev/null 2>&1; then
    # GitHub zipball extracted with tar on some environments
    tar -xf release.zip -C release_dir || true
  else
    echo "No unzip or tar available to extract archive. Please install unzip or tar."
    exit 1
  fi
fi

# Find extracted folder
EXTRACTED_DIR=$(find release_dir -maxdepth 1 -mindepth 1 -type d | head -n1)
if [ -z "$EXTRACTED_DIR" ]; then
  echo "Could not find extracted release folder. Exiting."
  exit 1
fi

cd "$EXTRACTED_DIR"

# Check for requirements.txt
if [ -f requirements.txt ]; then
  echo "Found requirements.txt"
else
  echo "No requirements.txt found in the release. Continuing without installing Python packages."
fi

# Detect python3
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  # check if python is 3.x
  if "$PYTHON" -c "import sys; sys.exit(0)" 2>/dev/null; then
    PYTHON=python
  else
    PYTHON=python
  fi
else
  PYTHON=""
fi

if [ -z "$PYTHON" ]; then
  echo
  echo "Python 3 not found on PATH."
  echo "You can install Python 3 using your system package manager, for example:" 
  echo "  Ubuntu/Debian: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  echo "  Fedora/RHEL: sudo dnf install -y python3 python3-venv python3-pip"
  echo "  Arch: sudo pacman -Syu python python-virtualenv"
  echo "  macOS (Homebrew): brew install python"
  echo
  echo "Alternatively, install Python from https://www.python.org/downloads/ and re-run this script."
  exit 2
fi

# Create venv
echo "Using $PYTHON — creating virtual environment in ./venv"
$PYTHON -m venv venv

# Activate and install
# shellcheck disable=SC1091
. ./venv/bin/activate

if [ -f requirements.txt ]; then
  echo "Upgrading pip and installing requirements..."
  pip install --upgrade pip setuptools wheel
  pip install -r requirements.txt
else
  echo "No requirements.txt — skipping pip install."
fi

echo
echo "Installation complete. To start using the assistant, activate the virtualenv:"
echo "  source venv/bin/activate"
echo "Then run the assistant (if README or entrypoint is provided)."

echo "Installer finished successfully. Removed temporary files."

exit 0
