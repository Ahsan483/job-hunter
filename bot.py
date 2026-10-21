"""Standalone remote job hunter. Uses no Claude.

Each run:
  1. pulls remote jobs from Remotive, RemoteOK, Arbeitnow, Himalayas and the
     latest Hacker News "Who is hiring?" thread
  2. keeps roles matching your keywords that are remote, recent and (unless turned off)
     open worldwide or to your region
  3. finds an application email published in the post, or on the company's
     own careers/jobs/contact page
  4. asks Gemini (free tier) to check the fit and write the tailoring + email
  5. builds a tailored CV with cv.py and saves a Gmail DRAFT with it attached
     (IMAP). Nothing is ever sent.

Usage:
  python -I bot.py            normal run (needs config.json)
  python -I bot.py --dry-run  find and filter only; no Gemini, no Gmail
  python -I bot.py --job ID [draft|cv|skip]
                              act on one job from jobs.json (used by gui.py)
  python -I bot.py --custom job.json
                              CV + cover letter for a pasted job ({title, company, text, url?})
  python -I bot.py --import-cv my-cv.pdf
                              rebuild profile.json from your CV (.pdf, .docx or .txt)
  python -I gui.py            point-and-click window
"""
import base64
import csv
import datetime as dt
import email.message
import email.utils
import html
import imaplib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (personal job search script)"}
TRACKER = os.path.join(HERE, "tracker.csv")
RUNS_LOG = os.path.join(HERE, "runs.log")
LOCK = os.path.join(HERE, "bot.lock")
MAX_AGE_DAYS = 14

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
    "max_job_age_days": MAX_AGE_DAYS,
    # Skip jobs asking for this many years of experience or more (0 = never skip).
    "max_years_required": 8,
    # True: only jobs that say they hire worldwide or in my_region_words. False: every remote job, any country.
    "worldwide_only": True,
    # Your country/region, e.g. ["Pakistan", "South Asia"]. Jobs naming one of these count as open to you.
    "my_region_words": [],
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


TECH = word_re(DEFAULT_CONFIG["keywords"])
EXCLUDE = None
SEARCH = DEFAULT_CONFIG["keywords"][:6]  # terms sent to the sites that have a search
WORLDWIDE_ONLY = True
REGION = None  # regex of my_region_words
MAX_YEARS = 8


def apply_filters(cfg):
    global TECH, EXCLUDE, SEARCH, MAX_AGE_DAYS, WORLDWIDE_ONLY, REGION, MAX_YEARS
    kws = clean_words(cfg.get("keywords")) or DEFAULT_CONFIG["keywords"]
    TECH, SEARCH = word_re(kws), kws[:6]
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
BAD_EMAIL = re.compile(r"(noreply|no-reply|donotreply|example\.|sentry|wixpress|\.png|\.jpg|\.gif|\.webp|privacy|abuse|support|billing|sales)", re.I)
ATS_HOSTS = ("greenhouse.io", "lever.co", "workable.com", "ashbyhq.com", "bamboohr.com", "smartrecruiters.com",
             "recruitee.com", "breezy.hr", "jobvite.com", "myworkdayjobs.com", "teamtailor.com", "personio",
             "remotive.com", "remoteok.com", "arbeitnow.com", "himalayas.app", "linkedin.com", "indeed.",
             "glassdoor.", "wellfound.com", "angel.co", "ycombinator.com", "news.ycombinator.com",
             "google.com", "forms.gle", "typeform.com", "notion.site", "github.com", "twitter.com", "x.com")


# ---------- small helpers ----------

def log(msg):
    print(msg, flush=True)


