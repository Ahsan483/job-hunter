"""Point-and-click window for the job hunter.

Double-click "Job Hunter.bat" (or run: python -I gui.py). Every button runs bot.py
in the background, so the scheduled runs and the window share the same code,
tracker.csv and jobs.json.
"""
import ast
import datetime as dt
import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.join(HERE, "bot.py")
JOBS_FILE = os.path.join(HERE, "jobs.json")
CONFIG = os.path.join(HERE, "config.json")
TRACKER = os.path.join(HERE, "tracker.csv")
PROFILE = os.path.join(HERE, "profile.json")
TASK = "Remote Job Hunter"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# pythonw has no console; use the console python next to it, hidden, so we can read its output.
PY = os.path.join(os.path.dirname(sys.executable), "python.exe")
if not os.path.exists(PY):
    PY = sys.executable

VIEWS = {
    "Ready to draft (has email)": {"ready"},
    "Apply on company site": {"apply on site"},
    "All matches": {"ready", "apply on site"},
    "Done / skipped": {"done"},
    "Everything (incl. rejected)": {"ready", "apply on site", "done", "rejected"},
}
LABEL = {"ready": "✉ Ready", "apply on site": "🌐 Apply on site", "done": "✔ Done", "rejected": "✖ Rejected"}
DEFAULT_KEYWORDS = [".NET", "C#", "ASP.NET", "dotnet", "Blazor", "Entity Framework"]
SETTINGS = [("min_fit_score", "Minimum fit score (0-100)", int),
            ("max_drafts_per_run", "Max drafts per run", int),
            ("max_drafts_per_day", "Max drafts per day", int),
            ("max_gemini_calls_per_run", "Max Gemini calls per run", int),
            ("gemini_model", "Preferred Gemini model", str)]

LOG_FONT = ("Consolas", 10)
ROW = "  {:<12}{:<15}{:<28}{:<54}{}\n"
ROW_HEAD = ROW.format("STATUS", "SOURCE", "COMPANY", "ROLE", "EMAIL / LINK")
REASON_INDENT = 2 + 12 + 15  # reasons line up under the Company column


def ago(iso):
    try:
        d = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    days = (dt.datetime.now(dt.timezone.utc) - d).days
    return "today" if days <= 0 else f"{days}d ago"


def cut(s, n):
    return s if len(s) <= n else s[:n - 1] + "…"


def row(status, source, company, role, last):
    return ROW.format(status, source, cut(company, 26), cut(role, 52), last)


def pretty(line):
    """Lay out one line of bot.py output. Returns ([(text, tag)], is_table_row)."""
    m = re.match(r"(CANDIDATE|APPLY ON SITE) \[(\w+)\] (.*?) \| (.*) \| (\S+)(?: \(.*\))?$", line)
    if m:
        kind, src, company, role, last = m.groups()
        if role.startswith(company + " | "):  # HN titles repeat the company
            role = role[len(company) + 3:]
        if kind == "CANDIDATE":
            return [(row("READY", src, company, role, last), "ready")], True
        return [(row("ON SITE", src, company, role, last), "site")], True
    m = re.match(r"skip (.*?): eligible=(\S+) fit=(\S+) ?(.*)$", line)
    if m:
        company, _, fit, reason = m.groups()
        out = [(row("NOT A FIT", "gemini", company, f"fit {fit}", ""), "skip")]
        return out + ([(reason + "\n", "reason")] if reason else []), True
    m = re.match(r"DRAFT saved: (.*) -> (\S+) \(fit (.*)\)$", line)
    if m:
        company, mail, fit = m.groups()
        return [(row("DRAFTED", "gemini", company, f"fit {fit}", mail), "good")], True
    m = re.match(r"src_(\w+): (\d+) jobs$", line)
    if m:
        return [(f"  {m.group(1):<18}{m.group(2):>5} jobs\n", "dim")], False
    m = re.match(r"filter: (\{.*\})$", line)
    if m:
        try:
            counts = ast.literal_eval(m.group(1))
            text = "  ·  ".join(f"{k} {v}" for k, v in counts.items())
        except (ValueError, SyntaxError):
            text = m.group(1)
        return [("  Filtered out:  ", "key"), (text + "\n", "dim")], False
    m = re.match(r"\S+ (\d\d:\d\d) \| standalone( dry-run)? \| fetched (\d+) \| candidates (\d+) \| "
                 r"gemini (\d+) \| drafts (\d+)(?: \| (.*))?$", line)
    if m:
        at, dry, fetched, cands, gem, drafts, notes = m.groups()
        text = f"  ■ Finished {at}:  {fetched} jobs checked  ·  {cands} with email"
        text += "  (search only)" if dry else f"  ·  {gem} asked Gemini  ·  {drafts} drafts saved"
        out = [(text + "\n", "summary")]
        return out + ([(f"  Notes: {notes}\n", "err")] if notes else []), False
    tag = "err" if "ERROR" in line or "failed" in line.lower() else "good" if " saved" in line else None
    return [(f"  {line}\n", tag)], False


