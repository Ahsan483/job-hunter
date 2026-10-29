"""Standalone remote job hunter. Uses no Claude.

Each run:
  1. pulls remote jobs from Remotive, RemoteOK, Arbeitnow, Himalayas, Jobicy, We Work Remotely,
     Working Nomads and the latest Hacker News "Who is hiring?" thread
  2. keeps roles matching your keywords that are remote, recent and (unless turned off)
     open worldwide or to your region
  3. finds an application email published in the post, or on the company's
     own careers/jobs/contact page
  4. asks Gemini (free tier) to check the fit and write the tailoring + email
  5. builds a tailored CV with cv.py and saves a Gmail DRAFT with it attached
     (IMAP), or, without Gmail, the CV + cover letter + email text as files. Nothing is ever sent.

Usage:
  python -I bot.py            normal run (needs config.json)
  python -I bot.py --dry-run  find and filter only; no Gemini, no Gmail
  python -I bot.py --job ID [draft|cv|skip|applied]
                              act on one job from jobs.json (used by gui.py)
  python -I bot.py --custom job.json
                              CV + cover letter for a pasted job ({title, company, text, url?})
  python -I bot.py --import-cv my-cv.pdf
                              rebuild profile.json from your CV (.pdf, .docx, .txt or a photo)
  python -I gui.py            point-and-click window
"""
import base64
import csv
import datetime as dt
import difflib
import email.message
import email.utils
import hashlib
import html
import imaplib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed

# Your files (config, profile, CVs, tracker) live next to the scripts. The installed JobHunter.exe sits in a
# read-only program folder, so it keeps them in %APPDATA%\Job Hunter instead.
FROZEN = getattr(sys, "frozen", False)
# JOBHUNTER_HOME overrides both: a portable copy, or tests that must not touch your real files.
HERE = os.environ.get("JOBHUNTER_HOME") or (
    os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Job Hunter") if FROZEN
    else os.path.dirname(os.path.abspath(__file__)))
os.makedirs(HERE, exist_ok=True)
CODE = os.path.dirname(os.path.abspath(__file__))  # bot.py and cv.py
VERSION = "1.3.0"  # installer/build.ps1 checks that the release tag matches
REPO = "Ahsan483/job-hunter"
UA = {"User-Agent": f"Mozilla/5.0 (compatible; JobHunter/{VERSION}; +https://github.com/{REPO})"}
MIN_GAP = 1.5  # seconds between two requests to the same site
# Job APIs made for programs to read (company career pages) take requests faster than websites do.
API_GAP = {"boards-api.greenhouse.io": 0.3, "api.ashbyhq.com": 0.3, "api.lever.co": 0.3}
REMOTIVE_CACHE = os.path.join(HERE, "remotive_cache.json")
REMOTIVE_TTL = 6 * 3600  # Remotive asks for at most 4 fetches a day
TRACKER = os.path.join(HERE, "tracker.csv")
RUNS_LOG = os.path.join(HERE, "runs.log")
LOCK = os.path.join(HERE, "bot.lock")
MAX_AGE_DAYS = 30

DEFAULT_CONFIG = {
    "gmail_address": "",
    "gmail_app_password": "",
    "imap_host": "imap.gmail.com",
    "gemini_api_key": "",
    "gemini_model": "gemini-flash-latest",
    "max_drafts_per_run": 3,
    "max_drafts_per_day": 20,
    "max_gemini_calls_per_run": 8,
    "min_fit_score": 60,
    # Job filter, editable in the GUI (Settings). A job is kept if ANY keyword appears in its title or text.
    "keywords": [".NET", "C#", "ASP.NET", "dotnet", "Blazor", "Entity Framework"],
    "exclude_keywords": [],
    # True: a keyword must be in the job TITLE. Use it for words like "Sales" or "Finance" that appear in almost
    # every job description.
    "keywords_in_title": False,
    # Job categories to read on We Work Remotely (see WWR_FEEDS), e.g. ["sales & marketing"], or ["all"].
    "job_fields": ["software"],
    "max_job_age_days": MAX_AGE_DAYS,
    # Skip jobs asking for this many years of experience or more (0 = never skip).
    "max_years_required": 8,
    # True: only jobs that say they hire worldwide or in my_region_words. False: every remote job, any country.
    "worldwide_only": True,
    # Your country/region, e.g. ["Pakistan", "South Asia"]. Jobs naming one of these count as open to you.
    "my_region_words": [],
    # Also ask Gemini to search Google (finds posts on LinkedIn, Indeed, Glassdoor, company sites). One Gemini
    # request every few hours; needs a Gemini key.
    "search_google": True,
}


def word_re(words):
    """Regex matching any of the words; whole-word where the word starts/ends with a letter or digit."""
    parts = []
    for w in words:
        p = re.escape(w)
        if w[0].isalnum():
            p = r"\b" + p
        if w[-1].isalnum():
            p += r"\b"
        parts.append(p)
    return re.compile("(" + "|".join(parts) + ")", re.I) if parts else None


def clean_words(v):
    if isinstance(v, str):
        v = v.split(",")
    return [w.strip() for w in v or [] if w.strip()]


# ---------- keyword matching ----------
# People type a job the way they think of it ("remote SEO expert jobs", "seo speciliest"); job titles say
# "SEO Specialist", "Head of SEO", "SEO Manager". So each keyword is cut down to the words that name the job,
# and those words may appear in the title in any order, in another form (recruiter ~ recruiting) or with a typo.
NOISE = {"remote", "online", "job", "jobs", "work", "vacancy", "vacancies", "opening", "openings", "hiring",
         "position", "positions", "role", "roles", "wfh", "from", "home", "for", "of", "in", "the", "a", "an", "and",
         "&", "-", "/", "|", "at", "with", "full", "time", "part", "fulltime", "parttime", "worldwide", "anywhere"}
# Rank words: dropped too, unless what is left would be too broad ("Account Manager" stays as it is).
RANK = {"expert", "specialist", "professional", "freelancer", "freelance", "guru", "ninja", "consultant",
        "manager", "analyst", "executive", "officer", "associate", "strategist", "coordinator", "lead", "head",
        "senior", "junior", "sr", "jr", "entry", "level", "intern", "internship", "trainee", "mid"}
TOO_BROAD = {"account", "product", "project", "program", "data", "business", "office", "general", "technical",
             "digital", "customer", "client", "team", "operations", "senior"}
# Names for the same job; a keyword matching one also finds the others.
ALIASES = [("seo", "search engine optimization", "search engine optimisation"),
           ("ppc", "pay per click", "paid search", "google ads"), ("smm", "social media"),
           ("va", "virtual assistant"), ("ea", "executive assistant"), ("hr", "human resources", "people operations"),
           ("sdr", "sales development"), ("bdr", "business development"), ("cs", "customer success"),
           ("csr", "customer service", "customer support", "customer care"), ("qa", "quality assurance"),
           ("ux", "user experience"), ("ui", "user interface"), ("dotnet", ".net"), ("ai trainer", "ai tutor"),
           ("bookkeeper", "bookkeeping"), ("translator", "translation"), ("copywriter", "copywriting")]
# A word ending in one of these names a job or activity; the same stem with another ending is the same work
# (recruiter, recruiting, recruitment), but the bare stem is not ("marketing" is not "markets").
JOB_ENDING = "ments?|ings?|ers?|ors?|ists?|ants?|ions?"
TOKEN = re.compile(r"[a-z0-9][a-z0-9.#+]*[a-z0-9#+]|[a-z0-9]|\.net|&", re.I)
# Words written together or apart: "Full-Stack", "full stack" and "fullstack" are one word for matching.
COMPOUNDS = re.compile(r"\b(full|front|back|dev|e|cyber|data|word|web|copy|book|on|sales|java|type|white|sys|net)"
                       r"[\s-]+(stack|end|ops|commerce|security|base|press|site|flow|writ\w*|keep\w*|board\w*|"
                       r"force|script|label|admin|work\w*)\b", re.I)
# Words that only say what kind of job it is: "React Developer" partly matches "Frontend Engineer (React)",
# but "developer" alone is not a reason to show a job.
ROLE_WORDS = {"developer", "engineer", "programmer", "designer", "writer", "assistant", "agent", "representative",
              "rep", "administrator", "admin", "technician", "architect", "operator", "staff", "worker", "member"}


def joined(text):
    return COMPOUNDS.sub(lambda m: m.group(1) + m.group(2), text)


def stem(w):
    s = re.sub(rf"({JOB_ENDING}|ies|es|s|e|y)$", "", w)
    return s if len(s) >= 4 else w


def near(w, words):
    """True if w is one of words or a likely typo of one (speciliest ~ specialist, bookeeper ~ bookkeeping).
    Stems are compared only when both words have a job ending, so "accountant" is never "account"."""
    ratio = lambda a, b: difflib.SequenceMatcher(None, a, b).ratio()
    job = lambda x: re.search(rf"({JOB_ENDING})$", x)
    return w in words or len(w) >= 5 and any(
        abs(len(w) - len(x)) <= 3 and not (w.startswith(x) or x.startswith(w))  # account is not a typo of accountant
        and (ratio(w, x) >= 0.8 or job(w) and job(x) and ratio(stem(w), stem(x)) >= 0.85)
        for x in words)


def word_pattern(w):
    """Regex for one keyword word: other forms of a long plain word count (recruiter ~ recruiting, recruitment)."""
    if not re.fullmatch(r"[a-z]{5,}", w):
        return (r"\b" if w[0].isalnum() else "") + re.escape(w) + (r"\b" if w[-1].isalnum() else "")
    s = stem(w)
    if s == w:
        return rf"\b{w}(?:s|es)?\b"
    if re.search(rf"({JOB_ENDING})$", w):
        return rf"\b{s}(?:{JOB_ENDING})\b"
    return rf"\b{s}(?:s|es|e|y|ies)?\b"  # sales ~ sale


def job_words(keyword):
    """The words of a keyword that name the job: 'remote SEO expert jobs' -> ['seo']."""
    words = [w.lower() for w in TOKEN.findall(keyword)]
    words = [w for w in words if w not in NOISE] or words
    core = [w for w in words if not near(w, RANK)]
    return core if core and not (len(core) == 1 and core[0] in TOO_BROAD) else words


class Keyword:
    """One keyword, matched loosely against job titles and exactly against job text."""

    def __init__(self, keyword):
        self.keyword, self.words = keyword, job_words(joined(keyword))
        phrase = " ".join(self.words)
        self.aliases = next((list(a) for a in ALIASES if phrase in a), [phrase])
        self.alias_res = [word_re([a]) for a in self.aliases]
        self.parts = [(w, re.compile(word_pattern(w), re.I)) for w in self.words]
        self.exact = word_re([joined(keyword)])  # job text names skills in passing: it must say the keyword itself
        # Words of a several-word keyword that say what the job is about, for partial matches.
        self.specific = [(w, rx) for w, rx in self.parts if len(self.parts) > 1 and w not in ROLE_WORDS
                         and w not in NOISE and w not in TOO_BROAD and not near(w, RANK)]
        self.squashed = "".join(self.words) if all(w.isalpha() for w in self.words) else ""

    def in_title(self, title):
        """title: already passed through joined()."""
        if any(r.search(title) for r in self.alias_res):
            return True
        words = [t.lower() for t in TOKEN.findall(title) if t.isalpha()]
        if all(rx.search(title) or (len(w) >= 5 and near(w, words)) for w, rx in self.parts):
            return True
        # Other compounds written apart in the title: "WordPress" ~ "Word Press", "Salesforce" ~ "Sales Force".
        pairs = {a + b for a, b in zip(words, words[1:])}
        return len(self.squashed) >= 6 and (self.squashed in pairs or near(self.squashed, pairs))

    def partly_in_title(self, title):
        return any(rx.search(title) for _, rx in self.specific)

    def in_text(self, text):
        return bool(self.exact and self.exact.search(text))

    def search_term(self):
        return self.aliases[0]  # what goes into the job sites' search boxes: "seo", not "seo expert"


