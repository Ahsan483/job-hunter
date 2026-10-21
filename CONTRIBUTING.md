# Contributing

Thanks for helping! Bug reports, new job sources and small fixes are all welcome.

## Getting started
1. Fork the repo and clone your fork.
2. Follow the setup in [README.md](README.md). For most changes you only need `profile.json` (copy `profile.example.json`), not Gmail or Gemini keys.
3. Test the job search without keys: `python -I bot.py --dry-run`

## Rules
- **Standard library only.** People install this from a TikTok video, so `pip install` must never be needed.
- **Never send email.** The bot only saves Gmail drafts. Pull requests that send mail automatically won't be merged.
- **Be polite to job sites.** Use `fetch()` in `bot.py` (it pauses between requests and backs off on errors), follow each site's API terms, and don't add sources that forbid automated access.
- **Never commit personal data.** `config.json`, `profile.json`, `cvs/`, `tailor/`, `jobs.json`, `tracker.csv` and `runs.log` are ignored. Keep it that way.
- Match the existing style: short functions, plain names, comments only where the reason isn't obvious.

## Adding a job source
Write a `src_<name>()` function in `bot.py` that returns a list of dicts with `source`, `id`, `title`, `company`, `url`, `location`, `text` and `date`. Add it to `SOURCES`, then check it with `--dry-run`.

## Pull requests
Keep each PR to one change, say what you tested, and add a screenshot for GUI changes.
