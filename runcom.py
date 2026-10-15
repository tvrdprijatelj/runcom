#!/usr/bin/env python3
"""Skriptstudio – skapa, öppna, redigera och kör skriptfiler.

Fungerar på Linux, macOS och Windows.
  Linux/macOS: skript med shebang (bash). Sudo-lösenord kan hållas i minnet under sessionen.
  Windows:     .bat/.cmd och .ps1. "Kör som admin" visar Windows egen UAC-ruta.

Start:  python3 skriptstudio.py   (Windows: py skriptstudio.py)
Kräver: Python 3.8+ med Tkinter (Debian/Ubuntu: sudo apt install python3-tk)
"""
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
    if IS_WIN:
        return TPL_PS1 if name.lower().endswith(".ps1") else TPL_BAT
    return TPL_UNIX


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Skriptstudio")
        self.geometry("1100x720")
        self.minsize(700, 450)

        self.mono = tkfont.nametofont("TkFixedFont").copy()
        self.mono.configure(size=11)
        self.mono_small = tkfont.nametofont("TkFixedFont").copy()
        self.mono_small.configure(size=10)

        self.folder = DEFAULT_DIR
        self.folder.mkdir(parents=True, exist_ok=True)
        self.current = None  # Path eller None
        self.proc = None
        self.q = queue.Queue()
        self.files = []
        self.sudo_pw = None   # lösenordet finns bara i minnet, aldrig på disk
        self.sudo_dir = None
        self.btn_sudo = None
        self._btn_bg = None

        self._build_ui()
        self._bind_keys()
        self.refresh_list()
        self._update_title()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        if IS_MAC:
            self.createcommand("tk::mac::Quit", self.on_close)
        self.after(50, self._drain_queue)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        bar = tk.Frame(self, padx=6, pady=6)
        bar.pack(fill="x")
        buttons = [
            (f"Ny ({MOD}+N)", self.new_file),
            (f"Öppna… ({MOD}+O)", self.open_file),
            (f"Spara ({MOD}+S)", self.save),
            ("Ta bort", self.delete_file),
            ("Byt mapp…", self.change_folder),
        ]
        for text, cmd in buttons:
            tk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)

        tk.Frame(bar, width=20).pack(side="left")
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
            self.btn_sudo = tk.Button(bar, text="Sudo: av", command=self.toggle_sudo)
            self.btn_sudo.pack(side="left", padx=2)
            self._btn_bg = self.btn_sudo.cget("bg")

        main = tk.PanedWindow(self, orient="horizontal", sashwidth=5)
        main.pack(fill="both", expand=True)

        # Vänster: fillista
        left = tk.Frame(main)
        self.folder_label = tk.Label(left, anchor="w", fg="#555", text="")
        self.folder_label.pack(fill="x", padx=4, pady=(4, 0))
        lf = tk.Frame(left)
        lf.pack(fill="both", expand=True, padx=4, pady=4)
        sb = tk.Scrollbar(lf)
        sb.pack(side="right", fill="y")
        self.listbox = tk.Listbox(lf, yscrollcommand=sb.set, exportselection=False, activestyle="none")
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
        self.editor = tk.Text(ef, wrap="none", undo=True, font=self.mono,
                              yscrollcommand=esb.set, tabs=("1c",))
        self.editor.pack(side="left", fill="both", expand=True)
        esb.config(command=self.editor.yview)
        self.editor.bind("<<Modified>>", lambda e: self._update_title())
        right.add(ef, minsize=150, height=400)

        of = tk.Frame(right)
        tk.Label(of, text="Utdata", anchor="w", font=tkfont.nametofont("TkDefaultFont")).pack(fill="x")
        osb = tk.Scrollbar(of)
        osb.pack(side="right", fill="y")
        self.output = tk.Text(of, height=10, wrap="word", state="disabled", bg="#1e1e1e", fg="#dcdcdc",
                              font=self.mono_small, yscrollcommand=osb.set)
        self.output.pack(side="left", fill="both", expand=True)
        osb.config(command=self.output.yview)
        self.output.tag_config("info", foreground="#6cb6ff")
        self.output.tag_config("err", foreground="#ff7b72")
        right.add(of, minsize=80)

        self.status = tk.Label(self, anchor="w", relief="sunken", text="Redo")
        self.status.pack(fill="x", side="bottom")

    def _shortcut(self, fn):
        fn()
        return "break"  # hindra Text-widgetens egna kortkommandon (t.ex. Ctrl+O)

    def _bind_keys(self):
        mods = ["Control", "Command"] if IS_MAC else ["Control"]
        actions = {"s": self.save, "n": self.new_file, "o": self.open_file}
        for m in mods:
            for key, fn in actions.items():
                for w in (self, self.editor):
                    w.bind(f"<{m}-{key}>", lambda e, f=fn: self._shortcut(f))
        self.bind("<F5>", lambda e: self._shortcut(self.run_in_app))
        self.bind("<F6>", lambda e: self._shortcut(self.run_in_terminal))

    # ------------------------------------------------------------ hjälpare
    def _dirty(self):
        return bool(self.editor.edit_modified())

    def _update_title(self):
        name = self.current.name if self.current else "(ingen fil)"
        self.title(f"{'● ' if self._dirty() else ''}{name} – Skriptstudio")

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
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def refresh_list(self):
        self.folder_label.config(text=str(self.folder))
        self.listbox.delete(0, "end")
        try:
            self.files = sorted(
                (p for p in self.folder.iterdir() if p.is_file() and not p.name.startswith(".")),
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
        hint = "backup.bat eller backup.ps1" if IS_WIN else "backup.sh"
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
            path.write_text(text, encoding=file_encoding(path))
            self._make_executable(path)
        except (OSError, UnicodeEncodeError) as e:
            messagebox.showerror("Fel", str(e))
            return
        self.current = path
        self._set_text(text)
        self.refresh_list()
        self._set_status(f"Skapade {path}")
        self.editor.focus_set()

    def open_file(self):
        path = filedialog.askopenfilename(initialdir=self.folder, title="Öppna skriptfil")
        if path:
            self.load_path(Path(path))

    def load_path(self, path):
        if path == self.current and not self._dirty():
            return
        if not self._confirm_discard():
            return
        try:
            text = path.read_text(encoding=file_encoding(path), errors="replace")
        except OSError as e:
            messagebox.showerror("Kunde inte öppna", str(e))
            return
        if path.parent != self.folder:
            self.folder = path.parent
        self.current = path
        self._set_text(text)
        self.refresh_list()
        self._set_status(f"Öppnade {path}")

    def save(self):
        if self.current is None:
            return self.save_as()
        # Linux/macOS: se till att filen har en shebang så att den går att köra direkt
        if not IS_WIN and not self.editor.get("1.0", "end-1c").startswith("#!"):
            self.editor.insert("1.0", SHEBANG)
        text = self.editor.get("1.0", "end-1c")
        if not text.endswith("\n"):
            text += "\n"
        try:
            self.current.write_text(text, encoding=file_encoding(self.current))
            self._make_executable(self.current)
        except UnicodeEncodeError:
            messagebox.showerror("Kunde inte spara",
                                 "Filen innehåller tecken som inte finns i batchfilernas teckentabell "
                                 f"({OEM}). Ta bort dem eller använd en .ps1-fil.")
            return False
        except OSError as e:
            messagebox.showerror("Kunde inte spara", str(e))
            return False
        self.editor.edit_modified(False)
        self._update_title()
        self._set_status(f"Sparade {self.current}")
        return True

    def save_as(self):
        path = filedialog.asksaveasfilename(initialdir=self.folder, title="Spara som",
                                            defaultextension=DEFAULT_EXT)
        if not path:
            return False
        self.current = Path(path)
        self.folder = self.current.parent
        ok = self.save()
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
            self._set_text("")
            self.refresh_list()

    # ------------------------------------------------------------ körning
    def _out(self, text, tag=None):
        self.output.config(state="normal")
        self.output.insert("end", text, tag)
        self.output.see("end")
        self.output.config(state="disabled")

    def _prepare_run(self):
        if self.current is None and not self.save():
            return False
        if self._dirty() and not self.save():
            return False
        return True

    def _command_for(self, path, keep_open=False):
        """Kommandoraden som kör skriptet, eller None om filtypen inte stöds (Windows)."""
        if not IS_WIN:
            return [str(path)]
        ext = path.suffix.lower()
        if ext in (".bat", ".cmd"):
            return ["cmd.exe", "/k", str(path)] if keep_open else [str(path)]
        if ext == ".ps1":
            ps = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
            flag = "-NoExit" if keep_open else "-NoProfile"
            return [ps, flag, "-ExecutionPolicy", "Bypass", "-File", str(path)]
        return None

    def run_in_app(self):
        if self.proc is not None:
            return
        if not self._prepare_run():
            return
        path = self.current
        cmd = self._command_for(path)
        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        self.output.config(state="disabled")
        if cmd is None:
            self._out("Filtypen stöds inte. Använd .bat, .cmd eller .ps1.\n", "err")
            return
        self._out(f"> {path}\n", "info")
        kwargs = dict(
            cwd=str(path.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, bufsize=1, encoding=OEM, errors="replace",
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
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _reader(self, proc):
        for line in proc.stdout:
            self.q.put(("line", line))
        proc.wait()
        self.q.put(("done", proc.returncode))

    def _drain_queue(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "line":
                    self._out(val)
                else:
                    self._out(f"\n[Avslutades med kod {val}]\n", "info" if val == 0 else "err")
                    self.proc = None
                    self.btn_run.config(state="normal")
                    self.btn_stop.config(state="disabled")
                    self._set_status(f"Klar (kod {val})")
        except queue.Empty:
            pass
        self.after(50, self._drain_queue)

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
            self._out("\n[Stoppad av användaren]\n", "err")
        except (ProcessLookupError, PermissionError, OSError):
            pass

    # ------------------------------------------------- terminal / admin
    @staticmethod
    def _unix_inner(path):
        return (f"{shlex.quote(str(path))}; echo; "
                "printf '[Klart - tryck Enter för att stänga] '; read -r _x")

    def run_in_terminal(self):
        if not self._prepare_run():
            return
        path = self.current
        try:
            if IS_WIN:
                cmd = self._command_for(path, keep_open=True)
                if cmd is None:
                    messagebox.showerror("Filtypen stöds inte", "Använd .bat, .cmd eller .ps1.")
                    return
                subprocess.Popen(cmd, cwd=str(path.parent), creationflags=NEW_CONSOLE)
                self._set_status(f"Startade {path.name} i ett konsolfönster")
            elif IS_MAC:
                line = f"cd {shlex.quote(str(path.parent))} && {self._unix_inner(path)}"
                esc = line.replace("\\", "\\\\").replace('"', '\\"')
                script = f'tell application "Terminal"\nactivate\ndo script "{esc}"\nend tell'
                subprocess.Popen(["osascript", "-e", script])
                self._set_status(f"Startade {path.name} i Terminal")
            else:
                for prog, prefix in TERMINALS:
                    if shutil.which(prog):
                        subprocess.Popen([prog, *prefix, "bash", "-c", self._unix_inner(path)],
                                         cwd=str(path.parent), start_new_session=True)
                        self._set_status(f"Startade {path.name} i {prog}")
                        return
                messagebox.showerror("Ingen terminal hittades",
                                     "Installera t.ex. gnome-terminal, konsole eller xterm, "
                                     "eller använd ”Kör här”.")
        except OSError as e:
            messagebox.showerror("Fel", str(e))

    def run_as_admin(self):
        """Windows: kör skriptet förhöjt. Windows visar sin egen UAC-ruta varje gång."""
        if not IS_WIN or not self._prepare_run():
            return
        path = self.current
        ext = path.suffix.lower()
        if ext in (".bat", ".cmd"):
            exe, params = "cmd.exe", f'/k ""{path}""'
        elif ext == ".ps1":
            exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
            params = f'-NoExit -ExecutionPolicy Bypass -File "{path}"'
        else:
            messagebox.showerror("Filtypen stöds inte", "Använd .bat, .cmd eller .ps1.")
            return
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, str(path.parent), 1)
        if r <= 32:
            self._set_status("Admin-körningen avbröts eller misslyckades")
        else:
            self._set_status(f"Startade {path.name} som administratör")

    # --------------------------------------------------- sudo (Linux/macOS)
    def toggle_sudo(self):
        if self.sudo_pw is not None:
            self._forget_sudo()
            self._set_status("Sudo-lösenordet glömdes")
        else:
            self._enable_sudo()

    def _enable_sudo(self):
        real_sudo = shutil.which("sudo")
        if not real_sudo:
            messagebox.showerror("Sudo saknas", "Kommandot sudo hittades inte.")
            return
        pw = simpledialog.askstring("Sudo", "Lösenord för sudo (sparas bara i minnet\n"
                                    "tills du stänger appen eller trycker på knappen igen):",
                                    show="*", parent=self)
        if not pw:
            return
        env = dict(os.environ, LC_ALL="C", LANG="C")  # engelska meddelanden som går att tolka
        try:
            r = subprocess.run([real_sudo, "-S", "-k", "-p", "", "true"],
                               input=(pw + "\n").encode("utf-8"),
                               capture_output=True, timeout=20, env=env)
        except (OSError, subprocess.TimeoutExpired) as e:
            messagebox.showerror("Fel", str(e))
            return
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace").strip()
            low = err.lower()
            if "not in the sudoers" in low or "may not run sudo" in low:
                msg = "Ditt konto har inte sudo-rättigheter."
            elif "incorrect password" in low or "try again" in low:
                msg = ("Sudo godkände inte lösenordet. Använd ditt eget användarlösenord "
                       "(inte root-lösenordet) och kontrollera Caps Lock.")
            else:
                msg = "Sudo svarade:"
            messagebox.showerror("Sudo nekade", f"{msg}\n\n{err}")
            return
        # Hjälpskript i en privat tempmapp (0700). Lösenordet ligger INTE i filerna,
        # bara i miljövariabeln som skickas till de skript som körs härifrån.
        self.sudo_dir = tempfile.mkdtemp(prefix="skriptstudio-")
        askpass = os.path.join(self.sudo_dir, "askpass")
        shim = os.path.join(self.sudo_dir, "sudo")
        with open(askpass, "w") as f:
            f.write('#!/bin/sh\nprintf \'%s\\n\' "$SKRIPTSTUDIO_SUDO_PW"\n')
        with open(shim, "w") as f:
            f.write(f'#!/bin/sh\nexec {shlex.quote(real_sudo)} -A "$@"\n')
        os.chmod(askpass, 0o700)
        os.chmod(shim, 0o700)
        self.sudo_pw = pw
        self.btn_sudo.config(text="Sudo: på", bg="#f9a825")
        self._set_status("Sudo aktivt för skript som körs med ”Kör här” (F5)")

    def _forget_sudo(self):
        self.sudo_pw = None
        if self.sudo_dir:
            shutil.rmtree(self.sudo_dir, ignore_errors=True)
            self.sudo_dir = None
        if self.btn_sudo is not None:
            self.btn_sudo.config(text="Sudo: av", bg=self._btn_bg)

    def _run_env(self):
        env = os.environ.copy()
        if IS_MAC:
            # Appar som startas från Finder får en minimal PATH – lägg till Homebrew
            have = env.get("PATH", "").split(os.pathsep)
            extra = [p for p in ("/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin")
                     if os.path.isdir(p) and p not in have]
            env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
        if self.sudo_pw is not None and self.sudo_dir:
            env["SUDO_ASKPASS"] = os.path.join(self.sudo_dir, "askpass")
            env["SKRIPTSTUDIO_SUDO_PW"] = self.sudo_pw
            env["PATH"] = self.sudo_dir + os.pathsep + env.get("PATH", "")
        return env

    def on_close(self):
        if not self._confirm_discard():
            return
        if self.proc is not None:
            self.stop()
        self._forget_sudo()
        self.destroy()


if __name__ == "__main__":
    if IS_WIN:
        try:  # skarp text på skärmar med skalning
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()