def read_config():
    try:
        with open(CONFIG, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Job Hunter")
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.jobs, self.by_iid, self.mtime = [], {}, 0
        self.proc, self.out = None, queue.Queue()
        self.sort_col, self.sort_rev = "Posted", False
        self.in_table = False

        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Big.TButton", font=("Segoe UI", 10, "bold"), padding=(10, 6))
        style.configure("TButton", padding=(8, 5))

        self.build_toolbar()
        self.build_cv_row()
        self.build_filters()
        # Jobs on top, console below; drag the divider to resize them.
        self.vpane = ttk.PanedWindow(self, orient="vertical")
        self.vpane.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.build_body()
        self.build_log()
        self.after(200, lambda: self.vpane.sashpos(0, int(self.vpane.winfo_height() * 0.55)))
        self.load_jobs()
        self.refresh_task_button()
        self.after(100, self.pump)
        self.after(3000, self.watch_file)

    # ---------- layout ----------

    def build_toolbar(self):
        bar = ttk.Frame(self, padding=(10, 10, 10, 4))
        bar.pack(fill="x")
        self.busy_buttons = []
        for text, cmd, tip in [
            ("🔍  Find jobs", self.find_jobs, "Search all job sites now (no Gemini, no Gmail)"),
            ("✉  Auto-draft best matches", self.auto_draft, "Same as a scheduled run: Gemini + CV + Gmail drafts"),
        ]:
            b = ttk.Button(bar, text=text, style="Big.TButton", command=cmd)
            b.pack(side="left", padx=(0, 8))
            self.busy_buttons.append(b)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        for text, cmd in [("📧  Gmail drafts", self.open_gmail), ("📂  CVs folder", self.open_cvs),
                          ("📊  Tracker", self.open_tracker), ("📜  Run log", self.open_runs),
                          ("⚙  Settings", self.settings)]:
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=(0, 6))
        self.task_btn = ttk.Button(bar, text="Auto-run: …", command=self.toggle_task)
        self.task_btn.pack(side="right")

    def build_cv_row(self):
        row = ttk.Frame(self, padding=(10, 2))
        row.pack(fill="x")
        ttk.Label(row, text="Your CV:").pack(side="left", padx=(0, 6))
        for text, cmd, busy in [("📤  Upload my CV", self.upload_cv, True),
                                ("👤  My profile", self.open_profile, False),
                                ("📝  Tailor CV to a job description…", self.paste_job, True)]:
            b = ttk.Button(row, text=text, command=cmd)
            b.pack(side="left", padx=(0, 6))
            if busy:
                self.busy_buttons.append(b)
        self.profile_lbl = ttk.Label(row, text="", foreground="#666")
        self.profile_lbl.pack(side="left", padx=(8, 0))
        self.show_profile()

    def show_profile(self):
        try:
            with open(PROFILE, encoding="utf-8") as f:
                p = json.load(f)
            self.profile_lbl.config(text=f"Using: {p['name']}  ·  {p['default_title'][:60]}  ·  "
                                         f"{len(p['experience'])} roles  (profile.json)")
        except (OSError, ValueError, KeyError):
            self.profile_lbl.config(text="No profile yet. Press Upload my CV.")

    def build_filters(self):
        row = ttk.Frame(self, padding=(10, 4))
        row.pack(fill="x")
        ttk.Label(row, text="Show:").pack(side="left")
        self.view = tk.StringVar(value="All matches")
        cb = ttk.Combobox(row, textvariable=self.view, values=list(VIEWS), state="readonly", width=28)
        cb.pack(side="left", padx=(4, 12))
        cb.bind("<<ComboboxSelected>>", lambda e: self.fill_table())
        ttk.Label(row, text="Search in list:").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self.fill_table())
        ttk.Entry(row, textvariable=self.search, width=30).pack(side="left", padx=(4, 12))
        self.count_lbl = ttk.Label(row, text="")
        self.count_lbl.pack(side="left")
        self.updated_lbl = ttk.Label(row, text="", foreground="#666")
        self.updated_lbl.pack(side="right")

        # What the bot looks for. Saved in config.json, so scheduled runs use it too.
        cfg = read_config()
        box = ttk.LabelFrame(self, text=" Job filter (used by Find jobs and the 30-minute auto-run) ", padding=(8, 4))
        box.pack(fill="x", padx=10, pady=(2, 2))
        self.kw = tk.StringVar(value=", ".join(cfg.get("keywords") or DEFAULT_KEYWORDS))
        self.excl = tk.StringVar(value=", ".join(cfg.get("exclude_keywords") or []))
        self.age = tk.StringVar(value=str(cfg.get("max_job_age_days") or 14))
        self.pk_only = tk.BooleanVar(value=cfg.get("worldwide_only", cfg.get("pakistan_only", True)))
        ttk.Label(box, text="Keywords (any of):").pack(side="left")
        ttk.Entry(box, textvariable=self.kw, width=28).pack(side="left", padx=(4, 12), fill="x", expand=True)
        ttk.Label(box, text="Exclude in title:").pack(side="left")
        ttk.Entry(box, textvariable=self.excl, width=22).pack(side="left", padx=(4, 12))
        ttk.Label(box, text="Max age (days):").pack(side="left")
        ttk.Spinbox(box, from_=1, to=60, textvariable=self.age, width=4).pack(side="left", padx=(4, 12))
        ttk.Checkbutton(box, text="Only open worldwide / to my region", variable=self.pk_only).pack(side="left",
                                                                                                  padx=(0, 12))
        b = ttk.Button(box, text="🔍  Save & search", command=self.find_jobs)
        b.pack(side="left")
        self.busy_buttons.append(b)

    def build_body(self):
        pane = ttk.PanedWindow(self.vpane, orient="horizontal")
        self.vpane.add(pane, weight=3)

        left = ttk.Frame(pane)
        cols = ("Status", "Posted", "Company", "Role", "Location", "Salary")
        widths = (115, 65, 120, 240, 130, 100)
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for c, w in zip(cols, widths):
            self.tree.heading(c, text=c, command=lambda c=c: self.sort_by(c))
            self.tree.column(c, width=w, minwidth=50, stretch=c in ("Role", "Company", "Location"))
        self.tree.tag_configure("ready", background="#e7f6e7")
        self.tree.tag_configure("apply on site", background="#eaf1fb")
        self.tree.tag_configure("done", foreground="#888")
        self.tree.tag_configure("rejected", foreground="#a33")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_detail())
        self.tree.bind("<Double-1>", lambda e: self.open_job())
        pane.add(left, weight=3)

        right = ttk.Frame(pane, padding=(8, 0, 0, 0))
        acts = ttk.Frame(right)
        acts.pack(fill="x", pady=(0, 6))
        self.b_open = ttk.Button(acts, text="🌐  Open job page", command=self.open_job)
        self.b_draft = ttk.Button(acts, text="✉  Draft email + CV", style="Big.TButton", command=lambda: self.act("draft"))
        self.b_cv = ttk.Button(acts, text="📄  Make CV + cover letter", command=lambda: self.act("cv"))
        self.b_copy = ttk.Button(acts, text="📋  Copy email", command=self.copy_email)
        self.b_skip = ttk.Button(acts, text="🚫  Skip job", command=lambda: self.act("skip"))
        for i, b in enumerate((self.b_draft, self.b_cv, self.b_open, self.b_copy, self.b_skip)):
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
        for i in range(2):
            acts.columnconfigure(i, weight=1)
        self.detail = tk.Text(right, wrap="word", font=("Segoe UI", 10), padx=10, pady=8, relief="flat",
                              background="#fbfbfb", state="disabled")
        dsb = ttk.Scrollbar(right, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=dsb.set)
        self.detail.tag_configure("h1", font=("Segoe UI", 14, "bold"), spacing3=4)
        self.detail.tag_configure("h2", font=("Segoe UI", 11), foreground="#444", spacing3=8)
        self.detail.tag_configure("key", font=("Segoe UI", 10, "bold"))
        self.detail.tag_configure("link", foreground="#1a5fb4", underline=True)
        self.detail.tag_bind("link", "<Button-1>", lambda e: self.open_job())
        self.detail.tag_bind("link", "<Enter>", lambda e: self.detail.config(cursor="hand2"))
        self.detail.tag_bind("link", "<Leave>", lambda e: self.detail.config(cursor=""))
        self.detail.pack(side="left", fill="both", expand=True)
        dsb.pack(side="left", fill="y")
        pane.add(right, weight=2)
        self.set_job_buttons(None)

    def build_log(self):
        box = ttk.Frame(self.vpane, padding=(0, 6, 0, 0))
        top = ttk.Frame(box)
        top.pack(fill="x")
        self.status_lbl = ttk.Label(top, text="Ready.")
        self.status_lbl.pack(side="left")
        ttk.Button(top, text="Clear", command=self.clear_log).pack(side="right")
        self.bar = ttk.Progressbar(top, mode="indeterminate", length=180)
        body = ttk.Frame(box)
        body.pack(fill="both", expand=True, pady=(4, 0))
        self.log = tk.Text(body, height=16, wrap="none", font=LOG_FONT, background="#1e1e1e", foreground="#ddd",
                           insertbackground="#ddd", relief="flat", padx=8, pady=6, spacing1=1, state="disabled")
        ysb = ttk.Scrollbar(body, orient="vertical", command=self.log.yview)
        xsb = ttk.Scrollbar(body, orient="horizontal", command=self.log.xview)
        self.log.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        bold = LOG_FONT + ("bold",)
        indent = tkfont.Font(self, font=LOG_FONT).measure(" " * REASON_INDENT)
        self.log.tag_configure("head", foreground="#ffffff", font=bold, spacing1=8, spacing3=4)
        self.log.tag_configure("colhead", foreground="#8b949e", font=bold)
        self.log.tag_configure("ready", foreground="#7ee787")
        self.log.tag_configure("site", foreground="#79c0ff")
        self.log.tag_configure("skip", foreground="#e3b341")
        self.log.tag_configure("reason", foreground="#b1a27a", wrap="word", lmargin1=indent, lmargin2=indent,
                               spacing3=4)
        self.log.tag_configure("good", foreground="#7ee787", font=bold)
        self.log.tag_configure("err", foreground="#ff7b72")
        self.log.tag_configure("dim", foreground="#8b949e")
        self.log.tag_configure("key", foreground="#ddd", font=bold)
        self.log.tag_configure("summary", foreground="#d2a8ff", font=bold, spacing1=4)
        self.vpane.add(box, weight=2)

    # ---------- data ----------

    def load_jobs(self):
        try:
            self.mtime = os.path.getmtime(JOBS_FILE)
            with open(JOBS_FILE, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {"updated": "", "jobs": []}
        self.jobs = d["jobs"]
        self.updated_lbl.config(text=f"Last search: {d['updated']}" if d["updated"] else "No search yet. Press Find jobs.")
        self.fill_table()

    def watch_file(self):
        try:
            if os.path.getmtime(JOBS_FILE) != self.mtime:
                self.load_jobs()
        except OSError:
            pass
        self.after(3000, self.watch_file)

    def row_values(self, j):
        status = LABEL.get(j["status"], j["status"])
        if j["status"] in ("done", "rejected") and j.get("why"):
            status = f"{status[:1]} {j['why']}"
        return (status, ago(j.get("date")), j["company"], j["title"], j["location"][:60],
                j.get("salary", ""))

    def fill_table(self):
        keep = self.tree.selection()
        keep = self.by_iid.get(keep[0], {}).get("id") if keep else None
        self.tree.delete(*self.tree.get_children())
        self.by_iid = {}
        want, q = VIEWS[self.view.get()], self.search.get().lower().strip()
        rows = [j for j in self.jobs if j["status"] in want and
                (not q or q in f"{j['title']} {j['company']} {j['location']} {j.get('tags', '')} {j['text']}".lower())]
        idx = ("Status", "Posted", "Company", "Role", "Location", "Salary").index(self.sort_col)
        if self.sort_col == "Posted":
            rows.sort(key=lambda j: j.get("date") or "", reverse=not self.sort_rev)
        else:
            rows.sort(key=lambda j: str(self.row_values(j)[idx]).lower(), reverse=self.sort_rev)
        again = None
        for j in rows:
            iid = self.tree.insert("", "end", values=self.row_values(j), tags=(j["status"],))
            self.by_iid[iid] = j
            if j["id"] == keep:
                again = iid
        self.count_lbl.config(text=f"{len(rows)} jobs  ·  "
                              f"{sum(j['status'] == 'ready' for j in self.jobs)} ready, "
                              f"{sum(j['status'] == 'apply on site' for j in self.jobs)} apply on site, "
                              f"{len(self.jobs)} checked")
        if again:
            self.tree.selection_set(again)
            self.tree.see(again)
        else:
            self.show_detail()

    def sort_by(self, col):
        self.sort_rev = not self.sort_rev if self.sort_col == col else False
        self.sort_col = col
        self.fill_table()

    def selected(self):
        s = self.tree.selection()
        return self.by_iid.get(s[0]) if s else None

    def show_detail(self):
        j = self.selected()
        self.set_job_buttons(j)
        t = self.detail
        t.config(state="normal")
        t.delete("1.0", "end")
        if not j:
            t.insert("end", "Pick a job on the left to see the details.", "h2")
            t.config(state="disabled")
            return
        t.insert("end", j["title"] + "\n", "h1")
        t.insert("end", f"{j['company']}  ·  {j['location'][:120]}\n", "h2")
        facts = [("Status", LABEL.get(j["status"], j["status"]) + (f"  ({j['why']})" if j.get("why") else "")),
                 ("Posted", (j.get("date") or "")[:10] + (f"  ({ago(j.get('date'))})" if j.get("date") else "")),
                 ("Salary", j.get("salary", "")), ("Type", j.get("job_type", "")), ("Level", j.get("level", "")),
                 ("Tags", j.get("tags", "")), ("Email", j.get("email", "")),
                 ("Email found on", j.get("email_src", "")), ("Source", j["source"])]
        for k, v in facts:
            if v:
                t.insert("end", f"{k}: ", "key")
                t.insert("end", f"{v}\n")
        t.insert("end", "Link: ", "key")
        t.insert("end", j.get("apply") or j["url"], "link")
        t.insert("end", "\n\n")
        t.insert("end", j["text"])
        t.config(state="disabled")
        t.yview_moveto(0)

    def set_job_buttons(self, j):
        busy = self.proc is not None
        open_ = j is not None and j["status"] in ("ready", "apply on site")
        self.b_open.state(["!disabled"] if j else ["disabled"])
        self.b_copy.state(["!disabled"] if j and j.get("email") else ["disabled"])
        self.b_draft.state(["!disabled"] if open_ and j.get("email") and not busy else ["disabled"])
        self.b_cv.state(["!disabled"] if j and j["status"] != "rejected" and not busy else ["disabled"])
        self.b_skip.state(["!disabled"] if open_ and not busy else ["disabled"])

    # ---------- running bot.py ----------

    def run_bot(self, args, what):
        if self.proc:
            return
        self.write_log(f"\n▶ {what}\n", "head")
        self.status_lbl.config(text=f"{what} …")
        try:
            self.proc = subprocess.Popen([PY, "-I", "-X", "utf8", "-u", BOT, *args], cwd=HERE,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                         encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        except OSError as e:
            self.write_log(f"Could not start bot.py: {e}\n")
            return
        self.bar.pack(side="right")
        self.bar.start(12)
        for b in self.busy_buttons:
            b.state(["disabled"])
        self.set_job_buttons(self.selected())
        threading.Thread(target=self.reader, args=(self.proc,), daemon=True).start()

    def reader(self, proc):
        for line in proc.stdout:
            self.out.put(line)
        proc.wait()
        self.out.put(None)

    def pump(self):
        try:
            while True:
                line = self.out.get_nowait()
                if line is None:
                    self.finished()
                else:
                    self.log_line(line)
        except queue.Empty:
            pass
        self.after(100, self.pump)

    def finished(self):
        self.proc = None
        self.bar.stop()
        self.bar.pack_forget()
        self.status_lbl.config(text="Done. " + dt.datetime.now().strftime("%H:%M"))
        for b in self.busy_buttons:
            b.state(["!disabled"])
        self.load_jobs()
        self.show_profile()

    def write_log(self, s, tag=None):
        self.in_table = False
        self.log.config(state="normal")
        self.log.insert("end", s, tag)
        self.log.see("end")
        self.log.config(state="disabled")

    def log_line(self, line):
        """One line of bot.py output, with a column header before each run of job rows."""
        pieces, is_row = pretty(line.rstrip("\n"))
        if is_row and not self.in_table:
            pieces = [(ROW_HEAD, "colhead")] + pieces
        self.log.config(state="normal")
        for text, tag in pieces:
            m = re.search(r"[A-Za-z]:\\.+?\.(?:pdf|txt|json)\b", text)
            if not m:
                self.log.insert("end", text, tag)
                continue
            # Saved files are links: click to open.
            link = f"file{self.log.index('end')}"
            self.log.tag_configure(link, foreground="#79c0ff", underline=True)
            self.log.tag_bind(link, "<Button-1>", lambda e, p=m.group(): os.startfile(p))
            self.log.tag_bind(link, "<Enter>", lambda e: self.log.config(cursor="hand2"))
            self.log.tag_bind(link, "<Leave>", lambda e: self.log.config(cursor=""))
            self.log.insert("end", text[:m.start()], tag)
            self.log.insert("end", m.group(), (tag, link) if tag else link)
            self.log.insert("end", text[m.end():], tag)
        self.log.see("end")
        self.log.config(state="disabled")
        self.in_table = is_row

    def clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        self.in_table = False

    def find_jobs(self):
        if self.save_filter():
            self.search.set("")
            self.run_bot(["--dry-run"], "Searching job sites (takes 1-3 minutes)")

    def auto_draft(self):
        if self.save_filter():
            self.search.set("")
            self.run_bot([], "Finding jobs and drafting the best matches")

    def act(self, mode):
        j = self.selected()
        if not j:
            return
        what = {"draft": f"Drafting email + CV for {j['company']}",
                "cv": f"Making CV + cover letter for {j['company']}",
                "skip": f"Skipping {j['company']}"}[mode]
        self.run_bot(["--job", j["id"], mode], what)

    # ---------- simple actions ----------

    def open_job(self):
        j = self.selected()
        url = j and (j.get("apply") or j["url"])
        if url and url.lower().startswith(("https://", "http://")):
            webbrowser.open(url)

    def copy_email(self):
        j = self.selected()
        if j and j.get("email"):
            self.clipboard_clear()
            self.clipboard_append(j["email"])
            self.status_lbl.config(text=f"Copied {j['email']}")

    def open_gmail(self):
        who = read_config().get("gmail_address", "")
        webbrowser.open(f"https://mail.google.com/mail/?authuser={who}#drafts" if who
                        else "https://mail.google.com/mail/#drafts")

    def open_cvs(self):
        os.makedirs(os.path.join(HERE, "cvs"), exist_ok=True)
        os.startfile(os.path.join(HERE, "cvs"))

    def open_tracker(self):
        if os.path.exists(TRACKER):
            os.startfile(TRACKER)

    def open_profile(self):
        subprocess.Popen(["notepad.exe", PROFILE])

    def upload_cv(self):
        path = filedialog.askopenfilename(parent=self, title="Choose your CV",
                                          filetypes=[("CV", "*.pdf *.docx *.txt *.md"), ("All files", "*.*")])
        if not path:
            return
        if not messagebox.askokcancel("Upload my CV", "Gemini will read this CV and rebuild profile.json from it.\n\n"
                                      "Every tailored CV, cover letter and email is built only from profile.json. "
                                      "Your current profile is kept as a backup.\n\nContinue?", parent=self):
            return
        self.run_bot(["--import-cv", path], f"Reading your CV: {os.path.basename(path)}")

    def paste_job(self):
        win = tk.Toplevel(self)
        win.title("Tailor CV to a job description")
        win.transient(self)
        win.geometry("760x620")
        frm = ttk.Frame(win, padding=14)
        frm.pack(fill="both", expand=True)
        j = self.selected()
        fields = {}
        for i, (key, label, start) in enumerate([("company", "Company", j["company"] if j else ""),
                                                 ("title", "Job title", j["title"] if j else ""),
                                                 ("url", "Link (optional)", (j.get("apply") or j["url"]) if j else "")]):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=3)
            fields[key] = tk.StringVar(value=start)
            ttk.Entry(frm, textvariable=fields[key]).grid(row=i, column=1, sticky="ew", padx=(10, 0), pady=3)
        ttk.Label(frm, text="Paste the full job description:").grid(row=3, column=0, columnspan=2, sticky="w",
                                                                    pady=(10, 3))
        text = tk.Text(frm, wrap="word", font=("Segoe UI", 10), height=18, undo=True)
        text.grid(row=4, column=0, columnspan=2, sticky="nsew")
        if j:
            text.insert("1.0", j["text"])
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(4, weight=1)

        def go():
            job = {k: v.get().strip() for k, v in fields.items()}
            job["text"] = text.get("1.0", "end").strip()
            if not job["company"] or not job["title"] or len(job["text"]) < 100:
                messagebox.showerror("Tailor CV", "Fill in the company, the job title and the full description.",
                                     parent=win)
                return
            path = os.path.join(HERE, "tailor", "pasted-job.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False)
            win.destroy()
            self.run_bot(["--custom", path], f"Tailoring your CV + cover letter for {job['company']}")

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="📄  Make CV + cover letter", style="Big.TButton", command=go).pack(side="right")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=6)
        win.grab_set()

    def open_runs(self):
        p = os.path.join(HERE, "runs.log")
        if os.path.exists(p):
            os.startfile(p)

    # ---------- scheduled task ----------

    def task_state(self):
        try:
            r = subprocess.run(["schtasks", "/Query", "/TN", TASK, "/FO", "CSV", "/NH"], capture_output=True,
                               text=True, creationflags=NO_WINDOW, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode:
            return None
        return "off" if "Disabled" in r.stdout else "on"

    def refresh_task_button(self):
        s = self.task_state()
        self.task_btn.config(text={"on": "⏱  Auto-run every 30 min: ON", "off": "⏸  Auto-run: OFF",
                                   None: "Auto-run: not set up"}[s])
        self.task_btn.state(["disabled"] if s is None else ["!disabled"])

    def toggle_task(self):
        s = self.task_state()
        if s is None:
            return
        r = subprocess.run(["schtasks", "/Change", "/TN", TASK, "/DISABLE" if s == "on" else "/ENABLE"],
                           capture_output=True, text=True, creationflags=NO_WINDOW, timeout=15)
        if r.returncode:
            messagebox.showerror("Job Hunter", (r.stderr or r.stdout).strip() or "Could not change the task.")
        self.refresh_task_button()

    # ---------- settings ----------

    def save_filter(self):
        """Write the filter bar to config.json. Returns False (and says why) if it is not valid."""
        words = lambda v: [w.strip() for w in v.get().split(",") if w.strip()]
        if not words(self.kw):
            messagebox.showerror("Job filter", "Type at least one keyword, e.g.  .NET, C#, Angular")
            return False
        try:
            age = max(1, int(self.age.get()))
        except ValueError:
            messagebox.showerror("Job filter", "Max age must be a number of days.")
            return False
        cfg = read_config()
        new = dict(keywords=words(self.kw), exclude_keywords=words(self.excl), max_job_age_days=age,
                   worldwide_only=self.pk_only.get())
        if any(cfg.get(k) != v for k, v in new.items()):
            cfg.update(new)
            cfg.pop("pakistan_only", None)
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self.write_log(f"\nFilter saved: keywords {', '.join(new['keywords'])}"
                           + (f" | exclude {', '.join(new['exclude_keywords'])}" if new["exclude_keywords"] else "")
                           + f" | max age {age} days"
                           + (" | worldwide/my region only\n" if new["worldwide_only"] else " | any country\n"))
        return True

    def settings(self):
        cfg = read_config()
        win = tk.Toplevel(self)
        win.title("Settings")
        win.transient(self)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=16)
        frm.pack()
        vars_ = {}
        for i, (key, label, _) in enumerate(SETTINGS):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=4)
            v = tk.StringVar(value=str(cfg.get(key, "")))
            ttk.Entry(frm, textvariable=v, width=26).grid(row=i, column=1, padx=(12, 0), pady=4)
            vars_[key] = v

        def save():
            new = read_config()
            try:
                for key, label, typ in SETTINGS:
                    new[key] = typ(vars_[key].get().strip())
            except ValueError:
                messagebox.showerror("Settings", f"'{label}' must be a number.", parent=win)
                return
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(new, f, indent=2)
            win.destroy()
            self.status_lbl.config(text="Settings saved.")

        btns = ttk.Frame(frm)
        btns.grid(row=len(SETTINGS), column=0, columnspan=2, pady=(12, 0), sticky="ew")
        ttk.Button(btns, text="Edit Gmail / Gemini keys…",
                   command=lambda: subprocess.Popen(["notepad.exe", CONFIG])).pack(side="left")
        ttk.Button(btns, text="Save", style="Big.TButton", command=save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=6)
        win.grab_set()


if __name__ == "__main__":
    App().mainloop()
