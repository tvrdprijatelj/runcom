#!/usr/bin/env python3
"""Runcom – skapa, öppna, redigera och kör skriptfiler.

Fungerar på Linux, macOS och Windows.
  Linux/macOS: skal- och Python-skript. Sudo körs i en separat terminal.
  Windows:     .bat/.cmd och .ps1. "Kör som admin" visar Windows egen UAC-ruta.

Start:  python3 runcom.py   (Windows: py runcom.py)
Kräver: Python 3.8+ med Tkinter (Debian/Ubuntu: sudo apt install python3-tk)
"""
import codecs
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
from tkinter import filedialog, messagebox, simpledialog

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
MOD = "Cmd" if IS_MAC else "Ctrl"

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
NEW_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)

DEFAULT_DIR = Path.home() / "skript"
DEFAULT_EXT = ".bat" if IS_WIN else ".sh"
HELP_URL = "https://tvrdprijatelj.github.io/runcom/help.html"

SHEBANG = "#!/usr/bin/env bash\n"
TPL_UNIX = SHEBANG + 'set -euo pipefail\n\n# Skriv dina kommandon här\necho "Hej från $(hostname)!"\n'
TPL_BAT = "@echo off\nrem Skriv dina kommandon här\necho Hej fran %COMPUTERNAME%!\n"
TPL_PS1 = '# Skriv dina kommandon här\nWrite-Host "Hej från $env:COMPUTERNAME!"\n'

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
        return '#!/usr/bin/env python3\n\nprint("Hej från Runcom!")\n'
    if ext == ".ps1":
        return TPL_PS1
    if ext in (".bat", ".cmd"):
        return TPL_BAT
    return TPL_BAT if IS_WIN else TPL_UNIX


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
                raise ValueError("Byt namn på batchfilen eller mappen: %, radbrytningar och citattecken stöds inte.")
            exe = os.environ.get("COMSPEC", "cmd.exe")
            # cmd /s requires an extra quote pair; list2cmdline on the whole
            # command would escape quotes using rules cmd does not understand.
            flag = "/k" if keep_open else "/c"
            return subprocess.list2cmdline([exe]) + ' /d /v:off /s ' + flag + ' ""' + str(path) + '""'
        if ext == ".ps1":
            ps = shutil.which("pwsh") or shutil.which("powershell")
            if not ps:
                raise ValueError("PowerShell hittades inte.")
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
            raise ValueError("Skriptets shebang saknar ett program.")
        return interpreter + [str(path)]
    if ext in (".sh", ".bash"):
        return ["bash", str(path)]
    return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Runcom")
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
            messagebox.showerror("Kunde inte skapa skriptmappen", str(error), parent=self)
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
        tk.Label(header, text="Skriv. Kör. Se resultatet.", bg="#101722",
                 fg="#a5b5cc", padx=20).pack(side="left")
        self.btn_help = tk.Button(header, text="Hjälp", command=self.open_help,
                                  bg="#23334a", fg="#e4ecf7")
        self.btn_help.pack(side="right")
        bar = tk.Frame(self, padx=12, pady=6)
        bar.pack(fill="x")
        buttons = [
            (f"Ny ({MOD}+N)", self.new_file),
            (f"Öppna… ({MOD}+O)", self.open_file),
            (f"Spara ({MOD}+S)", self.save),
            ("Spara som…", self.save_as),
            ("Ta bort", self.delete_file),
            ("Byt mapp…", self.change_folder),
        ]
        for text, cmd in buttons:
            tk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)

        runbar = tk.Frame(self, padx=12, pady=8)
        runbar.pack(fill="x")
        bar = runbar
        self.btn_run = tk.Button(bar, text="▶ Kör här (F5)", command=self.run_in_app,
                                 bg="#2e7d32", fg="white", activebackground="#1b5e20")
        self.btn_run.pack(side="left", padx=2)
        self.btn_stop = tk.Button(bar, text="■ Stoppa", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=2)
        tk.Button(bar, text="Kör i terminal (F6)", command=self.run_in_terminal).pack(side="left", padx=2)

        tk.Frame(bar, width=20).pack(side="left")
        if IS_WIN:
            tk.Button(bar, text="Kör som admin", command=self.run_as_admin).pack(side="left", padx=2)
        else:
            tk.Button(bar, text="Kör med sudo…", command=self.run_with_sudo).pack(side="left", padx=2)

        main = tk.PanedWindow(self, orient="horizontal", sashwidth=5)
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
        tk.Label(left, text="Sök filnamn · dubbelklicka för att öppna", fg="#a5b5cc",
                 font=("TkDefaultFont", 9)).pack(fill="x", before=search)
        self.search.trace_add("write", lambda *_: self.refresh_list())
        self.listbox = tk.Listbox(lf, yscrollcommand=sb.set, exportselection=False, activestyle="none",
                                 bg="#101722", fg="#e4ecf7", selectbackground="#285a85",
                                 selectforeground="white", relief="flat", borderwidth=0)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.config(command=self.listbox.yview)
        self.listbox.bind("<Double-Button-1>", self._on_list_open)
        self.listbox.bind("<Return>", self._on_list_open)
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
        tk.Label(outputbar, text="UTDATA", anchor="w", padx=10).pack(side="left")
        tk.Button(outputbar, text="Rensa", command=self.clear_output).pack(side="right")
        tk.Label(outputbar, text="Behöver skriptet inmatning? Använd Kör i terminal.",
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
                               text="Redo · Skapa en fil med Ctrl+N eller öppna med Ctrl+O")
        self.status.pack(fill="x", side="bottom")

    def open_help(self):
        local = Path(__file__).resolve().with_name("help.html")
        url = local.as_uri() if local.is_file() else HELP_URL
        try:
            if webbrowser.open(url, new=2):
                return
        except (OSError, webbrowser.Error):
            pass
        messagebox.showerror("Kunde inte öppna hjälpen",
                             "Öppna hjälpen manuellt i din webbläsare:\n\n" + url, parent=self)

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
        self.bind("<F5>", lambda e: self._shortcut(self.run_in_app))
        self.bind("<F6>", lambda e: self._shortcut(self.run_in_terminal))

    # ------------------------------------------------------------ hjälpare
    def _dirty(self):
        return bool(self.editor.edit_modified())

    def _update_title(self):
        name = self.current.name if self.current else "(ingen fil)"
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
        ans = messagebox.askyesnocancel("Osparade ändringar", "Vill du spara ändringarna först?")
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
            self._set_status(f"Kunde inte läsa mappen: {e}")
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

    # ---------------------------------------------------------- filåtgärder
    def new_file(self):
        if not self._confirm_discard():
            return
        hint = "backup.bat, backup.ps1 eller hello.py" if IS_WIN else "backup.sh eller hello.py"
        name = simpledialog.askstring("Ny skriptfil", f"Filnamn (t.ex. {hint}):", parent=self)
        if not name:
            return
        name = name.strip().replace("/", "_").replace("\\", "_")
        if not name:
            return
        if "." not in name:
            name += DEFAULT_EXT
        path = self.folder / name
        if path.exists():
            messagebox.showerror("Finns redan", f"{name} finns redan i mappen.")
            return
        text = template_for(name)
        try:
            snapshot = atomic_write(path, text, file_encoding(path),
                                    executable=text.startswith("#!"), exclusive=True)
        except (OSError, UnicodeEncodeError) as e:
            messagebox.showerror("Fel", str(e))
            return
        self.current = path
        self._snapshot = snapshot
        self._set_text(text)
        self.search.set("")
        self.refresh_list()
        self._set_status(f"Skapade {path}")
        self.editor.focus_set()

    def open_file(self):
        path = filedialog.askopenfilename(initialdir=self.folder, title="Öppna skriptfil")
        if path:
            self.load_path(Path(path))

    def load_path(self, path):
        path = Path(path).absolute()
        if path == self.current and not self._dirty():
            return
        if not self._confirm_discard():
            return
        try:
            snapshot = path.read_bytes()
            text = snapshot.decode(file_encoding(path))
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        except (OSError, UnicodeDecodeError) as e:
            messagebox.showerror("Kunde inte öppna", str(e))
            return
        if path.parent != self.folder:
            self.folder = path.parent
        self.current = path
        self._snapshot = snapshot
        self._set_text(text)
        self.refresh_list()
        self._set_status(f"Öppnade {path}")

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
                        "Filen har ändrats", "Filen har ändrats eller tagits bort utanför Runcom.\n"
                        "Vill du skriva över den med innehållet i editorn?", parent=self):
                    return False
            snapshot = atomic_write(self.current, text, file_encoding(self.current),
                                    executable=text.startswith("#!"))
        except UnicodeEncodeError:
            messagebox.showerror("Kunde inte spara",
                                 "Filen innehåller tecken som inte finns i batchfilernas teckentabell "
                                 f"({OEM}). Ta bort dem eller använd en .ps1-fil.")
            return False
        except OSError as e:
            messagebox.showerror("Kunde inte spara", str(e))
            return False
        self._snapshot = snapshot
        self.editor.edit_modified(False)
        self._update_title()
        self._set_status(f"Sparade {self.current}")
        return True

    def save_as(self):
        path = filedialog.asksaveasfilename(initialdir=self.folder, title="Spara som",
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
        if not messagebox.askyesno("Ta bort", f"Ta bort {self.current.name} permanent?"):
            return
        try:
            self.current.unlink()
        except OSError as e:
            messagebox.showerror("Fel", str(e))
            return
        self.current = None
        self._snapshot = None
        self._set_text("")
        self.refresh_list()
        self._set_status("Filen togs bort")

    def change_folder(self):
        if not self._confirm_discard():
            return
        d = filedialog.askdirectory(initialdir=self.folder, title="Välj mapp")
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

    def run_in_app(self):
        if self.proc is not None:
            return
        if not self._prepare_run():
            return
        path = self.current
        try:
            cmd = self._command_for(path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Kunde inte köra skriptet", str(error), parent=self)
            return
        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        self.output.config(state="disabled")
        if cmd is None:
            self._out("Filtypen stöds inte. Använd ett skal- eller Python-skript (Windows: .bat, .cmd, .ps1 eller .py).\n", "err")
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
            self._out(f"Kunde inte starta: {e}\n", "err")
            self.proc = None
            return
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self._set_status("Kör…")
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
                    self._out(f"Kunde inte läsa utdata: {val}\n", "err")
                elif kind == "line":
                    self._out(val)
                else:
                    self._out(f"\n[Avslutades med kod {val}]\n", "info" if val == 0 else "err")
                    self.proc = None
                    self.btn_run.config(state="normal")
                    self.btn_stop.config(state="disabled")
                    self._set_status(f"Klar (kod {val})")
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
            self._out("\n[Stoppad av användaren]\n", "err")
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
            raise ValueError("Filtypen stöds inte. Välj ett skal- eller Python-skript.")
        if elevated:
            sudo = shutil.which("sudo")
            if not sudo:
                raise ValueError("Kommandot sudo hittades inte.")
            command = [sudo, "--", *command]
        return (shlex.join(command) + "; echo; "
                "printf '[Klart - tryck Enter för att stänga] '; read -r _x")

    def run_in_terminal(self, elevated=False):
        if not self._prepare_run():
            return
        path = self.current
        try:
            if IS_WIN:
                cmd = self._command_for(path, keep_open=True)
                if cmd is None:
                    messagebox.showerror("Filtypen stöds inte", "Använd .bat, .cmd, .ps1 eller .py.")
                    return
                subprocess.Popen(cmd, cwd=str(path.parent), creationflags=NEW_CONSOLE)
                self._set_status(f"Startade {path.name} i ett konsolfönster")
            elif IS_MAC:
                line = f"cd {shlex.quote(str(path.parent))} && {self._unix_inner(path, elevated)}"
                esc = line.replace("\\", "\\\\").replace('"', '\\"')
                script = f'tell application "Terminal"\nactivate\ndo script "{esc}"\nend tell'
                subprocess.Popen(["osascript", "-e", script])
                self._set_status(f"Startade {path.name} i Terminal")
            else:
                for prog, prefix in TERMINALS:
                    if shutil.which(prog):
                        subprocess.Popen([prog, *prefix, "bash", "-c", self._unix_inner(path, elevated)],
                                         cwd=str(path.parent), start_new_session=True)
                        self._set_status(f"Startade {path.name} i {prog}")
                        return
                messagebox.showerror("Ingen terminal hittades",
                                     "Installera t.ex. gnome-terminal, konsole eller xterm, "
                                     "eller använd ”Kör här”.")
        except (OSError, ValueError) as e:
            messagebox.showerror("Fel", str(e))

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
                messagebox.showerror("Kunde inte köra skriptet", str(error), parent=self)
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
            messagebox.showerror("Filtypen stöds inte", "Använd .bat, .cmd, .ps1 eller .py.")
            return
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, str(path.parent), 1)
        if r <= 32:
            self._set_status("Admin-körningen avbröts eller misslyckades")
        else:
            self._set_status(f"Startade {path.name} som administratör")

    def run_with_sudo(self):
        self.run_in_terminal(elevated=True)

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

    def on_close(self):
        if not self._confirm_discard():
            return
        if self.proc is not None:
            self.stop()
            if not IS_WIN:
                self._force_stop(self.proc)
        self._closing = True
        self.after_cancel(self._queue_after)
        if self._stop_after is not None:
            self.after_cancel(self._stop_after)
        self.destroy()


if __name__ == "__main__":
    if IS_WIN:
        try:  # skarp text på skärmar med skalning
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    try:
        App().mainloop()
    except tk.TclError as error:
        print(f"Runcom kunde inte starta det grafiska gränssnittet: {error}", file=sys.stderr)
        sys.exit(1)
