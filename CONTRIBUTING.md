# Contributing to Job Hunter

Thanks for helping! Small, focused pull requests are easiest to review.

## Ground rules
- Never commit secrets or personal data: `config.json`, `profile.json`, generated CVs, `jobs.json`, `tracker.csv` and logs are git-ignored. Check `git status` before you commit.
- The bot (`bot.py`, `cv.py`) uses only the standard library; keep it that way. The window uses pywebview and a React page in `ui/`.
- The bot must **never send email on its own**. It only creates Gmail drafts.
- Be polite to job sites: keep request delays and a descriptive User-Agent.

## Run it
```
python -I bot.py --dry-run     # no Gemini, no Gmail: shows what each job site returned
python -m pip install -r requirements.txt   # once: pywebview, for the window
cd ui && npm ci && npm run build && cd ..   # once, and after changing ui/
python -I webapp.py            # the window
cd ui && npm run dev           # work on the page in a browser, with sample data
python -I -m unittest discover -s tests   # the tests; GitHub Actions runs them on every push
```

## Good first contributions
- Add a new remote job source (one function in `bot.py` that returns normalised jobs).
- Linux / macOS support (scheduler, PDF export, GUI).
- Better application-email extraction from careers pages.
- More unit tests in `tests/` (each job source's parser, with a saved sample response).
- Translations of the README.

## Releasing
1. Set `VERSION` in `bot.py` (the window compares it with the latest release to offer updates).
2. `git tag v<VERSION> && git push origin v<VERSION>`. The Release workflow builds the installer and refuses a tag that does not match `VERSION`.

## Pull requests
1. Fork and create a branch.
2. Add or update a test in `tests/` when you fix a bug, and make sure `python -I -m unittest discover -s tests` passes.
3. Describe what changed and how you tested it (a `--dry-run` output is enough for most changes).
4. Keep unrelated formatting changes out of the diff.
