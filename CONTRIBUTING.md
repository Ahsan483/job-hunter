# Contributing to Job Hunter

Thanks for helping! Small, focused pull requests are easiest to review.

## Ground rules
- Never commit secrets or personal data: `config.json`, `profile.json`, generated CVs, `jobs.json`, `tracker.csv` and logs are git-ignored. Check `git status` before you commit.
- Keep it dependency-free (standard library only) unless there is a strong reason.
- The bot must **never send email on its own**. It only creates Gmail drafts.
- Be polite to job sites: keep request delays and a descriptive User-Agent.

## Run it
```
python -I bot.py --dry-run     # no Gemini, no Gmail: shows what each job site returned
python -I gui.py               # the window
```

## Good first contributions
- Add a new remote job source (one function in `bot.py` that returns normalised jobs).
- Linux / macOS support (scheduler, PDF export, GUI).
- Better application-email extraction from careers pages.
- Unit tests for the filters (keywords, age, region, years required).
- Translations of the README.

## Pull requests
1. Fork and create a branch.
2. Describe what changed and how you tested it (a `--dry-run` output is enough for most changes).
3. Keep unrelated formatting changes out of the diff.