STRONG, PARTIAL = 2, 1  # how well a job matches: a keyword in the title, or only part of one / only in the text


class Matcher:
    def __init__(self, keywords):
        self.keywords = [Keyword(k) for k in keywords]

    def score(self, title, text=None):
        """STRONG, PARTIAL or 0. text=None: the title alone counts (Keywords in title only)."""
        title = joined(title)
        if any(k.in_title(title) for k in self.keywords):
            return STRONG
        if any(k.partly_in_title(title) for k in self.keywords):
            return PARTIAL
        if text is not None:
            text = joined(text)
            if any(k.in_text(text) for k in self.keywords):
                return PARTIAL
        return 0

    def __call__(self, title, text=None):
        return self.score(title, text) == STRONG or bool(text is not None and self.score(title, text))

    def explain(self):
        """How the keywords are read, for the run log, only where that differs from what was typed."""
        out = []
        for k in self.keywords:
            shown = " ".join(k.words)
            if shown != k.keyword.lower() or len(k.aliases) > 1:
                also = [a for a in k.aliases if a != shown]
                out.append(f"'{k.keyword}' → titles with {shown}" + (f" (or {', '.join(also)})" if also else ""))
        return out


MATCH = Matcher(DEFAULT_CONFIG["keywords"])
TITLE_ONLY = False
EXCLUDE = None
SEARCH = DEFAULT_CONFIG["keywords"][:10]  # terms sent to the sites that have a search
WORLDWIDE_ONLY = True
REGION = None  # regex of my_region_words
MAX_YEARS = 8
# We Work Remotely has one feed per job category.
WWR_FEEDS = {
    "software": ("remote-full-stack-programming-jobs", "remote-back-end-programming-jobs", "remote-programming-jobs"),
    "devops": ("remote-devops-sysadmin-jobs",),
    "design": ("remote-design-jobs",),
    "sales & marketing": ("remote-sales-and-marketing-jobs",),
    "customer support": ("remote-customer-support-jobs",),
    "finance & management": ("remote-management-and-finance-jobs",),
    "product": ("remote-product-jobs",),
    "other": ("all-other-remote-jobs",),
}
FIELDS = DEFAULT_CONFIG["job_fields"]


GOOGLE = None  # the config, when src_google may ask Gemini to search Google


def apply_filters(cfg):
    global MATCH, TITLE_ONLY, EXCLUDE, SEARCH, MAX_AGE_DAYS, WORLDWIDE_ONLY, REGION, MAX_YEARS, FIELDS, GOOGLE
    GOOGLE = cfg if cfg.get("search_google", True) and is_set(str(cfg.get("gemini_api_key") or "")) else None
    kws = clean_words(cfg.get("keywords")) or DEFAULT_CONFIG["keywords"]
    MATCH = Matcher(kws)
    SEARCH = list(dict.fromkeys(k.search_term() for k in MATCH.keywords))[:10]
    TITLE_ONLY = bool(cfg.get("keywords_in_title"))
    FIELDS = [f.lower() for f in clean_words(cfg.get("job_fields"))
              if f.lower() in WWR_FEEDS or f.lower() == "all"] or DEFAULT_CONFIG["job_fields"]
    EXCLUDE = word_re(clean_words(cfg.get("exclude_keywords")))
    MAX_AGE_DAYS = int(cfg.get("max_job_age_days") or MAX_AGE_DAYS)
    WORLDWIDE_ONLY = bool(cfg.get("worldwide_only", cfg.get("pakistan_only", True)))
    REGION = word_re(clean_words(cfg.get("my_region_words")))
    MAX_YEARS = int(cfg.get("max_years_required", MAX_YEARS) or 0)


def q(term):
    return urllib.parse.quote(term)
REMOTE_OK_LOC = re.compile(r"(worldwide|anywhere|global|remote|emea|apac|any location|international)", re.I)
BLOCK_LOC = re.compile(
    r"(us only|usa only|u\.s\. only|united states only|must (be|reside|live) in (the )?(us|usa|united states|uk|eu|canada)"
    r"|(us|u\.s\.) citizen|green card|h-?1b|\bgc\b|\busc\b|security clearance|\bc2c\b|corp.to.corp|w-?2 only"
    r"|authori[sz]ed to work in the (us|united states|uk|eu)|eu work permit|right to work in the uk"
    r"|india only|remote.{0,15}\(india\)|canada only|uk only|europe only|eu only|latam only)", re.I)
OPEN_GEO = re.compile(r"(worldwide|anywhere|global|apac|emea)", re.I)
# Phrases in a post's text that say it hires from any country.
OPEN_TEXT = re.compile(
    r"(world-?wide|anywhere in the world|(work|live|based) (from )?anywhere|from anywhere"
    r"|hire (globally|internationally|anywhere)|hiring (globally|internationally)|global(ly)? (remote|team|hiring)"
    r"|fully distributed|any country|all countries|any location|any time ?zone|location[- ]independent"
    r"|international (candidates|applicants|contractors)|\bapac\b|\bemea\b)", re.I)
# What is left of a location like "Remote" or "100% Remote" once the generic words are removed.
GENERIC_LOC = re.compile(r"\b(remote|fully|work from home|wfh|n/?a|none)\b|[^a-z]", re.I)
YEARS_ASKED = re.compile(r"\b(\d{1,2})\+?\s*(years|yrs)", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
OBFUSCATED = re.compile(r"\b([A-Za-z0-9._%+-]+)\s*(?:[\[\(\{]\s*at\s*[\]\)\}]|\s+at\s+)\s*([A-Za-z0-9-]+)\s*(?:[\[\(\{]\s*dot\s*[\]\)\}]|\s+dot\s+)\s*([A-Za-z]{2,})\b", re.I)
ONSITE = re.compile(r"\b(onsite|on-site|in office|in-office|hybrid)\b", re.I)
HIRING_LOCAL = re.compile(r"^(careers?|jobs?|hr|hiring|talent|recruit(ing|ment)?|apply|people|work|joinus|join)$", re.I)
BAD_EMAIL = re.compile(r"(noreply|no-reply|donotreply|example\.|sentry|wixpress|\.png|\.jpg|\.gif|\.webp)", re.I)
# Addresses that reach a department, not hiring. Matched on the part before @ only, so jobs@salesloft.com is fine.
ROLE_EMAIL = re.compile(r"^(privacy|abuse|support|billing|sales)$", re.I)
ATS_HOSTS = ("greenhouse.io", "lever.co", "workable.com", "ashbyhq.com", "bamboohr.com", "smartrecruiters.com",
             "recruitee.com", "breezy.hr", "jobvite.com", "myworkdayjobs.com", "teamtailor.com", "personio",
             "remotive.com", "remoteok.com", "arbeitnow.com", "himalayas.app", "linkedin.com", "indeed.",
             "glassdoor.", "wellfound.com", "angel.co", "ycombinator.com", "news.ycombinator.com",
             "google.com", "forms.gle", "typeform.com", "notion.site", "github.com", "twitter.com", "x.com")


# ---------- small helpers ----------

def log(msg):
    print(msg, flush=True)


_last_hit = {}
_hit_lock = threading.Lock()  # company sites are checked from several threads (see find_emails)


def fetch(url, as_json=False, timeout=30, tries=3):
    """GET with a pause between requests to the same site and backoff on 429/5xx."""
    host = urllib.parse.urlparse(url).netloc
    for attempt in range(tries):
        with _hit_lock:  # book the next free slot for this site, then wait for it outside the lock
            slot = max(time.time(), _last_hit.get(host, 0) + API_GAP.get(host, MIN_GAP))
            _last_hit[host] = slot
        if slot > time.time():
            time.sleep(slot - time.time())
        try:
            # Job APIs can be several MB (Arbeitnow is ~4 MB); web pages are cut at 3 MB.
            limit = 20_000_000 if as_json else 3_000_000
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                data = r.read(limit + 1)
            if as_json and len(data) > limit:
                raise ValueError(f"response from {host} is over {limit // 1_000_000} MB")
            raw = data[:limit].decode("utf-8", errors="replace")
            return json.loads(raw) if as_json else raw
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500 or attempt == tries - 1:
                raise
            try:
                delay = float(e.headers.get("Retry-After") or 0)
            except ValueError:
                delay = 0
            time.sleep(min(max(delay, 5 * 2 ** attempt), 60))


_robots = {}


def allowed(url):
    """robots.txt check for pages we crawl ourselves (company sites). No robots.txt means allowed."""
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.parse(fetch(base + "/robots.txt", timeout=10, tries=1).splitlines())
        except Exception:
            rp = None
        _robots[base] = rp
    rp = _robots[base]
    return rp is None or rp.can_fetch(UA["User-Agent"], url)


def text_of(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s or "")
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t]+", " ", html.unescape(s)).strip()


def parse_date(v):
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)) or str(v).isdigit():
            ts = int(v)
            if ts > 10 ** 11:  # milliseconds; on Windows fromtimestamp() raises OSError for these
                ts //= 1000
            d = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
        else:
            d = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (OverflowError, OSError):
        return None
    except ValueError:
        try:
            d = email.utils.parsedate_to_datetime(str(v))
        except Exception:
            return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "company").lower()).strip("-")[:40] or "company"


# ---------- sources ----------

def money(lo, hi, cur="USD", period=""):
    def n(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0
        return v
    lo, hi = n(lo), n(hi)
    if not lo and not hi:
        return ""
    k = lambda v: f"{v / 1000:.0f}k" if v >= 1000 else f"{v:.0f}"
    rng = f"{k(lo)}–{k(hi)}" if lo and hi and lo != hi else k(lo or hi)
    return f"{rng} {cur or ''} {('/ ' + period) if period else ''}".strip()


def src_remotive():
    """One request for Remotive's public feed (every category), cached for 6 hours; the keyword filter runs on our side."""
    try:
        with open(REMOTIVE_CACHE, encoding="utf-8") as f:
            cached = json.load(f)
    except (OSError, ValueError):
        cached = {}
    if time.time() - cached.get("at", 0) < REMOTIVE_TTL:
        jobs = cached.get("jobs", [])
    else:
        jobs = fetch("https://remotive.com/api/remote-jobs", as_json=True).get("jobs", [])
        with open(REMOTIVE_CACHE + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"at": time.time(), "jobs": jobs}, f)
        os.replace(REMOTIVE_CACHE + ".tmp", REMOTIVE_CACHE)
    return [dict(source="remotive", id=f"remotive-{j['id']}", title=j["title"], company=j["company_name"],
                 url=j["url"], location=j.get("candidate_required_location", ""),
                 text=text_of(j.get("description")), date=parse_date(j.get("publication_date")),
                 salary=j.get("salary", ""), job_type=j.get("job_type", "").replace("_", " "),
                 tags=", ".join(j.get("tags", []))) for j in jobs]


