#!/usr/bin/env python3
"""Runcom – skapa, öppna, redigera och kör skriptfiler.

Fungerar på Linux, macOS och Windows.
  Linux/macOS: skal- och Python-skript. Sudo körs i den inbyggda terminalsessionen.
  Windows:     .bat/.cmd och .ps1. "Kör som admin" visar Windows egen UAC-ruta.

Start:  python3 runcom.py   (Windows: py runcom.py)
Kräver: Python 3.8+ med Tkinter (Debian/Ubuntu: sudo apt install python3-tk)
"""
import codecs
import json
import urllib.request
import urllib.parse
import urllib.error
import ctypes
import os
import queue
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import webbrowser
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
MOD = "Cmd" if IS_MAC else "Ctrl"

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
NEW_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)

DEFAULT_DIR = Path.home() / "skript"
DEFAULT_EXT = ".bat" if IS_WIN else ".sh"
HELP_URL = "https://tvrdprijatelj.github.io/runcom/help.html"

GITHUB_API = "https://api.github.com/repos/tvrdprijatelj/runcom"


# Run outside the installation so Windows can remove the venv after Runcom exits.
UNINSTALL_WORKER = r"""
import os, pathlib, shutil, subprocess, sys, tkinter as tk
from tkinter import messagebox
work, folder, language, parent_pid = sys.argv[1:]
try:
    # EOF arrives when the app exits and releases the pipe, including its venv.
    if sys.stdin.read() != 'uninstall':
        raise SystemExit(0)
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, int(parent_pid))
        if handle:
            try:
                kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
            finally:
                kernel.CloseHandle(handle)
    env = os.environ.copy()
    env['RUNCOM_INSTALL_DIR'] = folder
    env['PATH'] = str(pathlib.Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    script = str(pathlib.Path(work) / ('uninstall.ps1' if os.name == 'nt' else 'uninstall.sh'))
    command = (['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script,
                '-InstallDir', folder, '-Yes'] if os.name == 'nt' else ['bash', script, '--yes'])
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    try:
        result = subprocess.run(command, cwd=work, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, **options)
    except Exception as error:
        result = subprocess.CompletedProcess(command, 1, str(error).encode('utf-8'))
    root = tk.Tk()
    root.withdraw()
    title = 'Avinstallera Runcom' if language == 'sv' else 'Uninstall Runcom'
    if result.returncode:
        log = pathlib.Path(work) / 'uninstall.log'
        log.write_bytes(result.stdout)
        messagebox.showerror(title, ('Avinstallationen misslyckades. Logg: ' if language == 'sv'
                             else 'Uninstallation failed. Log: ') + str(log), parent=root)
    else:
        messagebox.showinfo(title, ('Runcom har avinstallerats. Dina egna skript finns kvar.'
                            if language == 'sv' else 'Runcom was uninstalled. Your own scripts are kept.'), parent=root)
    root.destroy()
finally:
    if 'result' not in locals() or result.returncode == 0:
        shutil.rmtree(work, ignore_errors=True)
"""


def launch_uninstaller(folder, language):
    folder = Path(folder).resolve()
    script = folder / ('uninstall.ps1' if IS_WIN else 'uninstall.sh')
    if (folder / '.git').exists() or not (folder / 'runcom-revision').is_file() or not script.is_file():
        raise ValueError('Avinstallation kräver en installerad kopia av Runcom. Kör installationsskriptet igen först.'
                         if language == 'sv' else
                         'Uninstallation requires an installed copy of Runcom. Run the installer again first.')
    work = Path(tempfile.mkdtemp(prefix='runcom-uninstall-'))
    try:
        shutil.copyfile(script, work / script.name)
        worker = work / 'worker.py'
        worker.write_text(UNINSTALL_WORKER, encoding='utf-8')
        python = getattr(sys, '_base_executable', None) or sys.executable
        options = {'creationflags': NO_WINDOW} if IS_WIN else {'start_new_session': True}
        process = subprocess.Popen([python, str(worker), str(work), str(folder), language, str(os.getpid())],
                                   cwd=str(work), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, **options)
        process.stdin.write(b'uninstall')
        process.stdin.flush()
        return process  # Keep stdin open until the application process exits.
    except Exception:
        if 'process' in locals():
            process.terminate()
            process.wait()
        shutil.rmtree(str(work), ignore_errors=True)
        raise


def github_json(endpoint):
    request = urllib.request.Request(GITHUB_API + endpoint, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "Runcom-updater"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def current_revision(folder):
    if (folder / ".git").exists():
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=str(folder)):
            raise ValueError("Spara och checka in lokala kodändringar först. / Commit local changes first.")
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(folder), text=True).strip()
    marker = folder / "runcom-revision"
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip()
    raise ValueError("Versionsinformation saknas. Kör den nya installationsfilen en gång först. / Run the new installer once to record the installed version.")


def available_release(folder):
    revision = current_revision(folder)
    try:
        release = github_json("/releases/latest")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    tag = urllib.parse.quote(release["tag_name"], safe="")
    target = github_json("/commits/" + tag)["sha"]
    comparison = github_json("/compare/" + urllib.parse.quote(revision, safe="") + "..." + target)
    if comparison["status"] != "ahead":
        return None
    # Pin the download to the compared commit, even if the tag moves later.
    release["revision"] = target
    return release


