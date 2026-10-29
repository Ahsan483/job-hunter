"""Build a tailored CV PDF from profile.json plus a small tailoring file.

Usage: python -I cv.py <tailor.json> <out.pdf>
       python -I cv.py --letter <letter.json> <out.pdf>

The tailoring file can only pick, reorder and emphasise facts that already
exist in profile.json. The free text is "summary" and the reworded bullets,
which bot.py checks against profile.json before they get here.

tailor.json fields (all optional):
  title         headline under the name
  summary       2-4 sentences, facts from profile.json only
  skills_first  skills to list first inside their categories
  bullets       {"<experience id>": [bullet indexes in the order to show]}
  rewrites      {"<experience id>": {"<bullet index>": "same bullet, reworded for the job"}}
  projects      [project ids to include, in order]

letter.json fields: company, role, text (paragraphs separated by blank lines)
"""
import datetime as dt
import html
import json
import os
import pathlib
import subprocess
import sys
import tempfile

FROZEN = getattr(sys, "frozen", False)  # the installed JobHunter.exe keeps your files in %APPDATA%\Job Hunter
HERE = os.environ.get("JOBHUNTER_HOME") or (
    os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Job Hunter") if FROZEN
    else os.path.dirname(os.path.abspath(__file__)))
# Edge comes with Windows; Chrome is the fallback when Edge is missing or broken (e.g. a half-installed update).
BROWSERS = [os.path.join(os.environ.get(v, ""), path)
            for path in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe")
            for v in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData")]
BROWSERS = [p for p in dict.fromkeys(BROWSERS) if os.path.exists(p)]

CSS = """
@page { size: A4; margin: 14mm 15mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 10.2pt; color: #1a1a1a; line-height: 1.38; }
h1 { font-size: 22pt; margin: 0; }
.title { color: #0f766e; font-weight: 600; font-size: 11.5pt; margin: 2px 0 4px; }
.contact { font-size: 9pt; color: #444; }
h2 { font-size: 10pt; letter-spacing: 2px; color: #0f766e; border-bottom: 1px solid #ccc; padding-bottom: 2px; margin: 14px 0 6px; }
.role { display: flex; justify-content: space-between; margin-top: 8px; }
.role .dates { color: #555; font-size: 9pt; white-space: nowrap; }
.note { color: #555; font-size: 9pt; }
ul { margin: 3px 0 0 0; padding-left: 16px; }
li { margin: 1px 0; }
table { border-collapse: collapse; }
td { vertical-align: top; padding: 1px 10px 1px 0; }
td.k { font-weight: 700; white-space: nowrap; }
.letter { font-size: 10.8pt; line-height: 1.5; margin-top: 18px; }
.letter p { margin: 0 0 10px; }
.meta { margin-top: 16px; color: #444; }
"""


def esc(s):
    return html.escape(s, quote=False)


def header(profile, title):
    c = profile.get("contact") or {}
    return [f"<h1>{esc(profile['name'])}</h1>", f"<div class='title'>{esc(title)}</div>",
            "<div class='contact'>" + " · ".join(esc(c[k]) for k in
                ("phone", "email", "linkedin", "github", "portfolio") if c.get(k)) + "</div>"]


def page(body):
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"


def build(profile, t):
    out = header(profile, t.get("title") or profile.get("default_title", ""))
    summary = t.get("summary") or profile.get("default_summary")
    if summary:
        out += ["<h2>SUMMARY</h2>", f"<div>{esc(summary)}</div>"]
    if profile.get("experience"):  # a student's or career changer's CV may have none
        out.append("<h2>EXPERIENCE</h2>")
    order = t.get("bullets") or {}
    for e in profile.get("experience") or []:
        lines = e.get("bullets") or []
        idx = [int(i) for i in order.get(e.get("id"), range(len(lines))) if str(i).isdigit()]
        reworded = (t.get("rewrites") or {}).get(e.get("id")) or {}
        bullets = [reworded.get(str(i)) or lines[i] for i in idx if i < len(lines)]
        where = ", ".join([f"<b>{esc(e['company'])}</b>"] * bool(e.get("company")) + [esc(e["place"])] * bool(e.get("place")))
        out.append(f"<div class='role'><div>{where}" + (f" — {esc(e['title'])}" if e.get("title") else "")
                   + f"</div><div class='dates'>{esc(e.get('dates', ''))}</div></div>")
        if e.get("note"):
            out.append(f"<div class='note'>{esc(e['note'])}</div>")
        if bullets:
            out.append("<ul>" + "".join(f"<li>{esc(b)}</li>" for b in bullets) + "</ul>")
    projects = {p.get("id"): p for p in profile.get("projects") or []}
    chosen = [projects[i] for i in t.get("projects") or [] if i in projects]
    if not chosen and not profile.get("experience"):  # no experience: projects are the evidence
        chosen = list(projects.values())
    if chosen:
        out.append("<h2>PROJECTS</h2><ul>" + "".join(
            f"<li><b>{esc(p.get('name', ''))}</b>: {esc(p.get('text', ''))}</li>" for p in chosen) + "</ul>")
    first = [str(s).lower() for s in t.get("skills_first") or []]
    rows = []
    for cat, skills in (profile.get("skills") or {}).items():
        skills = [s.strip() for s in skills.split(",")] if isinstance(skills, str) else [str(s) for s in skills]
        ranked = sorted(skills, key=lambda s: first.index(s.lower()) if s.lower() in first else len(first))
        rows.append(f"<tr><td class='k'>{esc(cat)}</td><td>{esc(', '.join(ranked))}</td></tr>")
    if rows:
        out.append("<h2>SKILLS</h2><table>" + "".join(rows) + "</table>")
    if profile.get("education"):
        out.append(f"<h2>EDUCATION</h2><div><b>{esc(profile['education'])}</b></div>")
    return page("".join(out))


def build_letter(profile, letter):
    out = header(profile, profile.get("default_title", ""))
    out.append(f"<div class='meta'>{dt.date.today():%d %B %Y}<br>{esc(letter.get('company', ''))}"
               + (f"<br><b>Re: {esc(letter['role'])}</b>" if letter.get("role") else "") + "</div>")
    paras = [p.strip() for p in letter["text"].replace("\r", "").split("\n\n") if p.strip()]
    out.append("<div class='letter'>" + "".join(f"<p>{esc(p).replace(chr(10), '<br>')}</p>" for p in paras) + "</div>")
    return page("".join(out))


def print_pdf(html_file, out_pdf):
    """Print the page to PDF with the first browser that manages it. Returns the error when none does."""
    error = "Microsoft Edge not found. Install it from https://www.microsoft.com/edge"
    for exe in BROWSERS:
        with tempfile.TemporaryDirectory() as profile_dir:  # its own profile: an open browser window cannot interfere
            try:
                r = subprocess.run([exe, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                                    f"--user-data-dir={profile_dir}", f"--print-to-pdf={out_pdf}",
                                    pathlib.Path(html_file).as_uri()],  # as_uri: folder names with spaces or accents
                                   timeout=120, capture_output=True)
            except (OSError, subprocess.TimeoutExpired) as e:
                error = f"{os.path.basename(exe)} could not make the PDF ({e.__class__.__name__})"
                continue
        if os.path.exists(out_pdf):
            return None
        error = (f"{os.path.basename(exe)} made no PDF (exit code {r.returncode}). Restart Windows to finish any "
                 "Edge update, or update Edge in edge://settings/help")
    return error


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    is_letter = sys.argv[1] == "--letter"
    data_path, out_pdf = sys.argv[1 + is_letter], os.path.abspath(sys.argv[2 + is_letter])
    with open(os.path.join(HERE, "profile.json"), encoding="utf-8-sig") as f:
        profile = json.load(f)
    with open(data_path, encoding="utf-8-sig") as f:
        t = json.load(f)
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(build_letter(profile, t) if is_letter else build(profile, t))
        tmp = f.name
    try:
        error = print_pdf(tmp, out_pdf)
    finally:
        os.remove(tmp)
    if error:
        sys.exit(error)
    print(out_pdf)

if __name__ == "__main__":
    main()
