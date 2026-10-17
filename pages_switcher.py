#!/usr/bin/env python3
"""Desktop control for Runcom's GitHub Pages source. Python standard library only."""
import json
import os
import queue
import threading
import time
from datetime import datetime
from html.parser import HTMLParser
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

    def request(self, method="GET", data=None, suffix=""):
        if not self.token:
            raise ValueError("Klistra in en GitHub-token först.")
        request = Request(
            f"https://api.github.com/repos/{REPOSITORY}/pages{suffix}",
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
        return self.rebuild(target)

    def rebuild(self, expected):
        current = self.status()
        if current["source"]["branch"] != expected:
            raise ValueError("Pages-källan ändrades. Läs status igen före publicering.")
        try:
            result = self.request("POST", suffix="/builds")
        except ValueError as error:
            raise ValueError(f"Vald branch är {expected}, men byggbegäran misslyckades: {error} Använd Publicera vald branch igen efter att du läst status.") from None
        return {**current, "requested_build": result}

    def detailed_status(self):
        data = self.status()
        try:
            data["latest_build"] = self.request(suffix="/builds/latest")
        except ValueError as error:
            data["build_warning"] = str(error)
        # Public probe deliberately uses no Authorization header.
        try:
            request = Request("https://tvrdprijatelj.github.io/runcom/?pages-check=" + str(time.time_ns()),
                              headers={"Cache-Control": "no-cache", "User-Agent": "Runcom-Pages-Switcher"})
            with urlopen(request, timeout=15) as response:
                data["live_http"] = response.status
                data["live_mode"] = identify_page(response.read(2_000_000).decode("utf-8", errors="replace"))
        except (URLError, OSError, TimeoutError):
            data["live_mode"] = None
        return data


def identify_page(html):
    class TitleParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.inside = False
            self.title = ""
        def handle_starttag(self, tag, attrs):
            if tag == "title":
                self.inside = True
        def handle_endtag(self, tag):
            if tag == "title":
                self.inside = False
        def handle_data(self, data):
            if self.inside:
                self.title += data
    parser = TitleParser()
    parser.feed(html)
    title = parser.title.strip()
    if title == "Runcom — Underhåll / Maintenance":
        return "maintenance"
    if title == "Runcom — Välj språk / Choose language":
        return "main"
    return None


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=28)
        self.pack(fill="both", expand=True)
        self.events = queue.Queue()
        self.branch = None
        self.pending = False
        self.target = None
        self.started = None
        self.auto_job = None
        root.title("Runcom · Webbplats")
        root.minsize(650, 740)
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
        self.republish = ttk.Button(self, text="Publicera vald branch igen", command=self.rebuild, state="disabled")
        self.republish.pack(fill="x", pady=(0, 10))
        ttk.Button(self, text="Öppna Pages-inställningar ↗", command=lambda: webbrowser.open(SETTINGS)).pack(anchor="w")
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", pady=(16, 8))
        self.details = tk.StringVar(value="Ingen status hämtad ännu.")
        ttk.Label(self, textvariable=self.details, wraplength=580, justify="left").pack(anchor="w")
        ttk.Label(self, text="Händelser", font=("", 11, "bold")).pack(anchor="w", pady=(12, 4))
        self.log = tk.Text(self, height=7, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)
        self.token.bind("<KeyRelease>", self.invalidate)
        root.after(100, self.poll)

    def invalidate(self, event=None):
        if self.auto_job:
            self.after_cancel(self.auto_job)
            self.auto_job = None
        self.target = None
        self.started = None
        self.progress.stop()
        self.branch = None
        self.toggle.configure(state="disabled", text="Läs status först")
        self.republish.configure(state="disabled")

    def run(self, operation):
        if self.pending:
            return
        self.pending = True
        self.toggle.configure(state="disabled")
        self.refresh.configure(state="disabled")
        self.republish.configure(state="disabled")
        self.token.configure(state="disabled")
        self.message.set("Kontaktar GitHub…")
        def work():
            try:
                self.events.put((operation(), None))
            except Exception as error:
                self.events.put((None, str(error)))
        threading.Thread(target=work, daemon=True).start()

    def record(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", datetime.now().astimezone().strftime("%H:%M:%S") + "  " + message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def read(self):
        if self.auto_job:
            self.after_cancel(self.auto_job)
            self.auto_job = None
        self.run(PagesClient(self.token.get()).detailed_status)

    def switch(self):
        if self.branch:
            client = PagesClient(self.token.get())
            branch = self.branch
            self.target = "maintenance" if branch == "main" else "main"
            self.started = time.monotonic()
            self.progress.start(12)
            self.record("Begär byte: " + branch + " → " + self.target)
            def change():
                result = client.switch(branch)
                return {**client.detailed_status(), "requested_build": result["requested_build"]}
            self.run(change)

    def rebuild(self):
        if not self.branch or self.pending:
            return
        client = PagesClient(self.token.get())
        branch = self.branch
        self.target = branch
        self.started = time.monotonic()
        self.progress.start(12)
        self.record("Begär ny publicering av " + branch)
        def build():
            result = client.rebuild(branch)
            return {**client.detailed_status(), "requested_build": result["requested_build"]}
        self.run(build)

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
                self.record(error)
            else:
                self.branch = data["source"]["branch"]
                if "requested_build" in data:
                    self.record("GitHub tog emot byggbegäran: " + data["requested_build"].get("status", "mottagen"))
                build = data.get("latest_build") or {}
                live = data.get("live_mode")
                elapsed = int(time.monotonic() - self.started) if self.started else 0
                lines = [f"Vald branch: {self.branch} · katalog: /",
                         f"Pages: {data.get('status', 'okänd')}",
                         f"Senaste bygge (kan avse tidigare byte): {build.get('status', 'ej tillgängligt')}",
                         f"Commit: {build.get('commit', '–')}",
                         f"Bygge startat (UTC): {build.get('created_at', '–')}",
                         f"Byggtid: {build['duration'] / 1000:.1f} sekunder" if isinstance(build.get("duration"), (int, float)) else "Byggtid: –",
                         f"Publik sida: {live or 'kunde inte identifieras'} · HTTP: {data.get('live_http', 'ej tillgänglig')}"]
                if self.started:
                    lines.append(f"Tid sedan begärt byte: {elapsed} sekunder")
                if data.get("build_warning"):
                    lines.append("Byggdetaljer: " + data["build_warning"])
                build_error = (build.get("error") or {}).get("message")
                if build_error:
                    lines.append("Senaste byggfelet: " + build_error)
                self.details.set("\n".join(lines))
                self.record(f"Branch: {self.branch}; Pages: {data.get('status', 'okänd')}; publik sida: {live or 'okänd'}")
                if self.target:
                    if self.branch == self.target and live == self.target:
                        self.record("Klart: önskat läge syns på den publika webbadressen.")
                        self.target = None
                        self.progress.stop()
                    elif elapsed >= 600:
                        self.record("Automatisk bevakning stoppad efter 10 minuter. Läs status för att kontrollera igen.")
                        self.target = None
                        self.progress.stop()
                    else:
                        self.auto_job = self.after(5000, self.read)
                mode = "Vanlig webbplats" if self.branch == "main" else "Underhåll"
                self.message.set(f"Vald källa: {mode}. GitHub-status: {data.get('status', 'okänd')}.\nEtt byte tar en stund att publicera. Läs status igen för att följa det.")
                self.republish.configure(state="disabled" if self.target else "normal")
                self.toggle.configure(state="disabled" if self.target else "normal", text="Aktivera underhåll" if self.branch == "main" else "Visa vanlig webbplats")
        self.after(100, self.poll)


if __name__ == "__main__":
    window = tk.Tk()
    App(window)
    window.mainloop()
