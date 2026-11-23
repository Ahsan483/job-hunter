"""Everything the Job Hunter window does, without the window.

The window itself is a web page (ui/, React) shown by webapp.py. It calls the public methods of Api through
pywebview, and Api pushes live updates (log lines, run start/end, file changes, update progress) back to it as
"jh" events. Every button still runs bot.py in the background, so the window and Auto-run share the same code,
config.json, jobs.json and tracker.csv.

Nothing in this module imports a GUI toolkit, so the tests run it directly.
"""
import csv
import datetime as dt
import imaplib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

# python -I leaves the script's folder off sys.path; bot.py sits next to this file.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot  # noqa: E402

# Your files live in bot.HERE: next to the scripts, or %APPDATA%\Job Hunter for the installed JobHunter.exe.
FROZEN, HERE = bot.FROZEN, bot.HERE
JOBS_FILE, TRACKER, LOCK = bot.JOBS_FILE, bot.TRACKER, bot.LOCK
CONFIG = os.path.join(HERE, "config.json")
PROFILE = os.path.join(HERE, "profile.json")
UI_PREFS = os.path.join(HERE, "ui.json")  # window-only choices (sounds, theme); the bot never reads it
RELEASES = f"https://github.com/{bot.REPO}/releases/latest"
SETUP_URL = f"{RELEASES}/download/JobHunterSetup.exe"  # the installer file itself is hosted on GitHub
DOWNLOAD_PAGE = "https://www.codeprojectsofficial.com/tools"
GUIDE_URL = f"https://github.com/{bot.REPO}#readme"
ISSUES_URL = f"https://github.com/{bot.REPO}/issues/new/choose"
TASK = "Remote Job Hunter"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# pythonw has no console; use the console python next to it, hidden, so we can read its output.
# JobHunter.exe runs the bot itself when started with --bot.
PY = os.path.join(os.path.dirname(sys.executable), "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
BOT = [sys.executable, "--bot"] if FROZEN else [PY, "-I", "-X", "utf8", "-u", os.path.join(bot.CODE, "bot.py")]
# What the 30-minute scheduled task runs: no console window either way.
PYW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
TASK_RUN = (f'"{sys.executable}" --bot' if FROZEN
            else f'"{PYW if os.path.exists(PYW) else sys.executable}" -I "{os.path.join(bot.CODE, "bot.py")}"')

# id -> (label, statuses shown)
VIEWS = {
    "ready": ("Ready to draft (has email)", {"ready"}),
    "site": ("Apply on company site", {"apply on site"}),
    "matches": ("All matches", {"ready", "apply on site"}),
    "done": ("Done, applied or skipped", {"done"}),
    "all": ("Everything (incl. rejected)", {"ready", "apply on site", "done", "rejected"}),
}
SORTS = ("match", "posted", "status", "company", "role", "location", "salary")
OPEN_TO_LABEL = {"me": "Worldwide + my country", "countries": "Countries I pick", "anywhere": "Any country"}
DEFAULT_KEYWORDS = bot.DEFAULT_CONFIG["keywords"]
# (key, label, lowest, highest, what it means). The AI model is picked in the main window.
SETTINGS = [("min_fit_score", "Minimum fit score", 0, 100,
             "Auto-draft skips jobs Gemini scores lower than this (0-100). Lower it if too few drafts are made."),
            ("max_drafts_per_run", "Max drafts per run", 1, 50, "Drafts (or CVs) one Auto-draft run makes at most."),
            ("max_drafts_per_day", "Max drafts per day", 1, 200, "All runs together, per calendar day."),
            ("max_gemini_calls_per_run", "Max Gemini calls per run", 1, 50,
             "Jobs one run asks Gemini about. Keeps you inside the free limits."),
            ("max_years_required", "Skip jobs asking for (years)", 0, 40,
             "Hide jobs that ask for this many years of experience or more. 0 = never hide.")]

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

# (field, label, secret, help steps, links). Shown in the "Connect your accounts" dialog.
KEY_FIELDS = [
    ("gemini_api_key", "Gemini API key", True,
     ["Open Google AI Studio and sign in with any Google account.",
      "Press Create API key (accept the terms if asked) and copy the key. It starts with AIza.",
      "Paste it here. The free tier is enough and needs no card."],
     [("Open Google AI Studio", "https://aistudio.google.com/apikey")]),
    ("gmail_address", "Gmail address", False, None, []),
    ("gmail_app_password", "Gmail app password", True,
     ["Google only gives app passwords to accounts with 2-Step Verification. Turn it on first if it is off.",
      "Open App passwords, type a name such as Job Hunter and press Create.",
      "Copy the 16-letter password Google shows and paste it here. The spaces do not matter.",
      "Note: use this app password, not your normal Gmail password. Some work and school accounts do not allow "
      "app passwords: use a personal Gmail account then."],
     [("Turn on 2-Step Verification", "https://myaccount.google.com/signinoptions/twosv"),
      ("Open App passwords", "https://myaccount.google.com/apppasswords")]),
]
CV_TYPES = ("CV files (*.pdf;*.docx;*.txt;*.md;*.png;*.jpg;*.jpeg;*.webp)", "All files (*.*)")


# ---------- small helpers ----------

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


def words(value):
    """'a, b,,c ' or ['a', 'b'] -> ['a', 'b', 'c']."""
    items = value if isinstance(value, list) else str(value or "").split(",")
    return [str(w).strip() for w in items if str(w).strip()]


def picked_types(types, keywords):
    """The ticked job types, or [] once the keywords are your own."""
    picked = [n for n in types or [] if n in PRESETS]
    mine = [w.lower() for w in words(keywords)]
    return picked if picked and [k.lower() for k in combine(picked)[0]] == mine else []


def ago(iso):
    try:
        d = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    days = (dt.datetime.now(dt.timezone.utc) - d).days
    return "today" if days <= 0 else f"{days}d ago"


def where(j):
    """The job's location with its work type in front, unless the location already says it: 'On-site · Lahore'."""
    mode, loc = bot.WORK_MODES.get(j.get("mode")), j.get("location", "")
    return f"{mode} · {loc}" if mode and mode.lower() not in loc.lower() else loc


def read_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def read_config():
    d = read_json(CONFIG, {})
    return d if isinstance(d, dict) else {}


def has_key(cfg, key):
    v = cfg.get(key)
    return isinstance(v, str) and bot.is_set(v.strip())


def write_json(path, data):
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(path + ".tmp", path)


def write_config(cfg):
    write_json(CONFIG, cfg)


def version_tuple(v):
    return tuple(int(n) for n in re.findall(r"\d+", v)[:3])


def latest_release():
    """Tag of the newest GitHub release, e.g. 'v1.2.0', or None when GitHub cannot be reached.

    The API allows 60 requests an hour per internet address, which a shared office or mobile network can use up.
    Then the releases page answers instead: github.com/.../releases/latest redirects to .../releases/tag/v1.2.0."""
    req = urllib.request.Request(f"https://api.github.com/repos/{bot.REPO}/releases/latest", headers=bot.UA)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            tag = json.loads(r.read().decode()).get("tag_name")
            if tag:
                return tag
    except (OSError, ValueError):
        pass
    try:
        with urllib.request.urlopen(urllib.request.Request(RELEASES, headers=bot.UA, method="HEAD"), timeout=15) as r:
            m = re.search(r"/releases/tag/([^/?#]+)$", r.geturl())
            return urllib.parse.unquote(m.group(1)) if m else None
    except (OSError, ValueError):
        return None


def download_setup(progress):
    """Download the newest installer to the temp folder and return its path. progress(percent) is called as it
    comes in. Raises OSError/ValueError when the download fails or is not an installer."""
    path = os.path.join(tempfile.gettempdir(), "JobHunterSetup-update.exe")
    with urllib.request.urlopen(urllib.request.Request(SETUP_URL, headers=bot.UA), timeout=60) as r, \
            open(path + ".part", "wb") as f:
        size, got, shown = int(r.headers.get("Content-Length") or 0), 0, -1
        while chunk := r.read(256 * 1024):
            f.write(chunk)
            got += len(chunk)
            if size and got * 100 // size != shown:
                shown = got * 100 // size
                progress(shown)
    with open(path + ".part", "rb") as f:
        if f.read(2) != b"MZ" or got < 1_000_000 or (size and got != size):
            raise ValueError("the download is not a complete installer")
    os.replace(path + ".part", path)
    return path


def tracker_files():
    """{job id: (cv, cover letter)} for every job with a CV in tracker.csv; the newest CV that still exists."""
    try:
        with open(TRACKER, newline="", encoding="utf-8-sig") as f:
            rows = [r for r in csv.DictReader(f) if r.get("draft_id") and r.get("cv_file")]
    except OSError:
        return {}
    out = {}
    for r in rows:  # later rows are newer and win
        cv = os.path.join(HERE, "cvs", r["cv_file"])
        if os.path.exists(cv):
            letter = os.path.join(HERE, "cvs", bot.letter_of(r["cv_file"]))
            out[r["draft_id"]] = (cv, letter if os.path.exists(letter) else None)
    return out


def job_files(job_id):
    """(cv, cover letter) PDFs made for one job; None where there is none."""
    return tracker_files().get(job_id, (None, None))


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
    except OSError:
        return "Could not reach Gmail. Check your internet connection."
    try:
        imap.login(address, password.replace(" ", ""))
        return None
    except imaplib.IMAP4.error:
        return "Gmail did not accept this address and app password. Check both, and make sure it is an app password."
    except OSError:
        return "Could not reach Gmail. Check your internet connection."
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
    except OSError:
        return "Could not reach Gemini. Check your internet connection."


# ---------- bot.py output -> structured log entries ----------

FILE_PATH = re.compile(r"[A-Za-z]:\\.+?\.(?:pdf|txt|json)\b")


def parse_line(line):
    """One line of bot.py output as a log entry for the window: {"type": ..., ...}.

    job:     a row of the results table (status READY / ON WEBSITE / DRAFTED / NOT A FIT)
    source:  how many jobs one site returned, or why it was not searched
    filter:  the "filtered out" counts
    summary: the end-of-run totals, plus plain-English notes
    text:    anything else, with a tone (info, good, warn, error, dim) and any saved file paths"""
    line = line.rstrip("\r\n")
    if line.startswith("FOUND {"):
        try:
            return {"type": "found", "job": json.loads(line[6:])}
        except ValueError:
            pass
    m = re.match(r"(CANDIDATE|APPLY ON SITE) \[(\w+)\] (.*?) \| (.*) \| (\S+)(?: \(.*\))?$", line)
    if m:
        kind, src, company, role, last = m.groups()
        if role.startswith(company + " | "):  # HN titles repeat the company
            role = role[len(company) + 3:]
        return {"type": "job", "status": "READY" if kind == "CANDIDATE" else "ON WEBSITE", "source": src,
                "company": company, "role": role, "link": last}
    m = re.match(r"skip (.*?): eligible=(\S+) fit=(\S+) ?(.*)$", line)
    if m:
        company, _, fit, reason = m.groups()
        return {"type": "job", "status": "NOT A FIT", "source": "gemini", "company": company,
                "role": f"fit {fit}", "link": "", "reason": reason}
    m = re.match(r"DRAFT saved: (.*) -> (\S+) \(fit (.*)\)$", line)
    if m:
        company, mail, fit = m.groups()
        return {"type": "job", "status": "DRAFTED", "source": "gemini", "company": company,
                "role": f"fit {fit}", "link": mail}
    m = re.match(r"src_(\w+)(?: \((.*?)\))?: (\d+) jobs$", line)
    if m:
        name, label, count = m.groups()
        return {"type": "source", "name": label or name, "count": int(count), "state": "ok"}
    m = re.match(r"NOT SEARCHED src_(\w+)(?: \((.*?)\))?: (.*?)(?: \[details: .*\])?$", line)
    if m:
        name, label, reason = m.groups()
        return {"type": "source", "name": label or name, "state": "failed", "note": reason}
    m = re.match(r"SKIPPED src_(\w+)(?: \((.*?)\))?: (.*)$", line)
    if m:
        name, label, reason = m.groups()
        return {"type": "source", "name": label or name, "state": "skipped", "note": reason}
    m = re.match(r"filter: (\{.*\})$", line)
    if m:
        try:
            import ast
            counts = ast.literal_eval(m.group(1))
            counts = {str(k): int(v) for k, v in counts.items()}
        except (ValueError, SyntaxError, TypeError, AttributeError):
            counts = {}
        return {"type": "filter", "counts": counts}
    m = re.match(r"\S+ (\d\d:\d\d) \| standalone( dry-run)? \| fetched (\d+) \| candidates (\d+) \| "
                 r"gemini (\d+) \| drafts (\d+)(?: \| (.*))?$", line)
    if m:
        at, dry, fetched, cands, gem, drafts, notes = m.groups()
        return {"type": "summary", "at": at, "dry": bool(dry), "fetched": int(fetched), "candidates": int(cands),
                "gemini": int(gem), "drafts": int(drafts), "notes": [n.strip() for n in (notes or "").split(";")
                                                                      if n.strip()]}
    text = line.strip()
    low = text.lower()
    tone = ("error" if text.startswith("ERROR") or " failed" in low or low.startswith("draft failed")
            else "good" if " saved" in text else "dim" if text.startswith(("Keyword ", "Filter saved")) else "info")
    if text.startswith("ERROR: "):
        text = text[7:]
    return {"type": "text", "text": text, "tone": tone, "files": FILE_PATH.findall(text)}


# ---------- the API the window calls ----------

class Api:
    """Public methods are called from the web page (window.pywebview.api.<name>) and return plain JSON data.
    pywebview runs each call on its own thread, so slow ones (key tests, model checks) simply block."""

    def __init__(self):
        self._window = None
        self._proc = None
        self._stopped = False
        self._run_lock = threading.Lock()
        self._sent = []          # events recorded when there is no window (tests)
        self._buffer = []        # log entries waiting to be sent in one batch
        self._last_flush = 0.0
        self._watch = {"jobs": 0, "models": 0, "external": False}
        self._new_tag = ""

    # ----- plumbing -----

    def _attach(self, window):
        self._window = window
        threading.Thread(target=self._watcher, daemon=True).start()

    def _emit(self, kind, data=None):
        event = {"kind": kind, "data": data}
        if not self._window:
            self._sent.append(event)
            return
        try:
            self._window.evaluate_js(f"window.dispatchEvent(new CustomEvent('jh', {{detail: {json.dumps(event)}}}))")
        except Exception:  # the window is closing
            pass

    def _log(self, entry, flush=False):
        self._buffer.append(entry)
        if flush or time.time() - self._last_flush > 0.12:
            self._flush()

    def _flush(self):
        if self._buffer:
            batch, self._buffer = self._buffer, []
            self._emit("log", batch)
        self._last_flush = time.time()

    def _note(self, text, tone="info"):
        self._log({"type": "text", "text": text, "tone": tone, "files": []}, flush=True)

    def _watcher(self):
        """jobs.json, gemini_state.json and runs started by Auto-run, checked every 3 seconds."""
        while True:
            time.sleep(3)
            try:
                m = os.path.getmtime(JOBS_FILE)
                if m != self._watch["jobs"]:
                    self._watch["jobs"] = m
                    self._emit("jobs-changed")
            except OSError:
                pass
            try:
                m = os.path.getmtime(bot.GEMINI_STATE)
                if m != self._watch["models"]:
                    self._watch["models"] = m
                    self._emit("models", self.models())
            except OSError:
                pass
            external = not self._proc and os.path.exists(LOCK) and lock_owner() is not None
            if external != self._watch["external"]:
                self._watch["external"] = external
                self._emit("external-run", external)

    def _running(self):
        return self._proc is not None or (os.path.exists(LOCK) and lock_owner() is not None)

    # ----- start-up -----

    def bootstrap(self):
        """Everything the window needs to draw itself."""
        cfg = read_config()
        self._watch["jobs"] = os.path.getmtime(JOBS_FILE) if os.path.exists(JOBS_FILE) else 0
        threading.Thread(target=bot.ping_usage, daemon=True).start()  # anonymous, once a day; see bot.ping_usage
        return {
            "version": bot.VERSION, "frozen": FROZEN, "dataFolder": HERE, "configFile": CONFIG,
            "downloadPage": DOWNLOAD_PAGE, "repo": f"https://github.com/{bot.REPO}",
            "filter": self.filter_state(cfg), "presets": list(PRESETS),
            "openTo": [{"value": k, "label": v} for k, v in OPEN_TO_LABEL.items()],
            "workModes": [{"value": k, "label": v} for k, v in bot.WORK_MODES.items()],
            "views": [{"value": k, "label": v[0]} for k, v in VIEWS.items()],
            "profile": self.profile(), "setup": self.setup(), "models": self.models(),
            "autorun": self.autorun_state(), "running": self._running(),
            "sources": len(bot.SOURCES), "prefs": self.prefs(), "usageStats": cfg.get("usage_stats", True) is not False,
        }

    def filter_state(self, cfg=None):
        cfg = cfg if cfg is not None else read_config()
        keywords = words(cfg.get("keywords")) or list(DEFAULT_KEYWORDS)
        mine = [k.lower() for k in keywords]
        types = [n for n in cfg.get("job_types") or [] if n in PRESETS] or \
            [n for n, (kws, _, _) in PRESETS.items() if [k.lower() for k in kws] == mine]
        return {
            "keywords": ", ".join(keywords), "exclude": ", ".join(words(cfg.get("exclude_keywords"))),
            "maxAge": int(cfg.get("max_job_age_days") or bot.MAX_AGE_DAYS),
            "modes": sorted(bot.work_modes(cfg)), "openTo": bot.open_to(cfg),
            "region": ", ".join(bot.clean_words(cfg.get("my_region_words"))),
            "countries": ", ".join(bot.clean_words(cfg.get("target_countries"))),
            "visa": bool(cfg.get("visa_sponsorship")), "google": bool(cfg.get("search_google", True)),
            "titleOnly": bool(cfg.get("keywords_in_title")), "jobTypes": types,
            "presetKeywords": ", ".join(combine(types)[0]) if types else "",
        }

    def job_types(self, names):
        """Keywords and title-only for the ticked job types, so the window can fill them in."""
        names = [n for n in names or [] if n in PRESETS]
        if not names:
            return {"keywords": None, "titleOnly": None, "presetKeywords": ""}
        kws, _, title_only = combine(names)
        return {"keywords": ", ".join(kws), "titleOnly": title_only, "presetKeywords": ", ".join(kws)}

    def profile(self):
        p = read_json(PROFILE, None)
        try:
            return {"name": p["name"], "title": p["default_title"][:80], "roles": len(p["experience"])}
        except (TypeError, KeyError):
            return None

    def setup(self):
        """The getting-started checklist."""
        cfg = read_config()
        p = self.profile()
        name = f"  ({p['name']})" if p else ""
        has_jobs = bool(read_json(JOBS_FILE, {}).get("jobs")) if os.path.exists(JOBS_FILE) else False
        return [
            {"id": "gemini", "done": has_key(cfg, "gemini_api_key"), "title": "Connect Gemini (free)",
             "note": "Gemini writes your tailored CVs. The key is free and needs no card."},
            {"id": "cv", "done": bool(p), "title": f"Upload your CV{name}",
             "note": "Gemini reads it once and builds your profile. Every CV it makes uses only facts from it."},
            {"id": "find", "done": has_jobs, "title": "Find jobs",
             "note": "Pick a job type (or type keywords) and your country, then press Find jobs."},
            {"id": "gmail", "done": has_key(cfg, "gmail_address") and has_key(cfg, "gmail_app_password"),
             "title": "Connect Gmail (optional)",
             "note": "Saves each application as a Gmail draft for you to check and send. Without it you get the PDFs."},
        ]

    def prefs(self):
        """Window choices. The theme follows Windows (auto) until you pick one."""
        p = read_json(UI_PREFS, {})
        return {"sounds": bool(p.get("sounds", True)),
                "theme": p["theme"] if p.get("theme") in ("dark", "light", "auto") else "auto"}

    def set_prefs(self, prefs):
        p = {**self.prefs(), **{k: v for k, v in (prefs or {}).items() if k in ("sounds", "theme")}}
        write_json(UI_PREFS, p)
        return p

    def diagnostics(self):
        """For a problem report: version, Windows and the last runs. Never keys, passwords, emails or the CV."""
        import platform
        try:
            with open(bot.RUNS_LOG, encoding="utf-8", errors="replace") as f:
                runs = "".join(f.readlines()[-15:])
        except OSError:
            runs = ""
        return {"version": bot.VERSION, "windows": f"{platform.system()} {platform.release()} ({platform.version()})",
                "installed": FROZEN, "runs": re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", runs)}

    def set_usage_stats(self, on):
        """Turn the anonymous daily active-user ping on or off (config.json, shared with Auto-run)."""
        cfg = read_config()
        cfg["usage_stats"] = bool(on)
        write_config(cfg)
        return {"ok": True, "on": bool(on)}

    def users(self):
        """How many installs were used in the last 30 days, or None when the counter cannot be reached."""
        req = urllib.request.Request(f"{bot.USAGE_URL}/stats", headers=bot.UA)
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                n = json.loads(r.read().decode()).get("monthly")
            return n if isinstance(n, int) else None
        except (OSError, ValueError, AttributeError):
            return None

    # ----- the job list -----

    def jobs(self, view="matches", query="", sort="match", desc=False):
        """The rows for the list (no long texts), the counts line and what loosening the filter would add."""
        d = read_json(JOBS_FILE, {"updated": "", "jobs": []})
        jobs = d.get("jobs") or []
        want = VIEWS.get(view, VIEWS["matches"])[1]
        q = (query or "").lower().strip()
        rows = [j for j in jobs if j.get("status") in want and
                (not q or q in f"{j.get('title', '')} {j.get('company', '')} {j.get('location', '')} "
                               f"{j.get('tags', '')} {j.get('text', '')}".lower())]
        sort = sort if sort in SORTS else "match"
        if sort in ("posted", "match"):  # newest first; for Match, strong matches before partial ones
            rows.sort(key=lambda j: j.get("date") or "", reverse=not desc)
            if sort == "match":
                rows.sort(key=lambda j: j.get("match") != "strong", reverse=desc)
        else:
            key = {"status": lambda j: j.get("status", ""), "company": lambda j: j.get("company", ""),
                   "role": lambda j: j.get("title", ""), "location": where,
                   "salary": lambda j: j.get("salary", "")}[sort]
            rows.sort(key=lambda j: str(key(j)).lower(), reverse=desc)
        files = tracker_files()
        ready = sum(j.get("status") == bot.STATUS_READY for j in jobs)
        site = sum(j.get("status") == bot.STATUS_SITE for j in jobs)
        return {
            "updated": d.get("updated", ""),
            "total": len(jobs), "ready": ready, "site": site,
            "rows": [{"id": j["id"], "status": j.get("status", ""), "why": j.get("why", ""),
                      "match": j.get("match") or "", "date": j.get("date") or "", "ago": ago(j.get("date")),
                      "company": j.get("company", ""), "title": j.get("title", ""), "where": where(j)[:80],
                      "salary": j.get("salary", ""), "email": bool(j.get("email")),
                      "hasCv": j["id"] in files} for j in rows],
            "hint": self.near_misses(jobs) if jobs and ready + site < 20 else "",
        }

    def near_misses(self, jobs):
        """What loosening the filter would add: jobs that match your keywords but were left out for age or place."""
        cfg = read_config()
        near = [j for j in jobs if j.get("status") == bot.STATUS_REJECTED and j.get("match")]
        why = lambda j: j.get("why") or ""
        old = sum(why(j) == "too old" for j in near)
        place = sum(why(j).startswith(("not open", "location/work-auth")) or " outside " in why(j) for j in near)
        kind = {m: sum(why(j) == f"{name.lower()} job" for j in near) for m, name in bot.WORK_MODES.items()}
        age = cfg.get("max_job_age_days") or bot.MAX_AGE_DAYS
        tips = ([f"{old} more are older than {age} days (raise Max age)"] if old else []) + \
               ([f"{place} more are limited to other countries (Open to: Any country, or Countries I pick)"]
                if place else []) + \
               [f"{n} more are {bot.WORK_MODES[m].lower()} (tick {bot.WORK_MODES[m]})" for m, n in kind.items() if n]
        if not tips:
            return "Try a Job type, more or shorter keywords, or untick Keywords in title only."
        return "; ".join(tips) + "."

    def job(self, job_id):
        """One job in full, with the CV and cover letter already made for it."""
        d = read_json(JOBS_FILE, {"jobs": []})
        j = next((x for x in d.get("jobs") or [] if x.get("id") == job_id), None)
        if not j:
            return None
        cv, letter = job_files(job_id)
        return {**{k: j.get(k, "") for k in ("id", "status", "why", "title", "company", "location", "salary",
                                              "job_type", "level", "match", "note", "tags", "email", "email_src",
                                              "source", "text")},
                "date": j.get("date") or "", "ago": ago(j.get("date")), "where": where(j),
                "link": j.get("apply") or j.get("url", ""), "cv": cv or "", "letter": letter or "",
                "letterText": bool(letter and os.path.exists(letter[:-4] + ".txt"))}

    # ----- runs -----

    def _start(self, args, what):
        with self._run_lock:
            if self._proc:
                return {"ok": False, "error": "A run is already in progress. Wait for it to finish, or press Stop."}
            if os.path.exists(LOCK) and lock_owner() is not None:
                return {"ok": False, "error": "Auto-run is busy right now. Wait for it to finish, or press Stop."}
            try:
                self._proc = subprocess.Popen([*BOT, *args], cwd=bot.CODE, stdout=subprocess.PIPE,
                                              stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                              errors="replace", creationflags=NO_WINDOW,
                                              env={**os.environ, "JOBHUNTER_LIVE": "1"})
            except OSError as e:
                return {"ok": False, "error": f"Job Hunter could not start its search engine ({e.strerror or e})."}
        self._stopped = False
        self._emit("run", {"state": "start", "what": what})
        threading.Thread(target=self._read, args=(self._proc, what), daemon=True).start()
        return {"ok": True}

    def _read(self, proc, what):
        summary, found, last = None, [], time.time()
        for line in proc.stdout:
            entry = parse_line(line)
            if entry["type"] == "found":  # live list rows, not activity lines; sent in small batches
                found.append(entry["job"])
                if time.time() - last > 0.3:
                    self._emit("found", found)
                    found, last = [], time.time()
                continue
            if found:
                self._emit("found", found)
                found = []
            if entry["type"] == "summary":
                summary = entry
            if entry["type"] != "text" or entry["text"]:
                self._log(entry)
        if found:
            self._emit("found", found)
        proc.wait()
        self._flush()
        self._proc = None
        self._emit("run", {"state": "end", "what": what, "stopped": self._stopped, "code": proc.returncode,
                           "summary": summary, "profile": self.profile(), "setup": self.setup()})
        self._flash()

    def _flash(self):
        """Flash the taskbar button when a run ends while you are in another window."""
        try:
            import ctypes
            hwnd = self._window.native.Handle.ToInt64()

            class FLASHWINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p), ("dwFlags", ctypes.c_uint),
                            ("uCount", ctypes.c_uint), ("dwTimeout", ctypes.c_uint)]
            info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x3 | 0xC, 0, 0)  # all, until the window is focused
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except Exception:
            pass

    def save_filter(self, f):
        """Check the filter and write it to config.json. Returns {"error": ...} when it is not valid."""
        kws = words(f.get("keywords"))
        if not kws:
            return {"error": "Type at least one keyword, for example  .NET, C#, Accountant, SEO", "field": "keywords"}
        try:
            age = max(1, min(60, int(f.get("maxAge"))))
        except (TypeError, ValueError):
            return {"error": "Max age must be a number of days.", "field": "maxAge"}
        modes = [m for m in bot.WORK_MODES if m in (f.get("modes") or [])]
        if not modes:
            return {"error": "Tick at least one work type: Remote, Hybrid or On-site.", "field": "modes"}
        where_ = f.get("openTo") if f.get("openTo") in OPEN_TO_LABEL else "me"
        if where_ == "countries" and not words(f.get("countries")):
            return {"error": "Type the countries you want in Countries, for example  UAE, Germany, Europe. "
                             "Or pick another Open to.", "field": "countries"}
        if where_ == "me" and modes != ["remote"] and not words(f.get("region")) and not f.get("visa"):
            return {"error": "Type your country in My country/region, for example  Pakistan. Hybrid and on-site "
                             "jobs are kept only if the office is there.", "field": "region"}
        cfg = read_config()
        picked = picked_types(f.get("jobTypes"), kws)
        new = dict(keywords=kws, exclude_keywords=words(f.get("exclude")), max_job_age_days=age, work_modes=modes,
                   open_to=where_, keywords_in_title=bool(f.get("titleOnly")),
                   job_fields=combine(picked)[1] if picked else ["all"], job_types=picked,
                   my_region_words=words(f.get("region")), target_countries=words(f.get("countries")),
                   visa_sponsorship=bool(f.get("visa")), search_google=bool(f.get("google")))
        if any(cfg.get(k) != v for k, v in new.items()) or "worldwide_only" in cfg or "pakistan_only" in cfg:
            cfg.update(new)
            cfg.pop("pakistan_only", None)
            cfg.pop("worldwide_only", None)
            write_config(cfg)
            label = " + ".join(picked) if picked else "Custom keywords"
            self._note(f"Filter saved: {label} | keywords {', '.join(kws)}"
                       + (" (in title)" if new["keywords_in_title"] else "")
                       + (f" | exclude {', '.join(new['exclude_keywords'])}" if new["exclude_keywords"] else "")
                       + f" | max age {age} days | {bot.wanted_jobs(new)}", "dim")
        return {"ok": True}

    def needs(self, gmail=False):
        """What a Gemini action is missing: "gemini", "profile", "gmail" (only with gmail=True) or None."""
        cfg = read_config()
        if not has_key(cfg, "gemini_api_key"):
            return "gemini"
        if not os.path.exists(PROFILE):
            return "profile"
        if gmail and not (has_key(cfg, "gmail_address") and has_key(cfg, "gmail_app_password")):
            return "gmail"
        return None

    def find_jobs(self, f):
        saved = self.save_filter(f)
        if saved.get("error"):
            return saved
        return self._start(["--dry-run"], f"Searching {len(bot.SOURCES)} job sources")

    def auto_draft(self, f):
        need = self.needs()
        if need:
            return {"need": need}
        saved = self.save_filter(f)
        if saved.get("error"):
            return saved
        return self._start([], "Finding jobs and drafting the best matches")

    def job_action(self, job_id, mode):
        """draft / cv / skip / applied for one job."""
        j = self.job(job_id)
        if not j or mode not in ("draft", "cv", "skip", "applied"):
            return {"ok": False, "error": "That job is no longer in the list. Search again."}
        if mode in ("draft", "cv"):
            need = self.needs(gmail=mode == "draft")
            if need:
                return {"need": need}
        what = {"draft": f"Drafting email + CV for {j['company']}",
                "cv": f"Making CV + cover letter for {j['company']}",
                "skip": f"Skipping {j['company']}",
                "applied": f"Marking {j['company']} as applied"}[mode]
        return self._start(["--job", job_id, mode], what)

    def stop(self):
        """Stop this window's run, or the one holding bot.lock (Auto-run, another window), and free the lock."""
        pid = self._proc.pid if self._proc else lock_owner()
        if pid is None:
            if os.path.exists(LOCK):  # left behind by a run that was killed
                os.remove(LOCK)
                self._note("Cleared a leftover lock from a run that had already ended.")
                return {"state": "cleared"}
            return {"state": "idle"}
        self._stopped = self._proc is not None
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       creationflags=NO_WINDOW, timeout=15)
        try:
            os.remove(LOCK)
        except OSError:
            pass
        self._note("Run stopped.", "warn")
        if not self._stopped:
            self._emit("external-run", False)
        return {"state": "stopped"}

    def pick_cv_file(self):
        """The native Open dialog. Returns the chosen path or None."""
        if not self._window:
            return None
        import webview
        picked = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=CV_TYPES)
        return picked[0] if picked else None

    def import_cv(self, path):
        if not path or not os.path.isfile(path):
            return {"ok": False, "error": "That file could not be found."}
        if not has_key(read_config(), "gemini_api_key"):
            return {"need": "gemini"}
        return self._start(["--import-cv", path], f"Reading your CV: {os.path.basename(path)}")

    def tailor(self, job):
        """A CV + cover letter for a job description pasted into the window."""
        need = self.needs()
        if need:
            return {"need": need}
        job = {k: str((job or {}).get(k) or "").strip() for k in ("company", "title", "url", "text")}
        if not job["company"] or not job["title"] or len(job["text"]) < 100:
            return {"error": "Fill in the company, the job title and the full job description (at least a few lines)."}
        path = os.path.join(HERE, "tailor", "pasted-job.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False)
        return self._start(["--custom", path], f"Tailoring your CV + cover letter for {job['company']}")

    # ----- opening things -----

    def open_url(self, url):
        if isinstance(url, str) and url.lower().startswith(("https://", "http://")):
            webbrowser.open(url)
            return True
        return False

    def open_job(self, job_id):
        j = self.job(job_id)
        return self.open_url(j and j["link"])

    def open_job_files(self, job_id):
        opened = 0
        for path in job_files(job_id):
            if path:
                os.startfile(path)
                opened += 1
        return opened

    def cover_letter(self, job_id):
        letter = job_files(job_id)[1]
        try:
            with open(letter[:-4] + ".txt", encoding="utf-8") as f:
                return f.read()
        except (OSError, TypeError):
            return None

    def open_path(self, path):
        """Open a file a run saved (shown as a link in the activity log). Only files inside the data folder."""
        try:
            real = os.path.realpath(path)
            if os.path.commonpath([real, os.path.realpath(HERE)]) != os.path.realpath(HERE) or not os.path.isfile(real):
                return False
        except (TypeError, ValueError):
            return False
        os.startfile(real)
        return True

    def open_place(self, what):
        """gmail, cvs, tracker, runs, data, profile, guide, issues, download. False (with a reason) when missing."""
        if what == "gmail":
            who = read_config().get("gmail_address", "")
            return self.open_url(f"https://mail.google.com/mail/?authuser={who}#drafts" if who
                                 else "https://mail.google.com/mail/#drafts")
        if what in ("guide", "issues", "download"):
            return self.open_url({"guide": GUIDE_URL, "issues": ISSUES_URL, "download": DOWNLOAD_PAGE}[what])
        if what == "cvs":
            os.makedirs(os.path.join(HERE, "cvs"), exist_ok=True)
            os.startfile(os.path.join(HERE, "cvs"))
            return True
        if what == "data":
            os.startfile(HERE)
            return True
        if what == "profile":
            if not os.path.exists(PROFILE):
                return {"missing": "You have no profile yet. Upload your CV to make one."}
            subprocess.Popen(["notepad.exe", PROFILE])
            return True
        path, missing = {"tracker": (TRACKER, "No tracker yet: it starts with the first CV, draft or skipped job."),
                         "runs": (bot.RUNS_LOG, "No run log yet: it starts with the first search.")}.get(what, (None, ""))
        if path and os.path.exists(path):
            os.startfile(path)
            return True
        return {"missing": missing or "Nothing to open."}

    # ----- AI model -----

    def _model_state(self):
        """gemini_state.json, or an empty state when it belongs to an older key."""
        cfg = read_config()
        state = bot.gemini_state()
        if not has_key(cfg, "gemini_api_key") or state.get("key") != bot.key_id(cfg["gemini_api_key"]):
            return cfg, {}
        return cfg, state

    def models(self):
        """Every model your key can use, with what the bot last saw: working, at its limit and until when."""
        cfg, state = self._model_state()
        names = sorted(state.get("models", []), key=bot.model_rank)
        current = cfg.get("gemini_model", bot.DEFAULT_CONFIG["gemini_model"])
        if current and current not in names:
            names.insert(0, current)
        options, usable = [], 0
        for m in names:
            ok, text = bot.model_status(state, m)
            usable += ok
            options.append({"value": m, "ok": bool(ok), "status": text})
        if state.get("refused"):
            note, tone = (f"Google refused your key: {state['refused']['message'][:90]}. Make a new key in "
                          "Settings > Gmail & Gemini keys."), "error"
        elif not state.get("models"):
            note, tone = "Press Check models to see which models your key can use.", "dim"
        else:
            note, tone = (f"{usable} of {len(names)} models usable right now. Others take over when the chosen one "
                          "is at its limit."), "dim"
        return {"options": options, "selected": current or "", "note": note, "tone": tone}

    def set_model(self, model, force=False):
        model = model or ""
        cfg, state = self._model_state()
        if model and state.get("blocked", {}).get(model, 0) > dt.datetime.now().timestamp():
            ok, text = bot.model_status(state, model)
            if not force:
                return {"confirm": f"{model}: {text}. Google may still refuse it until then. Try it anyway on the "
                                   "next run?"}
            if self._running():
                return {"error": "A run is in progress. Try again when it has finished."}
            for k in ("blocked", "why"):
                state.get(k, {}).pop(model, None)
            bot.save_gemini_state(state)
        cfg["gemini_model"] = model
        write_config(cfg)
        self._note(f"AI model: {model or 'Auto'}"
                   + (" (other free models take over when it is at its limit)" if model else ""), "dim")
        return {"ok": True, "models": self.models()}

    def check_models(self):
        """Ask Google which models this key can use now (the bot also does this once a day)."""
        cfg, state = self._model_state()
        if not has_key(cfg, "gemini_api_key"):
            return {"need": "gemini"}
        if self._running():
            return {"error": "A run is in progress. Check models when it has finished."}
        new = {**state, "key": bot.key_id(cfg["gemini_api_key"]), "listed": 0}
        bot.gemini_models(cfg, new)
        if not new.get("listed"):
            return {"error": "Could not reach Google. Check your internet connection and the key."}
        bot.save_gemini_state(new)
        return {"ok": True, "models": self.models()}

    # ----- keys and settings -----

    def keys(self):
        cfg = read_config()
        return {"fields": [{"key": k, "label": label, "secret": secret, "steps": steps or [],
                            "links": [{"label": t, "url": u} for t, u in links],
                            "value": "" if str(cfg.get(k, "")).startswith("PUT-") else str(cfg.get(k, ""))}
                           for k, label, secret, steps, links in KEY_FIELDS],
                "file": CONFIG}

    def test_keys(self, values):
        """Test the Gemini key and (when filled in) the Gmail app password. Saves nothing."""
        new = {k: str((values or {}).get(k) or "").strip() for k, *_ in KEY_FIELDS}
        if not new["gemini_api_key"]:
            return {"error": "Paste your Gemini API key."}
        gmail = bool(new["gmail_address"] or new["gmail_app_password"])
        if gmail and ("@" not in new["gmail_address"] or not new["gmail_app_password"]):
            return {"error": "For Gmail drafts fill in both the Gmail address and the app password, or leave both "
                             "empty."}
        errors = {"gemini_api_key": test_gemini(new["gemini_api_key"])}
        if gmail:
            errors["gmail_app_password"] = test_gmail(new["gmail_address"], new["gmail_app_password"],
                                                      read_config().get("imap_host", "imap.gmail.com"))
        return {"errors": errors}

    def save_keys(self, values):
        cfg = read_config()
        cfg.update({k: str((values or {}).get(k) or "").strip() for k, *_ in KEY_FIELDS})
        write_config(cfg)
        return {"ok": True, "setup": self.setup(), "models": self.models()}

    def settings(self):
        cfg = read_config()
        return [{"key": k, "label": label, "min": lo, "max": hi, "note": note,
                 "value": cfg.get(k, bot.DEFAULT_CONFIG[k])} for k, label, lo, hi, note in SETTINGS]

    def save_settings(self, values):
        new = read_config()
        for key, label, lo, hi, _ in SETTINGS:
            try:
                n = int(str((values or {}).get(key)).strip())
            except ValueError:
                n = None
            if n is None or not lo <= n <= hi:
                return {"error": f"{label}: type a whole number from {lo} to {hi}.", "field": key}
            new[key] = n
        write_config(new)
        return {"ok": True}

    # ----- Auto-run (Windows Task Scheduler) -----

    def autorun_state(self):
        try:
            r = subprocess.run(["schtasks", "/Query", "/TN", TASK, "/FO", "CSV", "/NH"], capture_output=True,
                               text=True, creationflags=NO_WINDOW, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode:
            return None
        return "off" if "Disabled" in r.stdout else "on"

    def set_autorun(self, on):
        """Create the 30-minute task the first time, then turn it on or off."""
        s = self.autorun_state()
        if s is None:
            if not on:
                return {"ok": True, "state": None}
            cmd = ["schtasks", "/Create", "/TN", TASK, "/SC", "MINUTE", "/MO", "30", "/TR", TASK_RUN, "/F"]
        else:
            cmd = ["schtasks", "/Change", "/TN", TASK, "/ENABLE" if on else "/DISABLE"]
        r = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW, timeout=15)
        if r.returncode:
            return {"error": (r.stderr or r.stdout).strip() or "Windows could not change the Auto-run task.",
                    "state": self.autorun_state()}
        return {"ok": True, "state": self.autorun_state()}

    # ----- updates -----

    def check_update(self):
        tag = latest_release()
        newer = bool(tag and version_tuple(tag) > version_tuple(bot.VERSION))
        if newer:
            self._new_tag = tag
        return {"latest": tag, "newer": newer, "current": bot.VERSION, "reachable": tag is not None,
                "frozen": FROZEN}

    def update_now(self):
        """Download the new installer, run it silently and close: it installs over this copy and reopens Job
        Hunter. Running from source there is no installer, so the download page opens instead."""
        if not FROZEN:
            self.open_url(DOWNLOAD_PAGE)
            return {"state": "source"}

        def work():
            try:
                path = download_setup(lambda pct: self._emit("update", {"state": "downloading", "pct": pct}))
            except (OSError, ValueError) as e:
                self._emit("update", {"state": "failed", "error": str(e)})
                return
            self._emit("update", {"state": "installing"})
            if self._running():
                self.stop()
            # /UPDATE tells the installer to open Job Hunter again when it is done (see JobHunter.iss).
            subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                              "/NOCANCEL", "/UPDATE"], close_fds=True)
            time.sleep(0.8)
            if self._window:
                self._window.destroy()

        threading.Thread(target=work, daemon=True).start()
        return {"state": "downloading"}