def src_remoteok():
    d = fetch("https://remoteok.com/api", as_json=True)
    out = []
    for j in d:
        if "position" not in j:
            continue
        out.append(dict(source="remoteok", id=f"remoteok-{j['id']}", title=j["position"], company=j.get("company", ""),
                        url=j.get("url", ""), location=j.get("location", "") or "Remote",
                        text=text_of(j.get("description")) + " " + " ".join(j.get("tags", [])),
                        date=parse_date(j.get("epoch") or j.get("date")), apply=j.get("apply_url", ""),
                        salary=money(j.get("salary_min"), j.get("salary_max"), "USD", "year"),
                        tags=", ".join(j.get("tags", []))))
    return out


def src_arbeitnow():
    out = []
    for page in (1, 2, 3):
        d = fetch(f"https://www.arbeitnow.com/api/job-board-api?page={page}", as_json=True)
        for j in d.get("data", []):
            if not j.get("remote"):
                continue
            out.append(dict(source="arbeitnow", id=f"arbeitnow-{j['slug']}", title=j["title"],
                            company=j["company_name"], url=j["url"], location=j.get("location", ""),
                            text=text_of(j.get("description")), date=parse_date(j.get("created_at")),
                            job_type=", ".join(j.get("job_types", [])), tags=", ".join(j.get("tags", []))))
        if not (d.get("links") or {}).get("next"):
            break
    return out


def _himalayas(j):
    loc = ", ".join(j.get("locationRestrictions") or []) or "Worldwide"
    return dict(source="himalayas", id=f"himalayas-{j.get('guid')}", title=j["title"],
                company=j.get("companyName", ""), url=j.get("applicationLink") or j.get("guid", ""),
                location=loc, text=text_of(j.get("description") or j.get("excerpt")),
                date=parse_date(j.get("pubDate")), apply=j.get("applicationLink", ""),
                salary=money(j.get("minSalary"), j.get("maxSalary"), j.get("currency"), j.get("salaryPeriod")),
                job_type=j.get("employmentType", ""), level=", ".join(j.get("seniority") or []), geo_strict=True)


def src_himalayas():
    out = []
    for offset in (0, 20, 40, 60):
        d = fetch(f"https://himalayas.app/jobs/api?limit=20&offset={offset}", as_json=True)
        out += [_himalayas(j) for j in d.get("jobs", [])]
    # Keyword search finds older posts the latest-jobs feed has already pushed out.
    for term in SEARCH:
        for page in ((1, 2, 3) if len(SEARCH) <= 3 else (1, 2)):
            d = fetch(f"https://himalayas.app/jobs/api/search?q={q(term)}&limit=20&page={page}", as_json=True)
            out += [_himalayas(j) for j in d.get("jobs", [])]
    return out


def src_jobicy():
    out = []
    for term in SEARCH:
        tag = term.lower().replace("c#", "c-sharp").replace(" ", "-")
        try:
            d = fetch(f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={q(tag)}", as_json=True)
        except urllib.error.HTTPError as e:
            log(f"  jobicy tag '{tag}': HTTP {e.code}, skipped")
            continue
        for j in d.get("jobs", []):
            out.append(dict(source="jobicy", id=f"jobicy-{j['id']}", title=html.unescape(j["jobTitle"]),
                            company=j.get("companyName", ""), url=j["url"], location=j.get("jobGeo", "") or "Anywhere",
                            text=text_of(j.get("jobDescription") or j.get("jobExcerpt")),
                            date=parse_date(j.get("pubDate")),
                            salary=money(j.get("salaryMin"), j.get("salaryMax"), j.get("salaryCurrency"),
                                         j.get("salaryPeriod")),
                            job_type=", ".join(j.get("jobType") or []), level=j.get("jobLevel", ""),
                            geo_strict=True))
    return out


def rss_items(url):
    """Each <item> of an RSS feed as {tag: text}, with CDATA unwrapped and entities decoded."""
    out = []
    for item in re.findall(r"(?s)<item>(.*?)</item>", fetch(url)):
        d = {}
        for tag, body in re.findall(r"(?s)<([\w:]+)[^>]*>(.*?)</\1>", item):
            d.setdefault(tag, html.unescape(re.sub(r"(?s)<!\[CDATA\[(.*?)\]\]>", r"\1", body)).strip())
        out.append(d)
    return out


def last_part(url):
    return url.rstrip("/").rsplit("/", 1)[-1]


def src_weworkremotely():
    out = []
    feeds = dict.fromkeys(c for f in (WWR_FEEDS if "all" in FIELDS else FIELDS) for c in WWR_FEEDS[f])
    for cat in feeds:
        for it in rss_items(f"https://weworkremotely.com/categories/{cat}.rss"):
            company, _, title = it.get("title", "").partition(": ")
            link = it.get("link") or it.get("guid", "")
            out.append(dict(source="weworkremotely", id=f"wwr-{last_part(link)}", title=title or company,
                            company=company if title else "", url=link, location=it.get("region") or "Remote",
                            text=text_of(it.get("description")), date=parse_date(it.get("pubDate")),
                            job_type=it.get("type", ""), tags=it.get("skills", "")))
    return out


def title_at_company(s):
    """'Data Analyst at Acme' -> ('Data Analyst', 'Acme')."""
    title, at, company = s.rpartition(" at ")
    return (title, company) if at else (s, "")


def src_remotefirstjobs():
    out = []
    for it in rss_items("https://remotefirstjobs.com/rss/jobs.rss"):
        title, company = title_at_company(it.get("title", ""))
        out.append(dict(source="remotefirstjobs", id=f"rfj-{last_part(it.get('link', ''))}", title=title,
                        company=company, url=it.get("link", ""), location="Remote",
                        text=text_of(it.get("description")), date=parse_date(it.get("pubDate"))))
    return out


def src_realworkfromanywhere():
    """Only jobs you can do from any country, as the site's name says."""
    out = []
    for it in rss_items("https://www.realworkfromanywhere.com/rss.xml"):
        title, company = title_at_company(it.get("title", ""))
        out.append(dict(source="realworkfromanywhere", id=f"rwfa-{last_part(it.get('link', ''))}", title=title,
                        company=company, url=it.get("link", ""), location="Anywhere",
                        text=text_of(it.get("description")), date=parse_date(it.get("pubDate"))))
    return out


def src_workew():
    out = []
    for it in rss_items("https://workew.com/feed/?post_type=job_listing"):
        link = it.get("link", "")
        # The link ends in <title>-<company>: https://workew.com/job/it-support-specialist-6sense/
        company = last_part(link).removeprefix(slug(it.get("title")) + "-").replace("-", " ").title()
        out.append(dict(source="workew", id=f"workew-{last_part(link)}", title=it.get("title", ""),
                        company=company, url=link, location="Remote",
                        text=text_of(it.get("description")).split("The post ")[0],
                        date=parse_date(it.get("pubDate"))))
    return out


def src_jobicy_feed():
    """Jobicy's feed of every new job; the API (src_jobicy) adds older ones by keyword."""
    out = []
    for it in rss_items("https://jobicy.com/feed/job_feed"):
        out.append(dict(source="jobicy", id=f"jobicy-{it.get('id') or last_part(it.get('link', ''))}",
                        title=it.get("title", ""), company=it.get("job_listing:company", ""), url=it.get("link", ""),
                        location=it.get("job_listing:location") or "Anywhere",
                        text=text_of(it.get("content:encoded") or it.get("description")),
                        date=parse_date(it.get("pubDate")), job_type=it.get("job_listing:job_type", ""),
                        salary=money(it.get("job_listing:salary_min"), it.get("job_listing:salary_max"),
                                     it.get("job_listing:salary_currency"), it.get("job_listing:salary_period")),
                        geo_strict=True))
    return out


def src_themuse():
    out = []
    for page in range(5):
        d = fetch("https://www.themuse.com/api/public/jobs?location=Flexible%20%2F%20Remote&descending=true"
                  f"&page={page}", as_json=True)
        for j in d.get("results", []):
            out.append(dict(source="themuse", id=f"themuse-{j['id']}", title=j.get("name", "").strip(),
                            company=(j.get("company") or {}).get("name", ""),
                            url=(j.get("refs") or {}).get("landing_page", ""),
                            location=", ".join(x["name"] for x in j.get("locations") or []) or "Remote",
                            text=text_of(j.get("contents")), date=parse_date(j.get("publication_date")),
                            level=", ".join(x["name"] for x in j.get("levels") or [])))
        if page + 1 >= d.get("page_count", 0):
            break
    return out


def src_4dayweek():
    out = []
    for page in (1, 2, 3):
        d = fetch(f"https://4dayweek.io/api?page={page}", as_json=True)
        for j in d.get("jobs", []):
            if str(j.get("is_remote")).lower() != "true":
                continue
            out.append(dict(source="4dayweek", id=f"4dayweek-{j.get('id_str') or j.get('slug')}",
                            title=j.get("title", ""), company=j.get("company_name", ""), url=j.get("url", ""),
                            location=j.get("location_original") or j.get("location_country") or "Remote",
                            text=text_of(j.get("description")), date=parse_date(j.get("posted")),
                            level=j.get("level", ""), tags=j.get("category", "")))
        if not d.get("has_more"):
            break
    return out


# Remote-first companies whose career pages run on Greenhouse, Ashby or Lever: these have public job APIs.
BOARDS = [("greenhouse", s) for s in ("gitlab", "grafanalabs", "mozilla", "wikimedia", "twilio", "reddit", "coinbase",
                                      "stripe", "pinterest", "dropbox", "automatticcareers", "datadog", "discord",
                                      "sourcegraph91", "airtable", "vercel")] + \
         [("ashby", s) for s in ("supabase", "vanta", "1password", "posthog", "ramp", "zapier", "linear", "sentry",
                                 "replit")] + \
         [("lever", s) for s in ("binance", "anchorage", "toptal")]


def board_jobs(ats, name):
    """One company's open jobs. Greenhouse lists titles only, so its texts are read for matching titles only."""
    if ats == "greenhouse":
        base = f"https://boards-api.greenhouse.io/v1/boards/{name}/jobs"
        out, reads = [], 0
        for j in fetch(base, as_json=True).get("jobs", []):
            job = dict(source="greenhouse", id=f"greenhouse-{j['id']}", title=j.get("title", ""),
                       company=j.get("company_name") or name, url=j.get("absolute_url", ""),
                       location=(j.get("location") or {}).get("name", ""), text="",
                       date=parse_date(j.get("first_published") or j.get("updated_at")), any_job=True)
            remote = REMOTE_OK_LOC.search(job["location"])
            if remote and reads < 15 and MATCH.score(job["title"]):  # 15 a company keeps a search quick
                reads += 1
                job["text"] = text_of(html.unescape(fetch(f"{base}/{j['id']}", as_json=True).get("content", "")))
            out.append(job)
        return out
    if ats == "ashby":
        d = fetch(f"https://api.ashbyhq.com/posting-api/job-board/{name}", as_json=True)
        return [dict(source="ashby", id=f"ashby-{j['id']}", title=j.get("title", ""), company=name.title(),
                     url=j.get("jobUrl", ""), location=", ".join(filter(None, [
                         j.get("location"), "Remote" if j.get("isRemote") or j.get("workplaceType") == "Remote" else ""])),
                     text=j.get("descriptionPlain", ""), date=parse_date(j.get("publishedAt")),
                     job_type=j.get("employmentType", ""), any_job=True) for j in d.get("jobs", [])]
    d = fetch(f"https://api.lever.co/v0/postings/{name}?mode=json", as_json=True)
    return [dict(source="lever", id=f"lever-{j['id']}", title=j.get("text", ""), company=name.title(),
                 url=j.get("hostedUrl", ""), location=", ".join(filter(None, [
                     (j.get("categories") or {}).get("location"),
                     "Remote" if j.get("workplaceType") == "remote" else ""])),
                 text=f"{j.get('descriptionPlain', '')}\n{j.get('additionalPlain', '')}",
                 date=parse_date(j.get("createdAt")), job_type=(j.get("categories") or {}).get("commitment", ""),
                 any_job=True) for j in d]


GOOGLE_CACHE = os.path.join(HERE, "google_cache.json")
GOOGLE_TTL = 4 * 3600  # Auto-run every 30 minutes must not use up the free Gemini quota
GOOGLE_PROMPT = """Use Google Search to find up to 30 real job postings published in the last {days} days for any of
these: {terms}. Only remote jobs{where}. Search LinkedIn, Indeed, Glassdoor, Wellfound, company career pages and other
job sites. Only include postings you actually found in the search results, each with the posting's own URL.
Return ONLY JSON:
{{"jobs": [{{"title": "", "company": "", "url": "", "location": "as the posting says", "posted": "YYYY-MM-DD or \\"\\"",
  "description": "3-5 sentences from the posting: the work, the requirements and how to apply (keep any email address)"}}]}}"""


def src_google():
    """Postings on sites with no public feed (LinkedIn, Indeed, Glassdoor, company sites), found by Gemini with Google
    Search. A posting is kept only if its site is among the pages Google returned, so no made-up links get in."""
    if not GOOGLE:
        return []
    where = f", open to people in {', '.join(clean_words(GOOGLE.get('my_region_words')))} or worldwide" \
        if WORLDWIDE_ONLY and clean_words(GOOGLE.get("my_region_words")) else \
        ", open worldwide" if WORLDWIDE_ONLY else ""
    prompt = GOOGLE_PROMPT.format(days=MAX_AGE_DAYS, terms=", ".join(SEARCH), where=where)
    ask = key_id(prompt)
    try:
        with open(GOOGLE_CACHE, encoding="utf-8") as f:
            cached = json.load(f)
    except (OSError, ValueError):
        cached = {}
    if cached.get("ask") == ask and time.time() - cached.get("at", 0) < GOOGLE_TTL:
        found = cached.get("jobs", [])
    elif cached.get("refused_until", 0) > time.time():
        return []  # this key has no Google Search quota: asked again once a day, not every run
    else:
        try:
            res = gemini(GOOGLE, prompt, search=True)
        except RuntimeError as e:
            if NO_SEARCH not in str(e):
                raise
            log(f"  {NO_SEARCH} (Google wants billing turned on for it). The other job sites were searched as usual; "
                "Job Hunter tries Google again tomorrow. Untick Search Google too to stop trying.")
            with open(GOOGLE_CACHE, "w", encoding="utf-8") as f:
                json.dump({"refused_until": time.time() + 86400}, f)
            return []
        sites = {s.lower().removeprefix("www.") for s in res.get("_sites", []) if s}
        found = []
        for j in res.get("jobs") or []:
            if not isinstance(j, dict) or not str(j.get("url", "")).startswith("http"):
                continue
            host = urllib.parse.urlparse(j["url"]).netloc.lower().removeprefix("www.")
            if any(host == s or host.endswith("." + s) or s.endswith("." + host) for s in sites):
                found.append(j)
        log(f"  Google: {len(found)} postings found ({len(res.get('jobs') or []) - len(found)} without a checked link "
            "left out)")
        with open(GOOGLE_CACHE + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"ask": ask, "at": time.time(), "jobs": found}, f)
        os.replace(GOOGLE_CACHE + ".tmp", GOOGLE_CACHE)
    now = dt.datetime.now(dt.timezone.utc)
    return [dict(source="google", id=f"google-{key_id(j['url'])}", title=str(j.get("title", "")),
                 company=str(j.get("company", "")), url=j["url"], location=str(j.get("location") or "Remote"),
                 text=str(j.get("description", "")), date=parse_date(j.get("posted")) or now) for j in found]


