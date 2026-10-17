#!/usr/bin/env bash
# Remove the per-user Runcom installation. User scripts are kept.
set -euo pipefail
ASSUME_YES=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --yes) ASSUME_YES=1; shift ;;
    --help|-h) echo 'Usage: bash uninstall.sh [--yes] (RUNCOM_INSTALL_DIR overrides the installation directory)'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
INSTALL_DIR="${RUNCOM_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/runcom}"
printf 'Avinstallera / Uninstall Runcom: %s\n' "$INSTALL_DIR"
echo 'Stäng Runcom först. Egna skript sparas. / Close Runcom first. Your scripts are kept.'
if [ "$ASSUME_YES" -ne 1 ]; then
  read -r -p 'Fortsätt? / Continue? [y/N] ' answer
  case "$answer" in y|Y|yes|ja) ;; *) echo 'Avbrutet / Cancelled'; exit 0 ;; esac
fi
PYTHON="$(command -v python3 || command -v python || true)"
[ -n "$PYTHON" ] || { echo 'Python is required.' >&2; exit 1; }
"$PYTHON" - "$INSTALL_DIR" <<'PY'
import os, pathlib, shlex, shutil, sys
folder = pathlib.Path(sys.argv[1]).expanduser()
if folder.is_symlink():
    raise SystemExit('Refusing a symlink installation directory')
folder = folder.resolve()
if folder in (pathlib.Path.home().resolve(), pathlib.Path(folder.anchor)):
    raise SystemExit('Unsafe installation directory')
if folder.exists() and not (folder / 'runcom.py').is_file():
    raise SystemExit('Not a Runcom installation; nothing removed')
# Only installer-owned files are removed. Extra files in the folder are kept.
for name in ('runcom.py', 'runcom', 'runcom-language', 'runcom-revision',
             'help.html', 'help.css', 'style.css', 'runcom.png', 'runcom.ico',
             'uninstall.sh', 'uninstall.ps1', 'runcom-uninstall', 'Uninstall Runcom.command'):
    path = folder / name
    if path.is_file() or path.is_symlink():
        path.unlink()
venv = folder / 'venv'
if venv.is_symlink():
    venv.unlink()
elif (venv / 'pyvenv.cfg').is_file():
    shutil.rmtree(str(venv))
data_home = pathlib.Path(os.environ.get('XDG_DATA_HOME') or pathlib.Path.home() / '.local/share')
if not data_home.is_absolute():
    data_home = pathlib.Path.home() / '.local/share'
def desktop_unescape(text):
    # Decode the Desktop Entry string escaping, without interpreting arbitrary escapes.
    result = []
    chars = iter(text)
    mapping = {'s': ' ', 'n': '\n', 'r': '\r', 't': '\t', '\\': '\\'}
    for char in chars:
        if char == '\\':
            char = next(chars, '\\')
            result.append(mapping.get(char, '\\' + char))
        else:
            result.append(char)
    return ''.join(result)
for name in ('runcom.desktop', 'runcom-uninstall.desktop'):
    entry = data_home / 'applications' / name
    if entry.is_file():
        text = entry.read_text(encoding='utf-8')
        paths = [line[5:] for line in text.splitlines() if line.startswith('Path=')]
        own = any(pathlib.Path(desktop_unescape(value)).resolve() == folder for value in paths)
        # Compatibility with older entries which contained only Exec.
        if not paths:
            for line in text.splitlines():
                if not line.startswith('Exec='):
                    continue
                try:
                    args = shlex.split(desktop_unescape(line[5:]))
                    own = any(pathlib.Path(arg).name in ('runcom', 'runcom-uninstall')
                              and pathlib.Path(arg).parent.resolve() == folder for arg in args)
                except ValueError:
                    own = False
        if own:
            entry.unlink()
if folder.exists():
    try:
        folder.rmdir()
    except OSError:
        print('Extra files kept in: ' + str(folder))
print('Runcom har avinstallerats. Egna skript finns kvar. / Runcom uninstalled. Your scripts are kept.')
PY