def install_release(folder, release):
    # Fetch all files before touching the installation; keep backups for rollback.
    revision = urllib.parse.quote(release["revision"], safe="")
    files = {}
    for name in ("runcom.py", "help.html", "help.css", "style.css", "runcom.png", "runcom.ico",
                 "uninstall.sh", "uninstall.ps1"):
        url = "https://raw.githubusercontent.com/tvrdprijatelj/runcom/" + revision + "/" + name
        request = urllib.request.Request(url, headers={"User-Agent": "Runcom-updater"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(10 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as error:
            if error.code == 404 and name != "runcom.py":
                continue
            raise
        if len(data) > 10 * 1024 * 1024:
            raise ValueError("Release file is too large")
        files[name] = data
    compile(files["runcom.py"], "runcom.py", "exec")
    files["runcom-revision"] = release["revision"].encode("utf-8")
    backups = {}
    def replace(path, data):
        fd, temporary = tempfile.mkstemp(prefix=".runcom-update-", dir=str(folder))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if path.exists():
                os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    try:
        for name, data in files.items():
            path = folder / name
            backups[name] = path.read_bytes() if path.exists() else None
            replace(path, data)
    except Exception:
        for name, data in backups.items():
            if data is None:
                (folder / name).unlink()
            else:
                replace(folder / name, data)
        raise


def installed_language():
    try:
        value = Path(__file__).with_name("runcom-language").read_text(encoding="utf-8").strip()
    except OSError:
        value = "sv"
    return value if value in ("sv", "en") else "sv"


LANGUAGE = installed_language()
TRANSLATIONS = {
    'Inställningar': 'Settings',
    'Avinstallera Runcom': 'Uninstall Runcom',
    'Stäng': 'Close',
    'Appen och dess genvägar tas bort. Dina egna skript sparas.': 'The app and its shortcuts are removed. Your own scripts are kept.',
    'Avinstallera Runcom och stäng appen? Pågående skript och terminaler stoppas. Dina egna skript sparas.': 'Uninstall Runcom and close the app? Running scripts and terminals will be stopped. Your own scripts are kept.',
    'Kunde inte starta avinstallationen': 'Could not start uninstallation',
    'Windows-kommandon: skriv på raden och tryck Enter. Interaktiva konsolprogram körs med F6.': 'Windows commands: type on the input line and press Enter. Use F6 for interactive console programs.',
    '▶ Kör vald fil': '▶ Run selected file',
    'Öppna och kör…': 'Open and run…',
    'Välj en fil i listan först.': 'Select a file in the list first.',
    'Skript': 'Scripts',
    'Terminal': 'Terminal',
    'Terminal (F7)': 'Terminal (F7)',
    'Terminalen är stängd. Starta om den.': 'The terminal is closed. Restart it.',
    'Starta om terminal': 'Restart terminal',
    'Rensa terminalen': 'Clear terminal',
    'Håll sudo aktivt i sessionen': 'Keep sudo active for this session',
    'Sudo: inte aktivt': 'Sudo: inactive',
    'Sudo: väntar på lösenord i terminalen': 'Sudo: waiting for password in the terminal',
    'Sudo: aktivt under appsessionen': 'Sudo: active for the app session',
    'Sudo: autentiseringen avbröts eller löpte ut': 'Sudo: authentication was cancelled or expired',
    'Aktivera sudo': 'Enable sudo',
    'Sudo-lösenordet skrivs direkt i terminalen och sparas aldrig av Runcom. Systemets sudo-behörighet hålls aktiv medan appen är öppen.': 'Enter the sudo password directly in the terminal. Runcom never stores it. The system sudo authorization is kept active while the app is open.',
    'Kommandoterminal · Ctrl+C avbryter · Ctrl+Shift+V klistrar in. Helskärmsprogram körs med F6.': 'Command terminal · Ctrl+C interrupts · Ctrl+Shift+V pastes. Use F6 for full-screen programs.',
    'Kunde inte starta terminalen': 'Could not start the terminal',
    'Ny terminalsession': 'New terminal session',
    'Terminalen är upptagen': 'Terminal is busy',
    'Avsluta det pågående kommandot först.': 'Finish the current command first.',
    'Klistra in flera rader': 'Paste multiple lines',
    'Inklistrade radbrytningar kan köra kommandon direkt. Fortsätt?': 'Pasted newlines can run commands immediately. Continue?',
    'Terminalsessionen avslutades. Starta om för att fortsätta.': 'The terminal session ended. Restart it to continue.',

    '@echo off\nrem Skriv dina kommandon här\necho Hej fran %COMPUTERNAME%!\n': '@echo off\nrem Write your commands here\necho Hello from %COMPUTERNAME%!\n',
    '# Skriv dina kommandon här\nWrite-Host "Hej från $env:COMPUTERNAME!"\n': '# Write your commands here\nWrite-Host "Hello from $env:COMPUTERNAME!"\n',
    'set -euo pipefail\n\n# Skriv dina kommandon här\necho "Hej från $(hostname)!"\n': 'set -euo pipefail\n\n# Write your commands here\necho "Hello from $(hostname)!"\n',
    '#!/usr/bin/env python3\n\nprint("Hej från Runcom!")\n': '#!/usr/bin/env python3\n\nprint("Hello from Runcom!")\n',
    'Kunde inte öppna hjälpen': 'Could not open help',
    '(ingen fil)': '(no file)',
    'Osparade ändringar': 'Unsaved changes',
    'Vill du spara ändringarna först?': 'Do you want to save your changes first?',
    'backup.bat, backup.ps1 eller hello.py': 'backup.bat, backup.ps1 or hello.py',
    'backup.sh eller hello.py': 'backup.sh or hello.py',
    'Ny skriptfil': 'New script file',
    'Filen togs bort': 'File deleted',
    'Kör…': 'Running…',
    "; echo; printf '[Klart - tryck Enter för att stänga] '; read -r _x": "; echo; printf '[Done - press Enter to close] '; read -r _x",
    'Skriptets shebang saknar ett program.': 'The script shebang is missing an interpreter.',
    'Hjälp': 'Help (Swedish)',
    'Spara som…': 'Save as…',
    'Ta bort': 'Delete',
    'Byt mapp…': 'Change folder…',
    '▶ Kör här (F5)': '▶ Run here (F5)',
    '■ Stoppa': '■ Stop',
    'Redo · Skapa en fil med Ctrl+N eller öppna med Ctrl+O': 'Ready · Create a file with Ctrl+N or open with Ctrl+O',
    'Öppna hjälpen manuellt i din webbläsare:\n\n': 'Open the help manually in your browser:\n\n',
    'Filnamn (t.ex. ': 'Filename (e.g. ',
    'Finns redan': 'Already exists',
    'Skapade ': 'Created ',
    'Öppna skriptfil': 'Open script file',
    'Öppnade ': 'Opened ',
    'Sparade ': 'Saved ',
    'Spara som': 'Save as',
    'Välj mapp': 'Choose folder',
    'Filtypen stöds inte. Använd ett skal- eller Python-skript (Windows: .bat, .cmd, .ps1 eller .py).\n': 'Unsupported file type. Use a shell or Python script (Windows: .bat, .cmd, .ps1 or .py).\n',
    '\n[Stoppad av användaren]\n': '\n[Stopped by the user]\n',
    'Filtypen stöds inte. Välj ett skal- eller Python-skript.': 'Unsupported file type. Choose a shell or Python script.',
    'Admin-körningen avbröts eller misslyckades': 'Administrator launch was cancelled or failed',
    'Byt namn på batchfilen eller mappen: %, radbrytningar och citattecken stöds inte.': 'Rename the batch file or folder: %, newlines and quotes are not supported.',
    'PowerShell hittades inte.': 'PowerShell was not found.',
    'Kunde inte skapa skriptmappen': 'Could not create the scripts folder',
    'Ny (': 'New (',
    'Öppna… (': 'Open… (',
    'Spara (': 'Save (',
    ' finns redan i mappen.': ' already exists in the folder.',
    'Fel': 'Error',
    'Kunde inte öppna': 'Could not open',
    'Kunde inte spara': 'Could not save',
    'Ta bort ': 'Delete ',
    ' permanent?': ' permanently?',
    'Kunde inte köra skriptet': 'Could not run the script',
    'Kommandot sudo hittades inte.': 'The sudo command was not found.',
    'Startade ': 'Started ',
    ' som administratör': ' as administrator',
    'Runcom kunde inte starta det grafiska gränssnittet: ': 'Runcom could not start the graphical interface: ',
    'Skriv. Kör. Se resultatet.': 'Write. Run. See the result.',
    'Kör i terminal (F6)': 'Run in terminal (F6)',
    'Kör med sudo (F8)': 'Run with sudo (F8)',
    'Sök filnamn · dubbelklicka för att öppna': 'Search filenames · double-click to open',
    'UTDATA': 'OUTPUT',
    'Rensa': 'Clear',
    'Behöver skriptet inmatning? Använd Kör i terminal.': 'Does your script need input? Use Run in terminal.',
    'Kunde inte läsa mappen: ': 'Could not read the folder: ',
    'Filen innehåller tecken som inte finns i batchfilernas teckentabell (': 'The file contains characters not supported by the batch encoding (',
    '). Ta bort dem eller använd en .ps1-fil.': '). Remove them or use a .ps1 file.',
    'Kunde inte starta: ': 'Could not start: ',
    'Filtypen stöds inte': 'Unsupported file type',
    'Använd .bat, .cmd, .ps1 eller .py.': 'Use .bat, .cmd, .ps1 or .py.',
    ' i ett konsolfönster': ' in a console window',
    'Ingen terminal hittades': 'No terminal found',
    'Installera t.ex. gnome-terminal, konsole eller xterm, eller använd ”Kör här”.': 'Install gnome-terminal, konsole or xterm, or use Run here.',
    'Kör som admin': 'Run as administrator',
    'Kör med sudo…': 'Run with sudo…',
    'Filen har ändrats': 'File changed',
    'Filen har ändrats eller tagits bort utanför Runcom.\nVill du skriva över den med innehållet i editorn?': 'The file was changed or deleted outside Runcom.\nDo you want to overwrite it with the editor contents?',
    'Kunde inte läsa utdata: ': 'Could not read output: ',
    ' i Terminal': ' in Terminal',
    '\n[Avslutades med kod ': '\n[Finished with exit code ',
    'Klar (kod ': 'Done (exit code ',
    ' i ': ' in ',
}


def tr(text):
    return TRANSLATIONS.get(text, text) if LANGUAGE == "en" else text


SHEBANG = "#!/usr/bin/env bash\n"
TPL_UNIX = SHEBANG + tr('set -euo pipefail\n\n# Skriv dina kommandon här\necho "Hej från $(hostname)!"\n')
TPL_BAT = tr('@echo off\nrem Skriv dina kommandon här\necho Hej fran %COMPUTERNAME%!\n')
TPL_PS1 = tr('# Skriv dina kommandon här\nWrite-Host "Hej från $env:COMPUTERNAME!"\n')

# Linux: (program, argument som föregår kommandot)
TERMINALS = [
    ("x-terminal-emulator", ["-e"]),
    ("gnome-terminal", ["--"]),
    ("konsole", ["-e"]),
    ("xfce4-terminal", ["-x"]),
    ("kitty", []),
    ("alacritty", ["-e"]),
    ("xterm", ["-e"]),
]


def oem_encoding():
    """Teckentabellen som cmd/PowerShell använder för utdata (Windows). Annars UTF-8."""
    if IS_WIN:
        try:
            cp = ctypes.windll.kernel32.GetOEMCP()
            return "utf-8" if cp == 65001 else f"cp{cp}"
        except Exception:
            return "cp850"
    return "utf-8"


OEM = oem_encoding()


def file_encoding(path):
    """Vilken teckenkodning filen ska läsas/sparas med."""
    if IS_WIN:
        ext = path.suffix.lower()
        if ext in (".bat", ".cmd"):
            return OEM          # cmd läser batchfiler i OEM-tabellen
        if ext == ".ps1":
            return "utf-8-sig"  # PowerShell 5.1 kräver BOM för UTF-8
    return "utf-8"


def template_for(name):
    ext = Path(name).suffix.lower()
    if ext == ".py":
        return tr('#!/usr/bin/env python3\n\nprint("Hej från Runcom!")\n')
    if ext == ".ps1":
        return TPL_PS1
    if ext in (".bat", ".cmd"):
        return TPL_BAT
    return TPL_BAT if IS_WIN else TPL_UNIX


def contains_sudo_command(text):
    """Recognize explicit sudo commands in ordinary shell command lists."""
    for line in text.splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=';&|()')
        lexer.whitespace_split = True
        command_start = True
        try:
            for token in lexer:
                if token and all(char in ';&|()' for char in token):
                    command_start = True
                elif command_start:
                    if token in ('if', 'then', 'elif', 'else', 'do', '!', '{'):
                        continue
                    if '=' in token and token.split('=', 1)[0].isidentifier():
                        continue
                    if token in ('sudo', '/usr/bin/sudo', '/bin/sudo'):
                        return True
                    command_start = False
        except ValueError:
            continue  # An unfinished line is left to the script interpreter.
    return False


def atomic_write(path, text, encoding, executable=False, exclusive=False):
    """Encode before touching disk; replace the destination only after a full write."""
    data = text.encode(encoding)
    path = Path(path)
    # Follow an existing symlink without replacing the link itself.
    target = path.resolve() if path.is_symlink() else path
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o600
    if executable and not IS_WIN:
        mode |= stat.S_IXUSR
    fd, temp_name = tempfile.mkstemp(prefix=".runcom-", dir=str(target.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        temp.chmod(mode)
        if exclusive:
            # Hard-link creation fails atomically if another file already exists.
            os.link(str(temp), str(target))
        else:
            os.replace(str(temp), str(target))
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
    return data


def python_executable():
    executable = Path(sys.executable)
    if IS_WIN and executable.name.lower() == "pythonw.exe":
        return str(executable.with_name("python.exe"))
    return str(executable)


def script_command(path, keep_open=False):
    path = Path(path).absolute()
    ext = path.suffix.lower()
    if ext == ".py":
        return [python_executable(), "-u", str(path)]
    if IS_WIN:
        if ext in (".bat", ".cmd"):
            if any(char in str(path) for char in ('%', '\r', '\n', '"')):
                raise ValueError(tr('Byt namn på batchfilen eller mappen: %, radbrytningar och citattecken stöds inte.'))
            exe = os.environ.get("COMSPEC", "cmd.exe")
            # cmd /s requires an extra quote pair; list2cmdline on the whole
            # command would escape quotes using rules cmd does not understand.
            flag = "/k" if keep_open else "/c"
            return subprocess.list2cmdline([exe]) + ' /d /v:off /s ' + flag + ' ""' + str(path) + '""'
        if ext == ".ps1":
            ps = shutil.which("pwsh") or shutil.which("powershell")
            if not ps:
                raise ValueError(tr('PowerShell hittades inte.'))
            args = [ps, "-NoProfile"]
            if keep_open:
                args.append("-NoExit")
            return args + ["-ExecutionPolicy", "Bypass", "-File", str(path)]
        return None
    # Respect a script's interpreter even when it has a .sh extension.
    try:
        with path.open(encoding="utf-8-sig") as source:
            first = source.readline(4096).strip()
    except UnicodeError:
        return None
    if first.startswith("#!"):
        interpreter = shlex.split(first[2:])
        if not interpreter:
            raise ValueError(tr('Skriptets shebang saknar ett program.'))
        return interpreter + [str(path)]
    if ext in (".sh", ".bash"):
        return ["bash", str(path)]
    return None


class TerminalSession:
    """Persistent user shell; Unix input goes directly to a real pseudo-terminal."""
    def __init__(self, folder, env):
        self.events = queue.Queue(maxsize=256)
        self.closed = threading.Event()
        self.fd = None
        if IS_WIN:
            self.proc = subprocess.Popen(
                [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/q'], cwd=str(folder),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=env, creationflags=NO_WINDOW)
        else:
            import pty
            master, slave = pty.openpty()
            env = dict(env, TERM='dumb', PS1='$ ', PROMPT_COMMAND='')
            shell = shutil.which('bash') or '/bin/sh'
            try:
                self.proc = subprocess.Popen(
                    [python_executable(), str(Path(__file__).resolve()), '--terminal-child', shell],
                    cwd=str(folder), stdin=slave, stdout=slave, stderr=slave,
                    env=env, start_new_session=True, close_fds=True)
            except BaseException:
                os.close(master)
                raise
            finally:
                os.close(slave)
            self.fd = master
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _emit(self, kind, value):
        while not self.closed.is_set():
            try:
                self.events.put((kind, value), timeout=0.1)
                return
            except queue.Full:
                pass

    def _read(self):
        decoder = codecs.getincrementaldecoder(OEM if IS_WIN else 'utf-8')(errors='replace')
        try:
            source = self.proc.stdout.fileno() if IS_WIN else self.fd
            while not self.closed.is_set():
                data = os.read(source, 4096)
                if not data:
                    break
                self._emit('text', decoder.decode(data))
        except OSError:
            pass  # Unix PTYs report EIO when the shell exits.
        finally:
            self._emit('text', decoder.decode(b'', final=True))
            self._emit('done', self.proc.wait())

    def send(self, text):
        if self.closed.is_set() or self.proc.poll() is not None:
            raise OSError(tr('Terminalen är stängd. Starta om den.'))
        data = text.encode(OEM if IS_WIN else 'utf-8')
        if IS_WIN:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        else:
            while data:
                data = data[os.write(self.fd, data):]

    def idle(self):
        if self.proc.poll() is not None:
            return False
        if IS_WIN:
            return True
        try:
            return os.tcgetpgrp(self.fd) in (0, self.proc.pid)
        except OSError:
            return False

    def resize(self, rows, columns):
        if not IS_WIN and not self.closed.is_set():
            import fcntl
            import struct
            import termios
            try:
                fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))
            except OSError:
                pass

    def close(self):
        if self.closed.is_set():
            return
        self.closed.set()
        if IS_WIN:
            if self.proc.poll() is None:
                subprocess.run(['taskkill', '/PID', str(self.proc.pid), '/T', '/F'],
                               capture_output=True, creationflags=NO_WINDOW)
            self.proc.stdin.close()
        else:
            try:
                foreground = os.tcgetpgrp(self.fd)
                if (foreground > 0 and foreground != self.proc.pid
                        and os.getsid(foreground) == self.proc.pid):
                    os.killpg(foreground, signal.SIGHUP)
            except (OSError, ProcessLookupError):
                pass
            try:
                os.killpg(self.proc.pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
            os.close(self.fd)
        try:
            self.proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=1)
        if IS_WIN:
            self.proc.stdout.close()


class TerminalPanel(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.session = None
        self.escape = ''
        self.poll_id = None
        self.keep_sudo = tk.BooleanVar(value=False)
        self.sudo_active = False
        self.sudo_state = tk.StringVar(value=tr('Sudo: inte aktivt'))
        self._sudo_control_buffer = ''
        toolbar = tk.Frame(self)
        toolbar.pack(fill='x')
        tk.Button(toolbar, text=tr('Starta om terminal'), command=self.restart).pack(side='left')
        self.btn_clear = tk.Button(toolbar, text=tr('Rensa terminalen'), command=self.clear)
        self.btn_clear.pack(side='right')
        if not IS_WIN:
            tk.Checkbutton(toolbar, text=tr('Håll sudo aktivt i sessionen'),
                           variable=self.keep_sudo, command=self.toggle_sudo).pack(side='left')
            tk.Label(toolbar, textvariable=self.sudo_state, fg='#a5b5cc').pack(side='left', padx=10)
        hint = ('Windows-kommandon: skriv på raden och tryck Enter. Interaktiva konsolprogram körs med F6.' if IS_WIN else
                'Kommandoterminal · Ctrl+C avbryter · Ctrl+Shift+V klistrar in. Helskärmsprogram körs med F6.')
        tk.Label(self, text=tr(hint),
                 anchor='w', wraplength=750).pack(fill='x', padx=8)
        body = tk.Frame(self)
        body.pack(fill='both', expand=True)
        scroll = tk.Scrollbar(body)
        scroll.pack(side='right', fill='y')
        self.display = tk.Text(body, state='disabled', wrap='char', font=app.mono,
                               bg='#111b29', fg='#e4ecf7', insertbackground='#77c7ff',
                               yscrollcommand=scroll.set, takefocus=True)
        self.display.pack(fill='both', expand=True)
        scroll.config(command=self.display.yview)
        self.display.mark_set('terminal_cursor', '1.0')
        self.display.mark_gravity('terminal_cursor', 'right')
        if IS_WIN:
            self.line = tk.Entry(self, bg='#111b29', fg='#e4ecf7', insertbackground='white')
            self.line.pack(fill='x')
            self.line.bind('<Return>', self.send_line)
        else:
            self.display.bind('<KeyPress>', self.key)
            self.display.bind('<Control-Shift-V>', self.paste)
            self.display.bind('<Control-Shift-v>', self.paste)
            self.display.bind('<<Paste>>', self.paste)
            self.display.bind('<Button-2>', lambda e: 'break')

    def start(self):
        if self.session is None:
            try:
                self.session = TerminalSession(self.app.folder, self.app._run_env())
            except OSError as error:
                messagebox.showerror(tr('Kunde inte starta terminalen'), str(error), parent=self)
                return False
            self.poll_id = self.after(30, self.poll)
        return self.session.proc.poll() is None

    def focus_terminal(self):
        (self.line if IS_WIN else self.display).focus_set()

    def restart(self):
        self.close()
        self._set_sudo_state(False)
        self._sudo_control_buffer = ''
        self.escape = ''
        self.render('\n' + tr('Ny terminalsession') + '\n')
        self.start()
        self.focus_terminal()

    def clear(self, focus=True):
        self.escape = ''
        self.display.config(state='normal')
        self.display.delete('1.0', 'end')
        self.display.mark_set('terminal_cursor', '1.0')
        self.display.mark_gravity('terminal_cursor', 'right')
        self.display.config(state='disabled')
        if IS_WIN:
            self.line.delete(0, 'end')
        if focus:
            self.focus_terminal()

    def close(self):
        if self.poll_id is not None:
            self.after_cancel(self.poll_id)
            self.poll_id = None
        if self.session is not None:
            self.session.close()
            self.session = None

    def send(self, text):
        try:
            if self.start():
                self.session.send(text)
        except OSError as error:
            messagebox.showerror(tr('Fel'), str(error), parent=self)

    def command(self, command):
        if not self.start():
            return False
        if not self.session.idle():
            messagebox.showinfo(tr('Terminalen är upptagen'),
                                tr('Avsluta det pågående kommandot först.'), parent=self)
            return False
        if IS_WIN:
            self.render(command + '\r\n')
        self.send(command + ('\r\n' if IS_WIN else '\n'))
        self.focus_terminal()
        return True

    def send_line(self, _event=None):
        text = self.line.get()
        self.line.delete(0, 'end')
        self.render(text + '\r\n')
        self.send(text + '\r\n')
        return 'break'

    def key(self, event):
        if event.state & 4 and event.keysym.lower() == 'c' and event.state & 1:
            try:
                self.clipboard_clear()
                self.clipboard_append(self.display.get('sel.first', 'sel.last'))
            except tk.TclError:
                pass
            return 'break'
        keys = {'Return': '\r', 'BackSpace': '\x7f', 'Tab': '\t', 'Escape': '\x1b',
                'Up': '\x1b[A', 'Down': '\x1b[B', 'Right': '\x1b[C', 'Left': '\x1b[D',
                'Home': '\x01', 'End': '\x05', 'Delete': '\x1b[3~'}
        text = keys.get(event.keysym, event.char)
        if text:
            self.send(text)
        return 'break'

    def paste(self, _event=None):
        try:
            text = self.clipboard_get().replace('\r\n', '\n').replace('\r', '\n')
            if '\n' in text:
                if not messagebox.askokcancel(tr('Klistra in flera rader'),
                        tr('Inklistrade radbrytningar kan köra kommandon direkt. Fortsätt?'), parent=self):
                    return 'break'
            self.send(text)
        except tk.TclError:
            pass
        return 'break'

    def _sudo_keeper(self):
        refresh = ("import os, subprocess, sys, time; parent = os.getppid(); "
                   "\nwhile os.getppid() == parent:\n"
                   " time.sleep(45)\n"
                   " if os.getppid() != parent: break\n"
                   " if subprocess.call([sys.argv[1], '-n', '-v'], "
                   "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                   "stderr=subprocess.DEVNULL) != 0:\n"
                   "  sys.stdout.write('\\x1dRUNCOM_SUDO_EXPIRED\\x1d'); sys.stdout.flush(); break\n")
        return shlex.join([python_executable(), '-c', refresh, shutil.which('sudo')])

    def authorize_sudo(self, fresh=False, after=None):
        """Validate sudo in this PTY, keep it active, then optionally run a command."""
        if not shutil.which('sudo'):
            self.keep_sudo.set(False)
            messagebox.showerror(tr('Fel'), tr('Kommandot sudo hittades inte.'), parent=self)
            return False
        was_active = self.sudo_active is True
        self._set_sudo_state(None)
        stop_keeper = ('if [ -n "${__runcom_sudo_keeper:-}" ]; then '
                       'kill "$__runcom_sudo_keeper" 2>/dev/null; '
                       'wait "$__runcom_sudo_keeper" 2>/dev/null; '
                       'unset __runcom_sudo_keeper; fi')
        # -k and -v are separate on purpose: sudo -k -v may authenticate
        # without updating the cached credential on current sudo versions.
        validation = "sudo -k && sudo -v" if fresh else "sudo -v"
        success = ("printf '\\035RUNCOM_SUDO_ACTIVE\\035'; { "
                   + self._sudo_keeper() + " & __runcom_sudo_keeper=$!; "
                   "trap 'kill \"$__runcom_sudo_keeper\" 2>/dev/null' EXIT; }")
        if after:
            success += "; " + after
        command = (stop_keeper + "; if " + validation + "; then " + success
                   + "; else printf '\\035RUNCOM_SUDO_INACTIVE\\035'; fi")
        if not self.command(command):
            self._set_sudo_state(True if was_active else False)
            return False
        return True

    def revoke_sudo(self):
        command = ('if [ -n "${__runcom_sudo_keeper:-}" ]; then '
                   'kill "$__runcom_sudo_keeper" 2>/dev/null; '
                   'wait "$__runcom_sudo_keeper" 2>/dev/null; '
                   'unset __runcom_sudo_keeper; fi; sudo -k')
        if not self.command(command):
            self._set_sudo_state(True if self.sudo_active is True else False)
            return False
        self._set_sudo_state(False)
        return True

    def toggle_sudo(self, fresh=False):
        if self.keep_sudo.get():
            self.authorize_sudo(fresh=fresh)
        else:
            self.revoke_sudo()

    def _set_sudo_state(self, active):
        self.sudo_active = active
        if active is True:
            self.keep_sudo.set(True)
            self.sudo_state.set(tr('Sudo: aktivt under appsessionen'))
        elif active is None:
            self.keep_sudo.set(True)
            self.sudo_state.set(tr('Sudo: väntar på lösenord i terminalen'))
        else:
            self.keep_sudo.set(False)
            self.sudo_state.set(tr('Sudo: inte aktivt'))

    def _terminal_output(self, value):
        tokens = {
            '\x1dRUNCOM_SUDO_ACTIVE\x1d': True,
            '\x1dRUNCOM_SUDO_INACTIVE\x1d': 'expired',
            '\x1dRUNCOM_SUDO_EXPIRED\x1d': 'expired',
        }
        data = self._sudo_control_buffer + value
        self._sudo_control_buffer = ''
        while data:
            found = [(data.find(token), token, state) for token, state in tokens.items()
                     if data.find(token) >= 0]
            if found:
                position, token, state = min(found)
                self.render(data[:position])
                if state == 'expired':
                    self._set_sudo_state(False)
                    self.sudo_state.set(tr('Sudo: autentiseringen avbröts eller löpte ut'))
                else:
                    self._set_sudo_state(state)
                data = data[position + len(token):]
                continue
            held = max((size for token in tokens for size in range(1, len(token))
                        if data.endswith(token[:size])), default=0)
            self.render(data[:-held] if held else data)
            self._sudo_control_buffer = data[-held:] if held else ''
            break

    def poll(self):
        self.poll_id = None
        try:
            for _ in range(100):
                kind, value = self.session.events.get_nowait()
                if kind == 'text':
                    self._terminal_output(value)
                else:
                    self.render('\n' + tr('Terminalsessionen avslutades. Starta om för att fortsätta.') + '\n')
                    self._set_sudo_state(False)
                    return
        except queue.Empty:
            pass
        columns = max(20, self.display.winfo_width() // max(1, self.app.mono.measure('M')))
        rows = max(4, self.display.winfo_height() // max(1, self.app.mono.metrics('linespace')))
        self.session.resize(rows, columns)
        self.poll_id = self.after(30, self.poll)

    def render(self, text):
        # A bounded line terminal: CR redraw, backspace and erase-to-end-of-line.
        # TERM=dumb avoids advertising full-screen terminal capabilities.
        widget = self.display
        widget.config(state='normal')
        for char in text:
            if self.escape:
                self.escape += char
                if len(self.escape) == 2 and char != '[':
                    self.escape = ''
                elif len(self.escape) > 2 and ('@' <= char <= '~'):
                    if char == 'K':
                        widget.delete('terminal_cursor', 'terminal_cursor lineend')
                    self.escape = ''
                elif len(self.escape) > 64:
                    self.escape = ''
                continue
            if char == '\x1b':
                self.escape = char
            elif char == '\r':
                widget.mark_set('terminal_cursor', 'terminal_cursor linestart')
            elif char == '\n':
                widget.mark_set('terminal_cursor', 'terminal_cursor lineend')
                widget.insert('terminal_cursor', '\n')
            elif char == '\b':
                if widget.compare('terminal_cursor', '>', 'terminal_cursor linestart'):
                    widget.mark_set('terminal_cursor', 'terminal_cursor -1c')
            elif char >= ' ' or char == '\t':
                if widget.compare('terminal_cursor', '<', 'terminal_cursor lineend'):
                    widget.delete('terminal_cursor', 'terminal_cursor +1c')
                widget.insert('terminal_cursor', char)
        size = widget.count('1.0', 'end-1c', 'chars')
        if size and size[0] > 100_000:
            widget.delete('1.0', '1.0+20000c')
        widget.see('terminal_cursor')
        widget.config(state='disabled')


def terminal_child(shell):
    """Acquire the PTY after setsid, without preexec_fn in the threaded GUI."""
    import fcntl
    import termios
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    args = [shell, '--noprofile', '--norc', '-i'] if Path(shell).name == 'bash' else [shell, '-i']
    os.execv(shell, args)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Runcom")
        icon_dir = Path(__file__).resolve().parent
        try:
            self._app_icon = tk.PhotoImage(file=str(icon_dir / "runcom.png"))
            self.iconphoto(True, self._app_icon)
            if IS_WIN:
                self.iconbitmap(default=str(icon_dir / "runcom.ico"))
        except (tk.TclError, OSError):
            pass  # Older installations may not include the icon assets.
        self.geometry("1180x780")
        self.minsize(820, 540)

        self.mono = tkfont.nametofont("TkFixedFont").copy()
        self.mono.configure(size=11)
        self.mono_small = tkfont.nametofont("TkFixedFont").copy()
        self.mono_small.configure(size=10)

        self.folder = DEFAULT_DIR
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            messagebox.showerror(tr('Kunde inte skapa skriptmappen'), str(error), parent=self)
            self.folder = Path.home()
        self.current = None  # Path eller None
        self.proc = None
        self.q = queue.Queue(maxsize=256)
        self._closing = False
        self._stop_after = None
        self._snapshot = None
        self.files = []

        self._build_ui()
        self._bind_keys()
        self.refresh_list()
        self._update_title()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        if IS_MAC:
            self.createcommand("tk::mac::Quit", self.on_close)
        self._queue_after = self.after(50, self._drain_queue)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.configure(bg="#101722")
        self.option_add("*Font", "{Segoe UI} 10" if IS_WIN else "{DejaVu Sans} 10")
        self.option_add("*Background", "#182231")
        self.option_add("*Foreground", "#e4ecf7")
        self.option_add("*Button.Relief", "flat")
        self.option_add("*Button.BorderWidth", 0)
        self.option_add("*Button.Padx", 12)
        self.option_add("*Button.Pady", 7)
        self.option_add("*Button.ActiveBackground", "#30435e")
        self.option_add("*Button.ActiveForeground", "#ffffff")
        self.option_add("*Button.DisabledForeground", "#718198")
        header = tk.Frame(self, padx=18, pady=14, bg="#101722")
        header.pack(fill="x")
        tk.Label(header, text="runcom", font=("TkDefaultFont", 23, "bold"),
                 bg="#101722", fg="#77c7ff").pack(side="left")
        tk.Label(header, text=tr('Skriv. Kör. Se resultatet.'), bg="#101722",
                 fg="#a5b5cc", padx=20).pack(side="left")
        self.btn_settings = tk.Button(header, text=tr('Inställningar'), command=self.open_settings)
        self.btn_settings.pack(side="right", padx=6)
        self.btn_help = tk.Button(header, text=tr('Hjälp'), command=self.open_help,
                                  bg="#23334a", fg="#e4ecf7")
        self.btn_help.pack(side="right")
        self.btn_update = tk.Button(header, text="Uppdatera" if LANGUAGE == "sv" else "Update",
                                    command=self.check_update)
        self.btn_update.pack(side="right", padx=6)
        self.btn_terminal = tk.Button(header, text=tr('Terminal (F7)'), command=self.open_terminal)
        self.btn_terminal.pack(side="right", padx=6)
        bar = tk.Frame(self, padx=12, pady=6)
        bar.pack(fill="x")
        buttons = [
            ('{0}{1}+N)'.format(tr('Ny ('), MOD), self.new_file),
            ('{0}{1}+O)'.format(tr('Öppna… ('), MOD), self.open_file),
            ('{0}{1}+S)'.format(tr('Spara ('), MOD), self.save),
            (tr('Spara som…'), self.save_as),
            (tr('Ta bort'), self.delete_file),
            (tr('Byt mapp…'), self.change_folder),
        ]
        for text, cmd in buttons:
            tk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)

        runbar = tk.Frame(self, padx=12, pady=8)
        runbar.pack(fill="x")
        bar = runbar
        self.btn_run = tk.Button(bar, text=tr('▶ Kör här (F5)'), command=self.run_in_app,
                                 bg="#2e7d32", fg="white", activebackground="#1b5e20")
        self.btn_run.pack(side="left", padx=2)
        self.btn_stop = tk.Button(bar, text=tr('■ Stoppa'), command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=2)
        tk.Button(bar, text=tr('Kör i terminal (F6)'), command=self.run_in_terminal).pack(side="left", padx=2)

        tk.Frame(bar, width=20).pack(side="left")
        if IS_WIN:
            tk.Button(bar, text=tr('Kör som admin'), command=self.run_as_admin).pack(side="left", padx=2)
        else:
            tk.Button(bar, text=tr('Kör med sudo (F8)'), command=self.run_with_sudo).pack(side="left", padx=2)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        script_tab = tk.Frame(self.tabs)
        self.tabs.add(script_tab, text=tr('Skript'))
        self.terminal = TerminalPanel(self.tabs, self)
        self.tabs.add(self.terminal, text=tr('Terminal'))
        self.tabs.bind('<<NotebookTabChanged>>', self._tab_changed)
        main = tk.PanedWindow(script_tab, orient="horizontal", sashwidth=5)
        main.pack(fill="both", expand=True)

        # Vänster: fillista
        left = tk.Frame(main)
        self.folder_label = tk.Label(left, anchor="w", fg="#a5b5cc", text="")
        self.folder_label.pack(fill="x", padx=4, pady=(4, 0))
        lf = tk.Frame(left)
        lf.pack(fill="both", expand=True, padx=4, pady=4)
        sb = tk.Scrollbar(lf)
        sb.pack(side="right", fill="y")
        self.search = tk.StringVar()
        search = tk.Entry(left, textvariable=self.search, bg="#101722", fg="#e4ecf7",
                          insertbackground="white", relief="flat")
        search.pack(fill="x", padx=8, pady=8, before=lf)
        tk.Label(left, text=tr('Sök filnamn · dubbelklicka för att öppna'), fg="#a5b5cc",
                 font=("TkDefaultFont", 9)).pack(fill="x", before=search)
        self.search.trace_add("write", lambda *_: self.refresh_list())
        self.listbox = tk.Listbox(lf, yscrollcommand=sb.set, exportselection=False, activestyle="none",
                                 bg="#101722", fg="#e4ecf7", selectbackground="#285a85",
                                 selectforeground="white", relief="flat", borderwidth=0)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.config(command=self.listbox.yview)
        self.listbox.bind("<Double-Button-1>", self._on_list_open)
        self.listbox.bind("<Return>", self._on_list_open)
        self.listbox.bind('<Control-Return>', lambda e: self._shortcut(self.run_selected))
        self.btn_run_selected = tk.Button(left, text=tr('▶ Kör vald fil'),
                                         command=self.run_selected, bg="#2e7d32", fg="white")
        self.btn_run_selected.pack(fill="x", padx=8, pady=(8, 4))
        self.btn_open_run = tk.Button(left, text=tr('Öppna och kör…'), command=self.open_and_run)
        self.btn_open_run.pack(fill="x", padx=8, pady=(0, 8))
        main.add(left, minsize=180, width=230)

        # Höger: editor + utdata
        right = tk.PanedWindow(main, orient="vertical", sashwidth=5)
        main.add(right, minsize=400)

        ef = tk.Frame(right)
        esb = tk.Scrollbar(ef)
        esb.pack(side="right", fill="y")
        xsb = tk.Scrollbar(ef, orient="horizontal")
        xsb.pack(side="bottom", fill="x")
        self.editor = tk.Text(ef, wrap="none", undo=True, font=self.mono,
                              bg="#111b29", fg="#e4ecf7", insertbackground="#77c7ff",
                              selectbackground="#285a85", padx=16, pady=14,
                              relief="flat", xscrollcommand=xsb.set,
                              yscrollcommand=esb.set, tabs=("1c",))
        self.editor.pack(side="left", fill="both", expand=True)
        esb.config(command=self.editor.yview)
        xsb.config(command=self.editor.xview)
        self.editor.bind("<<Modified>>", lambda e: self._update_title())
        right.add(ef, minsize=150, height=400)

        of = tk.Frame(right)
        outputbar = tk.Frame(of)
        outputbar.pack(fill="x")
        tk.Label(outputbar, text=tr('UTDATA'), anchor="w", padx=10).pack(side="left")
        tk.Button(outputbar, text=tr('Rensa'), command=self.clear_output).pack(side="right")
        tk.Label(outputbar, text=tr('Behöver skriptet inmatning? Använd Kör i terminal.'),
                 fg="#a5b5cc", font=("TkDefaultFont", 9)).pack(side="left", padx=12)
        osb = tk.Scrollbar(of)
        osb.pack(side="right", fill="y")
        self.output = tk.Text(of, height=10, wrap="char", state="disabled", bg="#1e1e1e", fg="#dcdcdc",
                              font=self.mono_small, yscrollcommand=osb.set)
        self.output.pack(side="left", fill="both", expand=True)
        osb.config(command=self.output.yview)
        self.output.tag_config("info", foreground="#6cb6ff")
        self.output.tag_config("err", foreground="#ff7b72")
        right.add(of, minsize=80)

        self.status = tk.Label(self, anchor="w", padx=14, pady=8, bg="#101722", fg="#a5b5cc",
                               text=tr('Redo · Skapa en fil med Ctrl+N eller öppna med Ctrl+O'))
        self.status.pack(fill="x", side="bottom")

    def _tab_changed(self, _event=None):
        if self.tabs.select() == str(self.terminal):
            self.terminal.start()
            self.terminal.focus_terminal()

    def startup_sudo(self):
        """Authenticate in the same PTY used for subsequent sudo commands."""
        self.activate_sudo(fresh=True)

    def activate_sudo(self, show_error=False, fresh=False):
        """Request sudo in the app PTY; sudo itself owns the password prompt."""
        if IS_WIN or self._closing:
            return
        if not shutil.which('sudo'):
            if show_error:
                messagebox.showerror(tr('Fel'), tr('Kommandot sudo hittades inte.'), parent=self)
            return
        self.open_terminal()
        self.terminal.keep_sudo.set(True)
        self.terminal.toggle_sudo(fresh=fresh)

    def open_terminal(self):
        self.tabs.select(self.terminal)
        self.terminal.start()
        self.terminal.focus_terminal()

    def open_settings(self):
        existing = getattr(self, '_settings_window', None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return
        window = self._settings_window = tk.Toplevel(self)
        window.title(tr('Inställningar'))
        window.transient(self)
        window.resizable(False, False)
        frame = tk.Frame(window, padx=24, pady=20)
        frame.pack(fill="both", expand=True)
        if not IS_WIN:
            def enable_sudo():
                window.destroy()
                self.activate_sudo(show_error=True)
            tk.Label(frame, text='Sudo', font=('TkDefaultFont', 12, 'bold')).pack(anchor='w')
            tk.Label(frame, text=tr('Sudo-lösenordet skrivs direkt i terminalen och sparas aldrig av Runcom. Systemets sudo-behörighet hålls aktiv medan appen är öppen.'),
                     wraplength=380, justify='left').pack(anchor='w', pady=(8, 4))
            tk.Label(frame, textvariable=self.terminal.sudo_state, fg='#a5b5cc').pack(anchor='w')
            tk.Button(frame, text=tr('Aktivera sudo'), command=enable_sudo).pack(anchor='w', pady=(8, 18))
            ttk.Separator(frame).pack(fill='x', pady=(0, 18))
        tk.Label(frame, text=tr('Avinstallera Runcom'), font=('TkDefaultFont', 12, 'bold')).pack(anchor='w')
        tk.Label(frame, text=tr('Appen och dess genvägar tas bort. Dina egna skript sparas.'),
                 wraplength=380, justify='left').pack(anchor='w', pady=12)
        tk.Button(frame, text=tr('Avinstallera Runcom'), command=self.uninstall_app,
                  bg='#8b3030', fg='white').pack(anchor='w')
        tk.Button(frame, text=tr('Stäng'), command=window.destroy).pack(anchor='e', pady=(16, 0))

    def uninstall_app(self):
        if not messagebox.askyesno(tr('Avinstallera Runcom'),
                tr('Avinstallera Runcom och stäng appen? Pågående skript och terminaler stoppas. Dina egna skript sparas.'),
                parent=self, default='no'):
            return
        if not self._confirm_discard():
            return
        try:
            self._uninstall_process = launch_uninstaller(Path(__file__).resolve().parent, LANGUAGE)
        except (OSError, ValueError) as error:
            messagebox.showerror(tr('Kunde inte starta avinstallationen'), str(error), parent=self)
            return
        self.on_close(confirm=False)

    def check_update(self):
        self.btn_update.config(state="disabled")
        self._update_result = queue.Queue()
        def worker():
            try:
                result = available_release(Path(__file__).resolve().parent)
                self._update_result.put(("checked", result))
            except Exception as error:
                self._update_result.put(("error", str(error)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_update)

    def _poll_update(self):
        try:
            kind, value = self._update_result.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_update)
            return
        title = "Uppdatering" if LANGUAGE == "sv" else "Update"
        if kind == "checked" and value:
            prompt = (("Installera release {}? Starta om appen efter uppdateringen.")
                      if LANGUAGE == "sv" else "Install release {}? Restart the app after updating.")
            if messagebox.askyesno(title, prompt.format(value["tag_name"]), parent=self):
                def worker():
                    try:
                        install_release(Path(__file__).resolve().parent, value)
                        self._update_result.put(("installed", None))
                    except Exception as error:
                        self._update_result.put(("error", str(error)))
                threading.Thread(target=worker, daemon=True).start()
                self.after(100, self._poll_update)
                return
        elif kind == "error":
            messagebox.showerror(title, value, parent=self)
        else:
            text = (("Uppdateringen är klar. Starta om Runcom." if LANGUAGE == "sv" else
                     "Update complete. Restart Runcom.") if kind == "installed" else
                    ("Ingen nyare release finns." if LANGUAGE == "sv" else "No newer release is available."))
            messagebox.showinfo(title, text, parent=self)
        self.btn_update.config(state="normal")

    def open_help(self):
        local = Path(__file__).resolve().with_name("help.html")
        url = local.as_uri() if local.is_file() else HELP_URL
        try:
            if webbrowser.open(url, new=2):
                return
        except (OSError, webbrowser.Error):
            pass
        messagebox.showerror(tr('Kunde inte öppna hjälpen'),
                             tr('Öppna hjälpen manuellt i din webbläsare:\n\n') + url, parent=self)

    def _shortcut(self, fn):
        fn()
        return "break"  # hindra Text-widgetens egna kortkommandon (t.ex. Ctrl+O)

    def _bind_keys(self):
        mods = ["Control", "Command"] if IS_MAC else ["Control"]
        actions = {"s": self.save, "n": self.new_file, "o": self.open_file, "Shift-S": self.save_as}
        for m in mods:
            for key, fn in actions.items():
                for w in (self, self.editor):
                    w.bind(f"<{m}-{key}>", lambda e, f=fn: self._shortcut(f))
        self.bind("<F1>", lambda e: self._shortcut(self.open_help))
        self.bind("<F7>", lambda e: self._shortcut(self.open_terminal))
        self.bind("<F5>", lambda e: self._shortcut(self.run_in_app))
        self.bind("<F6>", lambda e: self._shortcut(self.run_in_terminal))
        if not IS_WIN:
            self.bind("<F8>", lambda e: self._shortcut(self.run_with_sudo))

    # ------------------------------------------------------------ hjälpare
    def _dirty(self):
        return bool(self.editor.edit_modified())

    def _update_title(self):
        name = self.current.name if self.current else tr('(ingen fil)')
        self.title(f"{'● ' if self._dirty() else ''}{name} – Runcom")

    def _set_status(self, text):
        self.status.config(text=text)

    def _set_text(self, text):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self._update_title()

    def _confirm_discard(self):
        """True om det är okej att gå vidare (ändringar sparade eller förkastade)."""
        if not self._dirty():
            return True
        ans = messagebox.askyesnocancel(tr('Osparade ändringar'), tr('Vill du spara ändringarna först?'))
        if ans is None:
            return False
        if ans:
            return self.save()
        return True

    def _make_executable(self, path):
        if IS_WIN:
            return
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR)

    def refresh_list(self):
        self.folder_label.config(text=str(self.folder))
        self.listbox.delete(0, "end")
        try:
            self.files = sorted(
                (p for p in self.folder.iterdir() if p.is_file() and not p.name.startswith(".")
                 and self.search.get().casefold() in p.name.casefold()),
                key=lambda p: p.name.lower(),
            )
        except OSError as e:
            self.files = []
            self._set_status('{0}{1}'.format(tr('Kunde inte läsa mappen: '), e))
        for p in self.files:
            self.listbox.insert("end", p.name)
        if self.current in self.files:
            i = self.files.index(self.current)
            self.listbox.selection_set(i)
            self.listbox.see(i)

    def _on_list_open(self, _e=None):
        sel = self.listbox.curselection()
        if sel:
            self.load_path(self.files[sel[0]])

    def run_selected(self):
        if self.proc is not None:
            return
        selection = self.listbox.curselection()
        if not selection:
            self._set_status(tr('Välj en fil i listan först.'))
            return
        self._open_and_run_path(self.files[selection[0]])

    def open_and_run(self):
        if self.proc is not None:
            return
        path = filedialog.askopenfilename(initialdir=self.folder, title=tr('Öppna och kör…'))
        if path:
            self._open_and_run_path(Path(path))

    def _open_and_run_path(self, path):
        if Path(path).absolute() != self.current and not self.load_path(path):
            return
        self.tabs.select(0)
        self.run_in_app()

    # ---------------------------------------------------------- filåtgärder
    def new_file(self):
        if not self._confirm_discard():
            return
        hint = tr('backup.bat, backup.ps1 eller hello.py') if IS_WIN else tr('backup.sh eller hello.py')
        name = simpledialog.askstring(tr('Ny skriptfil'), '{0}{1}):'.format(tr('Filnamn (t.ex. '), hint), parent=self)
        if not name:
            return
        name = name.strip().replace("/", "_").replace("\\", "_")
        if not name:
            return
        if "." not in name:
            name += DEFAULT_EXT
        path = self.folder / name
        if path.exists():
            messagebox.showerror(tr('Finns redan'), '{0}{1}'.format(name, tr(' finns redan i mappen.')))
            return
        text = template_for(name)
        try:
            snapshot = atomic_write(path, text, file_encoding(path),
                                    executable=text.startswith("#!"), exclusive=True)
        except (OSError, UnicodeEncodeError) as e:
            messagebox.showerror(tr('Fel'), str(e))
            return
        self.current = path
        self._snapshot = snapshot
        self._set_text(text)
        self.search.set("")
        self.refresh_list()
        self._set_status('{0}{1}'.format(tr('Skapade '), path))
        self.editor.focus_set()

    def open_file(self):
        path = filedialog.askopenfilename(initialdir=self.folder, title=tr('Öppna skriptfil'))
        if path:
            self.load_path(Path(path))

    def load_path(self, path):
        path = Path(path).absolute()
        if path == self.current and not self._dirty():
            return True
        if not self._confirm_discard():
            return False
        try:
            snapshot = path.read_bytes()
            text = snapshot.decode(file_encoding(path))
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        except (OSError, UnicodeDecodeError) as e:
            messagebox.showerror(tr('Kunde inte öppna'), str(e))
            return False
        if path.parent != self.folder:
            self.folder = path.parent
        self.current = path
        self._snapshot = snapshot
        self._set_text(text)
        self.refresh_list()
        self._set_status('{0}{1}'.format(tr('Öppnade '), path))
        return True

    def save(self):
        if self.current is None:
            return self.save_as()
        text = self.editor.get("1.0", "end-1c")
        if not text.endswith("\n"):
            text += "\n"
        try:
            snapshot = getattr(self, "_snapshot", None)
            if snapshot is not None:
                actual = self.current.read_bytes() if self.current.exists() else None
                if actual != snapshot and not messagebox.askyesno(
                        tr('Filen har ändrats'), tr('Filen har ändrats eller tagits bort utanför Runcom.\nVill du skriva över den med innehållet i editorn?'), parent=self):
                    return False
            snapshot = atomic_write(self.current, text, file_encoding(self.current),
                                    executable=text.startswith("#!"))
        except UnicodeEncodeError:
            messagebox.showerror(tr('Kunde inte spara'),
                                 '{0}{1}{2}'.format(tr('Filen innehåller tecken som inte finns i batchfilernas teckentabell ('), OEM, tr('). Ta bort dem eller använd en .ps1-fil.')))
            return False
        except OSError as e:
            messagebox.showerror(tr('Kunde inte spara'), str(e))
            return False
        self._snapshot = snapshot
        self.editor.edit_modified(False)
        self._update_title()
        self._set_status('{0}{1}'.format(tr('Sparade '), self.current))
        return True

    def save_as(self):
        path = filedialog.asksaveasfilename(initialdir=self.folder, title=tr('Spara som'),
                                            defaultextension=DEFAULT_EXT)
        if not path:
            return False
        previous, folder = self.current, self.folder
        snapshot = getattr(self, "_snapshot", None)
        self.current = Path(path).resolve()
        self.folder = self.current.parent
        self._snapshot = snapshot if self.current == previous else None
        ok = self.save()
        if not ok:
            self.current, self.folder = previous, folder
            self._snapshot = snapshot
            self._update_title()
        self.refresh_list()
        return ok

    def delete_file(self):
        if self.current is None:
            return
        if not messagebox.askyesno(tr('Ta bort'), '{0}{1}{2}'.format(tr('Ta bort '), self.current.name, tr(' permanent?'))):
            return
        try:
            self.current.unlink()
        except OSError as e:
            messagebox.showerror(tr('Fel'), str(e))
            return
        self.current = None
        self._snapshot = None
        self._set_text("")
        self.refresh_list()
        self._set_status(tr('Filen togs bort'))

    def change_folder(self):
        if not self._confirm_discard():
            return
        d = filedialog.askdirectory(initialdir=self.folder, title=tr('Välj mapp'))
        if d:
            self.folder = Path(d)
            self.current = None
            self._snapshot = None
            self.search.set("")
            self._set_text("")
            self.refresh_list()

    # ------------------------------------------------------------ körning
    def _out(self, text, tag=None):
        self.output.config(state="normal")
        # Trim incoming data before inserting: huge single lines are costly in Tk.
        limit = 100_000
        text = text[-limit:]
        count = self.output.count("1.0", "end-1c", "chars")
        size = int(count[0]) if count else 0
        if size + len(text) > limit:
            self.output.delete("1.0", f"1.0+{size + len(text) - 80_000}c")
        self.output.insert("end", text, tag or ())
        self.output.see("end")
        self.output.config(state="disabled")

    def _prepare_run(self):
        if self.current is None and not self.save():
            return False
        if self._dirty() and not self.save():
            return False
        return True

    def _command_for(self, path, keep_open=False):
        return script_command(path, keep_open)

    def _script_uses_sudo(self):
        return (not IS_WIN and self.current is not None
                and self.current.suffix.lower() in ('.sh', '.bash', '.zsh', '.ksh')
                and contains_sudo_command(self.editor.get('1.0', 'end-1c')))

    def run_in_app(self):
        if self.proc is not None:
            return
        if not self._prepare_run():
            return
        path = self.current
        if self._script_uses_sudo():
            self._run_in_builtin_terminal(elevated=True, prepared=True)
            return
        try:
            cmd = self._command_for(path)
        except (OSError, ValueError) as error:
            messagebox.showerror(tr('Kunde inte köra skriptet'), str(error), parent=self)
            return
        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        self.output.config(state="disabled")
        if cmd is None:
            self._out(tr('Filtypen stöds inte. Använd ett skal- eller Python-skript (Windows: .bat, .cmd, .ps1 eller .py).\n'), "err")
            return
        self._out(f"> {path}\n", "info")
        kwargs = dict(
            cwd=str(path.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, bufsize=0,
            env=self._run_env(),
        )
        if IS_WIN:
            kwargs["creationflags"] = NO_WINDOW | NEW_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            self.proc = subprocess.Popen(cmd, **kwargs)
        except OSError as e:
            self._out('{0}{1}\n'.format(tr('Kunde inte starta: '), e), "err")
            self.proc = None
            return
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self._set_status(tr('Kör…'))
        encoding = OEM
        if path.suffix.lower() == ".py" or (
                path.suffix.lower() == ".ps1" and isinstance(cmd, list)
                and Path(cmd[0]).stem.lower() == "pwsh"):
            encoding = "utf-8"
        threading.Thread(target=self._reader, args=(self.proc, encoding), daemon=True).start()

    def _enqueue(self, kind, proc, value):
        while not self._closing:
            try:
                self.q.put((kind, proc, value), timeout=0.1)
                return
            except queue.Full:
                continue

    def _reader(self, proc, encoding=OEM):
        decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        try:
            while not self._closing:
                data = os.read(proc.stdout.fileno(), 4096)
                if not data:
                    break
                text = decoder.decode(data)
                if text:
                    self._enqueue("line", proc, text)
            tail = decoder.decode(b"", final=True)
            if tail:
                self._enqueue("line", proc, tail)
        except OSError as error:
            self._enqueue("error", proc, str(error))
        finally:
            proc.stdout.close()
            proc.wait()
            self._enqueue("done", proc, proc.returncode)

    def _drain_queue(self):
        try:
            for _ in range(200):
                kind, proc, val = self.q.get_nowait()
                if proc is not self.proc:
                    continue
                if kind == "error":
                    self._out('{0}{1}\n'.format(tr('Kunde inte läsa utdata: '), val), "err")
                elif kind == "line":
                    self._out(val)
                else:
                    self._out('{0}{1}]\n'.format(tr('\n[Avslutades med kod '), val), "info" if val == 0 else "err")
                    self.proc = None
                    self.btn_run.config(state="normal")
                    self.btn_stop.config(state="disabled")
                    self._set_status('{0}{1})'.format(tr('Klar (kod '), val))
        except queue.Empty:
            pass
        self._queue_after = self.after(50, self._drain_queue)

    def stop(self):
        if self.proc is None:
            return
        pid = self.proc.pid
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, creationflags=NO_WINDOW)
            else:
                os.killpg(pid, signal.SIGTERM)
                if self._stop_after is not None:
                    self.after_cancel(self._stop_after)
                self._stop_after = self.after(1500, lambda proc=self.proc: self._force_stop(proc))
            self._out(tr('\n[Stoppad av användaren]\n'), "err")
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def _force_stop(self, proc):
        if proc is not None and proc is self.proc:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass

    def clear_output(self):
        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        self.output.config(state="disabled")

    # ------------------------------------------------- terminal / admin
    def _unix_inner(self, path, elevated=False):
        command = self._command_for(path)
        if command is None:
            raise ValueError(tr('Filtypen stöds inte. Välj ett skal- eller Python-skript.'))
        if elevated:
            sudo = shutil.which("sudo")
            if not sudo:
                raise ValueError(tr('Kommandot sudo hittades inte.'))
            command = [sudo, "--", *command]
        return (shlex.join(command) + tr("; echo; printf '[Klart - tryck Enter för att stänga] '; read -r _x"))

    def run_in_terminal(self, elevated=False):
        if not self._prepare_run():
            return
        path = self.current
        try:
            if IS_WIN:
                cmd = self._command_for(path, keep_open=True)
                if cmd is None:
                    messagebox.showerror(tr('Filtypen stöds inte'), tr('Använd .bat, .cmd, .ps1 eller .py.'))
                    return
                subprocess.Popen(cmd, cwd=str(path.parent), creationflags=NEW_CONSOLE)
                self._set_status('{0}{1}{2}'.format(tr('Startade '), path.name, tr(' i ett konsolfönster')))
            elif IS_MAC:
                line = f"cd {shlex.quote(str(path.parent))} && {self._unix_inner(path, elevated)}"
                esc = line.replace("\\", "\\\\").replace('"', '\\"')
                script = f'tell application "Terminal"\nactivate\ndo script "{esc}"\nend tell'
                subprocess.Popen(["osascript", "-e", script])
                self._set_status('{0}{1}{2}'.format(tr('Startade '), path.name, tr(' i Terminal')))
            else:
                for prog, prefix in TERMINALS:
                    if shutil.which(prog):
                        subprocess.Popen([prog, *prefix, "bash", "-c", self._unix_inner(path, elevated)],
                                         cwd=str(path.parent), start_new_session=True)
                        self._set_status('{0}{1}{2}{3}'.format(tr('Startade '), path.name, tr(' i '), prog))
                        return
                messagebox.showerror(tr('Ingen terminal hittades'),
                                     tr('Installera t.ex. gnome-terminal, konsole eller xterm, eller använd ”Kör här”.'))
        except (OSError, ValueError) as e:
            messagebox.showerror(tr('Fel'), str(e))

    def run_as_admin(self):
        """Windows: kör skriptet förhöjt. Windows visar sin egen UAC-ruta varje gång."""
        if not IS_WIN or not self._prepare_run():
            return
        path = self.current
        ext = path.suffix.lower()
        if ext in (".bat", ".cmd"):
            try:
                command = self._command_for(path, keep_open=True)
            except ValueError as error:
                messagebox.showerror(tr('Kunde inte köra skriptet'), str(error), parent=self)
                return
            exe = os.environ.get("COMSPEC", "cmd.exe")
            params = command[len(subprocess.list2cmdline([exe])):].lstrip()
        elif ext == ".py":
            exe = python_executable()
            params = subprocess.list2cmdline([str(path)])
        elif ext == ".ps1":
            exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
            params = f'-NoExit -ExecutionPolicy Bypass -File "{path}"'
        else:
            messagebox.showerror(tr('Filtypen stöds inte'), tr('Använd .bat, .cmd, .ps1 eller .py.'))
            return
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, str(path.parent), 1)
        if r <= 32:
            self._set_status(tr('Admin-körningen avbröts eller misslyckades'))
        else:
            self._set_status('{0}{1}{2}'.format(tr('Startade '), path.name, tr(' som administratör')))

    def run_with_sudo(self):
        if IS_WIN:
            return
        self._run_in_builtin_terminal(elevated=True)

    def _run_in_builtin_terminal(self, elevated=False, prepared=False):
        if not prepared and not self._prepare_run():
            return
        try:
            command = self._command_for(self.current)
            sudo = shutil.which('sudo')
            if not sudo:
                raise ValueError(tr('Kommandot sudo hittades inte.'))
            if command is None:
                raise ValueError(tr('Filtypen stöds inte. Välj ett skal- eller Python-skript.'))
            if elevated:
                command = [sudo, '--', *command]
            self.open_terminal()
            shell_command = ('cd ' + shlex.quote(str(self.current.parent)) + ' && '
                             + shlex.join(command))
            self.terminal.authorize_sudo(after=shell_command)
        except (OSError, ValueError) as error:
            messagebox.showerror(tr('Kunde inte köra skriptet'), str(error), parent=self)

    def _run_env(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # Do not forward legacy cached credentials inherited from an old Runcom.
        env.pop("SKRIPTSTUDIO_SUDO_PW", None)
        if IS_MAC:
            have = env.get("PATH", "").split(os.pathsep)
            extra = [p for p in ("/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin")
                     if os.path.isdir(p) and p not in have]
            env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
        return env

    def on_close(self, confirm=True):
        if confirm and not self._confirm_discard():
            return
        if self.proc is not None:
            self.stop()
            if not IS_WIN:
                self._force_stop(self.proc)
        self.terminal.clear(focus=False)
        self.terminal.close()
        self._closing = True
        self.after_cancel(self._queue_after)
        if self._stop_after is not None:
            self.after_cancel(self._stop_after)
        self.destroy()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == '--terminal-child' and not IS_WIN:
        terminal_child(sys.argv[2])
    if IS_WIN:
        try:  # skarp text på skärmar med skalning
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    try:
        app = App()
        app.after_idle(app.startup_sudo)
        app.mainloop()
    except tk.TclError as error:
        print('{0}{1}'.format(tr('Runcom kunde inte starta det grafiska gränssnittet: '), error), file=sys.stderr)
        sys.exit(1)