def src_companies():
    out = []
    with ThreadPoolExecutor(max_workers=3) as pool:  # one per job system; fetch() spaces requests to each
        for f in as_completed([pool.submit(board_jobs, ats, name) for ats, name in BOARDS]):
            try:
                out += f.result()
            except Exception as e:  # one company's page moving must not lose the others
                log(f"  a company career page failed ({e.__class__.__name__}), skipped")
    return out


def src_workingnomads():
    d = fetch("https://www.workingnomads.com/api/exposed_jobs/", as_json=True)
    return [dict(source="workingnomads", id=f"workingnomads-{j['url'].rstrip('/').rsplit('/', 1)[-1]}",
                 title=j["title"], company=j.get("company_name", ""), url=j["url"],
                 location=j.get("location", "") or "Remote", text=text_of(j.get("description")),
                 date=parse_date(j.get("pub_date")), tags=j.get("tags", "")) for j in d]


def src_hn():
    d = fetch("https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&query=who%20is%20hiring",
              as_json=True)
    stories = [h for h in d["hits"] if h["title"].startswith("Ask HN: Who is hiring?")]
    out, seen = [], set()
    # This month's thread and last month's (early in a month the new one is still small).
    for story in stories[:2]:
        sid = story["objectID"]
        for term in SEARCH:
            c = fetch(f"https://hn.algolia.com/api/v1/search?tags=comment,story_{sid}&query={q(term)}"
                      "&hitsPerPage=100", as_json=True)
            for h in c["hits"]:
                if h["objectID"] in seen or h.get("parent_id") != int(sid):
                    continue
                seen.add(h["objectID"])
                t = text_of(h.get("comment_text"))
                first = t.split("\n")[0]
                parts = [p.strip() for p in first.split("|")]
                out.append(dict(source="hn", id=f"hn-{h['objectID']}", title=first[:140],
                                company=parts[0][:60] if parts else "",
                                url=f"https://news.ycombinator.com/item?id={h['objectID']}", location=first,
                                text=t, date=parse_date(h.get("created_at")), raw_html=h.get("comment_text", "")))
    return out


SOURCES = [src_remotive, src_remoteok, src_arbeitnow, src_himalayas, src_jobicy, src_jobicy_feed, src_weworkremotely,
           src_workingnomads, src_hn, src_themuse, src_remotefirstjobs, src_realworkfromanywhere, src_workew,
           src_4dayweek, src_companies, src_google]


# ---------- filtering ----------

# HN's location line: "Remote (US)" or "REMOTE - Europe" says where remote means.
REMOTE_SOMEWHERE = re.compile(r"remote\W{0,4}(us|usa|u\.s\.?|united states|canada|uk|europe|eu|north america|americas"
                              r"|latam|germany|india)\b", re.I)


def open_to_me(job):
    """True if the post says it hires worldwide or in my_region_words, False if it names somewhere else,
    None if it does not say (many posts just say "Remote": those are kept, marked "location not stated")."""
    if OPEN_GEO.search(job["location"]) or (REGION and REGION.search(job["location"])):
        return True
    # Himalayas and Jobicy list the allowed countries; trust that list over words in the text.
    if job.get("geo_strict"):
        return False
    # A location like "USA" or "Berlin" names somewhere else. HN's "location" is the whole first line.
    if job["source"] != "hn" and GENERIC_LOC.sub("", job["location"]):
        return False
    if job["source"] == "hn" and REMOTE_SOMEWHERE.search(job["location"]):
        return False
    head = job["text"][:6000]
    return True if OPEN_TEXT.search(head) or (REGION and REGION.search(head)) else None


def prefilter(job, now):
    """Why a job is left out, or None. Sets job["match"] ("strong" / "partial") and job["note"]."""
    blob = f"{job['title']}\n{job['location']}\n{job['text']}"
    score = MATCH.score(job["title"], None if TITLE_ONLY else job["text"][:4000])
    if not score:
        return "no keyword match"
    job["match"] = "strong" if score == STRONG else "partial"
    if EXCLUDE and EXCLUDE.search(job["title"]):
        return "excluded word in title"
    if not job["date"]:
        return "no post date"
    if (now - job["date"]).days > MAX_AGE_DAYS:
        return "too old"
    # Job boards list remote jobs only (Arbeitnow is filtered on its own remote flag), so a location like
    # "Philippines" there still means remote. HN posts and company career pages list every kind of job.
    where = job["location"] + " " + job["text"][:3000]
    if (job["source"] == "hn" or job.get("any_job")) and not (REMOTE_OK_LOC.search(where)
                                                             or (REGION and REGION.search(where))):
        return "not remote"
    if WORLDWIDE_ONLY:
        if BLOCK_LOC.search(blob):
            return "location/work-auth restricted"
        open_ = open_to_me(job)
        if open_ is False:
            return "not open worldwide/to my region"
        if open_ is None:
            job["note"] = "location not stated: check the post hires in your country"
    head = job["location"] if job["source"] == "hn" else job["location"] + " " + job["title"]
    if ONSITE.search(head) and not re.search(r"remote", head, re.I):
        return "onsite/hybrid"
    if MAX_YEARS and max(years_asked(blob), default=0) >= MAX_YEARS:
        return f"{MAX_YEARS}+ years"
    return None


ABOUT_COMPANY = re.compile(r"\b(company|companies|we|we've|we have|our|founded|history|business|brand|industry)\b", re.I)


def years_asked(text):
    """Years of experience a post asks for. "A company with 30+ years of experience" is about the company, and
    no post asks for more than 20 years, so those are left out."""
    out = []
    for m in YEARS_ASKED.finditer(text):
        n = int(m.group(1))
        if n <= 20 and not ABOUT_COMPANY.search(text[max(0, m.start() - 40):m.start()]):
            out.append(n)
    return out


def find_emails_in_text(t):
    found = set(EMAIL_RE.findall(t))
    for a, b, c in OBFUSCATED.findall(t):
        found.add(f"{a}@{b}.{c}")
    return [e.strip(".").lower() for e in found if not BAD_EMAIL.search(e) and not ROLE_EMAIL.match(e.split("@")[0])]


def company_sites(job):
    urls = re.findall(r"https?://[^\s\"'<>)]+", (job.get("raw_html") or "") + " " + job["text"] + " " + job.get("apply", ""))
    hosts = []
    for u in urls:
        host = urllib.parse.urlparse(html.unescape(u)).netloc.lower().split(":")[0]
        if host and not any(a in host for a in ATS_HOSTS) and host not in hosts:
            hosts.append(host)
    return hosts[:2]


_site_email = {}  # site -> (email, page) or (None, None): each company site is read once per run


def site_email(site):
    base = "https://" + site
    for path in ("/careers", "/jobs", "/join-us", "/contact", "/"):
        try:
            if not allowed(base + path):
                continue
            page = fetch(base + path, timeout=10, tries=1)
        except urllib.error.HTTPError:
            continue  # this page is missing; the site is up, so try the next one
        except Exception:
            break  # site down, slow or refusing connections: skip its other pages
        for e in find_emails_in_text(page):
            local, _, domain = e.lower().partition("@")
            same_site = site == domain or site.endswith("." + domain) or domain.endswith("." + site)
            if HIRING_LOCAL.match(local) and same_site:
                return e, base + path
    return None, None


def careers_page_email(job):
    """Look for a published hiring address on the company's own site."""
    for host in company_sites(job):
        site = host.removeprefix("www.")
        if site not in _site_email:
            _site_email[site] = site_email(site)
        if _site_email[site][0]:
            return _site_email[site]
    return None, None


def pick_email(job):
    emails = find_emails_in_text(job["text"])
    hiring = [e for e in emails if HIRING_LOCAL.match(e.split("@")[0])]
    if hiring:
        return hiring[0], job["url"]
    if emails and re.search(r"(email|send|apply|cv|resume|reach out|contact)", job["text"], re.I):
        return emails[0], job["url"]
    return careers_page_email(job)


