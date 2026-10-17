#!/usr/bin/env python3
"""Desktop control for Runcom's GitHub Pages source. Python standard library only."""
import json
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html.parser import HTMLParser
import tkinter as tk
from tkinter import ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import webbrowser

REPOSITORY = "tvrdprijatelj/runcom"
SETTINGS = f"https://github.com/{REPOSITORY}/settings/pages"
API_TIMEOUT = 15
PUBLIC_TIMEOUT = 6
PUBLIC_READ_LIMIT = 128 * 1024
UI_POLL_INTERVAL_MS = 50


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
            with urlopen(request, timeout=API_TIMEOUT) as response:
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
        # A successful PUT means GitHub accepted this source. Reusing the
        # response we already validated saves a full API round trip before
        # the build can start.
        updated = {**current, "source": {**current["source"], "branch": target, "path": "/"}}
        return self._request_build(updated, target)

    def rebuild(self, expected):
        current = self.status()
        if current["source"]["branch"] != expected:
            raise ValueError("Pages-källan ändrades. Läs status igen före publicering.")
        return self._request_build(current, expected)

    def _request_build(self, current, expected):
        try:
            result = self.request("POST", suffix="/builds")
        except ValueError as error:
            raise ValueError(f"Vald branch är {expected}, men byggbegäran misslyckades: {error} Använd Publicera vald branch igen efter att du läst status.") from None
        return {**current, "requested_build": result}

    def detailed_status(self):
        # These calls are independent. Starting all three together reduces a
        # refresh from two network round trips to one on a healthy connection.
        with ThreadPoolExecutor(max_workers=3) as executor:
            status = executor.submit(self.status)
            build = executor.submit(self.request, suffix="/builds/latest")
            live = executor.submit(self.live_status)
            data = status.result()
            try:
                data["latest_build"] = build.result()
            except ValueError as error:
                data["build_warning"] = str(error)
            data.update(live.result())
        return data

    def live_status(self):
        # Public probe deliberately uses no Authorization header.
        try:
            request = Request("https://tvrdprijatelj.github.io/runcom/?pages-check=" + str(time.time_ns()),
                              headers={"Cache-Control": "no-cache", "User-Agent": "Runcom-Pages-Switcher"})
            with urlopen(request, timeout=PUBLIC_TIMEOUT) as response:
                return {"live_http": response.status,
                        "live_mode": identify_page(response.read(PUBLIC_READ_LIMIT).decode("utf-8", errors="replace"))}
        except (URLError, OSError, TimeoutError):
            return {"live_mode": None}


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


