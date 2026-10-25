"""Point-and-click window for the job hunter.

Double-click "Job Hunter.bat" (or run: python -I gui.py), or install JobHunterSetup.exe.
Every button runs bot.py in the background, so the scheduled runs and the window share
the same code, tracker.csv and jobs.json.
"""
import ast
import datetime as dt
import imaplib
import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

# python -I leaves the script's folder off sys.path; bot.py sits next to this file.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot  # noqa: E402

# The installed JobHunter.exe sits in a read-only program folder, so it keeps your files in %APPDATA%\Job Hunter.
FROZEN = getattr(sys, "frozen", False)
HERE = (os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Job Hunter") if FROZEN
        else os.path.dirname(os.path.abspath(__file__)))
os.makedirs(HERE, exist_ok=True)
ICON = (os.path.join(sys._MEIPASS, "icon.ico") if FROZEN
        else os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer", "icon.ico"))
JOBS_FILE = os.path.join(HERE, "jobs.json")
CONFIG = os.path.join(HERE, "config.json")
TRACKER = os.path.join(HERE, "tracker.csv")
PROFILE = os.path.join(HERE, "profile.json")
LOCK = os.path.join(HERE, "bot.lock")
AUTO_MODEL = "Auto: best free model that is not at its limit"
TASK = "Remote Job Hunter"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# pythonw has no console; use the console python next to it, hidden, so we can read its output.
# JobHunter.exe runs the bot itself when started with --bot.
PY = os.path.join(os.path.dirname(sys.executable), "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
BOT = [sys.executable, "--bot"] if FROZEN else [PY, "-I", "-X", "utf8", "-u", os.path.join(HERE, "bot.py")]
# What the 30-minute scheduled task runs: no console window either way.
PYW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
TASK_RUN = (f'"{sys.executable}" --bot' if FROZEN
            else f'"{PYW if os.path.exists(PYW) else sys.executable}" -I "{os.path.join(HERE, "bot.py")}"')

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

# Job type -> (keywords, We Work Remotely categories from bot.WWR_FEEDS, keywords must be in the title).
# Words like "Sales" or "Finance" are in almost every job ad, so most presets match on the title only.
# Put the most important keywords first: the sites that have a search get the first ten.
PRESETS = {
    "Software / .NET": (DEFAULT_KEYWORDS, ["software"], False),
    "Software (any stack)": (["Developer", "Engineer", "Programmer", "Full Stack", "Backend", "Frontend"],
                             ["software", "devops"], True),
    "SEO / Digital marketing": (["SEO", "Marketing", "Social Media", "PPC", "Google Ads", "Email Marketing",
                                 "Content Marketing", "Digital Marketing", "Paid Media", "Performance Marketing",
                                 "Growth", "Media Buyer", "Community Manager"], ["sales & marketing", "other"], True),
    "Writing / Content": (["Writer", "Copywriter", "Content", "Editor", "Proofreader", "Ghostwriter",
                           "Content Strategist", "Blog"], ["other", "sales & marketing"], True),
    "Finance / Accounting": (["Accountant", "Bookkeeper", "Accounting", "Accounts Payable", "Accounts Receivable",
                              "Payroll", "Financial Analyst", "Finance", "Financial", "FP&A", "Controller", "Tax",
                              "Auditor", "Billing"], ["finance & management"], True),
    "Sales / Business development": (["Sales", "SDR", "BDR", "Sales Development", "Business Development",
                                      "Lead Generation", "Appointment Setter", "Account Executive",
                                      "Account Manager", "CRM", "Inside Sales", "Partnerships", "Customer Success"],
                                     ["sales & marketing"], True),
    "Customer support / success": (["Customer Support", "Customer Success", "Customer Service", "Technical Support",
                                    "Support Specialist", "Support Agent", "Support Representative", "Live Chat",
                                    "Chat Support", "Help Desk", "Helpdesk", "Client Services", "Moderator"],
                                   ["customer support"], True),
    "Operations / Admin / Virtual assistant": (["Virtual Assistant", "Executive Assistant", "Operations",
                                                "Administrative", "Admin Assistant", "Project Coordinator",
                                                "Data Entry", "Personal Assistant", "Office Manager", "Coordinator",
                                                "Workforce Management"], ["other", "finance & management"], True),
    "HR / Recruiting": (["Recruiter", "Sourcer", "Talent Acquisition", "Recruiting", "Recruitment", "HR",
                         "Human Resources", "People Operations", "People Partner", "Talent"],
                        ["finance & management", "other"], True),
    "AI training / Research": (["AI Trainer", "AI Training", "Data Annotator", "Annotation", "Annotator",
                                "Data Labeling", "Rater", "Evaluator", "Search Quality", "AI Tutor", "RLHF",
                                "Data Quality", "Research Assistant", "Online Researcher"], ["other", "software"],
                               True),
    "Translation / Transcription": (["Translator", "Translation", "Transcription", "Transcriptionist", "Interpreter",
                                     "Localization", "Linguist", "Subtitler", "Captioner"], ["other"], True),
    "Teaching / Tutoring": (["Tutor", "Teacher", "Instructor", "ESL", "English Teacher", "Curriculum",
                             "Instructional Designer"], ["other"], True),
    "Design": (["Designer", "UI", "UX", "Graphic", "Illustrator", "Motion"], ["design"], True),
    "Data / Analytics": (["Data Analyst", "Data Scientist", "Analytics", "Business Intelligence", "BI",
                          "Data Engineer"], ["software", "other"], True),
    "Project / Product management": (["Project Manager", "Product Manager", "Program Manager", "Scrum Master",
                                      "Product Owner"], ["product", "finance & management"], True),
}
CUSTOM = "Custom (my own keywords)"  # reads every We Work Remotely category


def combine(names):
    """Keywords, We Work Remotely categories and title-only for several job types searched together.
    Keywords are interleaved so the first ten (the ones sent to search boxes) cover every chosen type."""
    lists = [PRESETS[n][0] for n in names]
    kws = []
    for i in range(max(map(len, lists), default=0)):
        for words in lists:
            if i < len(words) and words[i].lower() not in (k.lower() for k in kws):
                kws.append(words[i])
    fields = list(dict.fromkeys(f for n in names for f in PRESETS[n][1]))
    return kws, fields, any(PRESETS[n][2] for n in names)

LOG_FONT = ("Consolas", 10)
ROW = "  {:<12}{:<15}{:<28}{:<54}{}\n"
ROW_HEAD = ROW.format("STATUS", "SOURCE", "COMPANY", "ROLE", "EMAIL / LINK")
REASON_INDENT = 2 + 12 + 15  # reasons line up under the Company column

# ---------- look ----------
# Tk has no see-through widgets, so the glass is faked: the background is a still gradient of diagonal colour
# bands, and each card takes the colour under its centre mixed with white (dark for the console).
# Inputs, the table and text boxes stay solid.
GRADIENT = [(15, 23, 42), (30, 58, 138), (30, 41, 59), (23, 37, 84)]  # slate and navy
PERIOD = 2400   # pixels along the diagonal before the colours repeat
BAND = 6        # width of one colour band
GAP, PAD, RADIUS = 14, 10, 14  # space between cards, card padding, corner radius
FROST, SMOKE = 0.92, 0.55       # how much white (light cards) or near-black (console) covers the gradient
WHITE, NIGHT = (255, 255, 255), (11, 18, 32)
INK, MUTED, LIGHT_INK, LIGHT_MUTED = "#0f172a", "#475569", "#e2e8f0", "#94a3b8"
SURFACE, LINE, ACCENT, CONSOLE, DIALOG = "#ffffff", "#cbd5e1", "#2563eb", "#0b1220", "#f1f5f9"


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


def has_key(cfg, key):
    v = cfg.get(key)
    return bool(v) and not v.startswith("PUT-")


# ---------- connecting Gmail and Gemini ----------

# (field, label, secret, help steps, links). Shown in the "Connect your accounts" window.
KEY_FIELDS = [
    ("gemini_api_key", "Gemini API key", True,
     ["Open Google AI Studio and sign in with any Google account.",
      "Press Create API key (accept the terms if asked) and copy the key. It starts with AIza.",
      "Paste it here. The free tier is enough and needs no card."],
     [("Open Google AI Studio", "https://aistudio.google.com/apikey")]),
    ("gmail_address", "Gmail address (optional)", False, None, []),
    ("gmail_app_password", "Gmail app password", True,
     ["Google only gives app passwords to accounts with 2-Step Verification. Turn it on first if it is off.",
      "Open App passwords, type a name such as Job Hunter and press Create.",
      "Copy the 16-letter password Google shows and paste it here. The spaces do not matter.",
      "Note: use this app password, not your normal Gmail password. Some work and school accounts do not allow "
      "app passwords: use a personal Gmail account then."],
     [("Turn on 2-Step Verification", "https://myaccount.google.com/signinoptions/twosv"),
      ("Open App passwords", "https://myaccount.google.com/apppasswords")]),
]


def lock_owner():
    """PID of the bot run that holds bot.lock, or None when no live bot process owns it."""
    try:
        with open(LOCK, encoding="utf-8") as f:
            pid = int(f.read().strip())
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                           text=True, creationflags=NO_WINDOW, timeout=10)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    # Windows reuses PIDs: only a Python or Job Hunter process can be the bot.
    name = r.stdout.split(",")[0].strip().strip('"').lower()
    return pid if name in ("python.exe", "pythonw.exe", "jobhunter.exe") else None


def test_gmail(address, password, host="imap.gmail.com"):
    """None if Gmail accepts the address and app password, else what went wrong."""
    try:
        imap = imaplib.IMAP4_SSL(host, timeout=20)
    except OSError as e:
        return f"Could not reach Gmail ({e.__class__.__name__}). Check your internet connection."
    try:
        imap.login(address, password.replace(" ", ""))
        return None
    except imaplib.IMAP4.error:
        return "Gmail did not accept this address and app password. Check both, and make sure it is an app password."
    except OSError as e:
        return f"Could not reach Gmail ({e.__class__.__name__})."
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def test_gemini(key):
    """None if Gemini accepts the key, else what went wrong.

    Asks for a one-word answer: Google can block a key's project from generating text while it can still
    list models, so listing alone would pass keys that fail on the first real run."""
    body = json.dumps({"contents": [{"parts": [{"text": "Reply with OK."}]}],
                       "generationConfig": {"maxOutputTokens": 5}}).encode()
    req = urllib.request.Request(f"{bot.GEMINI_API}/gemini-flash-lite-latest:generateContent", data=body,
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30):
            return None
    except urllib.error.HTTPError as e:
        if e.code in (404, 429):  # the key works; this one model is missing or out of free quota today
            return None
        try:
            message = json.loads(e.read().decode()).get("error", {}).get("message", "")
        except (ValueError, OSError):
            message = ""
        if "denied access" in message:
            return ("Google has blocked the project this key belongs to (\"Your project has been denied access\"). "
                    "In Google AI Studio press Create API key > Create project to make a key in a new project. "
                    "If that is refused too, use a different Google account.")
        if e.code in (400, 401, 403):
            return f"Google did not accept this Gemini key ({message[:120] or e.code}). Copy it again from Google AI Studio."
        return f"Gemini answered with error {e.code}. Try again in a minute."
    except OSError as e:
        return f"Could not reach Gemini ({e.__class__.__name__}). Check your internet connection."


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def hexcolor(c):
    return "#%02x%02x%02x" % c


def gradient_at(s):
    """Colour at distance s (x + y) along the diagonal, repeating every PERIOD pixels."""
    s = s % PERIOD / PERIOD * len(GRADIENT)
    i, f = int(s) % len(GRADIENT), s - int(s)
    return mix(GRADIENT[i], GRADIENT[(i + 1) % len(GRADIENT)], f * f * (3 - 2 * f))


def rounded(x0, y0, x1, y1, r):
    pts = []
    for cx, cy, a in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(7):
            t = math.radians(a + k * 15)
            pts += [cx + r * math.cos(t), cy + r * math.sin(t)]
    return pts


class Card(tk.Frame):
    """A frosted panel on the gradient. Its frames, labels and checkboxes take the card colour."""

    def __init__(self, app, dark=False):
        super().__init__(app, bd=0, highlightthickness=0)
        self.canvas, self.dark, self.face, self.centre = app.canvas, dark, None, 0
        self.ink, self.muted = (LIGHT_INK, LIGHT_MUTED) if dark else (INK, MUTED)
        self.shape = app.canvas.create_polygon(0, 0, 0, 0, width=1, tags="card")

    def row(self, parent=None, **pack):
        f = tk.Frame(parent or self, bd=0)
        f.pack(fill="x", **pack)
        return f

    def label(self, parent, text="", muted=False, **kw):
        return tk.Label(parent, text=text, fg=self.muted if muted else self.ink, bd=0, **kw)

    def check(self, parent, text, var):
        return tk.Checkbutton(parent, text=text, variable=var, fg=self.ink, activeforeground=self.ink,
                              selectcolor=SURFACE, bd=0, highlightthickness=0)

    def place_at(self, x, y, w, h):
        w, h = max(w, 1), max(h, 1)
        self.place(x=x, y=y, width=w, height=h)
        self.canvas.coords(self.shape, *rounded(x - PAD, y - PAD, x + w + PAD, y + h + PAD, RADIUS))
        self.centre = x + w / 2 + y + h / 2

    def tint(self):
        under = gradient_at(self.centre)
        face = mix(under, NIGHT, SMOKE) if self.dark else mix(under, WHITE, FROST)
        if face == self.face:
            return
        self.face, bg = face, hexcolor(face)
        self.canvas.itemconfigure(self.shape, fill=bg, outline=hexcolor(mix(face, WHITE, 0.12 if self.dark else 0.6)))
        todo = [self]
        while todo:
            w = todo.pop()
            todo += w.winfo_children()
            if getattr(w, "solid", False):
                continue
            if isinstance(w, tk.Checkbutton):
                w.configure(bg=bg, activebackground=bg)
            elif isinstance(w, (tk.Frame, tk.Label)):
                w.configure(bg=bg)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Job Hunter")
        try:
            self.iconbitmap(default=ICON)
        except tk.TclError:
            pass
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.jobs, self.by_iid, self.mtime = [], {}, 0
        self.proc, self.out, self.stopped = None, queue.Queue(), False
        self.sort_col, self.sort_rev = "Posted", False
        self.in_table = False
        self.style_widgets()

        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0, background=hexcolor(GRADIENT[0]))
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_size = (0, 0)
        self.build_background(self.winfo_screenwidth(), self.winfo_screenheight())
        # Jobs on top, console below, table left, details right: drag the gaps between cards to resize them.
        self.split_x, self.split_y, self.drag, self.body = 0.6, 0.55, None, None
        self.canvas.bind("<Configure>", self.layout)
        self.canvas.bind("<Motion>", self.sash_cursor)
        self.canvas.bind("<ButtonPress-1>", lambda e: setattr(self, "drag", self.sash_at(e.x, e.y)))
        self.canvas.bind("<B1-Motion>", self.sash_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))

        self.build_toolbar()
        self.build_filters()
        self.build_body()
        self.build_log()
        self.load_jobs()
        self.refresh_task_button()
        self.after(100, self.pump)
        self.after(3000, self.watch_file)
        self.after(500, self.first_run)

    # ---------- look ----------

    def style_widgets(self):
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            tkfont.nametofont(name).configure(family="Segoe UI", size=10)
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=DIALOG, foreground=INK, bordercolor=LINE, lightcolor=SURFACE,
                     darkcolor=SURFACE, troughcolor="#e2e8f0", focuscolor=ACCENT, fieldbackground=SURFACE,
                     selectbackground=ACCENT, selectforeground="white", arrowcolor=MUTED)

        def button(name, bg, fg, hover, press, off_bg, off_fg, border=None, **kw):
            st.configure(name, background=bg, foreground=fg, bordercolor=border or bg, lightcolor=bg, darkcolor=bg,
                         relief="flat", focuscolor=bg, **{"padding": (10, 5), **kw})
            states = [("disabled", off_bg), ("pressed", press), ("active", hover)]
            st.map(name, background=states, lightcolor=states, darkcolor=states, focuscolor=states,
                   foreground=[("disabled", off_fg)],
                   bordercolor=[("disabled", off_bg), ("active", "#94a3b8" if border else hover)])

        button("TButton", SURFACE, INK, "#f8fafc", "#e2e8f0", "#f1f5f9", "#94a3b8", border=LINE)
        button("Big.TButton", ACCENT, "white", "#3b82f6", "#1d4ed8", "#a9c1f5", "#eff6ff",
               font=("Segoe UI", 10, "bold"), padding=(12, 6))
        button("Dark.TButton", "#1e293b", LIGHT_INK, "#334155", "#0f172a", "#1e293b", "#64748b")
        for name in ("TEntry", "TSpinbox", "TCombobox"):
            st.configure(name, fieldbackground=SURFACE, background=SURFACE, bordercolor=LINE, lightcolor=SURFACE,
                         darkcolor=SURFACE, padding=(6, 3), insertcolor=INK)
            st.map(name, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", SURFACE)])
        st.map("TCombobox", fieldbackground=[("readonly", SURFACE)], selectbackground=[("readonly", SURFACE)],
               selectforeground=[("readonly", INK)], bordercolor=[("focus", ACCENT)])
        self.option_add("*TCombobox*Listbox.background", SURFACE)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))
        st.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=INK, rowheight=28,
                     bordercolor=LINE, lightcolor=SURFACE, darkcolor=SURFACE)
        st.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        st.configure("Treeview.Heading", background=DIALOG, foreground=MUTED, relief="flat", bordercolor=LINE,
                     lightcolor=DIALOG, darkcolor=DIALOG, font=("Segoe UI", 10, "bold"), padding=(6, 4))
        st.map("Treeview.Heading", background=[("active", "#e2e8f0")])
        for orient in ("Vertical", "Horizontal"):
            for prefix, trough, thumb, hover in (("", SURFACE, "#cbd5e1", "#94a3b8"),
                                                 ("Dark.", CONSOLE, "#334155", "#475569")):
                name = f"{prefix}{orient}.TScrollbar"
                st.configure(name, background=thumb, troughcolor=trough, bordercolor=trough, lightcolor=thumb,
                             darkcolor=thumb, gripcount=0, arrowsize=12)
                st.map(name, background=[("active", hover)], lightcolor=[("active", hover)],
                       darkcolor=[("active", hover)])
        st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#1e293b", bordercolor="#1e293b",
                     lightcolor=ACCENT, darkcolor=ACCENT)

    def build_background(self, w, h):
        """Diagonal colour bands covering a w x h window."""
        self.canvas.delete("bg")
        self.bg_size = (w, h)
        for a in range(0, w + h, BAND):
            self.canvas.create_polygon(a, 0, a + BAND + 1, 0, a + BAND + 1 - h, h, a - h, h, outline="",
                                       fill=hexcolor(gradient_at(a + BAND / 2)), tags="bg")
        self.canvas.tag_lower("bg")

    def tint(self):
        for c in (self.c_head, self.c_filter, self.c_table, self.c_detail, self.c_log):
            c.tint()

    def layout(self, e=None):
        W, H = self.canvas.winfo_width(), self.canvas.winfo_height()
        if W < 100 or H < 100:
            return
        if W > self.bg_size[0] or H > self.bg_size[1]:
            self.build_background(max(W, self.bg_size[0]), max(H, self.bg_size[1]))
        m, step = GAP + PAD, 2 * PAD + GAP
        x, w, y = m, W - 2 * m, m
        for c in (self.c_head, self.c_filter):
            h = c.winfo_reqheight()
            c.place_at(x, y, w, h)
            y += h + step
        avail = max(H - m - y - step, 2)
        self.split_x, self.split_y = min(max(self.split_x, 0.25), 0.8), min(max(self.split_y, 0.15), 0.85)
        top, left = round(avail * self.split_y), round((w - step) * self.split_x)
        self.c_table.place_at(x, y, left, top)
        self.c_detail.place_at(x + left + step, y, w - step - left, top)
        self.c_log.place_at(x, y + top + step, w, avail - top)
        self.body = (x, y, w, avail, step, left, top)
        self.tint()

    def sash_at(self, x, y):
        if not self.body:
            return None
        bx, by, w, avail, step, left, top = self.body
        if by + top <= y <= by + top + step:
            return "y"
        if by <= y <= by + top and bx + left <= x <= bx + left + step:
            return "x"
        return None

    def sash_cursor(self, e):
        if not self.drag:
            cursor = {"y": "sb_v_double_arrow", "x": "sb_h_double_arrow"}.get(self.sash_at(e.x, e.y), "")
            self.canvas.config(cursor=cursor)

    def sash_drag(self, e):
        bx, by, w, avail, step, left, top = self.body
        if self.drag == "y":
            self.split_y = (e.y - by - step / 2) / avail
        elif self.drag == "x":
            self.split_x = (e.x - bx - step / 2) / (w - step)
        else:
            return
        self.layout()

    # ---------- layout ----------

    def build_toolbar(self):
        c = self.c_head = Card(self)
        bar = c.row()
        self.busy_buttons = []
        for text, cmd, tip in [
            ("🔍  Find jobs", self.find_jobs, "Search all job sites now (no Gemini, no Gmail)"),
            ("✉  Auto-draft best matches", self.auto_draft, "Same as a scheduled run: Gemini + CV + Gmail drafts"),
        ]:
            b = ttk.Button(bar, text=text, style="Big.TButton", command=cmd)
            b.pack(side="left", padx=(0, 8))
            self.busy_buttons.append(b)
        # Not a busy button: it must work while a run is going, including one started by Auto-run.
        ttk.Button(bar, text="⏹  Stop run", command=self.stop_run).pack(side="left", padx=(0, 8))
        sep = tk.Frame(bar, width=1, bg=LINE)
        sep.solid = True
        sep.pack(side="left", fill="y", padx=8, pady=4)
        for text, cmd in [("📧  Gmail drafts", self.open_gmail), ("📂  CVs folder", self.open_cvs),
                          ("📊  Tracker", self.open_tracker), ("📜  Run log", self.open_runs),
                          ("⚙  Settings", self.settings)]:
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=(0, 6))
        self.task_btn = ttk.Button(bar, text="Auto-run: …", command=self.toggle_task)
        self.task_btn.pack(side="right")

        row = c.row(pady=(8, 0))
        c.label(row, "Your CV:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 8))
        for text, cmd, busy in [("📤  Upload my CV", self.upload_cv, True),
                                ("👤  My profile", self.open_profile, False),
                                ("📝  Tailor CV to a job description…", self.paste_job, True)]:
            b = ttk.Button(row, text=text, command=cmd)
            b.pack(side="left", padx=(0, 6))
            if busy:
                self.busy_buttons.append(b)
        self.profile_lbl = c.label(row, muted=True)
        self.profile_lbl.pack(side="left", padx=(8, 0))
        self.show_profile()

        row = c.row(pady=(8, 0))
        c.label(row, "AI model:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 8))
        self.model_var, self.model_of, self.model_mtime = tk.StringVar(), {}, 0
        cb = self.model_cb = ttk.Combobox(row, textvariable=self.model_var, state="readonly", width=70,
                                          postcommand=self.fill_models)
        cb.pack(side="left", padx=(0, 6))
        cb.bind("<<ComboboxSelected>>", lambda e: self.pick_model())
        self.model_btn = ttk.Button(row, text="↻  Check models", command=self.check_models)
        self.model_btn.pack(side="left", padx=(0, 6))
        self.model_lbl = c.label(row, muted=True)
        self.model_lbl.pack(side="left", padx=(8, 0))
        self.fill_models()

    def show_profile(self):
        try:
            with open(PROFILE, encoding="utf-8") as f:
                p = json.load(f)
            self.profile_lbl.config(text=f"Using: {p['name']}  ·  {p['default_title'][:60]}  ·  "
                                         f"{len(p['experience'])} roles  (profile.json)")
        except (OSError, ValueError, KeyError):
            self.profile_lbl.config(text="No profile yet. Press Upload my CV.")

    def model_state(self):
        """gemini_state.json, or an empty state when it belongs to an older key."""
        cfg = read_config()
        state = bot.gemini_state()
        if not has_key(cfg, "gemini_api_key") or state.get("key") != bot.key_id(cfg["gemini_api_key"]):
            return cfg, {}
        return cfg, state

    def fill_models(self):
        """Every model your key can use, with what the bot last saw: working, at its limit and until when."""
        cfg, state = self.model_state()
        models = sorted(state.get("models", []), key=bot.model_rank)
        current = cfg.get("gemini_model", bot.DEFAULT_CONFIG["gemini_model"])
        if current and current not in models:
            models.insert(0, current)
        self.model_of = {AUTO_MODEL: ""}
        usable = 0
        for m in models:
            ok, text = bot.model_status(state, m)
            usable += ok
            self.model_of[f"{'✓' if ok else '⛔'}  {m}   ·   {text}"] = m
        self.model_var.set(next((k for k, m in self.model_of.items() if m == current), AUTO_MODEL))
        self.model_cb.config(values=list(self.model_of))
        if state.get("refused"):
            self.model_lbl.config(text=f"⚠ Google refused your key: {state['refused']['message'][:70]}. "
                                       "Make a new key (Settings > Gmail & Gemini keys).")
        elif not state.get("models"):
            self.model_lbl.config(text="Press Check models to see which models your key can use.")
        else:
            self.model_lbl.config(text=f"{usable} of {len(models)} models usable right now. "
                                       "Others are used when the chosen one is at its limit.")

    def pick_model(self):
        model = self.model_of.get(self.model_var.get(), "")
        cfg, state = self.model_state()
        if model and state.get("blocked", {}).get(model, 0) > dt.datetime.now().timestamp():
            ok, text = bot.model_status(state, model)
            if not messagebox.askyesno("AI model", f"{model}: {text}.\n\nGoogle may still refuse it until then. "
                                       "Try it anyway on the next run?", parent=self):
                self.fill_models()
                return
            if self.proc or lock_owner():
                messagebox.showinfo("AI model", "A run is in progress. Try again when it has finished.", parent=self)
                self.fill_models()
                return
            for k in ("blocked", "why"):
                state.get(k, {}).pop(model, None)
            bot.save_gemini_state(state)
        cfg["gemini_model"] = model
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        self.write_log(f"\nAI model: {model or 'Auto'}"
                       + (" (other free models take over when it is at its limit)\n" if model else "\n"))
        self.fill_models()

    def check_models(self):
        """Ask Google which models this key can use now (the bot also does this once a day)."""
        cfg, state = self.model_state()
        if not has_key(cfg, "gemini_api_key"):
            self.keys()
            return
        if self.proc or lock_owner():
            self.model_lbl.config(text="A run is in progress. Check models when it has finished.")
            return
        self.model_btn.state(["disabled"])
        self.model_lbl.config(text="Asking Google …")

        def work():
            new = {**state, "key": bot.key_id(cfg["gemini_api_key"]), "listed": 0}
            bot.gemini_models(cfg, new)
            self.after(0, done, new)

        def done(new):
            self.model_btn.state(["!disabled"])
            if not new.get("listed"):
                self.model_lbl.config(text="Could not reach Google. Check your internet connection and the key.")
                return
            bot.save_gemini_state(new)
            self.fill_models()

        threading.Thread(target=work, daemon=True).start()

    def build_filters(self):
        # What the bot looks for. Saved in config.json, so scheduled runs use it too.
        cfg = read_config()
        c = self.c_filter = Card(self)
        self.kw = tk.StringVar(value=", ".join(cfg.get("keywords") or DEFAULT_KEYWORDS))
        self.excl = tk.StringVar(value=", ".join(cfg.get("exclude_keywords") or []))
        self.age = tk.StringVar(value=str(cfg.get("max_job_age_days") or 14))
        self.pk_only = tk.BooleanVar(value=cfg.get("worldwide_only", cfg.get("pakistan_only", True)))
        self.title_only = tk.BooleanVar(value=bool(cfg.get("keywords_in_title")))
        self.preset = tk.StringVar()
        mine = [k.strip().lower() for k in self.kw.get().split(",")]
        picked = [n for n in cfg.get("job_types") or [] if n in PRESETS] or \
            [n for n, (kws, _, _) in PRESETS.items() if [k.lower() for k in kws] == mine]
        self.types = {n: tk.BooleanVar(value=n in picked) for n in PRESETS}

        top = c.row()
        c.label(top, "Job filter", font=("Segoe UI", 10, "bold")).pack(side="left")
        c.label(top, "Job type:").pack(side="left", padx=(14, 4))
        mb = ttk.Menubutton(top, textvariable=self.preset, width=40)
        menu = tk.Menu(mb, tearoff=False, font=("Segoe UI", 10))
        for n in PRESETS:  # tick several to search them together
            menu.add_checkbutton(label=n, variable=self.types[n], command=self.use_preset)
        mb["menu"] = menu
        mb.pack(side="left", padx=(0, 14))
        c.check(top, "Keywords in title only", self.title_only).pack(side="left", padx=(0, 12))
        c.check(top, "Only open worldwide / to my region", self.pk_only).pack(side="left", padx=(0, 12))
        c.label(top, "Saved for the 30-minute auto-run too", muted=True).pack(side="right")

        row = c.row(pady=(8, 0))
        c.label(row, "Keywords (any of):").pack(side="left")
        ttk.Entry(row, textvariable=self.kw, width=28).pack(side="left", padx=(4, 12), fill="x", expand=True)
        c.label(row, "Exclude in title:").pack(side="left")
        ttk.Entry(row, textvariable=self.excl, width=22).pack(side="left", padx=(4, 12))
        c.label(row, "Max age (days):").pack(side="left")
        ttk.Spinbox(row, from_=1, to=60, textvariable=self.age, width=4).pack(side="left", padx=(4, 12))
        b = ttk.Button(row, text="🔍  Save & search", style="Big.TButton", command=self.find_jobs)
        b.pack(side="left")
        self.busy_buttons.append(b)
        self.show_preset()
        self.kw.trace_add("write", lambda *a: self.show_preset())

    def picked_types(self):
        """The ticked job types, or [] once the keywords are your own."""
        picked = [n for n, v in self.types.items() if v.get()]
        mine = [w.strip().lower() for w in self.kw.get().split(",") if w.strip()]
        return picked if picked and [k.lower() for k in combine(picked)[0]] == mine else []

    def show_preset(self):
        """Name the ticked job types the keywords come from, or Custom once you have typed your own."""
        picked = self.picked_types()
        self.preset.set(CUSTOM if not picked else picked[0] if len(picked) == 1
                        else f"{picked[0]} + {len(picked) - 1} more")

    def use_preset(self):
        picked = [n for n, v in self.types.items() if v.get()]
        if picked:
            kws, _, title_only = combine(picked)
            self.kw.set(", ".join(kws))
            self.title_only.set(title_only)
        self.show_preset()

    def build_body(self):
        c = self.c_table = Card(self)
        row = c.row(pady=(0, 4))
        c.label(row, "Show:").pack(side="left")
        self.view = tk.StringVar(value="All matches")
        cb = ttk.Combobox(row, textvariable=self.view, values=list(VIEWS), state="readonly", width=26)
        cb.pack(side="left", padx=(4, 12))
        cb.bind("<<ComboboxSelected>>", lambda e: self.fill_table())
        c.label(row, "Search in list:").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self.fill_table())
        ttk.Entry(row, textvariable=self.search, width=24).pack(side="left", padx=(4, 12))
        info = c.row(pady=(0, 8))
        self.count_lbl = c.label(info, muted=True)
        self.count_lbl.pack(side="left")
        self.updated_lbl = c.label(info, muted=True)
        self.updated_lbl.pack(side="right")

        left = tk.Frame(c)
        left.pack(fill="both", expand=True)
        cols = ("Status", "Posted", "Company", "Role", "Location", "Salary")
        widths = (115, 65, 120, 240, 130, 100)
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col, command=lambda col=col: self.sort_by(col))
            self.tree.column(col, width=w, minwidth=50, stretch=col in ("Role", "Company", "Location"))
        self.tree.tag_configure("ready", background="#ecfdf5")
        self.tree.tag_configure("apply on site", background="#eff6ff")
        self.tree.tag_configure("done", foreground="#94a3b8")
        self.tree.tag_configure("rejected", foreground="#b91c1c")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_detail())
        self.tree.bind("<Double-1>", lambda e: self.open_job())

        right = self.c_detail = Card(self)
        acts = right.row(pady=(0, 8))
        self.b_open = ttk.Button(acts, text="🌐  Open job page", command=self.open_job)
        self.b_draft = ttk.Button(acts, text="✉  Draft email + CV", style="Big.TButton", command=lambda: self.act("draft"))
        self.b_cv = ttk.Button(acts, text="📄  Make CV + cover letter", command=lambda: self.act("cv"))
        self.b_copy = ttk.Button(acts, text="📋  Copy email", command=self.copy_email)
        self.b_skip = ttk.Button(acts, text="🚫  Skip job", command=lambda: self.act("skip"))
        for i, b in enumerate((self.b_draft, self.b_cv, self.b_open, self.b_copy, self.b_skip)):
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
        for i in range(2):
            acts.columnconfigure(i, weight=1)
        box = tk.Frame(right)
        box.pack(fill="both", expand=True)
        self.detail = tk.Text(box, wrap="word", font=("Segoe UI", 10), padx=12, pady=10, relief="flat",
                              background=SURFACE, foreground=INK, highlightthickness=1, highlightbackground=LINE,
                              highlightcolor=LINE, state="disabled")
        dsb = ttk.Scrollbar(box, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=dsb.set)
        self.detail.tag_configure("h1", font=("Segoe UI", 14, "bold"), spacing3=4)
        self.detail.tag_configure("h2", font=("Segoe UI", 11), foreground=MUTED, spacing3=8)
        self.detail.tag_configure("key", font=("Segoe UI", 10, "bold"))
        self.detail.tag_configure("link", foreground=ACCENT, underline=True)
        self.detail.tag_bind("link", "<Button-1>", lambda e: self.open_job())
        self.detail.tag_bind("link", "<Enter>", lambda e: self.detail.config(cursor="hand2"))
        self.detail.tag_bind("link", "<Leave>", lambda e: self.detail.config(cursor=""))
        self.detail.pack(side="left", fill="both", expand=True)
        dsb.pack(side="left", fill="y")
        self.set_job_buttons(None)

    def build_log(self):
        c = self.c_log = Card(self, dark=True)
        top = c.row()
        self.status_lbl = c.label(top, "Ready.", font=("Segoe UI", 10, "bold"))
        self.status_lbl.pack(side="left")
        ttk.Button(top, text="Clear", style="Dark.TButton", command=self.clear_log).pack(side="right")
        self.bar = ttk.Progressbar(top, mode="indeterminate", length=180)
        body = tk.Frame(c)
        body.pack(fill="both", expand=True, pady=(8, 0))
        self.log = tk.Text(body, height=16, wrap="none", font=LOG_FONT, background=CONSOLE, foreground="#ddd",
                           insertbackground="#ddd", relief="flat", padx=10, pady=8, spacing1=1,
                           highlightthickness=0, state="disabled")
        ysb = ttk.Scrollbar(body, orient="vertical", command=self.log.yview, style="Dark.Vertical.TScrollbar")
        xsb = ttk.Scrollbar(body, orient="horizontal", command=self.log.xview, style="Dark.Horizontal.TScrollbar")
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
        try:  # a run just used a model or hit a limit
            if os.path.getmtime(bot.GEMINI_STATE) != self.model_mtime:
                self.model_mtime = os.path.getmtime(bot.GEMINI_STATE)
                self.fill_models()
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
            self.proc = subprocess.Popen([*BOT, *args], cwd=HERE,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                         encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        except OSError as e:
            self.write_log(f"Could not start bot.py: {e}\n")
            return
        self.bar.pack(side="right", padx=(0, 10))
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

    def stop_run(self):
        """Stop this window's run, or the one holding bot.lock (Auto-run, another window), and free the lock."""
        pid = self.proc.pid if self.proc else lock_owner()
        if pid is None:
            if os.path.exists(LOCK):  # left behind by a run that was killed
                os.remove(LOCK)
                self.write_log("\n■ Cleared a leftover lock from a run that had already ended.\n", "head")
            else:
                self.status_lbl.config(text="No run in progress.")
            return
        if not messagebox.askyesno("Stop run", "Stop the run that is in progress?\n\n"
                                   "Drafts it already made stay in Gmail.", parent=self):
            return
        self.stopped = self.proc is not None
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       creationflags=NO_WINDOW, timeout=15)
        try:
            os.remove(LOCK)
        except OSError:
            pass
        self.write_log("\n■ Run stopped.\n", "head")
        self.status_lbl.config(text="Stopped. " + dt.datetime.now().strftime("%H:%M"))

    def finished(self):
        self.proc = None
        self.bar.stop()
        self.bar.pack_forget()
        self.status_lbl.config(text=("Stopped. " if self.stopped else "Done. ") + dt.datetime.now().strftime("%H:%M"))
        self.stopped = False
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

    def upload_cv(self, ask=True):
        path = filedialog.askopenfilename(parent=self, title="Choose your CV",
                                          filetypes=[("CV", "*.pdf *.docx *.txt *.md"), ("All files", "*.*")])
        if not path:
            return
        if ask and not messagebox.askokcancel("Upload my CV", "Gemini will read this CV and rebuild profile.json from it.\n\n"
                                      "Every tailored CV, cover letter and email is built only from profile.json. "
                                      "Your current profile is kept as a backup.\n\nContinue?", parent=self):
            return
        self.run_bot(["--import-cv", path], f"Reading your CV: {os.path.basename(path)}")

    def paste_job(self):
        win = tk.Toplevel(self, background=DIALOG)
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
        text = tk.Text(frm, wrap="word", font=("Segoe UI", 10), height=18, undo=True, relief="flat", padx=8, pady=6,
                       background=SURFACE, foreground=INK, insertbackground=INK, highlightthickness=1,
                       highlightbackground=LINE, highlightcolor=ACCENT)
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
                                   None: "⏱  Set up auto-run"}[s])

    def toggle_task(self):
        s = self.task_state()
        if s is None:
            if not messagebox.askyesno("Auto-run", "Run Job Hunter every 30 minutes in the background while you "
                                       "are signed in to Windows?\n\nEach run searches, tailors up to "
                                       "'Max drafts per run' CVs and saves Gmail drafts. Nothing is ever sent.\n\n"
                                       "You can turn it off again with this button."):
                return
            cmd = ["schtasks", "/Create", "/TN", TASK, "/SC", "MINUTE", "/MO", "30", "/TR", TASK_RUN, "/F"]
        else:
            cmd = ["schtasks", "/Change", "/TN", TASK, "/DISABLE" if s == "on" else "/ENABLE"]
        r = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW, timeout=15)
        if r.returncode:
            messagebox.showerror("Job Hunter", (r.stderr or r.stdout).strip() or "Could not change the task.")
        self.refresh_task_button()

    # ---------- settings ----------

    def save_filter(self):
        """Write the filter bar to config.json. Returns False (and says why) if it is not valid."""
        words = lambda v: [w.strip() for w in v.get().split(",") if w.strip()]
        if not words(self.kw):
            messagebox.showerror("Job filter", "Type at least one keyword, e.g.  .NET, C#, Accountant, SEO")
            return False
        try:
            age = max(1, int(self.age.get()))
        except ValueError:
            messagebox.showerror("Job filter", "Max age must be a number of days.")
            return False
        cfg = read_config()
        picked = self.picked_types()
        fields = combine(picked)[1] if picked else ["all"]
        new = dict(keywords=words(self.kw), exclude_keywords=words(self.excl), max_job_age_days=age,
                   worldwide_only=self.pk_only.get(), keywords_in_title=self.title_only.get(), job_fields=fields,
                   job_types=picked)
        if any(cfg.get(k) != v for k, v in new.items()):
            cfg.update(new)
            cfg.pop("pakistan_only", None)
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self.write_log(f"\nFilter saved: {self.preset.get()} | keywords {', '.join(new['keywords'])}"
                           + (" (in title)" if new["keywords_in_title"] else "")
                           + (f" | exclude {', '.join(new['exclude_keywords'])}" if new["exclude_keywords"] else "")
                           + f" | max age {age} days"
                           + (" | worldwide/my region only\n" if new["worldwide_only"] else " | any country\n"))
        return True

    def keys(self, first=False):
        """The "Connect your accounts" window: Gmail app password and Gemini key, with how to get each."""
        cfg = read_config()
        win = tk.Toplevel(self, background=DIALOG)
        win.title("Connect your accounts")
        win.transient(self)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=18)
        frm.pack(fill="both")
        ttk.Label(frm, text="Connect Gmail and Gemini", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(frm, wraplength=560, foreground=MUTED, justify="left",
                  text="Job Hunter writes your tailored CVs with Google Gemini (free) and saves each email as a "
                       "draft in your Gmail, ready for you to check and send. It never sends anything itself. "
                       "Gmail is optional: without it you still get the CVs and cover letters.\n\n"
                       f"Your keys stay on this computer, in {CONFIG}").pack(anchor="w", pady=(4, 10))
        vars_, status = {}, {}
        for key, label, secret, steps, links in KEY_FIELDS:
            box = ttk.Frame(frm)
            box.pack(fill="x", pady=(6, 0))
            ttk.Label(box, text=label, font=("Segoe UI", 10, "bold"), width=24).pack(side="left")
            start = cfg.get(key, "")
            vars_[key] = tk.StringVar(value="" if start.startswith("PUT-") else start)
            entry = ttk.Entry(box, textvariable=vars_[key], width=44, show="•" if secret else "")
            entry.pack(side="left", padx=(6, 6))
            if secret:
                ttk.Button(box, text="Show", width=6, command=lambda e=entry: e.config(
                    show="" if e.cget("show") else "•")).pack(side="left")
            status[key] = ttk.Label(frm, text="", wraplength=560, justify="left")
            if steps:
                how = ttk.Frame(frm, padding=(12, 6, 0, 4))
                for i, step in enumerate(steps, 1):
                    ttk.Label(how, text=step if step.startswith("Note:") else f"{i}.  {step}", wraplength=540,
                              justify="left").pack(anchor="w", pady=1)
                links_row = ttk.Frame(how)
                links_row.pack(anchor="w", pady=(4, 0))
                for text, url in links:
                    ttk.Button(links_row, text=f"↗  {text}", command=lambda u=url: webbrowser.open(u)).pack(
                        side="left", padx=(0, 6))
                toggle = ttk.Label(frm, text=f"❔ How do I get a {label}?", foreground=ACCENT,
                                   cursor="hand2", font=("Segoe UI", 9, "underline"))
                toggle.pack(anchor="w", padx=(186, 0), pady=(2, 0))

                def flip(e, how=how, toggle=toggle):
                    if how.winfo_ismapped():
                        how.pack_forget()
                    else:
                        how.pack(after=toggle, fill="x")
                toggle.bind("<Button-1>", flip)
                if first and not vars_[key].get():
                    how.pack(fill="x")
            status[key].pack(anchor="w", padx=(186, 0))

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(16, 0))
        busy = ttk.Label(btns, text="", foreground=MUTED)
        busy.pack(side="left")
        save_btn = ttk.Button(btns, text="Test & save", style="Big.TButton")
        save_btn.pack(side="right")
        ttk.Button(btns, text="Later" if first else "Cancel", command=win.destroy).pack(side="right", padx=6)

        def save(new):
            cfg = read_config()
            cfg.update(new)
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            win.destroy()
            self.status_lbl.config(text="Keys saved.")
            if first and not os.path.exists(PROFILE) and messagebox.askyesno(
                    "Job Hunter", "Next, upload your CV (PDF, Word or text). Gemini reads it once and builds your "
                                  "profile, which every tailored CV is made from.\n\nUpload it now?", parent=self):
                self.upload_cv(ask=False)

        def tested(new, errors):
            if not win.winfo_exists():
                return
            save_btn.state(["!disabled"])
            busy.config(text="")
            for key, err in errors.items():
                status[key].config(text=f"✖  {err}" if err else "✔  Works", foreground="#b91c1c" if err else "#15803d")
            if not any(errors.values()) or messagebox.askyesno(
                    "Connect your accounts", "Some keys did not pass the test (see the red notes).\n\n"
                                             "Save them anyway?", parent=win):
                save(new)

        def test():
            new = {k: v.get().strip() for k, v in vars_.items()}
            if not new["gemini_api_key"]:
                messagebox.showerror("Connect your accounts", "Paste your Gemini API key.", parent=win)
                return
            gmail = bool(new["gmail_address"] or new["gmail_app_password"])
            if gmail and ("@" not in new["gmail_address"] or not new["gmail_app_password"]):
                messagebox.showerror("Connect your accounts", "For Gmail drafts fill in both the Gmail address and "
                                     "the app password, or leave both empty.", parent=win)
                return
            save_btn.state(["disabled"])
            busy.config(text="Testing…")
            host = cfg.get("imap_host", "imap.gmail.com")

            def work():
                errors = {"gemini_api_key": test_gemini(new["gemini_api_key"])}
                if gmail:
                    errors["gmail_app_password"] = test_gmail(new["gmail_address"], new["gmail_app_password"], host)
                self.after(0, tested, new, errors)
            threading.Thread(target=work, daemon=True).start()

        save_btn.config(command=test)
        win.grab_set()

    def first_run(self):
        if not has_key(read_config(), "gemini_api_key"):
            self.keys(first=True)

    def settings(self):
        cfg = read_config()
        win = tk.Toplevel(self, background=DIALOG)
        win.title("Settings")
        win.transient(self)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=16)
        frm.pack()
        vars_ = {}
        for i, (key, label, _) in enumerate(SETTINGS):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=4)
            v = tk.StringVar(value=str(cfg.get(key, bot.DEFAULT_CONFIG.get(key, ""))))
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
        ttk.Button(btns, text="🔑  Gmail & Gemini keys…",
                   command=lambda: (win.destroy(), self.keys())).pack(side="left")
        ttk.Button(btns, text="Save", style="Big.TButton", command=save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=6)
        win.grab_set()


if __name__ == "__main__":
    App().mainloop()
