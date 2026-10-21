# Job Hunter

**Find remote jobs, get a tailored ATS-friendly CV + cover letter for each one, and have the application email waiting in your Gmail drafts.** Free Gemini AI, a simple Windows window, and nothing to `pip install`.

The bot never sends anything. You read each draft and press Send yourself.

> 🎥 Made by **Ahsan Mehmood**. Follow on TikTok: [@YOUR-TIKTOK](https://www.tiktok.com/@YOUR-TIKTOK) · GitHub: [Ahsan483](https://github.com/Ahsan483)

## Demo

<!-- Replace with a GIF or screenshot of the window: docs/demo.gif -->
![Job Hunter window](docs/demo.gif)

## Features

- **Searches 8 job sources at once:** Remotive, RemoteOK, Arbeitnow, Himalayas, Jobicy, We Work Remotely, Working Nomads and the Hacker News "Who is hiring?" thread.
- **Smart filter:** your keywords, max post age, max years of experience, and "only open worldwide / to my region".
- **Finds the application email** in the post, or on the company's own careers page.
- **Tailored CV + cover letter (PDF)** for each job, built only from facts in your profile. The bot drops any line that adds a skill or number you don't have.
- **Gmail drafts** with the CV attached, ready for you to review and send.
- **Paste any job post** (LinkedIn, a company site) and get a tailored CV + cover letter for it.
- **Upload your CV** once and Gemini turns it into your profile.
- **Auto-run every 30 minutes** with Windows Task Scheduler.
- **Uses only free Gemini models** and switches to another model when one runs out of free quota.

## Requirements

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
Copy `config.example.json` to `config.json` and fill in:

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

**Top bar**
- **Find jobs**: searches every job site and lists the matches.
- **Auto-draft best matches**: Gemini checks the fit of the top matches, writes a tailored CV and email for each, and saves Gmail drafts.
- **Gmail drafts**, **CVs folder**, **Tracker**, **Run log**: open your drafts, the PDFs, `tracker.csv` and `runs.log`.
- **Settings**: fit score, draft limits, Gemini call limit and preferred model. **Edit Gmail / Gemini keys…** opens `config.json`.
- **Auto-run**: turns the 30-minute schedule on or off (see below).

**Your CV**
- **Upload my CV**: rebuilds `profile.json` from your CV. The old one is kept as `profile.backup-*.json`.
- **My profile**: opens `profile.json` in Notepad.
- **Tailor CV to a job description…**: paste any job post to get a tailored CV + cover letter.

**Job list**
- **Show** picks the list: ready to draft (has an email), apply on company site, all matches, done / skipped, or everything (rejected jobs show why).
- **Search in list** filters by any text.
- Click a job to read the full post, salary, type and tags, then:
  - **Draft email + CV**: for jobs that published an email address.
  - **Make CV + cover letter**: for jobs you apply to on the company site. The files go to `cvs/`.
  - **Open job page**, **Copy email**, **Skip job** (the bot won't draft it again).

## Filters

Set these in the **Job filter** bar (then press **Save & search**) or in `config.json`:

| Setting | Meaning | Example |
|---|---|---|
| Keywords (`keywords`) | A job is kept if **any** of these appears in it | `React, Node.js, TypeScript` |
| Exclude in title (`exclude_keywords`) | Skip jobs with these words in the title | `Intern, PHP` |
| Max age (`max_job_age_days`) | Ignore older posts | `14` |
| Only open worldwide / to my region (`worldwide_only`) | On: only jobs that hire worldwide or in your region. Off: any remote job | on |
| `my_region_words` (config.json) | Your country/region. Posts naming these count as open to you | `["Pakistan", "South Asia"]` |
| `max_years_required` (config.json) | Skip jobs asking for this many years or more (`0` = off) | `8` |

The defaults look for .NET / C# jobs. Change the keywords to your own stack.

**Settings** also has: `min_fit_score` (0-100 score Gemini gives a job before a draft is made, default 60), `max_drafts_per_run` (3), `max_drafts_per_day` (20) and `max_gemini_calls_per_run` (8, keeps you inside the free limits).

## Auto-run every 30 minutes

Create the scheduled task once in PowerShell (change the path to your folder):
```
schtasks /Create /TN "Remote Job Hunter" /SC MINUTE /MO 30 /TR "pythonw -I \"C:\path\to\job-hunter\bot.py\""
```
After that, the **Auto-run** button in the window turns it on and off. Each run searches, tailors up to `max_drafts_per_run` CVs, and saves the drafts. Nothing is ever sent.

## Command line

```
python -I bot.py --dry-run          # search and filter only (no Gemini, no Gmail)
python -I bot.py                    # one full run, the same as Auto-run
python -I bot.py --import-cv cv.pdf # rebuild profile.json from your CV
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Double-clicking `Job Hunter.bat` does nothing / "Python was not found" | Install Python 3.10+ from python.org and tick "Add python.exe to PATH". |
| "config.json is missing gmail_address, gmail_app_password or gemini_api_key" | Fill in `config.json` (install step 4). |
| "profile.json not found" | Press **Upload my CV**, or copy `profile.example.json` to `profile.json`. |
| "Another run is in progress" | A run was killed halfway. Wait 25 minutes or delete `bot.lock`. |
| "Microsoft Edge not found" | Install Edge from https://www.microsoft.com/edge. |
| Gmail login fails | Use the 16-letter **app password**, not your normal password, and check that IMAP is on. |
| "every free model is out of quota" | Gemini's free limit is used up. The log says when it's back, usually within a day. |
| "model was not found" in `runs.log` | Set `gemini_model` to a current name from https://ai.google.dev/gemini-api/docs/models. |
| No jobs found | Add more keywords, raise the max age, or turn off "Only open worldwide / to my region". |

## Files

| File | Purpose | Uploaded to GitHub? |
|---|---|---|
| `bot.py` | Job search, Gemini tailoring, Gmail drafts | yes |
| `gui.py` | The window | yes |
| `cv.py` | Builds the CV / cover letter PDF | yes |
| `config.example.json`, `profile.example.json` | Templates to copy | yes |
| `config.json` | Your keys, password and settings | **no** |
| `profile.json` | Your CV data | **no** |
| `cvs/`, `tailor/`, `jobs.json`, `tracker.csv`, `runs.log` | Your generated files and history | **no** |

## Job sources and credits

Job listings come from [Remotive](https://remotive.com), [Remote OK](https://remoteok.com), [Arbeitnow](https://www.arbeitnow.com), [Himalayas](https://himalayas.app), [Jobicy](https://jobicy.com), [We Work Remotely](https://weworkremotely.com), [Working Nomads](https://www.workingnomads.com) and [Hacker News](https://news.ycombinator.com). Every job links back to its original post. Please apply through those links and support these sites.

To stay polite, the bot pauses between requests to the same site, backs off when a site says it's busy, checks robots.txt before reading company career pages, and fetches Remotive at most every 6 hours, as its API terms ask.

## Disclaimer

- This tool is for **personal job searching** only. Respect each job site's terms of service and robots.txt, and don't use it to re-publish listings or to collect emails.
- Gemini can make mistakes. **Read every CV, cover letter and email before you send it.** You're responsible for what you send.
- Job posts are written by strangers, and some may be scams. Never pay to apply, and be careful with anyone asking for money or personal documents.
- There's no guarantee of jobs, interviews or replies.
- The software is provided "as is", without warranty. See [LICENSE](LICENSE).

## Contributing

Ideas and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Support

If Job Hunter helped you land interviews, you can [buy me a coffee](https://www.buymeacoffee.com/YOUR-USERNAME) ☕ or star the repo ⭐.

## License

[MIT](LICENSE) © Ahsan Mehmood