# ---------- tracker ----------

def read_tracker():
    if not os.path.exists(TRACKER):
        with open(TRACKER, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["date", "company", "role", "email", "poster", "post_url", "cv_file", "draft_id", "status"])
        return []
    with open(TRACKER, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def add_tracker(row):
    with open(TRACKER, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([row.get(k, "") for k in
                                ["date", "company", "role", "email", "poster", "post_url", "cv_file", "draft_id", "status"]])


def already_done(rows, job, mail, today):
    for r in rows:
        if r.get("post_url") == job["url"] or r.get("draft_id") == job["id"]:
            return True
        if mail and r.get("email", "").lower() == mail:
            try:
                if (today - dt.date.fromisoformat(r["date"][:10])).days < 14:
                    return True
            except ValueError:
                return True
    return False


# ---------- Gemini ----------

GEMINI_PROMPT = """You help {name} apply for remote jobs. {name} lives in {location}.
PROFILE (the ONLY source of facts; never add anything that is not here):
{profile}

JOB (source: {source}, url: {url}):
Title: {title}
Company: {company}
Location: {job_location}
Description:
{text}

Decide and write. Return ONLY JSON with exactly these keys:
{{
 "eligible": true/false,   // false if the job is not open to someone working remotely from {location}, needs a visa/citizenship/residency/clearance, is onsite/hybrid, is a staffing/C2C/bench-sales post, or looks like a scam
 "reason": "one short sentence",
 "fit_score": 0-100,       // how well the profile matches the job's real requirements; be strict about missing core skills
 "tailor": {{
   "title": "headline for THIS role built only from titles and skills in PROFILE, e.g. 'Backend Software Engineer | C# | Docker | Azure' or 'Accountant | IFRS | Xero | Payroll'; say 'Senior' or 'Lead' only if a PROFILE title does",
   "summary": "3-4 sentences written for THIS job. Do NOT copy default_summary. Open with the PROFILE experience closest to what the job asks for, use the job's own wording where PROFILE supports it, and leave out PROFILE skills the job does not care about",
   "skills_first": ["job keywords that exist in PROFILE skills, most important first"],
   "bullets": {{"<experience id>": [bullet indexes, most relevant to this job first; leave out unrelated ones but keep at least 2 per role]}},
   "rewrites": {{"<experience id>": {{"<bullet index>": "that bullet reworded so its relevance to this job is obvious. Same facts and same numbers; every tool, skill, certification, language and number must already be in PROFILE"}}}},
   "projects": ["1-3 project ids most relevant to this job"]
 }},
 "subject": "Application: <role> – {name}",
 "body": "plain-text email, 120-200 words",
 "cover_letter": "one-page cover letter, 250-350 words, 4-5 paragraphs separated by a blank line"
}}
These words are in the job ad but NOT in PROFILE. Never put them in the title, summary or rewrites (the CV check removes any sentence that uses one): {avoid}
Rewrites: reword the 2-3 bullets per role that matter most for this job. Never add a technology, tool, software, certification, language, number, client or responsibility that is not in PROFILE: if the job asks for C++ and PROFILE has C#, write about C#, never C++; if it asks for SAP and PROFILE has QuickBooks, write about QuickBooks.
Email rules: greeting to the company team (or the person if the post names who to email); say which role and where it was seen; 2-3 short sentences matching their requirements to real facts and numbers from PROFILE, only the relevant ones; "I'm based in {location_short}, available for remote work and able to overlap with your team's hours."; links: {links}; "My CV is attached."; ask for a short call; sign off with {sign_off}.
Cover letter rules: start "Dear <team or the person named in the post>,"; paragraph 1: the role, where it was seen, one specific reason this company or product fits; paragraphs 2-3: take the job's 3-4 main requirements and answer each with a concrete PROFILE fact (project, result, number); only paragraph 1 may describe the company's product; from paragraph 2 on, describe only work PROFILE says {name} did, in PROFILE's own terms, without adding the job's wording to it; if the job needs something PROFILE does not have, say plainly and briefly which PROFILE experience is closest and how it transfers, never claim it; no inflated words like "extensive", "deep", "massive", "expert"; last paragraph: remote from {location_short}, overlap with their hours, ask for a call; end "Sincerely,\\n{name}". No address block, no date, no links, no markdown.
Never claim more than {years} years. No cliches like "passionate" or "hardworking"."""


GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_TIMEOUT = 120  # seconds to wait for one model's answer before trying the next model
GEMINI_STATE = os.path.join(HERE, "gemini_state.json")  # model list + which models are out of free quota
NOT_TEXT_MODEL = re.compile(r"(tts|image|banana|live|audio|transcribe|robotics|computer-use|embedding|antigravity"
                            r"|deep-research|lyria|omni|customtools|argon|aqa)", re.I)
NO_MODEL = "No Gemini model is available"
NO_SEARCH = "Google Search is not in your Gemini key's free quota"


def gemini_state():
    try:
        with open(GEMINI_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def key_id(key):
    """Short fingerprint of a key, so the state file knows which key it belongs to without storing it."""
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def save_gemini_state(s):
    with open(GEMINI_STATE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)
    os.replace(GEMINI_STATE + ".tmp", GEMINI_STATE)


def model_rank(name):
    """Flash first, then Flash-Lite, Gemma and Pro (rarely free); stable before preview; newest first."""
    kind = (1 if "lite" in name else 0) if "flash" in name else 2 if "gemma" in name else 3
    m = re.search(r"-(\d+(?:\.\d+)?)", name)
    ver = 99 if name.endswith("-latest") else float(m.group(1)) if m else 0
    return kind, "preview" in name, -ver, name


def gemini_models(cfg, state):
    """Your chosen models first, then every other text model your key can use, best first. Listed once a day."""
    if time.time() - state.get("listed", 0) > 86400 or not state.get("models"):
        try:
            req = urllib.request.Request(f"{GEMINI_API}?pageSize=200", headers={"x-goog-api-key": cfg["gemini_api_key"]})
            with urllib.request.urlopen(req, timeout=30) as r:
                listed = json.loads(r.read().decode()).get("models", [])
            state["models"] = [m["name"].removeprefix("models/") for m in listed
                               if "generateContent" in m.get("supportedGenerationMethods", [])
                               and not NOT_TEXT_MODEL.search(m["name"])
                               and re.search(r"(flash|gemma|pro)", m["name"])]
            state["listed"] = time.time()
        except Exception as e:
            log(f"  could not list Gemini models ({e.__class__.__name__}), using the ones in config.json")
    # gemini_model "" means Auto: the best model first. A chosen model goes first, then its fallback.
    chosen = ([cfg["gemini_model"], cfg.get("gemini_fallback_model", "gemini-flash-lite-latest")]
              if cfg.get("gemini_model") else [])
    found = sorted(state.get("models", []), key=model_rank) or ["gemini-flash-latest", "gemini-flash-lite-latest"]
    return list(dict.fromkeys([m for m in chosen if m] + found))


def model_status(state, model):
    """(ok, text) for one model, as the window's model menu shows it."""
    now = time.time()
    if state.get("blocked", {}).get(model, 0) > now:
        back = time.strftime("%d %b %H:%M", time.localtime(state["blocked"][model]))
        why = state.get("why", {}).get(model, "blocked")
        return False, f"{why}, checked again {back}" if why.startswith(("no free", "not avail")) else f"{why} until {back}"
    u = state.get("usage", {}).get(model, {})
    if u.get("day") == dt.date.today().isoformat():
        return True, f"working, {u['calls']} call{'s' if u['calls'] != 1 else ''} today"
    if u.get("ok"):
        return True, f"last worked {time.strftime('%d %b %H:%M', time.localtime(u['ok']))}"
    return True, "not tried yet"


def answer_json(d):
    """The JSON object in a Gemini reply, even when the model wraps it in ```json fences."""
    text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"] if not p.get("thought"))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text[text.index("{"):text.rindex("}") + 1])


def quota_wait(err):
    """(seconds until the quota resets, model the quota belongs to) from a 429 error body."""
    wait, owner = 60.0, None
    for det in err.get("details", []):
        if det.get("retryDelay"):
            wait = float(det["retryDelay"].rstrip("s") or 60)
        for v in det.get("violations", []):
            owner = v.get("quotaDimensions", {}).get("model") or owner
            if "PerDay" in v.get("quotaId", ""):
                wait = max(wait, 3600)
    if "limit: 0" in err.get("message", ""):  # this model has no free tier for your key
        wait = 7 * 86400
    return wait, owner


def gemini(cfg, prompt, attach=None, search=False):
    """Ask Gemini for a JSON answer. When a model is out of free quota, switches to the next free one
    and remembers until when that model is blocked. attach: optional (mime type, bytes), e.g. a PDF.
    search: let Gemini use Google Search; the answer then gets "_sites", the sites Google returned."""
    parts = [{"text": prompt}]
    if attach:
        parts.append({"inline_data": {"mime_type": attach[0], "data": base64.b64encode(attach[1]).decode()}})
    state = gemini_state()
    if state.get("key") != key_id(cfg["gemini_api_key"]):  # new key: its quotas and model list are not the old key's
        state = {"key": key_id(cfg["gemini_api_key"])}
    blocked, why = state.setdefault("blocked", {}), state.setdefault("why", {})
    usage = state.setdefault("usage", {})
    models = gemini_models(cfg, state)
    if attach or search:  # Gemma cannot read files (a PDF CV gets error 500) or use Google Search
        models = [m for m in models if not m.startswith("gemma")] or models
    last, tried, back_at = "no response", 0, []
    for model in models:
        if blocked.get(model, 0) > time.time():
            back_at.append(blocked[model])
            continue
        if tried == (2 if search else 8):  # Google Search is extra: not worth a long hunt for a model
            break
        tried += 1
        if tried > 1:  # say why we moved on, so a slow fallback does not look like a hang
            log(f"  {last}. Trying {model} ...")
        gen = {"temperature": 0.4}
        if not model.startswith("gemma") and not search:  # no JSON mode for Gemma or with Google Search;
            gen["responseMimeType"] = "application/json"   # the prompt still asks for JSON
        ask = {"contents": [{"parts": parts}], "generationConfig": gen}
        if search:
            ask["tools"] = [{"google_search": {}}]
        body = json.dumps(ask).encode()
        req = urllib.request.Request(f"{GEMINI_API}/{model}:generateContent", data=body,
                                     headers={"Content-Type": "application/json", "x-goog-api-key": cfg["gemini_api_key"]})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=GEMINI_TIMEOUT) as r:
                    data = json.loads(r.read().decode())
                res = answer_json(data)
                if search and isinstance(res, dict):
                    chunks = data["candidates"][0].get("groundingMetadata", {}).get("groundingChunks", [])
                    res["_sites"] = [c["web"].get("title", "") for c in chunks if c.get("web")]
                if model != models[0]:
                    log(f"  (answered by Gemini model {model})")
                today = dt.date.today().isoformat()
                u = usage.get(model) if usage.get(model, {}).get("day") == today else {"day": today, "calls": 0}
                usage[model] = {**u, "calls": u["calls"] + 1, "ok": time.time()}
                state.pop("refused", None)
                save_gemini_state(state)
                return res
            except urllib.error.HTTPError as e:
                try:
                    err = json.loads(e.read().decode()).get("error", {})
                except ValueError:
                    err = {}
                last = f"Gemini error {e.code} ({model}): {err.get('message', '')[:150]}"
                if e.code == 429 and search:
                    # The Search tool has its own, smaller quota (none on many free keys). The model itself may
                    # still be fine for CVs, so nothing is marked as blocked.
                    raise RuntimeError(NO_SEARCH)
                if e.code == 429:
                    wait, owner = quota_wait(err)
                    if wait <= 60 and attempt < 2:  # per-minute limit: just wait
                        time.sleep(wait + 1)
                        continue
                    for m in {model, owner} - {None}:
                        blocked[m] = time.time() + wait
                        why[m] = ("no free tier for your key" if wait >= 7 * 86400 else
                                  "daily free limit used up" if wait >= 3600 else "per-minute limit hit")
                    save_gemini_state(state)
                    log(f"  {model} is out of free quota until "
                        f"{time.strftime('%d %b %H:%M', time.localtime(time.time() + wait))}, trying another model")
                elif e.code in (500, 503) and attempt < 2:
                    time.sleep(10 * (attempt + 1))
                    continue
                elif e.code == 404:
                    blocked[model] = time.time() + 86400
                    why[model] = "not available to your key"
                    save_gemini_state(state)
                elif e.code in (401, 403) or "API_KEY_INVALID" in json.dumps(err):
                    # the key or its whole Google project is refused: every other model would fail the same way
                    state["refused"] = {"at": time.time(), "message": err.get("message", "")[:150]}
                    save_gemini_state(state)
                    raise RuntimeError(f"{NO_MODEL}: Google refused this Gemini key ({err.get('message', '')[:150]}). Make a new key "
                                       f"in a new project at aistudio.google.com/apikey (Create API key > Create "
                                       f"project), then paste it in Settings > Gmail & Gemini keys.")
                break  # anything else (bad request, overloaded, not found): next model
            except (TimeoutError, urllib.error.URLError, OSError) as e:
                if isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError):
                    # a model that went quiet usually stays quiet: try the next one instead of waiting again
                    last = f"{model} did not answer within {GEMINI_TIMEOUT} s"
                    break
                last = f"Gemini timeout/network error ({model}): {e}"
                if attempt < 2:
                    time.sleep(10)
                    continue
                break
            except (KeyError, IndexError, ValueError):
                last = f"Gemini returned an unusable answer ({model})"
                if attempt < 2:
                    continue
                break
    save_gemini_state(state)
    if not tried and back_at:
        raise RuntimeError(f"{NO_MODEL}: every free model is out of quota. The first one is back at "
                           f"{time.strftime('%d %b %H:%M', time.localtime(min(back_at)))}.")
    raise RuntimeError(f"{NO_MODEL} right now. Last error: {last}")


def safe(result, profile):
    if not isinstance(result.get("tailor"), dict):
        result["tailor"] = {}
    if not isinstance(result.get("fit_score"), (int, float)):
        try:
            result["fit_score"] = int(str(result.get("fit_score", 0)).strip().rstrip("%"))
        except ValueError:
            result["fit_score"] = 0
    titles = " ".join([profile.get("default_title", "")] + [e.get("title", "") for e in profile.get("experience", [])])
    if not re.search(r"\b(senior|lead)\b", titles, re.I) and \
            re.search(r"\b(senior|lead)\b", result.get("tailor", {}).get("title", ""), re.I):
        result["tailor"]["title"] = re.sub(r"\b(senior|lead)\b\s*", "", result["tailor"]["title"], flags=re.I).strip()
    if not result.get("subject") or not result.get("body"):
        return "empty email"
    return None


# Words that name a tool, language or number: anything with a capital, digit or symbol like C++ / .NET / 50K+.
FACT_WORD = re.compile(r"(?<![\w.#+])(?=\S*[A-Z0-9#+])[\w.#+/%<>-]*\w[#+%]*")


GENERIC_WORDS = set("""about above across after again ability able also apply based being build building
candidate company could currently daily deliver design develop direct directly ensure every excellent experience
experienced familiar field great growth help hiring ideal including join looking maintain making minimum must
other others plus position preferred product professional quickly ready related required requirement requirements
responsible role skills solid strong success support team their there these they this those through using various
very want well where which while will with within work working would years engineer engineering software
opportunity contribute background closely aligns align primary expertise foundation translates translate""".split())


def words(text):
    """Content words, singular, for comparing a CV text against the profile and the job ad."""
    return {w.rstrip("s") for w in re.findall(r"[a-z]{5,}", (text or "").lower())} - GENERIC_WORDS


def new_facts(text, known, borrowed=()):
    """Tools/numbers in text that profile.json never mentions (sentence-initial words are ignored),
    plus any word from `borrowed` (job-ad words that are not in profile.json)."""
    tools = []
    for m in FACT_WORD.finditer(text or ""):
        w = m.group().strip(".,;:()/-")
        before = text[:m.start()].rstrip()
        if not w or not before or before[-1] in ".:!?" or len(w) < 2:
            continue
        if w.lower() not in known:
            tools.append(w)
    named = {t.lower().rstrip("s") for t in tools}  # "Kubernetes" is already listed: no "kubernete" too
    return sorted(w for w in words(text) & set(borrowed) if w not in named) + tools


def borrowed_words(job_text, profile):
    """Content words of the job ad that profile.json never uses: the CV must not claim them."""
    return words(job_text) - words(json.dumps(profile, ensure_ascii=False))


def check_tailor(tailor, profile, job_text):
    """Drop any reworded line that brings in a tool, language, number or job-ad claim not in profile.json.
    The summary loses only the sentences that do; it falls back to the default only when none is left."""
    known = json.dumps(profile, ensure_ascii=False).lower()
    borrowed = borrowed_words(job_text, profile)
    bad = new_facts(tailor.get("title", ""), known, borrowed)
    if bad:
        log(f"  title mentioned {', '.join(bad)} (not in your profile), using your default title")
        tailor["title"] = profile["default_title"]
    kept, dropped = [], []
    for sentence in re.split(r"(?<=[.!?])\s+", (tailor.get("summary") or "").strip()):
        bad = new_facts(sentence, known, borrowed)
        if bad:
            dropped.append(", ".join(bad))
        elif sentence:
            kept.append(sentence)
    if dropped:
        log(f"  summary: removed {len(dropped)} sentence(s) that mentioned {'; '.join(dropped)} (not in your profile)")
    tailor["summary"] = " ".join(kept) if len(" ".join(kept)) >= 80 else profile["default_summary"]
    bullets = {e["id"]: e["bullets"] for e in profile["experience"]}
    for eid, lines in list((tailor.get("rewrites") or {}).items()):
        if eid not in bullets or not isinstance(lines, dict):
            tailor["rewrites"].pop(eid)
            continue
        for i, text in list(lines.items()):
            bad = new_facts(text, known, borrowed)
            if bad or not str(i).isdigit() or int(i) >= len(bullets[eid]):
                lines.pop(i)
                if bad:
                    log(f"  dropped a reworded bullet for {eid}: it added {', '.join(bad)}")
    return tailor


# ---------- CV + Gmail ----------

def run_cv_py(data, json_path, pdf, *flags):
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    if os.path.exists(pdf):
        os.remove(pdf)
    cmd = [sys.executable, "--cv"] if FROZEN else [sys.executable, "-I", os.path.join(CODE, "cv.py")]
    r = subprocess.run([*cmd, *flags, json_path, pdf], capture_output=True, text=True, timeout=300,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if not os.path.exists(pdf):
        raise RuntimeError("Could not make the PDF: " + (r.stderr or r.stdout).strip()[-300:])
    return pdf


def job_slug(company, role):
    """File-name part for one job: two roles at the same company must not overwrite each other's CV."""
    return f"{slug(company)}-{slug(role)[:30]}".strip("-")


def letter_of(cv_file):
    """The cover letter that goes with a CV file name, e.g. Jane-CV-acme-dev.pdf -> Jane-Cover-Letter-acme-dev.pdf."""
    return cv_file.replace("-CV-", "-Cover-Letter-", 1)


def build_cv(tailor, company, role, today):
    s = job_slug(company, role)
    return run_cv_py(tailor, os.path.join(HERE, "tailor", f"{today}-{s}.json"),
                     os.path.join(HERE, "cvs", f"{file_prefix()}-CV-{s}.pdf"))


def build_letter(text, company, role, today):
    s = job_slug(company, role)
    return run_cv_py(dict(company=company, role=role, text=text),
                     os.path.join(HERE, "tailor", f"{today}-{s}-letter.json"),
                     os.path.join(HERE, "cvs", f"{file_prefix()}-Cover-Letter-{s}.pdf"), "--letter")


def drafts_folder(imap):
    typ, boxes = imap.list()
    for b in boxes or []:
        line = b.decode(errors="replace")
        if "\\Drafts" in line:
            return line.split(' "/" ')[-1].strip()
    return '"[Gmail]/Drafts"'


def save_draft(cfg, to, subject, body, pdf):
    msg = email.message.EmailMessage()
    msg["From"] = email.utils.formataddr((load_profile().get("name", ""), cfg["gmail_address"]))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg.set_content(body)
    with open(pdf, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename=f"{file_prefix()}-CV.pdf")
    imap = imaplib.IMAP4_SSL(cfg["imap_host"], timeout=60)
    try:
        imap.login(cfg["gmail_address"], cfg["gmail_app_password"].replace(" ", ""))
        typ, data = imap.append(drafts_folder(imap), "\\Draft", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        if typ != "OK":
            raise RuntimeError(f"IMAP append failed: {data}")
    finally:
        try:
            imap.logout()
        except Exception:
            pass


# ---------- main ----------

JOBS_FILE = os.path.join(HERE, "jobs.json")
STATUS_READY, STATUS_SITE, STATUS_DONE, STATUS_REJECTED = "ready", "apply on site", "done", "rejected"


NUMBERS = ("max_drafts_per_run", "max_drafts_per_day", "max_gemini_calls_per_run", "min_fit_score",
           "max_job_age_days", "max_years_required")


def load_config():
    path = os.path.join(HERE, "config.json")
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8-sig") as f:
                cfg.update(json.load(f))
        except ValueError as e:
            raise RuntimeError(f"config.json is not valid JSON ({e}). Fix it in Notepad, or delete it and enter "
                               "your keys again in the window.") from None
    for k in NUMBERS:  # a hand-edited "3" or "" must not break the run
        try:
            cfg[k] = int(cfg[k])
        except (TypeError, ValueError):
            cfg[k] = DEFAULT_CONFIG[k]
    for k in ("gmail_address", "gmail_app_password", "gemini_api_key", "imap_host", "gemini_model"):
        cfg[k] = str(cfg.get(k) or "").strip()
    cfg["imap_host"] = cfg["imap_host"] or DEFAULT_CONFIG["imap_host"]
    return cfg


def is_set(v):
    return bool(v) and not v.startswith("PUT-")


def has_gmail(cfg):
    return is_set(cfg["gmail_address"]) and is_set(cfg["gmail_app_password"])


def check_config(cfg, gmail=False):
    """Gemini is needed for anything that writes; Gmail only for saving drafts."""
    if not is_set(cfg["gemini_api_key"]):
        raise RuntimeError("Gemini is not connected yet: press Settings, then Gmail & Gemini keys "
                           "(or fill in gemini_api_key in config.json)")
    if gmail and not has_gmail(cfg):
        raise RuntimeError("Gmail is not connected, so no draft can be saved. Press Settings, then Gmail & Gemini "
                           "keys, or use Make CV + cover letter instead (it needs no Gmail).")


def pid_alive(pid):
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes  # os.kill on Windows would terminate the process, so ask for its exit code instead
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


def take_lock():
    """The lock holds the PID of the run that owns it; a run that was killed leaves a lock nobody owns."""
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 1500:
        try:
            with open(LOCK, encoding="utf-8") as f:
                owner = int(f.read().strip())
        except (OSError, ValueError):
            owner = None  # an old empty lock: trust its age
        if owner is None or pid_alive(owner):
            return False
    with open(LOCK, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return True


def drop_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


def load_profile():
    path = os.path.join(HERE, "profile.json")
    if not os.path.exists(path):
        raise RuntimeError("profile.json not found: copy profile.example.json to profile.json and fill it in, "
                           "or press Upload my CV in the window")
    try:
        with open(path, encoding="utf-8-sig") as f:
            p = json.load(f)
    except ValueError as e:
        raise RuntimeError(f"profile.json has a typo ({e}). Press My profile to fix it, or Upload my CV again. "
                           "A missing comma or quote is the usual cause.") from None
    return normalise_profile(p)


def normalise_profile(p):
    """Fill in what a hand-edited profile.json left out, so a missing key never crashes a run."""
    if not isinstance(p, dict) or not str(p.get("name") or "").strip():
        raise RuntimeError("profile.json has no \"name\". Press My profile to fix it, or Upload my CV again.")
    exps = [e for e in p.get("experience") or [] if isinstance(e, dict)]  # may be empty: students, career changers
    for i, e in enumerate(exps):
        e["id"] = str(e.get("id") or slug(e.get("company") or f"role-{i + 1}"))
        e["bullets"] = [str(b) for b in e.get("bullets") or [] if str(b).strip()]
        for k in ("company", "place", "title", "dates", "note"):
            e[k] = str(e.get(k) or "")
    p["experience"] = exps
    p["projects"] = [dict(pr, id=str(pr.get("id") or slug(pr.get("name"))), name=str(pr.get("name") or ""),
                          text=str(pr.get("text") or ""))
                     for pr in p.get("projects") or [] if isinstance(pr, dict)]
    skills = p.get("skills") if isinstance(p.get("skills"), dict) else {}
    p["skills"] = {k: clean_words(v) if isinstance(v, str) else [str(s) for s in v]
                   for k, v in skills.items() if isinstance(v, (list, str))}
    p["contact"] = p.get("contact") if isinstance(p.get("contact"), dict) else {}
    for k in ("location", "years", "education", "default_summary"):
        p[k] = str(p.get(k) or "")
    p["default_title"] = str(p.get("default_title") or (exps[0]["title"] if exps else ""))
    return p


def file_prefix():
    """Your name for file names, e.g. "Jane Doe" -> cvs/Jane-Doe-CV-acme.pdf."""
    try:
        name = load_profile().get("name", "")
    except (RuntimeError, ValueError):
        name = ""
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-") or "My"


def collect(rows, now, today, notes):
    """Fetch every source and give each job a status: ready / apply on site / done / rejected.
    The sites are read at the same time (fetch() still spaces requests to any one site)."""
    got = {}
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        running = {pool.submit(src): src for src in SOURCES}
        for f in as_completed(running):
            src = running[f]
            try:
                got[src] = f.result()
                log(f"{src.__name__}: {len(got[src])} jobs")
            except Exception as e:
                notes.append(f"{src.__name__} failed ({e.__class__.__name__})")
                log(f"{src.__name__}: ERROR {e}")
    jobs = [j for src in SOURCES for j in got.get(src, [])]  # in SOURCES order, so duplicates resolve the same way
    out, seen, matches = [], set(), []
    for j in jobs:
        # The same post often shows up on several boards.
        key = (slug(j["company"]), slug(j["title"]))
        if j["id"] in seen or key in seen:
            continue
        seen.update((j["id"], key))
        j["email"] = j["email_src"] = ""
        why = prefilter(j, now)
        if why:
            j["status"], j["why"] = STATUS_REJECTED, why
        elif already_done(rows, j, None, today):
            j["status"], j["why"] = STATUS_DONE, "already handled"
        else:
            matches.append(j)
        out.append(j)
    find_emails(matches)
    for j in matches:
        if j["email"] and already_done(rows, j, j["email"], today):
            j["status"], j["why"] = STATUS_DONE, "already handled"
        elif j["email"]:
            j["status"], j["why"] = STATUS_READY, ""
        else:
            j["status"], j["why"] = STATUS_SITE, "no published email"
    return out


def find_emails(matches):
    """Fill in each match's application email. Posts without one need a visit to the company's site, which
    can take seconds per site, so 8 sites are read at a time (fetch still spaces requests to any one site)."""
    if not matches:
        return
    log(f"{len(matches)} jobs match. Looking for their application emails"
        + (" (posts without one: checking the company's own site)" if len(matches) > 5 else "") + " ...")
    done = 0

    def one(j):
        mail, src = pick_email(j)
        j["email"], j["email_src"] = mail or "", src or ""

    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(one, j) for j in matches]):
            f.result()
            done += 1
            if done % 10 == 0 and done < len(matches):
                log(f"  emails checked for {done} of {len(matches)} jobs")


def write_jobs(d):
    with open(JOBS_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(JOBS_FILE + ".tmp", JOBS_FILE)


def save_jobs(jobs, stamp):
    keep = []
    for j in jobs:
        j = {k: v for k, v in j.items() if k != "raw_html"}
        j["date"] = j["date"].isoformat() if j.get("date") else ""
        if j["status"] == STATUS_REJECTED:
            j["text"] = j["text"][:3000]
        keep.append(j)
    write_jobs({"updated": stamp, "jobs": keep})


def load_jobs():
    if not os.path.exists(JOBS_FILE):
        return {"updated": "", "jobs": []}
    with open(JOBS_FILE, encoding="utf-8") as f:
        return json.load(f)


def set_job_status(job_id, status, why=""):
    d = load_jobs()
    for j in d["jobs"]:
        if j["id"] == job_id:
            j["status"], j["why"] = status, why
    write_jobs(d)


def job_prompt(profile, j):
    c = profile["contact"]
    links = " , ".join(f"{label} {c[k]}" for label, k in
                       (("Portfolio", "portfolio"), ("GitHub", "github"), ("LinkedIn", "linkedin")) if c.get(k))
    home = profile.get("location") or "my country"
    avoid = sorted(borrowed_words(f"{j['title']}\n{j['text'][:9000]}", profile))[:120]
    return GEMINI_PROMPT.format(profile=json.dumps(profile, ensure_ascii=False), source=j["source"],
                                avoid=", ".join(avoid) or "(none)",
                                url=j["url"], title=j["title"], company=j["company"], job_location=j["location"],
                                text=j["text"][:9000], name=profile["name"], location=home,
                                location_short=re.sub(r",?\s*open to remote.*$", "", home, flags=re.I),
                                years=profile.get("years") or "the stated", links=links,
                                sign_off=", ".join(f'"{v}"' for v in (profile["name"], c.get("email"),
                                                                       c.get("phone")) if v))


def tailor_job(cfg, profile, j, today, min_fit=None):
    """Ask Gemini about one job and build the tailored CV. Returns (result, pdf), pdf is None if skipped.
    min_fit=0 means you asked for this CV yourself: it is made even if Gemini thinks you are not eligible."""
    res = gemini(cfg, job_prompt(profile, j))
    if not isinstance(res, dict):
        res = {}
    problem = safe(res, profile)
    min_fit = cfg["min_fit_score"] if min_fit is None else min_fit
    if (min_fit and not res.get("eligible")) or res.get("fit_score", 0) < min_fit or problem:
        res["skip_reason"] = problem or res.get("reason", "")
        return res, None
    check_tailor(res["tailor"], profile, f"{j['title']}\n{j['text']}")
    return res, build_cv(res["tailor"], j["company"], j["title"], today.isoformat())


def draft_job(cfg, profile, j, today):
    """Gemini check + tailored CV + Gmail draft. Returns True if a draft was saved."""
    res, pdf = tailor_job(cfg, profile, j, today)
    if not pdf:
        log(f"skip {j['company']}: eligible={res.get('eligible')} fit={res.get('fit_score')} {res['skip_reason']}")
        add_tracker(dict(date=today.isoformat(), company=j["company"], role=j["title"][:100],
                         email=j["email"], post_url=j["url"], draft_id=j["id"],
                         status=f"skipped: {res['skip_reason']}"[:150]))
        return False
    save_draft(cfg, j["email"], res["subject"], res["body"], pdf)
    add_tracker(dict(date=today.isoformat(), company=j["company"], role=j["title"][:100], email=j["email"],
                     poster=f"via {j['email_src']}", post_url=j["url"], cv_file=os.path.basename(pdf),
                     draft_id=j["id"], status="draft-attached"))
    log(f"DRAFT saved: {j['company']} -> {j['email']} (fit {res.get('fit_score')})")
    return True


def cv_only_job(cfg, profile, j, today, min_fit=0):
    """Tailored CV + cover letter: to upload on the company's site, or to email yourself when Gmail is not
    connected. min_fit=0 (you asked for it) makes it whatever Gemini thinks of the fit."""
    res, pdf = tailor_job(cfg, profile, j, today, min_fit=min_fit)
    if not pdf:
        if min_fit:
            log(f"skip {j['company']}: eligible={res.get('eligible')} fit={res.get('fit_score')} {res['skip_reason']}")
            add_tracker(dict(date=today.isoformat(), company=j["company"], role=j["title"][:100],
                             email=j.get("email", ""), post_url=j["url"], draft_id=j["id"],
                             status=f"skipped: {res['skip_reason']}"[:150]))
        else:
            log(f"No CV made for {j['company']}: {res['skip_reason']}")
        return False
    if not res.get("eligible"):
        log(f"Note: Gemini thinks you may not be eligible: {res.get('reason', '')}")
    text = res.get("cover_letter") or res["body"]
    # Paragraph 1 may talk about the job; after that, job-ad words that are not in your profile need a look.
    paras = [p for p in text.split("\n\n") if p.strip()]
    review = sorted(words(" ".join(paras[1:-2])) & borrowed_words(f"{j['title']} {j['text']}", profile))
    letter = build_letter(text, j["company"], j["title"][:120], today.isoformat())
    with open(letter[:-4] + ".txt", "w", encoding="utf-8") as f:  # for pasting into application forms
        f.write(text)
    if j.get("email"):  # no Gmail: keep the email Gemini wrote, to send yourself
        with open(pdf[:-4] + "-email.txt", "w", encoding="utf-8") as f:
            f.write(f"To: {j['email']}\nSubject: {res.get('subject', '')}\n\n{res['body']}\n")
    add_tracker(dict(date=today.isoformat(), company=j["company"], role=j["title"][:100], email=j.get("email", ""),
                     post_url=j["url"], cv_file=os.path.basename(pdf), draft_id=j["id"],
                     status="cv-made" if j.get("email") else "cv-made, apply on site"))
    log(f"CV saved: {pdf} (fit {res.get('fit_score')})")
    log(f"Cover letter saved: {letter}")
    log(f"Gemini: {res.get('reason', '')}")
    if review:
        log(f"Read the cover letter before sending: it uses these words from the job ad that are not in "
            f"your profile, make sure each is true: {', '.join(review[:12])}")
    return True


def run_custom(path):
    """GUI 'Tailor to a job description': CV + cover letter for a job you pasted in."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    today = dt.date.today()
    j = dict(source="pasted by you", id=f"pasted-{slug(d['company'])}-{slug(d['title'])}-{today}",
             title=d["title"], company=d["company"], url=d.get("url", ""), location=d.get("location", ""),
             text=d["text"], email=(find_emails_in_text(d["text"]) or [""])[0])
    cfg = load_config()
    check_config(cfg)
    if not take_lock():
        log("The bot is busy with another run. Try again in a minute.")
        return
    try:
        log(f"Asking Gemini to tailor your CV for {j['company']} | {j['title'][:80]} ...")
        cv_only_job(cfg, load_profile(), j, today)
    finally:
        drop_lock()


IMPORT_PROMPT = """Turn the attached CV into JSON for a CV builder. Copy every fact exactly as the CV says it:
do not shorten, merge, reword, add or drop anything. Only repair broken line wraps and hyphenation.
Return ONLY JSON with exactly these keys:
{
 "name": "full name",
 "default_title": "the headline under the name",
 "contact": {"phone": "", "email": "", "linkedin": "", "github": "", "portfolio": ""},
 "location": "city, country as the CV states it, or \\"\\"",
 "years": "years of experience exactly as the CV states it, e.g. \\"4+\\", or \\"\\"",
 "default_summary": "the CV's summary / profile paragraph",
 "experience": [{"id": "short unique lowercase id from the company name", "company": "", "place": "city or Remote",
                 "title": "", "dates": "", "note": "extra line such as Part-time or Self-employed, or \\"\\"",
                 "bullets": ["every bullet, word for word"]}],
 "projects": [{"id": "short unique lowercase id", "name": "", "text": "description (projects, portfolio pieces, campaigns, case studies), word for word"}],
 "skills": {"category as in the CV (certifications, languages and software go here too)": ["skill", "..."]},
 "education": "degree — school, city (several entries joined with ' | ')"
}
Keep experience and projects in the CV's order. Use "" for anything the CV does not have."""


CV_FILES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp"}  # sent to Gemini as they are: it reads scanned and photographed CVs too
MAX_ATTACH = 18_000_000  # Gemini takes up to 20 MB inline, base64 included


def read_cv_file(path):
    """Returns (text, attachment) for a CV: PDFs and images go to Gemini as they are, other files as text."""
    ext = os.path.splitext(path)[1].lower()
    if ext in CV_FILES:
        if os.path.getsize(path) * 4 / 3 > MAX_ATTACH:
            raise RuntimeError("That file is too big for Gemini (over about 13 MB). Save the CV as a smaller PDF.")
        with open(path, "rb") as f:
            return "", (CV_FILES[ext], f.read())
    if ext == ".doc":
        raise RuntimeError("Old Word .doc files cannot be read. In Word use File > Save As > PDF (or .docx), "
                           "then upload that.")
    if ext == ".docx":
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        except (zipfile.BadZipFile, KeyError):
            raise RuntimeError("That .docx file is damaged or not really a Word file. Save it as PDF and "
                               "upload that.") from None
        xml = re.sub(r"<w:tab/>", "\t", xml)
        xml = re.sub(r"</w:p>|<w:br/>|<w:cr/>", "\n", xml)
        return html.unescape(re.sub(r"<[^>]+>", "", xml)), None
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read(), None


def import_cv(path):
    """GUI 'Upload my CV': rebuild profile.json from a CV file. The old profile is kept as a backup."""
    cfg = load_config()
    check_config(cfg)
    text, attach = read_cv_file(path)
    if not attach and len(text.strip()) < 200:
        raise RuntimeError("Could not read any text from that file. Try a PDF or .docx.")
    log(f"Reading {os.path.basename(path)} with Gemini ...")
    p = gemini(cfg, IMPORT_PROMPT + (f"\n\nCV:\n{text[:30000]}" if text else ""), attach)
    if not isinstance(p, dict) or not str(p.get("name") or "").strip():
        raise RuntimeError("Gemini could not find your name in that CV. Is it the right file?")
    try:  # a broken old profile must not stop you replacing it
        old = load_profile() if os.path.exists(os.path.join(HERE, "profile.json")) else {}
    except RuntimeError:
        old = {}
    ids = set()
    for e in [e for e in p.get("experience") or [] if isinstance(e, dict)]:
        e["id"] = slug(e.get("id") or e.get("company"))
        while e["id"] in ids:
            e["id"] += "-2"
        ids.add(e["id"])
    p["projects"] = [dict(pr, id=slug(pr.get("id") or pr.get("name"))) for pr in p.get("projects") or []
                     if isinstance(pr, dict)]
    p["skills"] = {k: v for k, v in (p.get("skills") or {}).items() if isinstance(v, list) and v} \
        if isinstance(p.get("skills"), dict) else {}
    contact = p.get("contact") if isinstance(p.get("contact"), dict) else {}
    p["contact"] = {k: str(contact.get(k) or "") for k in ("phone", "email", "linkedin", "github", "portfolio")}
    if str(old.get("name", "")).lower() == p["name"].lower():  # same person: keep links the CV left out
        for k, v in old.get("contact", {}).items():
            p["contact"][k] = p["contact"].get(k) or v
        p["location"] = p.get("location") or old.get("location", "")
    p = normalise_profile(p)
    if not p["experience"]:
        log("No work experience found in that CV: your CVs will lead with your projects, skills and education.")
    if os.path.exists(os.path.join(HERE, "profile.json")):
        backup = os.path.join(HERE, f"profile.backup-{dt.datetime.now():%Y%m%d-%H%M%S}.json")
        os.replace(os.path.join(HERE, "profile.json"), backup)
        log(f"Old profile kept as {os.path.basename(backup)}")
    with open(os.path.join(HERE, "profile.json"), "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)
    n_bullets = sum(len(e["bullets"]) for e in p["experience"])
    log(f"Profile saved: {p['name']} | {len(p['experience'])} roles, {n_bullets} bullets, "
        f"{len(p['projects'])} projects, {sum(map(len, p['skills'].values()))} skills")
    log("Check it with 'My profile' before making CVs: every CV and email is built only from this file.")


def run_one(job_id, mode):
    """GUI action on one saved job: mode is 'draft', 'cv', 'skip' or 'applied'."""
    today = dt.date.today()
    j = next((x for x in load_jobs()["jobs"] if x["id"] == job_id), None)
    if not j:
        log("That job is no longer in jobs.json. Press Find jobs again.")
        return
    if mode in ("skip", "applied"):
        status, why = ("skipped: by you", "skipped by you") if mode == "skip" else ("applied", "applied by you")
        add_tracker(dict(date=today.isoformat(), company=j["company"], role=j["title"][:100], email=j["email"],
                         post_url=j["url"], draft_id=j["id"], status=status))
        set_job_status(job_id, STATUS_DONE, why)
        log(f"Skipped {j['company']}. The bot will not draft it." if mode == "skip" else
            f"Marked {j['company']} as applied. It is in tracker.csv and the bot will not draft it again.")
        return
    cfg = load_config()
    check_config(cfg, gmail=mode == "draft")
    if not take_lock():
        log("The bot is busy with another run. Try again in a minute.")
        return
    try:
        log(f"Asking Gemini about {j['company']} | {j['title'][:80]} ...")
        if mode == "draft":
            ok = draft_job(cfg, load_profile(), j, today)
            set_job_status(job_id, STATUS_DONE, "drafted" if ok else "skipped by Gemini")
        elif cv_only_job(cfg, load_profile(), j, today):
            set_job_status(job_id, STATUS_DONE, "CV made")
    finally:
        drop_lock()


def main():
    for flag, action in (("--import-cv", import_cv), ("--custom", run_custom)):
        if flag in sys.argv:
            try:
                action(sys.argv[sys.argv.index(flag) + 1])
            except Exception as e:
                log(f"ERROR: {e}")
            return
    if "--job" in sys.argv:
        i = sys.argv.index("--job")
        mode = sys.argv[i + 2] if len(sys.argv) > i + 2 else "draft"
        try:
            run_one(sys.argv[i + 1], mode)
        except Exception as e:
            log(f"ERROR: {e}")
        return
    dry = "--dry-run" in sys.argv
    if not take_lock():
        log("Another run is in progress; exiting.")
        return
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    stats = {"fetched": 0, "candidates": 0, "gemini": 0, "drafts": 0}
    notes = []
    try:
        cfg = load_config()
        apply_filters(cfg)
        for line in MATCH.explain():
            log(f"Keyword {line}")
        if not dry:
            check_config(cfg)
            if not has_gmail(cfg):
                log("Gmail is not connected: making a CV + cover letter for the best matches instead of drafts "
                    "(the email to send is saved next to each CV).")
        now = dt.datetime.now(dt.timezone.utc)
        today = dt.date.today()
        rows = read_tracker()
        # Only what was made counts toward the daily limit, not the jobs Gemini or you skipped.
        today_count = sum(1 for r in rows if r.get("date", "")[:10] == today.isoformat()
                          and r.get("status", "").startswith(("draft", "cv-made")))
        profile = None if dry else load_profile()  # searching needs no CV; only drafting does

        jobs = collect(rows, now, today, notes)
        stats["fetched"] = len(jobs)
        reasons = {}
        for j in jobs:
            if j["why"]:
                reasons[j["why"]] = reasons.get(j["why"], 0) + 1
        # Gemini sees the best matches first: keyword in the title, then the newest.
        candidates = sorted([j for j in jobs if j["status"] == STATUS_READY],
                            key=lambda j: (j.get("match") != "strong", -(j["date"].timestamp() if j["date"] else 0)))
        stats["candidates"] = len(candidates)
        log(f"filter: {reasons}")
        if all(j["status"] == STATUS_REJECTED for j in jobs) and reasons.get("no keyword match", 0) > len(jobs) / 2:
            log("Tip: no job title matched. Try fewer or other words, a longer Max age, or tick a Job type, "
                "which brings its common title variations.")
        for c in candidates:
            log(f"CANDIDATE [{c['source']}] {c['company']} | {c['title'][:80]} | {c['email']} ({c['email_src']})")
        for c in jobs:
            if c["status"] == STATUS_SITE:
                log(f"APPLY ON SITE [{c['source']}] {c['company']} | {c['title'][:80]} | {c['url']}")
        save_jobs(jobs, stamp)
        if dry:
            return

        budget = min(cfg["max_drafts_per_run"], cfg["max_drafts_per_day"] - today_count)
        for j in candidates[: cfg["max_gemini_calls_per_run"]]:
            if budget <= 0:
                break
            stats["gemini"] += 1
            try:
                if has_gmail(cfg):
                    ok = draft_job(cfg, profile, j, today)
                else:
                    ok = cv_only_job(cfg, profile, j, today, min_fit=cfg["min_fit_score"])
            except Exception as e:
                notes.append(f"{j['company']}: {e}"[:200])
                log(f"draft failed for {j['company']}: {e}")
                if NO_MODEL in str(e):  # no point trying the next job
                    break
                continue
            made = "drafted" if has_gmail(cfg) else "CV made"
            set_job_status(j["id"], STATUS_DONE, made if ok else "skipped by Gemini")
            if ok:
                stats["drafts"] += 1
                budget -= 1
    except Exception as e:
        notes.append(f"run error: {e}"[:200])
        log(f"ERROR: {e}")
    finally:
        line = (f"{stamp} | standalone{' dry-run' if dry else ''} | fetched {stats['fetched']} | "
                f"candidates {stats['candidates']} | gemini {stats['gemini']} | drafts {stats['drafts']}"
                + (f" | {'; '.join(notes)}" if notes else ""))
        with open(RUNS_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        log(line)
        drop_lock()


if __name__ == "__main__":
    main()
