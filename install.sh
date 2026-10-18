#!/usr/bin/env bash
# Install the latest release into a persistent, per-user directory.
set -euo pipefail
REF=""
APP_LANGUAGE=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --lang)
      [ "$#" -ge 2 ] || { echo "Missing language" >&2; exit 2; }
      case "$2" in sv|en) APP_LANGUAGE="$2" ;; *) echo "Language must be sv or en" >&2; exit 2 ;; esac
      shift 2 ;;
    --ref)
      [ "$#" -ge 2 ] && [ -n "$2" ] || { echo 'Usage: bash install.sh [--ref main|TAG] [--lang sv|en]' >&2; exit 2; }
      REF="$2"; shift 2 ;;
    --help|-h) echo 'Usage: bash install.sh [--ref main|TAG] [--lang sv|en]'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
INSTALL_DIR="${RUNCOM_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/runcom}"
PYTHON="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON" ]; then
  echo 'Python 3.8+ is required. Install Python with Tkinter and venv, then retry.' >&2
  exit 1
fi
"$PYTHON" -c 'import sys; sys.exit("Python 3.8+ required" if sys.version_info < (3,8) else 0)'
if ! "$PYTHON" -c 'import tkinter; tkinter.Tcl()' 2>/dev/null; then
  echo 'Tkinter is missing. Ubuntu/Debian: sudo apt install python3-tk python3-venv' >&2
  echo 'Arch: sudo pacman -S python tk | Fedora: sudo dnf install python3-tkinter' >&2
  echo 'macOS: use a Python installation with Tk support from python.org.' >&2
  exit 1
fi
command -v curl >/dev/null || { echo 'Install curl and retry.' >&2; exit 1; }
RUNCOM_TEMP="$(mktemp -d)"
trap 'rm -rf "$RUNCOM_TEMP"' EXIT
if [ -n "$REF" ]; then
  ENCODED_REF="$("$PYTHON" -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$REF")"
  ZIP_URL="https://api.github.com/repos/tvrdprijatelj/runcom/zipball/$ENCODED_REF"
  echo "Installing source ref: $REF"
else
  curl --fail --location --silent --show-error --retry 2 --connect-timeout 15 --max-time 180 \
    https://api.github.com/repos/tvrdprijatelj/runcom/releases/latest -o "$RUNCOM_TEMP/release.json" || {
    echo 'Could not retrieve the latest release. Check your connection or use --ref main for current source.' >&2; exit 1;
  }
  ZIP_URL="$("$PYTHON" -c 'import json,sys; data=json.load(open(sys.argv[1])); print(data["zipball_url"])' "$RUNCOM_TEMP/release.json")"
fi
curl --fail --location --show-error --retry 2 --connect-timeout 15 --max-time 180 "$ZIP_URL" -o "$RUNCOM_TEMP/release.zip"
"$PYTHON" - "$RUNCOM_TEMP" <<'PY'
import pathlib, sys, zipfile
root = pathlib.Path(sys.argv[1])
with zipfile.ZipFile(root / 'release.zip') as archive:
    target = (root / 'source').resolve()
    entries = archive.infolist()
    if sum(entry.file_size for entry in entries) > 100 * 1024 * 1024:
        raise SystemExit('Archive is unexpectedly large')
    for entry in entries:
        if (target not in (target / entry.filename).resolve().parents
                or (entry.external_attr >> 16) & 0o170000 == 0o120000):
            raise SystemExit('Unsafe archive path or symlink')
    archive.extractall(target)
    roots = list(target.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise SystemExit('Archive must contain one project directory')
    app = roots[0] / 'runcom.py'
    compile(app.read_bytes(), str(app), 'exec')
PY
SOURCE="$(find "$RUNCOM_TEMP/source" -mindepth 1 -maxdepth 1 -type d -print -quit)"
[ -f "$SOURCE/runcom.py" ] || { echo 'Release does not contain runcom.py' >&2; exit 1; }
mkdir -p "$INSTALL_DIR"
# Validate the environment before replacing the application.
if ! "$INSTALL_DIR/venv/bin/python" -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3,8) else 1)' >/dev/null 2>&1; then
  "$PYTHON" -m venv --clear "$INSTALL_DIR/venv" || { echo 'Install Python venv support and retry.' >&2; exit 1; }
fi
"$INSTALL_DIR/venv/bin/python" -c 'import tkinter'
if [ -f "$SOURCE/requirements.txt" ]; then
  "$INSTALL_DIR/venv/bin/python" -m pip install -r "$SOURCE/requirements.txt"
fi
"$PYTHON" - "$INSTALL_DIR" "$SOURCE" "$APP_LANGUAGE" <<'PY'
import os, pathlib, shlex, stat, sys, tempfile
folder = pathlib.Path(sys.argv[1]).resolve()
source = pathlib.Path(sys.argv[2])
language = sys.argv[3]

