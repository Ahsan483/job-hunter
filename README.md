# Job Hunter: Free AI Remote Job Search Bot (Python, Gemini, Gmail Drafts)

**Job Hunter** is a free, open-source **remote job search bot with a desktop GUI** for Windows. It searches 8 remote job boards at once, filters by your keywords, job age and region ("only open to Pakistan / worldwide"), finds the **recruiter or company email**, and uses **Google Gemini (free tier)** to write a **tailored ATS-friendly CV (PDF), cover letter and application email** for each job. It then saves the email as a **Gmail draft**. It never sends anything on its own: you read each draft and press Send yourself.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6.svg)](#what-you-need)
[![No pip packages](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#what-you-need)
[![Free Gemini API](https://img.shields.io/badge/AI-Gemini%20free%20tier-8E75B2.svg)](https://aistudio.google.com/app/apikey)

> **Watch the 1-minute demo:** https://www.youtube.com/watch?v=4s38kwQLMh4

Good for developers and freelancers looking for **remote jobs from Pakistan, India, Bangladesh, Africa or anywhere in the world**, and for anyone who wants to **automate job applications** without paying for an AI service.

## Features

- **Searches 8 remote job sources:** Remotive, RemoteOK, Arbeitnow, Himalayas, Jobicy, We Work Remotely, Working Nomads and the latest Hacker News "Who is hiring?" thread.
- **Smart filter:** keywords, words to exclude, maximum job age, maximum years required, and **"only open worldwide / to my region"** (for example Pakistan or South Asia).
- **Finds the application email** in the job post or on the company's own careers page, so you can contact the recruiter or CEO directly.
- **Tailored CV + cover letter for every job** from your own `profile.json`, exported as a PDF in **ATS format** (it uses Microsoft Edge to make the PDF).
- **Gmail drafts, never auto-send.** You review every email before sending.
- **Desktop GUI** (`Job Hunter.bat`): job list, fit scores, filters, one-click "Make CV + cover letter", skip list, tracker and run log.
- **Upload your CV** (.pdf, .docx, .txt, .md) and Gemini builds your `profile.json` for you.
- **Auto-run every 30 minutes** with a Windows scheduled task, switched on and off from the app.
- **Runs inside Gemini's free limits** (configurable call and draft limits).
- **No dependencies:** plain Python 3.10+, no `pip install`.

## Quick start

```bash
git clone https://github.com/Ahsan483/job-hunter.git
cd job-hunter
copy config.example.json config.json    # add your Gmail app password + free Gemini key
python -I gui.py                        # or double-click "Job Hunter.bat"
```

Full setup is below. It takes about 5 minutes.

## What you need

- Windows 10 or 11 with **Microsoft Edge** (used to turn the CV into a PDF)
- **Python 3.10+** (no extra packages needed)
- A **Gmail** account with an app password (the drafts are saved here)
- A free **Gemini API key**

## Setup

### 1. Get the code
```
git clone https://github.com/Ahsan483/job-hunter.git
cd job-hunter
```

### 2. Add your secrets: `config.json`
Copy `config.example.json` to `config.json` and fill in:

| Key | What to put |
|---|---|
| `gmail_address` | The Gmail address that should hold the drafts |
| `gmail_app_password` | A 16-letter app password: turn on 2-Step Verification at https://myaccount.google.com/security, then create one at https://myaccount.google.com/apppasswords |
| `gemini_api_key` | A free key from https://aistudio.google.com/app/apikey |

Gmail must allow IMAP (Gmail → Settings → See all settings → Forwarding and POP/IMAP). It is on by default for most accounts.

### 3. Add your CV data: `profile.json`
Every CV, cover letter and email is built **only** from facts in `profile.json`. Pick one way to create it:

- **Easiest:** open the window (step 4) and press **Upload my CV**. Gemini reads your CV (.pdf, .docx or .txt) and writes `profile.json` for you. Check the result afterwards.
- **By hand:** copy `profile.example.json` to `profile.json` and replace the sample person (Jane Doe) with your own details. Keep the same keys: `name`, `default_title`, `contact`, `location`, `years`, `default_summary`, `experience` (each with a unique `id` and a list of `bullets`), `projects`, `skills`, `education`.
- **From the command line:** `python -I bot.py --import-cv my-cv.pdf`

### 4. Set your job filter
In `config.json`, or in the window's **Job filter** bar:

| Key | Meaning | Example |
|---|---|---|
| `keywords` | A job is kept if **any** of these appears in it | `["React", "Node.js", "TypeScript"]` |
| `exclude_keywords` | Skip jobs with these words in the title | `["Intern", "PHP"]` |
| `max_job_age_days` | Ignore older posts | `14` |
| `max_years_required` | Skip jobs asking for this many years or more (`0` = off) | `8` |
| `worldwide_only` | `true`: only jobs open worldwide or to your region. `false`: any remote job | `true` |
| `my_region_words` | Your country/region; posts naming these count as open to you | `["Pakistan", "South Asia"]` |
| `min_fit_score` | Gemini's 0-100 fit score a job needs before a draft is made | `60` |
| `max_drafts_per_run` / `max_drafts_per_day` | Draft limits | `3` / `20` |
| `max_gemini_calls_per_run` | Keeps you inside Gemini's free limits | `8` |

The defaults look for .NET / C# jobs. Change `keywords` for your own stack.

### 5. Test it
```
python -I bot.py --dry-run
```
This uses no Gemini and no Gmail. It shows how many jobs each site returned and which passed the filter. Then do a real run:
```
python -I bot.py
```
This takes 1-3 minutes and ends with a line like `... | drafts 1`. Check Gmail → Drafts.

## The window (GUI)

Start it by double-clicking **Job Hunter.bat**, or run:
```
python -I gui.py
```

**Top bar**
- **Find jobs**: searches every job site (1-3 min) and lists the matches. Uses no Gemini and no Gmail.
- **Auto-draft best matches**: the same as a scheduled run. Gemini checks the fit, writes a tailored CV and email, and saves Gmail drafts.
- **Gmail drafts**, **CVs folder**, **Tracker**, **Run log**: open your drafts, the generated PDFs, `tracker.csv` and `runs.log`.
- **Settings**: fit score, draft limits, Gemini call limit and preferred model. **Edit Gmail / Gemini keys…** opens `config.json`.
- **Auto-run**: turns the 30-minute scheduled task on or off (see below).

**Your CV**
- **Upload my CV**: Gemini reads your CV (.pdf, .docx, .txt or .md) and rebuilds `profile.json`. The old one is kept as `profile.backup-*.json`.
- **My profile**: opens `profile.json` in Notepad so you can fix anything.
- **Tailor CV to a job description…**: paste any job post (from LinkedIn, a company site, etc.) to get a tailored CV + cover letter for it.

**Job filter bar**: keywords, words to exclude, max age, and "Only open worldwide / to my region". **Save & search** saves them to `config.json` (the scheduled run uses them too) and searches again.

**Job list**
- **Show** picks the list: ready to draft (has an email), apply on company site, all matches, done / skipped, or everything (rejected jobs show why).
- **Search in list** filters by any text.
- Click a job to read the full post, salary, type and tags, then:
  - **Draft email + CV**: for jobs that published an email address.
  - **Make CV + cover letter**: for jobs you apply to on the company site. The files go to `cvs/`.
  - **Open job page**, **Copy email**, **Skip job** (the bot won't draft it again).

## Run it every 30 minutes (optional)

Create the scheduled task once (change the path to your folder):
```
schtasks /Create /TN "Remote Job Hunter" /SC MINUTE /MO 30 /TR "pythonw -I \"C:\path\to\job-hunter\bot.py\""
```
After that, the **Auto-run** button in the window turns it on and off.

## Files

| File | Purpose | In git? |
|---|---|---|
| `bot.py` | Job search, Gemini tailoring, Gmail drafts | yes |
| `gui.py` | The window | yes |
| `cv.py` | Builds the CV / cover letter PDF from `profile.json` | yes |
| `config.example.json`, `profile.example.json` | Templates to copy | yes |
| `config.json` | Your passwords and settings | **no** (ignored) |
| `profile.json` | Your CV data | **no** (ignored) |
| `cvs/`, `tailor/`, `jobs.json`, `tracker.csv`, `runs.log` | Your generated files and history | **no** (ignored) |

`config.json` and `profile.json` hold private data and are listed in `.gitignore`. Don't commit them.

## Notes

- Read every draft before you send it. Gemini is told to use only facts from `profile.json`, and the bot drops reworded lines that add tools or numbers your profile doesn't have, but you are still the final check.
- If `runs.log` says the Gemini model was not found, set `gemini_model` to a current name from https://ai.google.dev/gemini-api/docs/models.
- The window says "Another run is in progress" when `bot.lock` is left over from a run that was killed. The lock expires after 25 minutes, or you can delete `bot.lock`.

## FAQ

**Is Job Hunter really free?**
Yes. The code is MIT-licensed. It uses the free tier of the Google Gemini API, and you use your own key. Gmail drafts are free too.

**Can it find remote jobs for Pakistan, India or other regions?**
Yes. Set `worldwide_only` and put your country or region in `my_region_words` (for example `["Pakistan", "South Asia"]`). Jobs that name your region, or that are open worldwide, are kept.

**Does it apply to jobs automatically or send emails by itself?**
No. It only creates Gmail **drafts**. You read each one and press Send.

**Will it make up facts on my CV?**
Gemini is told to use only facts from your `profile.json`, and the bot drops reworded lines that add tools or numbers your profile does not contain. Always read the result before you send it.

**Which job sites does it search?**
Remotive, RemoteOK, Arbeitnow, Himalayas, Jobicy, We Work Remotely, Working Nomads and the Hacker News "Who is hiring?" thread.

**Does it work on Mac or Linux?**
Currently it targets Windows 10/11 (the GUI, the scheduled task and the Edge PDF export are Windows-specific). Pull requests for other systems are welcome.

**How do I get a free Gemini API key?**
Create one at https://aistudio.google.com/app/apikey and paste it into `config.json`.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Good first contributions: new job sources, Linux/macOS support, better email extraction, tests, translations.

## Disclaimer

Use Job Hunter for personal job searching. Respect each job site's terms of service. It does not guarantee interviews, replies or jobs. You are responsible for everything you send.

## License

[MIT](LICENSE) © Ahsan Mehmood

## Related searches

remote job search bot, remote jobs for Pakistan, AI job application automation, tailored CV generator, ATS resume generator, cover letter generator, Gemini API project, free job hunting tool, Python job scraper, Gmail draft automation, Hacker News Who is hiring, RemoteOK, Remotive, We Work Remotely, Himalayas.
