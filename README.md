# Job Hunter: Free AI Remote Job Search Bot (Python, Gemini, Gmail Drafts)

**Job Hunter** is a free, open-source **remote job search bot with a desktop GUI** for Windows. It searches 8 remote job boards at once, filters by your keywords, job age and region ("only open to Pakistan / worldwide"), finds the **recruiter or company email**, and uses **Google Gemini (free tier)** to write a **tailored ATS-friendly CV (PDF), cover letter and application email** for each job, in any field: software, finance, sales, SEO, support, design, writing, HR and more. It then saves the email as a **Gmail draft**. It never sends anything on its own: you read each draft and press Send yourself.

[![Download for Windows](https://img.shields.io/badge/download-JobHunterSetup.exe-2563eb.svg)](https://github.com/Ahsan483/job-hunter/releases/latest/download/JobHunterSetup.exe)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6.svg)](#requirements-running-from-source)
[![No pip packages](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#requirements-running-from-source)
[![Free Gemini API](https://img.shields.io/badge/AI-Gemini%20free%20tier-8E75B2.svg)](https://aistudio.google.com/app/apikey)

> **Watch the 1-minute demo:** https://www.youtube.com/watch?v=4s38kwQLMh4

Good for developers and freelancers looking for **remote jobs from Pakistan, India, Bangladesh, Africa or anywhere in the world**, and for anyone who wants to **automate job applications** without paying for an AI service.

> 🎥 Made by **Ahsan Mehmood** · GitHub: [Ahsan483](https://github.com/Ahsan483)

## Features

- **Searches 8 job sources at once:** Remotive, RemoteOK, Arbeitnow, Himalayas, Jobicy, We Work Remotely, Working Nomads and the Hacker News "Who is hiring?" thread.
- **Any kind of remote job:** pick a job type (Finance / Accounting, Sales, SEO / Marketing, Customer support, Design, Writing, Data, HR, Virtual assistant, Project management, Software) or type your own keywords.
- **Smart filter:** your keywords, max post age, max years of experience, and "only open worldwide / to my region".
- **Finds the application email** in the post, or on the company's own careers page.
- **Tailored CV + cover letter (PDF)** for each job, built only from facts in your profile. The bot drops any line that adds a skill or number you don't have.
- **Gmail drafts** with the CV attached, ready for you to review and send. Gmail is optional: without it you get the CV, cover letter and email text as files.
- **Paste any job post** (LinkedIn, a company site) and get a tailored CV + cover letter for it.
- **Upload your CV** once (PDF, Word, text, or even a photo/scan) and Gemini turns it into your profile. Works without work experience too, for students and career changers.
- **Track your applications:** mark a job as applied, reopen the CV made for it, or copy its cover letter into an application form.
- **Tells you when an update is out**, with a getting-started checklist and a hint on every button.
- **Auto-run every 30 minutes** with Windows Task Scheduler.
- **Uses only free Gemini models** and switches to another model when one runs out of free quota.

## Download for Windows (easiest)

1. Download **[JobHunterSetup.exe](https://github.com/Ahsan483/job-hunter/releases/latest/download/JobHunterSetup.exe)** (or from [codeprojectsofficial.com/tools/job-hunter](https://www.codeprojectsofficial.com/tools/job-hunter)).
2. Run it. If Windows shows **"Windows protected your PC"**, click **More info → Run anyway** (the installer is not code-signed yet).
3. Job Hunter opens and asks for your **Gemini API key** and, optionally, a **Gmail app password**. Press **How do I get…?** under each box for step-by-step help, then **Test & save**.
4. Press **Upload my CV**, then **Find jobs**.

No Python needed. Your keys, profile and CVs stay on your computer in `%APPDATA%\Job Hunter`. Uninstalling keeps them.

To run from source instead, follow the steps below.

## Requirements (running from source)

- Windows 10 or 11
- [Python 3.10+](https://www.python.org/downloads/). Tick **"Add python.exe to PATH"** when installing.
- Microsoft Edge (built into Windows; used to make the PDFs)
- A free Gemini API key
- A Gmail account, only if you want automatic drafts

Nothing to `pip install`: the app uses only Python's standard library.

## Install

### 1. Download
```
git clone https://github.com/Ahsan483/job-hunter.git
cd job-hunter
```
Or click **Code → Download ZIP** on GitHub and unzip it.

### 2. Get a free Gemini API key
1. Go to https://aistudio.google.com/app/apikey and sign in with a Google account.
2. Click **Create API key** and copy it.

### 3. Set up Gmail drafts (optional)
Skip this if you only want CVs and cover letters.
1. Turn on 2-Step Verification: https://myaccount.google.com/security
2. Create an app password at https://myaccount.google.com/apppasswords (name it "Job Hunter") and copy the 16 letters.
3. Check that IMAP is on: Gmail → Settings → See all settings → Forwarding and POP/IMAP. It is on by default for most accounts.

### 4. Create `config.json`
The window asks for your keys the first time it opens and writes `config.json` for you. To do it by hand, copy `config.example.json` to `config.json` and fill in:

| Key | What to put |
|---|---|
| `gemini_api_key` | Your Gemini key from step 2 |
| `gmail_address` | The Gmail address that should hold the drafts |
| `gmail_app_password` | The 16-letter app password from step 3 |

`config.json` holds your passwords. It is in `.gitignore`, so it's never uploaded. Don't share it.

### 5. Create `profile.json` (your CV data)
Every CV, cover letter and email is built **only** from facts in `profile.json`. Pick one way to make it:

- **Easiest:** open the window (next step) and press **Upload my CV**. Gemini reads your CV (.pdf, .docx, .txt or .md) and writes `profile.json`. Then press **My profile** and check it.
- **By hand:** copy `profile.example.json` to `profile.json` and replace the sample person (Jane Doe) with your details. Keep the same keys: `name`, `default_title`, `contact`, `location`, `years`, `default_summary`, `experience` (each with a unique `id` and a list of `bullets`), `projects`, `skills`, `education`.
- **Command line:** `python -I bot.py --import-cv my-cv.pdf`

### 6. Start it
Double-click **Job Hunter.bat**, or run:
```
python -I gui.py
```
Press **Find jobs** for a first test. It takes 1-3 minutes and uses no Gemini and no Gmail.

## Using the window

The window is a set of frosted-glass cards over a navy gradient. Drag the gaps between the cards to resize the job list, the details and the console. Hover over any button to see what it does. While no job is picked, the details card shows a **Getting started** checklist.

**Top bar**
- **Find jobs** (F5): searches every job site and lists the matches. Uses no Gemini and no Gmail.
- **Auto-draft best matches**: Gemini checks the fit of the top matches, writes a tailored CV and email for each, and saves Gmail drafts. Without Gmail it saves the CV, cover letter and email text as files instead.
- **Stop**: stops the run in progress, including one started by Auto-run.
- **Open**: your Gmail drafts, your CVs and cover letters, `tracker.csv`, `runs.log` and the data folder.
- **Settings**: fit score, draft limits, Gemini call limit and the years-of-experience filter. **Gmail & Gemini keys…** changes your keys.
- **Help**: getting started, this guide, report a problem, check for updates.
- **Auto-run**: sets up and turns on or off the 30-minute schedule (see below).
- **Update to vX.Y**: shows up when a newer version is out. Download and run the installer: your keys, profile and CVs are kept.

**Your CV**
- **Upload my CV**: rebuilds `profile.json` from your CV (.pdf, .docx, .txt, .md, or a .png/.jpg photo). The old one is kept as `profile.backup-*.json`.
- **My profile**: opens `profile.json` in Notepad.
- **Tailor CV to a job description…**: paste any job post to get a tailored CV + cover letter.
- **AI model**: pick a Gemini model, or leave it on Auto. **Check models** shows which ones your key can use right now.

**Job list**
- **Show** picks the list: ready to draft (has an email), apply on company site, all matches, done / applied / skipped, or everything (rejected jobs show why).
- **Search in list** (Ctrl+F) filters by any text.
- Click a job to read the full post, salary, type and tags, then:
  - **Draft email + CV**: for jobs that published an email address.
  - **CV + cover letter**: for jobs you apply to on the company site. The files go to `cvs/`.
  - **Job page** (Enter), **Email** (copy the address), **My CV for it** (open the CV and cover letter made for this job), **Cover letter** (copy its text for an application form).
  - **Applied**: you sent it. It moves to Done and is noted in `tracker.csv`.
  - **Skip**: the bot won't draft it.

## Filters

Set these in the **Job filter** bar (then press **Save & search**) or in `config.json`:

| Setting | Meaning | Example |
|---|---|---|
| Job type | Fills in keywords that suit a field and picks the matching We Work Remotely categories. Pick **Custom** to type your own (then every category is read) | `Finance / Accounting` |
| Keywords (`keywords`) | A job is kept if **any** of these appears in it | `React, Node.js` or `Accountant, Bookkeeper` |
| Keywords in title only (`keywords_in_title`) | The keyword must be in the job title, not just the description. Turn it on for words like *Sales* or *Finance* that appear in almost every job ad | on |
| Exclude in title (`exclude_keywords`) | Skip jobs with these words in the title | `Intern, PHP` |
| Max age (`max_job_age_days`) | Ignore older posts | `14` |
| Only open worldwide / to my region (`worldwide_only`) | On: only jobs that hire worldwide or in your region. Off: any remote job | on |
| My country/region (`my_region_words`) | Your country/region. Posts naming these count as open to you | `Pakistan, South Asia` |
| Skip jobs asking for (years) (`max_years_required`, in Settings) | Skip jobs asking for this many years or more (`0` = off) | `8` |
| `job_fields` (config.json) | We Work Remotely categories to read: `software`, `devops`, `design`, `sales & marketing`, `customer support`, `finance & management`, `product`, `other`, or `all`. Set by **Job type** | `["sales & marketing"]` |

The defaults look for .NET / C# jobs. Pick a **Job type** or type your own keywords for any other field. Your CV can be from any field too: **Upload my CV** keeps certifications, languages and software as skills, and the tailoring never adds a tool, certification or number your CV doesn't have.

**Settings** also has: `min_fit_score` (0-100 score Gemini gives a job before a draft is made, default 60), `max_drafts_per_run` (3), `max_drafts_per_day` (20) and `max_gemini_calls_per_run` (8, keeps you inside the free limits).

## Auto-run every 30 minutes

Press **Set up auto-run** in the window once. It creates a Windows scheduled task named "Remote Job Hunter" that runs every 30 minutes while you are signed in. After that, the same button turns it on and off. Each run searches, tailors up to `max_drafts_per_run` CVs, and saves the drafts. Nothing is ever sent.

## Building the installer

`installer\build.ps1` builds `build\installer\JobHunterSetup.exe` with PyInstaller and [Inno Setup 6](https://jrsoftware.org/isinfo.php):
```
powershell -ExecutionPolicy Bypass -File installer\build.ps1 -Version 1.0.0
```
Pushing a tag such as `v1.0.0` does the same on GitHub Actions and publishes the installer as a release (`.github/workflows/release.yml`).

## Command line

```
python -I bot.py --dry-run          # search and filter only (no Gemini, no Gmail)
python -I bot.py                    # one full run, the same as Auto-run
python -I bot.py --import-cv cv.pdf # rebuild profile.json from your CV
python -I -m unittest discover -s tests   # run the tests (no network needed)
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Double-clicking `Job Hunter.bat` does nothing / "Python was not found" | Install Python 3.10+ from python.org and tick "Add python.exe to PATH". Or use the [installer](#download-for-windows-easiest), which needs no Python. |
| "Gmail or Gemini is not connected yet" | Press **Settings → Gmail & Gemini keys…** (or fill in `config.json`, install step 4). |
| "profile.json not found" | Press **Upload my CV**, or copy `profile.example.json` to `profile.json`. |
| "Another run is in progress" | A run was killed halfway. Wait 25 minutes or delete `bot.lock`. |
| "Could not make the PDF" / "Microsoft Edge not found" | Restart Windows (to finish a pending Edge update), or update Edge in `edge://settings/help`. If Google Chrome is installed it is used when Edge fails. |
| "Gmail is not connected" | Gmail is only needed for drafts. Use **CV + cover letter**, or connect Gmail in **Settings → Gmail & Gemini keys…** |
| "profile.json has a typo" | Press **My profile** and fix the line it names (usually a missing comma or quote), or **Upload my CV** again. |
| Gmail login fails | Use the 16-letter **app password**, not your normal password, and check that IMAP is on. |
| "every free model is out of quota" | Gemini's free limit is used up. The log says when it's back, usually within a day. |
| "model was not found" in `runs.log` | Set `gemini_model` to a current name from https://ai.google.dev/gemini-api/docs/models. |
| No jobs found | Add more keywords, raise the max age, or turn off "Only open worldwide / to my region". For non-software jobs, pick a **Job type** so the right job categories are searched. Pick **Show: Everything** to see why each job was left out. |

## Files

| File | Purpose | Uploaded to GitHub? |
|---|---|---|
| `bot.py` | Job search, Gemini tailoring, Gmail drafts | yes |
| `gui.py` | The window | yes |
| `cv.py` | Builds the CV / cover letter PDF | yes |
| `jobhunter.py`, `installer/` | The installed JobHunter.exe and how it is built | yes |
| `tests/` | Unit tests, run by GitHub Actions on every push | yes |
| `config.example.json`, `profile.example.json` | Templates to copy | yes |
| `config.json` | Your keys, password and settings | **no** |
| `profile.json` | Your CV data | **no** |
| `cvs/`, `tailor/`, `jobs.json`, `tracker.csv`, `runs.log` | Your generated files and history | **no** |

The installed app keeps the files that are not uploaded in `%APPDATA%\Job Hunter` instead of the program folder. To keep them somewhere else (a USB stick, or a test copy), set the environment variable `JOBHUNTER_HOME` to that folder.

## Job sources and credits

Job listings come from [Remotive](https://remotive.com), [Remote OK](https://remoteok.com), [Arbeitnow](https://www.arbeitnow.com), [Himalayas](https://himalayas.app), [Jobicy](https://jobicy.com), [We Work Remotely](https://weworkremotely.com), [Working Nomads](https://www.workingnomads.com) and [Hacker News](https://news.ycombinator.com). Every job links back to its original post. Please apply through those links and support these sites.

To stay polite, the bot pauses between requests to the same site, backs off when a site says it's busy, checks robots.txt before reading company career pages, and fetches Remotive at most every 6 hours, as its API terms ask.

## FAQ

**Is Job Hunter really free?**
Yes. The code is MIT-licensed. It uses the free tier of the Google Gemini API, and you use your own key. Gmail drafts are free too.

**Do I need Python?**
Not with the [Windows installer](#download-for-windows-easiest). Running from source needs Python 3.10+.

**Can it find remote jobs for Pakistan, India or other regions?**
Yes. Tick **Only open worldwide / to my region** and type your country or region in **My country/region** (for example `Pakistan, South Asia`). Jobs that name your region, or that are open worldwide, are kept.

**Does it apply to jobs automatically or send emails by itself?**
No. It only creates Gmail **drafts**. You read each one and press Send.

**Will it make up facts on my CV?**
Gemini is told to use only facts from your `profile.json`, and the bot drops reworded lines that add tools or numbers your profile does not contain. Always read the result before you send it.

**Which job sites does it search?**
Remotive, RemoteOK, Arbeitnow, Himalayas, Jobicy, We Work Remotely, Working Nomads and the Hacker News "Who is hiring?" thread.

**Does it work on Mac or Linux?**
Currently it targets Windows 10/11 (the GUI, the scheduled task and the Edge PDF export are Windows-specific). Pull requests for other systems are welcome.

**How do I get a free Gemini API key?**
Create one at https://aistudio.google.com/app/apikey. The window asks for it the first time it opens, with step-by-step help.

## Disclaimer

- This tool is for **personal job searching** only. Respect each job site's terms of service and robots.txt, and don't use it to re-publish listings or to collect emails.
- Gemini can make mistakes. **Read every CV, cover letter and email before you send it.** You're responsible for what you send.
- Job posts are written by strangers, and some may be scams. Never pay to apply, and be careful with anyone asking for money or personal documents.
- There's no guarantee of jobs, interviews or replies.
- The software is provided "as is", without warranty. See [LICENSE](LICENSE).

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Good first contributions: new job sources, Linux/macOS support, better email extraction, tests, translations.

## Support

If Job Hunter helped you land interviews, star the repo ⭐ and tell a friend.

## License

[MIT](LICENSE) © Ahsan Mehmood

## Related searches

remote job search bot, remote jobs for Pakistan, AI job application automation, tailored CV generator, ATS resume generator, cover letter generator, Gemini API project, free job hunting tool, Python job scraper, Gmail draft automation, Hacker News Who is hiring, RemoteOK, Remotive, We Work Remotely, Himalayas.
