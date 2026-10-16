# Runcom

A small Swedish-language script editor for Linux, macOS and Windows. Uses Python 3.8+ and Tkinter; no third-party Python packages.

## Start from source

Download or clone this repository, then run:

```sh
python3 runcom.py
```

Windows: `py runcom.py`.

Tkinter prerequisites:

- Ubuntu/Debian: `sudo apt install python3-tk python3-venv`
- Arch: `sudo pacman -Syu --needed python tk`
- Fedora: `sudo dnf install python3-tkinter python3-pip`
- Windows/macOS: install Python with Tcl/Tk support from python.org.

## Help

Click **Hjälp** in the app or press **F1** for the detailed Swedish guide and FAQ. The installer includes `help.html`, `help.css` and `style.css` for offline reading. A standalone `runcom.py` falls back to the online guide: https://tvrdprijatelj.github.io/runcom/help.html. The website also has a Hjälp button.

## Use

- Create a script with Ctrl+N, open with Ctrl+O, save with Ctrl+S, save as with Ctrl+Shift+S. macOS also supports Command.
- Filter file names in the sidebar. Double-click a file or press Enter to open it.
- F5 runs in the output panel. F6 runs in an external terminal; use this for interactive input.
- Linux/macOS support shell scripts and Python files; existing shebangs are respected. Windows supports `.bat`, `.cmd`, `.ps1` and `.py`.
- Stop terminates the running process group. Unsaved changes are checked before switching files or closing. Output is streamed even without a newline, and buffered output is bounded.
- On Linux/macOS, **Kör med sudo…** opens a terminal and uses normal sudo authentication. Runcom does not collect or cache the password.
- Saves use an encoded temporary file followed by replacement, so encoding or write errors leave the original intact. External edits or deletions require confirmation before overwrite. Existing file permissions are preserved; only owner execution permission is added for a shebang.
- Batch paths containing `%` are rejected with an explanation because cmd expands environment variables in those paths.

## Install a published release

Download `install.sh` (Linux/macOS) or `install.ps1` (Windows) from the download page. Inspect the script, then execute it from the download directory:

```sh
bash install.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Without arguments, the installers fetch the **latest published GitHub release**. To install the current fixes on main, use:

```sh
bash install.sh --ref main
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Ref main
```

The download page defaults to current fixes on main and lets you select the latest published release instead. The generated commands download a fresh installer to a fixed filename before running it, avoiding accidentally running an older `install.sh` left in Downloads. A published release can be older than main; the page labels this explicitly.

Linux/macOS installs to `${XDG_DATA_HOME:-~/.local/share}/runcom`. The installer prints the full launch command. Set `RUNCOM_INSTALL_DIR` to choose another location. On Linux the installer adds `runcom.desktop` to `${XDG_DATA_HOME:-~/.local/share}/applications`, so you can search for Runcom in the application menu. Windows installs to `%LOCALAPPDATA%\Runcom` and adds Start-menu and desktop shortcuts; use `-InstallDir` to customize the location. Run the installer again to update; scripts in `~/skript` are kept separately.

## Validation

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile runcom.py
bash -n install.sh download_assistant.sh
node --check download.js
node tests/test_download.cjs
```

CI runs Python tests on Linux (3.8, 3.12 and 3.14), Windows and macOS. Linux uses Xvfb for real Tk widget tests. Checks include file preservation on encoding/write failures, external changes, streaming output, bounded queues, actual script execution and stopping, and offline install/update fixtures. Native Windows checks exercise cmd paths containing spaces and `&`, PowerShell parsing, and the Windows installer.

Browser tests use Playwright/Chromium to check Swedish and English pages at desktop and mobile sizes, downloads, version selection and clipboard behavior. CI saves page screenshots as artifacts. These are automated functional checks, not exhaustive testing of every desktop configuration.

For local GUI tests on Linux, use `xvfb-run -a python3 -m unittest discover -s tests -v` or run in a desktop session. Without a display, GUI tests skip; CI sets `RUNCOM_REQUIRE_GUI=1` so display failures cannot pass silently.
