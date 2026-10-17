#!/usr/bin/env python3
"""Desktop control for Runcom's GitHub Pages source. Python standard library only."""
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import webbrowser

REPOSITORY = "tvrdprijatelj/runcom"
SETTINGS = f"https://github.com/{REPOSITORY}/settings/pages"


class PagesClient:
    def __init__(self, token):
        self.token = token.strip()

    def request(self, method="GET", data=None):
        if not self.token:
            raise ValueError("Klistra in en GitHub-token först.")
        request = Request(
            f"https://api.github.com/repos/{REPOSITORY}/pages",
            data=None if data is None else json.dumps(data).encode(),
            headers={"Authorization": f"Bearer {self.token}",
                     "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json",
                     "X-GitHub-Api-Version": "2026-03-10"}, method=method)
        try:
            with urlopen(request, timeout=25) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except HTTPError as error:
            error.close()
            messages = {401: "Token är ogiltig eller har gått ut.",
                        403: "Åtkomst nekad. Token behöver Pages och Administration: Read and write.",
                        404: "Webbplatsen hittades inte eller token saknar åtkomst till runcom.",
                        422: "GitHub avvisade ändringen. Kontrollera brancherna i Pages-inställningarna."}
            raise ValueError(messages.get(error.code, f"GitHub svarade med HTTP {error.code}.")) from None
        except (URLError, TimeoutError, OSError):
            raise ValueError("Kunde inte nå GitHub. Kontrollera anslutningen och läs status igen innan du försöker växla.") from None

    def status(self):
        data = self.request()
        source = data.get("source") or {}
        if data.get("build_type") == "workflow" or source.get("path") != "/" or source.get("branch") not in ("main", "maintenance"):
            raise ValueError("Välj Deploy from a branch, main eller maintenance och / (root) i Pages-inställningarna först.")
        return data

    def switch(self, expected):
        current = self.status()
        if current["source"]["branch"] != expected:
            raise ValueError("Inställningen ändrades på GitHub. Läs status igen före bytet.")
        target = "maintenance" if expected == "main" else "main"
        self.request("PUT", {"source": {"branch": target, "path": "/"}})
        return self.status()


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=28)
        self.pack(fill="both", expand=True)
        self.events = queue.Queue()
        self.branch = None
        self.pending = False
        root.title("Runcom · Webbplats")
        root.minsize(560, 460)
        ttk.Label(self, text="Runcom · Webbplats", font=("", 22, "bold")).pack(anchor="w")
        ttk.Label(self, text=REPOSITORY).pack(anchor="w", pady=(0, 20))
        ttk.Label(self, text="GitHub-token (sparas bara medan appen är öppen)").pack(anchor="w")
        self.token = ttk.Entry(self, show="•")
        self.token.insert(0, os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", ""))
        self.token.pack(fill="x", pady=(5, 12))
        ttk.Label(self, text="Välj endast runcom när du skapar token. Behörigheter:\nPages och Administration → Read and write.", wraplength=500).pack(anchor="w")
        ttk.Button(self, text="Skapa GitHub-token ↗", command=lambda: webbrowser.open("https://github.com/settings/personal-access-tokens/new")).pack(anchor="w", pady=10)
        self.message = tk.StringVar(value="Läs status för att ansluta till GitHub.")
        ttk.Label(self, textvariable=self.message, wraplength=500).pack(anchor="w", pady=16)
        self.toggle = ttk.Button(self, text="Läs status först", command=self.switch, state="disabled")
        self.toggle.pack(fill="x", ipady=10)
        self.refresh = ttk.Button(self, text="Läs status", command=self.read)
        self.refresh.pack(fill="x", pady=10)
        ttk.Button(self, text="Öppna Pages-inställningar ↗", command=lambda: webbrowser.open(SETTINGS)).pack(anchor="w")
        self.token.bind("<KeyRelease>", self.invalidate)
        root.after(100, self.poll)

    def invalidate(self, event=None):
        self.branch = None
        self.toggle.configure(state="disabled", text="Läs status först")

    def run(self, operation):
        if self.pending:
            return
        self.pending = True
        self.toggle.configure(state="disabled")
        self.refresh.configure(state="disabled")
        self.token.configure(state="disabled")
        self.message.set("Kontaktar GitHub…")
        def work():
            try:
                self.events.put((operation(), None))
            except Exception as error:
                self.events.put((None, str(error)))
        threading.Thread(target=work, daemon=True).start()

    def read(self):
        self.run(PagesClient(self.token.get()).status)

    def switch(self):
        if self.branch:
            client = PagesClient(self.token.get())
            branch = self.branch
            self.run(lambda: client.switch(branch))

    def poll(self):
        try:
            data, error = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.pending = False
            self.token.configure(state="normal")
            self.refresh.configure(state="normal")
            if error:
                self.invalidate()
                self.message.set(error)
            else:
                self.branch = data["source"]["branch"]
                mode = "Vanlig webbplats" if self.branch == "main" else "Underhåll"
                self.message.set(f"Vald källa: {mode}. GitHub-status: {data.get('status', 'okänd')}.\nEtt byte tar en stund att publicera. Läs status igen för att följa det.")
                self.toggle.configure(state="normal", text="Aktivera underhåll" if self.branch == "main" else "Visa vanlig webbplats")
        self.after(100, self.poll)


if __name__ == "__main__":
    window = tk.Tk()
    App(window)
    window.mainloop()
