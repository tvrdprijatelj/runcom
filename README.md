# Runcom

A small Swedish/English script editor for Linux, macOS and Windows. Uses Python 3.8+ and Tkinter; no third-party Python packages.

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

## Website maintenance

`maintenance.html` is a standalone Swedish/English maintenance page for GitHub Pages, with no external assets or JavaScript. It is available at `https://tvrdprijatelj.github.io/runcom/maintenance.html` after deployment. To display it as the homepage during maintenance, temporarily replace `index.html` with a copy of `maintenance.html` and publish through the existing GitHub Pages setup. Restore the original `index.html` when maintenance is complete. Other pages remain accessible through their direct URLs.

## Help

Click **Hjälp** in the app or press **F1** for the detailed Swedish guide and FAQ. The installer includes `help.html`, `help.css` and `style.css` for offline reading. A standalone `runcom.py` falls back to the online guide: https://tvrdprijatelj.github.io/runcom/help.html. The website also has a Hjälp button.

## Use

- Create a script with Ctrl+N, open with Ctrl+O, save with Ctrl+S, save as with Ctrl+Shift+S. macOS also supports Command.
- Select a file and click **▶ Kör vald fil** (or Ctrl+Enter in the file list) to open and run it. **Öppna och kör…** picks a file from any folder and runs it. Unsaved changes are checked before switching files; edits to the current script are saved before running.
- Filter file names in the sidebar. Double-click a file or press Enter to open it.
- F5 runs in the output panel. F6 runs in an external terminal. F7 opens the built-in command terminal.
- The Terminal tab keeps a user shell open independently of the editor. Linux/macOS support interactive commands, input, Ctrl+C, history and tab completion through a PTY. This is a line terminal; use F6 for full-screen programs such as nano, vim or top. Windows provides a persistent cmd session with a separate input line; use F6 for interactive console programs. Restart terminal ends the old session and starts in the currently selected scripts folder. Closing Runcom ends its built-in shell.
- Linux/macOS support shell scripts and Python files; existing shebangs are respected. Windows supports `.bat`, `.cmd`, `.ps1` and `.py`.
- Stop terminates the running process group. Unsaved changes are checked before switching files or closing. Output is streamed even without a newline, and buffered output is bounded.
- On Linux/macOS, running a `.sh`, `.bash`, `.zsh` or `.ksh` file with an explicit sudo command automatically uses **Kör med sudo…** in the built-in terminal. This runs the entire script with sudo. Comments and ordinary arguments such as `echo sudo` do not trigger it.
- On Linux/macOS, startup opens the built-in terminal and requests fresh sudo authentication (`sudo -k -v`), then keeps authorization active for the session. If sudo is unavailable, the editor starts normally. Password entry is hidden; Ctrl+C cancels authentication and the editor remains available. **Kör med sudo…** runs in the built-in terminal and uses normal sudo authentication. **Keep sudo active for this session** runs `sudo -v` and refreshes the existing authorization with `sudo -n -v` every 45 seconds. Enter the password directly at the terminal prompt; Runcom does not store it. The computer’s sudo policy controls reuse and expiration; authentication cannot be reused across app restarts. Unchecking the option stops renewal and runs `sudo -k`. Closing or restarting the terminal stops renewal. No sudoers settings are changed.
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

## Desktop Pages switcher

Run `python3 pages_switcher.py` to switch GitHub Pages between `main` and `maintenance` (repository root). Uses Python and Tkinter only. On this Linux computer it is also installed in the application menu as **Runcom Pages**.

Create a fine-grained GitHub personal access token for `tvrdprijatelj/runcom` with **Pages: Read and write** and **Administration: Read and write**. Paste it into the app, click **Läs status**, then use the toggle. The token is kept in memory only; `GH_TOKEN` or `GITHUB_TOKEN` can also supply it. The app changes the Pages source setting; publication takes time. It refuses unexpected branches, directories or workflow-based publishing. After a connection failure, read status again before retrying.

API contract: https://docs.github.com/en/rest/pages/pages#update-information-about-a-github-pages-site

Tests: `python3 -m unittest discover -s tests -p test_pages_switcher.py -v`.

The Swedish and English download pages install the matching app language. Commands pass `--lang sv|en` (Bash) or `-Language sv|en` (PowerShell). Download buttons provide language-specific installers for current main. The selection is stored beside the app in `runcom-language` and retained by updates without a language argument. Older releases without English support reject English installation; use current main. The detailed help guide remains in Swedish.

## Updates in the app

Click **Uppdatera / Update** next to Help to check the latest published GitHub release. Confirm to install it, then restart Runcom. Checks and downloads run in the background. Scripts and language preferences are preserved. Older or diverged releases are not installed. Existing installations without version metadata need to run the updated installer once. Git checkouts must have no uncommitted changes.

## Uninstall

In an installed copy, open **Settings → Uninstall Runcom** (Swedish: **Inställningar → Avinstallera Runcom**). Confirm and save any unsaved work when prompted. Runcom stops its scripts and terminals, closes, and runs the bundled uninstaller in a separate process. Personal scripts are kept. This option works offline and requires an installation containing the bundled uninstaller; it refuses development checkouts.

Close Runcom and open **Avinstallera Runcom** from the Linux application menu or Windows Start menu. Confirm the displayed location with `y` and Enter. The installed launcher remembers custom installation paths. On macOS open **Uninstall Runcom.command** in the installation folder. These local launchers are included with new main installations and work offline.

If the shortcut is missing, use https://tvrdprijatelj.github.io/runcom/download_sv.html#uninstall (or download_en.html#uninstall). The page has OS/distribution-specific steps, copyable commands, a separate download button, custom-path instructions, outcome checks and troubleshooting. Linux choices include Arch, Ubuntu, Debian, Mint, Fedora, openSUSE and Alpine.

Manual Linux/macOS removal:

```sh
curl -fL https://raw.githubusercontent.com/tvrdprijatelj/runcom/main/uninstall.sh -o runcom-uninstall.sh
bash runcom-uninstall.sh
```

Windows PowerShell:

```powershell
Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/tvrdprijatelj/runcom/main/uninstall.ps1 -OutFile runcom-uninstall.ps1
powershell -ExecutionPolicy Bypass -File .\runcom-uninstall.ps1
```

Only installer-owned files, the virtual environment and matching shortcuts are removed. Personal scripts and extra files are preserved; shared system tools are left installed. For custom locations use `RUNCOM_INSTALL_DIR` (Bash) or `-InstallDir` (PowerShell). `--yes` / `-Yes` bypasses confirmation for automation.