if language == 'en' and b'TRANSLATIONS' not in (source / 'runcom.py').read_bytes():
    raise SystemExit('This version does not support English. Retry with --ref main.')

def replace_file(path, data, mode):
    fd, temporary = tempfile.mkstemp(prefix='.runcom-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

files = []
if language:
    files.append((folder / 'runcom-language', language.encode(), 0o600))
files.extend([
    (folder / 'runcom.py', (source / 'runcom.py').read_bytes(), 0o600),
    (folder / 'runcom-revision', source.name.rsplit('-', 1)[-1].encode(), 0o600),
])
for name in ('help.html', 'help_en.html', 'help.css', 'style.css', 'runcom.png', 'runcom.ico', 'uninstall.sh', 'uninstall.ps1'):
    asset = source / name
    if asset.is_file():
        files.append((folder / name, asset.read_bytes(), 0o600))
launcher = folder / 'runcom'
launcher_text = ('#!/bin/sh\nexec ' + shlex.quote(str(folder / 'venv/bin/python')) + ' ' + shlex.quote(str(folder / 'runcom.py')) + ' "$@"\n')
files.append((launcher, launcher_text.encode(), 0o700))
uninstall_launcher = folder / ('Uninstall Runcom.command' if sys.platform == 'darwin' else 'runcom-uninstall')
if (source / 'uninstall.sh').is_file():
    command = ('#!/bin/sh\nexport RUNCOM_INSTALL_DIR=' + shlex.quote(str(folder)) + '\n'
               'exec bash ' + shlex.quote(str(folder / 'uninstall.sh')) + ' "$@"\n')
    files.append((uninstall_launcher, command.encode(), 0o700))

# Replace the complete application as one transaction. If any target cannot be
# written, restore every file already changed before reporting the failure.
backups = {}
applied = []
try:
    for path, data, mode in files:
        existed = path.is_file() or path.is_symlink()
        backups[path] = (existed, path.read_bytes() if existed else None,
                         stat.S_IMODE(path.stat().st_mode) if existed else None)
        replace_file(path, data, mode)
        applied.append(path)
except BaseException:
    for path in reversed(applied):
        existed, data, mode = backups[path]
        if existed:
            replace_file(path, data, mode)
        else:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    raise

if (source / 'uninstall.sh').is_file():
    print('Uninstall with: ' + shlex.quote(str(uninstall_launcher)))
if sys.platform.startswith('linux'):
    # Desktop Entry: escape the string layer, then the Exec argument layer.
    def desktop_value(value):
        return (str(value).replace('\\', '\\\\').replace('\n', '\\n')
                .replace('\r', '\\r').replace('\t', '\\t'))
    def exec_argument(value):
        argument = str(value).replace('%', '%%')
        for char in ('\\', '"', '`', '$'):
            argument = argument.replace(char, '\\' + char)
        return desktop_value('"' + argument + '"')
    data_home = pathlib.Path(os.environ.get('XDG_DATA_HOME') or pathlib.Path.home() / '.local/share')
    if not data_home.is_absolute():
        data_home = pathlib.Path.home() / '.local/share'
    entry = data_home / 'applications/runcom.desktop'
    try:
        entry.parent.mkdir(parents=True, exist_ok=True)
        text = ('[Desktop Entry]\nType=Application\nVersion=1.0\nName=Runcom\n'
                'Comment=Create, edit and run scripts\nComment[sv]=Skapa, redigera och kör skript\n'
                'Exec=' + exec_argument('/bin/sh') + ' ' + exec_argument(launcher) + '\n'
                'Path=' + desktop_value(folder) + '\n'
                'Icon=' + desktop_value(folder / 'runcom.png' if (folder / 'runcom.png').is_file() else 'utilities-terminal') + '\n'
                'Terminal=false\nCategories=Development;Utility;\n'
                'Keywords=script;editor;python;bash;skript;\n')
        replace_file(entry, text.encode('utf-8'), 0o644)
        print('Application menu shortcut: ' + str(entry))
        if (folder / 'uninstall.sh').is_file():
            remove_entry = entry.with_name('runcom-uninstall.desktop')
            text = ('[Desktop Entry]\nType=Application\nVersion=1.0\nName=Uninstall Runcom\n'
                    'Name[sv]=Avinstallera Runcom\nComment=Remove Runcom; keep personal scripts\n'
                    'Exec=' + exec_argument('/bin/sh') + ' ' + exec_argument(uninstall_launcher) + '\n'
                    'Path=' + desktop_value(folder) + '\n'
                    'Icon=system-software-install\nTerminal=true\nCategories=Development;Utility;\n')
            replace_file(remove_entry, text.encode('utf-8'), 0o644)
    except OSError as error:
        print('Could not create the application menu shortcut: ' + str(error), file=sys.stderr)
print('Installation complete. Start Runcom from your application menu (Linux), or with:\n' + shlex.quote(str(launcher)))
PY