def fetch(url, as_json=False, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(3_000_000).decode("utf-8", errors="replace")
    return json.loads(raw) if as_json else raw


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
            d = dt.datetime.fromtimestamp(int(v), dt.timezone.utc)
        else:
            d = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
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
    out = []
    for term in SEARCH:
        d = fetch(f"https://remotive.com/api/remote-jobs?search={q(term)}", as_json=True)
        for j in d.get("jobs", []):
            out.append(dict(source="remotive", id=f"remotive-{j['id']}", title=j["title"], company=j["company_name"],
                            url=j["url"], location=j.get("candidate_required_location", ""),
                            text=text_of(j.get("description")), date=parse_date(j.get("publication_date")),
                            salary=j.get("salary", ""), job_type=j.get("job_type", "").replace("_", " "),
                            tags=", ".join(j.get("tags", []))))
    return out


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
    d = fetch("https://www.arbeitnow.com/api/job-board-api", as_json=True)
    out = []
    for j in d.get("data", []):
        if not j.get("remote"):
            continue
        out.append(dict(source="arbeitnow", id=f"arbeitnow-{j['slug']}", title=j["title"], company=j["company_name"],
                        url=j["url"], location=j.get("location", ""), text=text_of(j.get("description")),
                        date=parse_date(j.get("created_at")), job_type=", ".join(j.get("job_types", [])),
                        tags=", ".join(j.get("tags", []))))
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
        except urllib.error.HTTPError:
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


def src_weworkremotely():
    out = []
    for cat in ("remote-full-stack-programming-jobs", "remote-back-end-programming-jobs", "remote-programming-jobs"):
        feed = fetch(f"https://weworkremotely.com/categories/{cat}.rss")
        for item in re.findall(r"(?s)<item>(.*?)</item>", feed):
            tag = lambda t: html.unescape((re.search(rf"(?s)<{t}>(.*?)</{t}>", item) or [None, ""])[1]).strip()
            company, _, title = tag("title").partition(": ")
            link = tag("link") or tag("guid")
            out.append(dict(source="weworkremotely", id=f"wwr-{link.rstrip('/').rsplit('/', 1)[-1]}",
                            title=title or company, company=company if title else "", url=link,
                            location=tag("region") or "Remote", text=text_of(tag("description")),
                            date=parse_date(tag("pubDate")), job_type=tag("type"), tags=tag("skills")))
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


SOURCES = [src_remotive, src_remoteok, src_arbeitnow, src_himalayas, src_jobicy, src_weworkremotely,
           src_workingnomads, src_hn]


# ---------- filtering ----------

def open_to_me(job):
    """True only if the post says it hires worldwide or in my_region_words; unclear posts count as no."""
    if OPEN_GEO.search(job["location"]) or (REGION and REGION.search(job["location"])):
        return True
    # Himalayas and Jobicy list the allowed countries; trust that list over words in the text.
    if job.get("geo_strict"):
        return False
    # A location like "USA" or "Berlin" names somewhere else. HN's "location" is the whole first line.
    if job["source"] != "hn" and GENERIC_LOC.sub("", job["location"]):
        return False
    head = job["text"][:6000]
    return bool(OPEN_TEXT.search(head) or (REGION and REGION.search(head)))


def prefilter(job, now):
    blob = f"{job['title']}\n{job['location']}\n{job['text']}"
    if not TECH.search(job["title"] + " " + job["text"][:4000]):
        return "no keyword match"
    if EXCLUDE and EXCLUDE.search(job["title"]):
        return "excluded word in title"
    if not job["date"]:
        return "no post date"
    if (now - job["date"]).days > MAX_AGE_DAYS:
        return "too old"
    where = job["location"] + " " + job["text"][:3000]
    if not (REMOTE_OK_LOC.search(where) or (REGION and REGION.search(where))):
        return "not remote"
    if WORLDWIDE_ONLY:
        if BLOCK_LOC.search(blob):
            return "location/work-auth restricted"
        if not open_to_me(job):
            return "not open worldwide/to my region"
    head = job["location"] if job["source"] == "hn" else job["location"] + " " + job["title"]
    if ONSITE.search(head) and not re.search(r"remote", head, re.I):
        return "onsite/hybrid"
    if MAX_YEARS and any(int(n) >= MAX_YEARS for n, _ in YEARS_ASKED.findall(blob)):
        return f"{MAX_YEARS}+ years"
    return None


def find_emails_in_text(t):
    found = set(EMAIL_RE.findall(t))
    for a, b, c in OBFUSCATED.findall(t):
        found.add(f"{a}@{b}.{c}")
    return [e.strip(".").lower() for e in found if not BAD_EMAIL.search(e)]


def company_sites(job):
    urls = re.findall(r"https?://[^\s\"'<>)]+", (job.get("raw_html") or "") + " " + job["text"] + " " + job.get("apply", ""))
    hosts = []
    for u in urls:
        host = urllib.parse.urlparse(html.unescape(u)).netloc.lower().split(":")[0]
        if host and not any(a in host for a in ATS_HOSTS) and host not in hosts:
            hosts.append(host)
    return hosts[:2]


def careers_page_email(job):
    """Look for a published hiring address on the company's own site."""
    for host in company_sites(job):
        base = "https://" + host.removeprefix("www.")
        for path in ("/careers", "/jobs", "/join-us", "/contact", "/"):
            try:
                page = fetch(base + path, timeout=15)
            except Exception:
                continue
            for e in find_emails_in_text(page):
                local, _, domain = e.partition("@")
                if HIRING_LOCAL.match(local) and host.removeprefix("www.").split(".")[-2] in domain:
                    return e, base + path
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
   "title": "headline for THIS role built only from titles and skills in PROFILE, e.g. 'Backend Software Engineer | C# | Docker | Azure'; say 'Senior' or 'Lead' only if a PROFILE title does",
   "summary": "3-4 sentences written for THIS job. Do NOT copy default_summary. Open with the PROFILE experience closest to what the job asks for, use the job's own wording where PROFILE supports it, and leave out PROFILE skills the job does not care about",
   "skills_first": ["job keywords that exist in PROFILE skills, most important first"],
   "bullets": {{"<experience id>": [bullet indexes, most relevant to this job first; leave out unrelated ones but keep at least 2 per role]}},
   "rewrites": {{"<experience id>": {{"<bullet index>": "that bullet reworded so its relevance to this job is obvious. Same facts and same numbers; every tool, language and number must already be in PROFILE"}}}},
   "projects": ["1-3 project ids most relevant to this job"]
 }},
 "subject": "Application: <role> – {name}",
 "body": "plain-text email, 120-200 words",
 "cover_letter": "one-page cover letter, 250-350 words, 4-5 paragraphs separated by a blank line"
}}
Rewrites: reword the 2-3 bullets per role that matter most for this job. Never add a technology, language, tool, number or responsibility that is not in PROFILE: if the job asks for C++ and PROFILE has C#, write about C#, never C++.
Email rules: greeting to the company team (or the person if the post names who to email); say which role and where it was seen; 2-3 short sentences matching their requirements to real facts and numbers from PROFILE, only the relevant ones; "I'm based in {location_short}, available for remote work and able to overlap with your team's hours."; links: {links}; "My CV is attached."; ask for a short call; sign off with {sign_off}.
Cover letter rules: start "Dear <team or the person named in the post>,"; paragraph 1: the role, where it was seen, one specific reason this company or product fits; paragraphs 2-3: take the job's 3-4 main requirements and answer each with a concrete PROFILE fact (project, result, number); only paragraph 1 may describe the company's product; from paragraph 2 on, describe only work PROFILE says {name} did, in PROFILE's own terms, without adding the job's wording to it; if the job needs something PROFILE does not have, say plainly and briefly which PROFILE experience is closest and how it transfers, never claim it; no inflated words like "extensive", "deep", "massive", "expert"; last paragraph: remote from {location_short}, overlap with their hours, ask for a call; end "Sincerely,\\n{name}". No address block, no date, no links, no markdown.
Never claim more than {years} years. No cliches like "passionate" or "hardworking"."""


GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_STATE = os.path.join(HERE, "gemini_state.json")  # model list + which models are out of free quota
NOT_TEXT_MODEL = re.compile(r"(tts|image|banana|live|audio|transcribe|robotics|computer-use|embedding|antigravity"
                            r"|deep-research|lyria|omni|customtools|argon|aqa)", re.I)
NO_MODEL = "No Gemini model is available"


def gemini_state():
    try:
        with open(GEMINI_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


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
    chosen = [cfg.get("gemini_model"), cfg.get("gemini_fallback_model", "gemini-flash-lite-latest")]
    return list(dict.fromkeys([m for m in chosen if m] + sorted(state.get("models", []), key=model_rank)))


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


def gemini(cfg, prompt, attach=None):
    """Ask Gemini for a JSON answer. When a model is out of free quota, switches to the next free one
    and remembers until when that model is blocked. attach: optional (mime type, bytes), e.g. a PDF."""
    parts = [{"text": prompt}]
    if attach:
        parts.append({"inline_data": {"mime_type": attach[0], "data": base64.b64encode(attach[1]).decode()}})
    state = gemini_state()
    blocked = state.setdefault("blocked", {})
    models = gemini_models(cfg, state)
    last, tried, back_at = "no response", 0, []
    for model in models:
        if blocked.get(model, 0) > time.time():
            back_at.append(blocked[model])
            continue
        if tried == 8:
            break
        tried += 1
        gen = {"temperature": 0.4}
        if not model.startswith("gemma"):  # Gemma has no JSON mode; the prompt still asks for JSON
            gen["responseMimeType"] = "application/json"
        body = json.dumps({"contents": [{"parts": parts}], "generationConfig": gen}).encode()
        req = urllib.request.Request(f"{GEMINI_API}/{model}:generateContent", data=body,
                                     headers={"Content-Type": "application/json", "x-goog-api-key": cfg["gemini_api_key"]})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    res = answer_json(json.loads(r.read().decode()))
                if model != models[0]:
                    log(f"  (answered by Gemini model {model})")
                save_gemini_state(state)
                return res
            except urllib.error.HTTPError as e:
                try:
                    err = json.loads(e.read().decode()).get("error", {})
                except ValueError:
                    err = {}
                last = f"Gemini error {e.code} ({model}): {err.get('message', '')[:150]}"
                if e.code == 429:
                    wait, owner = quota_wait(err)
                    if wait <= 60 and attempt < 2:  # per-minute limit: just wait
                        time.sleep(wait + 1)
                        continue
                    for m in {model, owner} - {None}:
                        blocked[m] = time.time() + wait
                    save_gemini_state(state)
                    log(f"  {model} is out of free quota until "
                        f"{time.strftime('%d %b %H:%M', time.localtime(time.time() + wait))}, trying another model")
                elif e.code in (500, 503) and attempt < 2:
                    time.sleep(10 * (attempt + 1))
                    continue
                elif e.code == 404:
                    blocked[model] = time.time() + 86400
                    save_gemini_state(state)
                break  # anything else (bad request, overloaded, not found): next model
            except (TimeoutError, urllib.error.URLError, OSError) as e:
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
    out = sorted(words(text) & set(borrowed))
    for m in FACT_WORD.finditer(text or ""):
        w = m.group().strip(".,;:()/-")
        before = text[:m.start()].rstrip()
        if not w or not before or before[-1] in ".:!?" or len(w) < 2:
            continue
        if w.lower() not in known:
            out.append(w)
    return out


def check_tailor(tailor, profile, job_text):
    """Drop any reworded line that brings in a tool, language, number or job-ad claim not in profile.json."""
    known = json.dumps(profile, ensure_ascii=False).lower()
    borrowed = words(job_text) - words(known)
    for key, fallback in (("title", profile["default_title"]), ("summary", profile["default_summary"])):
        bad = new_facts(tailor.get(key, ""), known, borrowed)
        if bad:
            log(f"  {key} mentioned {', '.join(bad)} (not in your profile), using your default {key}")
            tailor[key] = fallback
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
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "cv.py"), *flags, json_path, pdf],
                       capture_output=True, text=True, timeout=180)
    if not os.path.exists(pdf):
        raise RuntimeError("cv.py failed: " + (r.stderr or r.stdout)[-300:])
    return pdf


def build_cv(tailor, company, today):
    s = slug(company)
    return run_cv_py(tailor, os.path.join(HERE, "tailor", f"{today}-{s}.json"),
                     os.path.join(HERE, "cvs", f"{file_prefix()}-CV-{s}.pdf"))


def build_letter(text, company, role, today):
    s = slug(company)
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
    imap = imaplib.IMAP4_SSL(cfg["imap_host"])
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


def load_config():
    path = os.path.join(HERE, "config.json")
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            cfg.update(json.load(f))
    return cfg


def check_config(cfg):
    keys = (cfg["gmail_address"], cfg["gmail_app_password"], cfg["gemini_api_key"])
    if not all(k and not k.startswith("PUT-") for k in keys):
        raise RuntimeError("config.json is missing gmail_address, gmail_app_password or gemini_api_key")


def take_lock():
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 1500:
        return False
    open(LOCK, "w").close()
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
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def file_prefix():
    """Your name for file names, e.g. "Jane Doe" -> cvs/Jane-Doe-CV-acme.pdf."""
    try:
        name = load_profile().get("name", "")
    except (RuntimeError, ValueError):
        name = ""
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-") or "My"


def collect(rows, now, today, notes):
    """Fetch every source and give each job a status: ready / apply on site / done / rejected."""
    jobs = []
    for src in SOURCES:
        try:
            got = src()
            jobs += got
            log(f"{src.__name__}: {len(got)} jobs")
        except Exception as e:
            notes.append(f"{src.__name__} failed ({e.__class__.__name__})")
            log(f"{src.__name__}: ERROR {e}")
    out, seen = [], set()
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
            mail, mail_src = pick_email(j)
            j["email"], j["email_src"] = mail or "", mail_src or ""
            if mail and already_done(rows, j, mail, today):
                j["status"], j["why"] = STATUS_DONE, "already handled"
            elif mail:
                j["status"], j["why"] = STATUS_READY, ""
            else:
                j["status"], j["why"] = STATUS_SITE, "no published email"
        out.append(j)
    return out


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
    return GEMINI_PROMPT.format(profile=json.dumps(profile, ensure_ascii=False), source=j["source"],
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
    problem = safe(res, profile)
    min_fit = cfg["min_fit_score"] if min_fit is None else min_fit
    if (min_fit and not res.get("eligible")) or res.get("fit_score", 0) < min_fit or problem:
        res["skip_reason"] = problem or res.get("reason", "")
        return res, None
    check_tailor(res["tailor"], profile, f"{j['title']}\n{j['text']}")
    return res, build_cv(res["tailor"], j["company"], today.isoformat())


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


def cv_only_job(cfg, profile, j, today):
    """For jobs without an email: tailored CV + cover letter to upload on the company's site."""
    res, pdf = tailor_job(cfg, profile, j, today, min_fit=0)
    if not pdf:
        log(f"No CV made for {j['company']}: {res['skip_reason']}")
        return False
    if not res.get("eligible"):
        log(f"Note: Gemini thinks you may not be eligible: {res.get('reason', '')}")
    text = res.get("cover_letter") or res["body"]
    # Paragraph 1 may talk about the job; after that, job-ad words that are not in your profile need a look.
    paras = [p for p in text.split("\n\n") if p.strip()]
    borrowed = words(f"{j['title']} {j['text']}") - words(json.dumps(profile))
    review = sorted(words(" ".join(paras[1:-2])) & borrowed)
    letter = build_letter(text, j["company"], j["title"][:120], today.isoformat())
    with open(letter[:-4] + ".txt", "w", encoding="utf-8") as f:  # for pasting into application forms
        f.write(text)
    add_tracker(dict(date=today.isoformat(), company=j["company"], role=j["title"][:100],
                     post_url=j["url"], cv_file=os.path.basename(pdf), draft_id=j["id"],
                     status="cv-made, apply on site"))
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
             text=d["text"])
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
 "projects": [{"id": "short unique lowercase id", "name": "", "text": "description and tech, word for word"}],
 "skills": {"category as in the CV": ["skill", "..."]},
 "education": "degree — school, city (several entries joined with ' | ')"
}
Keep experience and projects in the CV's order. Use "" for anything the CV does not have."""