def monitor_delay_ms(elapsed, build_requested=False):
    """Return a responsive polling interval without hammering GitHub's API."""
    if build_requested:
        return 750
    if elapsed < 20:
        return 1500
    if elapsed < 90:
        return 3000
    return 5000


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
        root.minsize(650, 760)
        ttk.Label(self, text="Runcom · Webbplats", font=("", 22, "bold")).pack(anchor="w")
        ttk.Label(self, text="Växla snabbt mellan den vanliga webbplatsen och underhållssidan.",
                  wraplength=580).pack(anchor="w", pady=(2, 3))
        ttk.Label(self, text=REPOSITORY).pack(anchor="w", pady=(0, 20))
        ttk.Label(self, text="GitHub-token (sparas bara medan appen är öppen)").pack(anchor="w")
        token_row = ttk.Frame(self)
        token_row.pack(fill="x", pady=(5, 12))
        self.token_value = tk.StringVar(value=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", ""))
        self.token = ttk.Entry(token_row, textvariable=self.token_value, show="•")
        self.token.pack(side="left", fill="x", expand=True)
        self.show_token = tk.BooleanVar()
        ttk.Checkbutton(token_row, text="Visa", variable=self.show_token,
                        command=self.toggle_token_visibility).pack(side="left", padx=(10, 0))
        ttk.Label(self, text="Välj endast runcom när du skapar token. Behörigheter:\nPages och Administration → Read and write.", wraplength=500).pack(anchor="w")
        ttk.Button(self, text="Skapa GitHub-token ↗", command=lambda: webbrowser.open("https://github.com/settings/personal-access-tokens/new")).pack(anchor="w", pady=10)
        self.message = tk.StringVar(value="Läs status för att ansluta till GitHub.")
        ttk.Label(self, textvariable=self.message, wraplength=500).pack(anchor="w", pady=16)
        self.toggle = ttk.Button(self, text="Läs status först", command=self.switch, state="disabled")
        self.toggle.pack(fill="x", ipady=10)
        action_row = ttk.Frame(self)
        action_row.pack(fill="x", pady=10)
        action_row.columnconfigure((0, 1), weight=1)
        self.refresh = ttk.Button(action_row, text="Läs status  Ctrl+R", command=self.read)
        self.refresh.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.republish = ttk.Button(action_row, text="Publicera igen", command=self.rebuild, state="disabled")
        self.republish.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.stop = ttk.Button(self, text="Stoppa automatisk bevakning", command=self.stop_monitoring, state="disabled")
        self.stop.pack(fill="x", pady=(0, 10))
        ttk.Button(self, text="Öppna Pages-inställningar ↗", command=lambda: webbrowser.open(SETTINGS)).pack(anchor="w")
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", pady=(16, 8))
        self.checked = tk.StringVar(value="Inte kontrollerad ännu")
        ttk.Label(self, textvariable=self.checked, font=("", 9)).pack(anchor="w", pady=(0, 6))
        self.details = tk.StringVar(value="Ingen status hämtad ännu.")
        ttk.Label(self, textvariable=self.details, wraplength=580, justify="left").pack(anchor="w")
        ttk.Label(self, text="Händelser", font=("", 11, "bold")).pack(anchor="w", pady=(12, 4))
        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=7, wrap="word", state="disabled")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")
        self.token_value.trace_add("write", self.invalidate)
        self.token.bind("<Return>", lambda _event: self.read())
        root.bind("<Control-r>", lambda _event: self.read())
        root.bind("<Control-R>", lambda _event: self.read())
        root.bind("<Escape>", lambda _event: self.stop_monitoring())
        root.after(UI_POLL_INTERVAL_MS, self.poll)
        if self.token.get():
            root.after(150, self.read)

    def toggle_token_visibility(self):
        self.token.configure(show="" if self.show_token.get() else "•")

    def cancel_auto_read(self):
        if self.auto_job is not None:
            self.after_cancel(self.auto_job)
            self.auto_job = None

    def invalidate(self, *_args):
        self.cancel_auto_read()
        self.target = None
        self.started = None
        self.progress.stop()
        self.branch = None
        self.toggle.configure(state="disabled", text="Läs status först")
        self.republish.configure(state="disabled")
        self.stop.configure(state="disabled")

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
        self.cancel_auto_read()
        self.run(PagesClient(self.token.get()).detailed_status)

    def schedule_read(self, delay):
        self.cancel_auto_read()
        self.auto_job = self.after(delay, self.auto_read)

    def auto_read(self):
        self.auto_job = None
        self.read()

    def stop_monitoring(self):
        if not self.target:
            return
        self.cancel_auto_read()
        self.target = None
        self.started = None
        self.progress.stop()
        self.stop.configure(state="disabled")
        if self.branch and not self.pending:
            self.toggle.configure(state="normal")
            self.republish.configure(state="normal")
        self.message.set("Automatisk bevakning stoppad. Läs status när du vill kontrollera igen.")
        self.record("Automatisk bevakning stoppad.")

    def switch(self):
        if self.branch:
            client = PagesClient(self.token.get())
            branch = self.branch
            self.target = "maintenance" if branch == "main" else "main"
            self.started = time.monotonic()
            self.progress.start(12)
            self.record("Begär byte: " + branch + " → " + self.target)
            self.run(lambda: client.switch(branch))

    def rebuild(self):
        if not self.branch or self.pending:
            return
        client = PagesClient(self.token.get())
        branch = self.branch
        self.target = branch
        self.started = time.monotonic()
        self.progress.start(12)
        self.record("Begär ny publicering av " + branch)
        self.run(lambda: client.rebuild(branch))

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
                self.checked.set("Senast kontrollerad " + datetime.now().astimezone().strftime("%H:%M:%S"))
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
                        self.schedule_read(monitor_delay_ms(elapsed, "requested_build" in data))
                mode = "Vanlig webbplats" if self.branch == "main" else "Underhåll"
                self.message.set(f"Vald källa: {mode}. GitHub-status: {data.get('status', 'okänd')}.\nEtt byte tar en stund att publicera. Läs status igen för att följa det.")
                self.republish.configure(state="disabled" if self.target else "normal")
                self.toggle.configure(state="disabled" if self.target else "normal", text="Aktivera underhåll" if self.branch == "main" else "Visa vanlig webbplats")
                self.stop.configure(state="normal" if self.target else "disabled")
        self.after(UI_POLL_INTERVAL_MS, self.poll)


if __name__ == "__main__":
    window = tk.Tk()
    App(window)
    window.mainloop()
