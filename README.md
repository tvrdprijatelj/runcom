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

## Use

- Create a script with Ctrl+N, open with Ctrl+O, save with Ctrl+S, save as with Ctrl+Shift+S. macOS also supports Command.
- Filter file names in the sidebar. Double-click a file or press Enter to open it.
- F5 runs in the output panel. F6 runs in an external terminal; use this for interactive input.
- Linux/macOS support shell scripts and Python files. Windows supports `.bat`, `.cmd` and `.ps1`.
- Stop terminates the running process group. Unsaved changes are checked before switching files or closing.
- The optional Unix sudo mode keeps a password in memory and passes it to child processes through their environment. Only enable it for scripts you trust; turn it off when finished. Terminal execution uses the terminal's normal authentication.

## Install a published release

Download `install.sh` (Linux/macOS) or `install.ps1` (Windows) from the download page. Inspect the script, then execute it from the download directory:

```sh
bash install.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installers fetch the **latest published GitHub release**, not the current main branch. Changes on main become available to installed users after a new release is published.

Linux/macOS installs to `${XDG_DATA_HOME:-~/.local/share}/runcom`. The installer prints the full launch command. Set `RUNCOM_INSTALL_DIR` to choose another location. Windows installs to `%LOCALAPPDATA%\Runcom` and adds a desktop shortcut; use `-InstallDir` to customize the location. Run the installer again to update; scripts in `~/skript` are kept separately.

## Validation

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile runcom.py
bash -n install.sh download_assistant.sh
node --check download.js
```

The automated checks cover execution commands, shell path quoting, failed Save As, Python file preservation, and persistent installation/update using an offline release fixture. Desktop appearance and native Windows/macOS behavior need testing on those systems.