def read_cv_file(path):
    """Returns (text, attachment) for a CV: PDFs go to Gemini as they are, other files as text."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        with open(path, "rb") as f:
            return "", ("application/pdf", f.read())
    if ext == ".docx":
        import zipfile
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n", xml)
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
    old = load_profile() if os.path.exists(os.path.join(HERE, "profile.json")) else {}
    if not p.get("name") or not p.get("experience"):
        raise RuntimeError("Gemini could not find a name and work experience in that CV.")
    ids = set()
    for e in p["experience"]:
        e["id"] = slug(e.get("id") or e.get("company"))
        while e["id"] in ids:
            e["id"] += "-2"
        ids.add(e["id"])
        e["bullets"] = [b for b in e.get("bullets") or [] if b.strip()]
        for k in ("company", "place", "title", "dates", "note"):
            e[k] = e.get(k) or ""
    p["projects"] = [dict(pr, id=slug(pr.get("id") or pr.get("name"))) for pr in p.get("projects") or []]
    p["skills"] = {k: v for k, v in (p.get("skills") or {}).items() if isinstance(v, list) and v}
    p["contact"] = {k: (p.get("contact") or {}).get(k) or "" for k in ("phone", "email", "linkedin", "github", "portfolio")}
    if old.get("name", "").lower() == p["name"].lower():  # same person: keep links the CV left out
        for k, v in old.get("contact", {}).items():
            p["contact"][k] = p["contact"][k] or v
        p["location"] = p.get("location") or old.get("location", "")
    for k in ("default_title", "default_summary", "location", "years", "education"):
        p[k] = p.get(k) or ""
    p["default_title"] = p["default_title"] or (p["experience"][0]["title"])
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
    """GUI action on one saved job: mode is 'draft', 'cv' or 'skip'."""
    today = dt.date.today()
    j = next((x for x in load_jobs()["jobs"] if x["id"] == job_id), None)
    if not j:
        log("That job is no longer in jobs.json. Press Find jobs again.")
        return
    if mode == "skip":
        add_tracker(dict(date=today.isoformat(), company=j["company"], role=j["title"][:100], email=j["email"],
                         post_url=j["url"], draft_id=j["id"], status="skipped: by you"))
        set_job_status(job_id, STATUS_DONE, "skipped by you")
        log(f"Skipped {j['company']}. The bot will not draft it.")
        return
    cfg = load_config()
    check_config(cfg)
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
        if not dry:
            check_config(cfg)
        now = dt.datetime.now(dt.timezone.utc)
        today = dt.date.today()
        rows = read_tracker()
        today_count = sum(1 for r in rows if r.get("date", "")[:10] == today.isoformat())
        profile = load_profile()

        jobs = collect(rows, now, today, notes)
        stats["fetched"] = len(jobs)
        reasons = {}
        for j in jobs:
            if j["why"]:
                reasons[j["why"]] = reasons.get(j["why"], 0) + 1
        candidates = [j for j in jobs if j["status"] == STATUS_READY]
        stats["candidates"] = len(candidates)
        log(f"filter: {reasons}")
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
                ok = draft_job(cfg, profile, j, today)
            except Exception as e:
                notes.append(f"{j['company']}: {e}"[:200])
                log(f"draft failed for {j['company']}: {e}")
                if NO_MODEL in str(e):  # no point trying the next job
                    break
                continue
            set_job_status(j["id"], STATUS_DONE, "drafted" if ok else "skipped by Gemini")
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
