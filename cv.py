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
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EDGE_PATHS = [os.path.join(os.environ.get(v, ""), r"Microsoft\Edge\Application\msedge.exe")
              for v in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData")]
EDGE = next((p for p in EDGE_PATHS if os.path.exists(p)), None)

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
    c = profile["contact"]
    return [f"<h1>{esc(profile['name'])}</h1>", f"<div class='title'>{esc(title)}</div>",
            "<div class='contact'>" + " · ".join(esc(c[k]) for k in
                ("phone", "email", "linkedin", "github", "portfolio") if c.get(k)) + "</div>"]


def page(body):
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"


def build(profile, t):
    out = header(profile, t.get("title") or profile["default_title"]) + [
           "<h2>SUMMARY</h2>",
           f"<div>{esc(t.get('summary') or profile['default_summary'])}</div>",
           "<h2>EXPERIENCE</h2>"]
    order = t.get("bullets", {})
    for e in profile["experience"]:
        idx = order.get(e["id"], list(range(len(e["bullets"]))))
        reworded = t.get("rewrites", {}).get(e["id"], {})
        bullets = [reworded.get(str(i)) or e["bullets"][i] for i in idx if 0 <= i < len(e["bullets"])]
        out.append(f"<div class='role'><div><b>{esc(e['company'])}</b>, {esc(e['place'])} — "
                   f"{esc(e['title'])}</div><div class='dates'>{esc(e['dates'])}</div></div>")
        if e.get("note"):
            out.append(f"<div class='note'>{esc(e['note'])}</div>")
        out.append("<ul>" + "".join(f"<li>{esc(b)}</li>" for b in bullets) + "</ul>")
    projects = {p["id"]: p for p in profile["projects"]}
    chosen = [projects[i] for i in t.get("projects", []) if i in projects]
    if chosen:
        out.append("<h2>PROJECTS</h2><ul>" + "".join(
            f"<li><b>{esc(p['name'])}</b>: {esc(p['text'])}</li>" for p in chosen) + "</ul>")
    first = [s.lower() for s in t.get("skills_first", [])]
    rows = []
    for cat, skills in profile["skills"].items():
        ranked = sorted(skills, key=lambda s: first.index(s.lower()) if s.lower() in first else len(first))
        rows.append(f"<tr><td class='k'>{esc(cat)}</td><td>{esc(', '.join(ranked))}</td></tr>")
    out.append("<h2>SKILLS</h2><table>" + "".join(rows) + "</table>")
    out.append(f"<h2>EDUCATION</h2><div><b>{esc(profile['education'])}</b></div>")
    return page("".join(out))


def build_letter(profile, letter):
    out = header(profile, profile["default_title"])
    out.append(f"<div class='meta'>{dt.date.today():%d %B %Y}<br>{esc(letter.get('company', ''))}"
               + (f"<br><b>Re: {esc(letter['role'])}</b>" if letter.get("role") else "") + "</div>")
    paras = [p.strip() for p in letter["text"].replace("\r", "").split("\n\n") if p.strip()]
    out.append("<div class='letter'>" + "".join(f"<p>{esc(p).replace(chr(10), '<br>')}</p>" for p in paras) + "</div>")
    return page("".join(out))


def main():
    is_letter = sys.argv[1] == "--letter"
    data_path, out_pdf = sys.argv[1 + is_letter], os.path.abspath(sys.argv[2 + is_letter])
    if not EDGE:
        sys.exit("Microsoft Edge not found (needed to make the PDF). Install it from https://www.microsoft.com/edge")
    with open(os.path.join(HERE, "profile.json"), encoding="utf-8") as f:
        profile = json.load(f)
    with open(data_path, encoding="utf-8-sig") as f:
        t = json.load(f)
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(build_letter(profile, t) if is_letter else build(profile, t))
        tmp = f.name
    try:
        subprocess.run([EDGE, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={out_pdf}", "file:///" + tmp.replace("\\", "/")],
                       check=True, timeout=120, capture_output=True)
    finally:
        os.remove(tmp)
    print(out_pdf if os.path.exists(out_pdf) else "FAILED")


if __name__ == "__main__":
    main()
