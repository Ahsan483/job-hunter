"""The window (gui.py), built for real on a temporary folder. No run, browser or dialog is started."""
import contextlib
import csv
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402
import gui  # noqa: E402
from test_bot import PROFILE  # noqa: E402

JOBS = [
    {"id": "a-1", "status": "ready", "why": "", "title": "Backend Engineer", "company": "Acme", "source": "remotive",
     "location": "Worldwide", "date": "2026-10-28T10:00:00+00:00", "text": "C# APIs", "url": "https://a.example/1",
     "email": "jobs@acme.example", "email_src": "https://a.example/1"},
    {"id": "b-2", "status": "apply on site", "why": "no published email", "title": "SEO Specialist",
     "company": "Beta", "source": "himalayas", "location": "Pakistan", "date": "2026-10-27T10:00:00+00:00",
     "text": "SEO", "url": "https://b.example/2", "email": "", "salary": "40k USD"},
    {"id": "c-3", "status": "rejected", "why": "too old", "title": "Designer", "company": "Gamma",
     "source": "jobicy", "location": "USA", "date": "2026-08-01T10:00:00+00:00", "text": "Figma",
     "url": "https://c.example/3", "email": ""},
]


class Window(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.dir = self.tmp.name
        self.stack = contextlib.ExitStack()
        for mod, names in ((gui, dict(HERE=d, CONFIG="config.json", PROFILE="profile.json", JOBS_FILE="jobs.json",
                                      TRACKER="tracker.csv", LOCK="bot.lock")),
                           (bot, dict(HERE=d, GEMINI_STATE="gemini_state.json", TRACKER="tracker.csv"))):
            for k, v in names.items():
                self.stack.enter_context(mock.patch.object(mod, k, v if k == "HERE" else os.path.join(d, v)))
        for name in ("showinfo", "showerror", "askyesno", "askokcancel", "askyesnocancel"):
            self.stack.enter_context(mock.patch.object(gui.messagebox, name, return_value=False))
        self.run_bot = self.stack.enter_context(mock.patch.object(gui.App, "run_bot"))
        self.stack.enter_context(mock.patch.object(gui.App, "task_state", return_value=None))
        self.write("config.json", {"gemini_api_key": "AIza-test", "keywords": ["SEO"], "my_region_words": ["Pakistan"]})
        self.write("profile.json", PROFILE)
        self.write("jobs.json", {"updated": "2026-10-29 10:00", "jobs": JOBS})
        self.app = gui.App()
        self.app.withdraw()
        self.app.update_idletasks()

    def tearDown(self):
        for job in self.app.tk.splitlist(self.app.tk.call("after", "info")):
            self.app.after_cancel(job)
        self.app.destroy()
        self.stack.close()
        self.tmp.cleanup()

    def write(self, name, data):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def config(self):
        with open(os.path.join(self.dir, "config.json"), encoding="utf-8") as f:
            return json.load(f)

    def pick(self, job_id):
        iid = next(i for i, j in self.app.by_iid.items() if j["id"] == job_id)
        self.app.tree.selection_set(iid)
        self.app.show_detail()

    def enabled(self, *names):
        return [n for n in names if not getattr(self.app, n).instate(["disabled"])]

    def detail(self):
        return self.app.detail.get("1.0", "end")

    def test_lists_matches_with_counts(self):
        self.assertEqual(len(self.app.by_iid), 2)  # "All matches" hides the rejected job
        self.assertIn("1 with email, 1 apply on site, 3 checked", self.app.count_lbl.cget("text"))
        self.app.view.set("Everything (incl. rejected)")
        self.app.fill_table()
        self.assertEqual(len(self.app.by_iid), 3)
        self.app.search.set("pakistan")
        self.assertEqual([j["id"] for j in self.app.by_iid.values()], ["b-2"])

    def test_no_matches_gives_advice(self):
        self.write("jobs.json", {"updated": "x", "jobs": [JOBS[2]]})
        self.app.load_jobs()
        self.assertIn("No matches in 1 jobs", self.app.count_lbl.cget("text"))

    def test_few_matches_say_what_to_loosen(self):
        old = dict(JOBS[2], why="too old", match="strong")
        far = dict(JOBS[2], id="d-4", why="not open worldwide/to my region", match="partial")
        self.write("jobs.json", {"updated": "x", "jobs": [old, far]})
        self.app.load_jobs()
        text = self.app.count_lbl.cget("text")
        self.assertIn("1 more are older than", text)
        self.assertIn("1 more are limited to other countries", text)

    def test_buttons_follow_the_job(self):
        self.pick("a-1")
        self.assertEqual(self.enabled("b_draft", "b_cv", "b_open", "b_copy", "b_applied", "b_skip", "b_files"),
                         ["b_draft", "b_cv", "b_open", "b_copy", "b_applied", "b_skip"])
        self.assertIn("jobs@acme.example", self.detail())
        self.pick("b-2")
        self.assertEqual(self.enabled("b_draft", "b_copy"), [])

    def test_my_cv_for_this_job(self):
        cvs = os.path.join(self.dir, "cvs")
        os.makedirs(cvs)
        for name in ("Jane-CV-acme.pdf", "Jane-Cover-Letter-acme.pdf"):
            open(os.path.join(cvs, name), "wb").close()
        with open(os.path.join(cvs, "Jane-Cover-Letter-acme.txt"), "w", encoding="utf-8") as f:
            f.write("Dear team,")
        with open(os.path.join(self.dir, "tracker.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "company", "role", "email", "poster", "post_url", "cv_file", "draft_id", "status"])
            w.writerow(["2026-10-29", "Acme", "r", "", "", "", "Jane-CV-acme.pdf", "a-1", "cv-made"])
        self.pick("a-1")
        self.assertEqual(self.enabled("b_files", "b_letter"), ["b_files", "b_letter"])
        self.app.copy_letter()
        self.assertEqual(self.app.clipboard_get(), "Dear team,")

    def test_actions_start_the_right_run(self):
        self.pick("b-2")
        self.app.act("applied")
        self.assertEqual(self.run_bot.call_args.args[0], ["--job", "b-2", "applied"])
        self.app.act("cv")
        self.assertEqual(self.run_bot.call_args.args[0], ["--job", "b-2", "cv"])

    def test_draft_without_gmail_offers_a_cv_instead(self):
        self.pick("a-1")
        with mock.patch.object(gui.messagebox, "askyesnocancel", return_value=False):  # No: make the CV
            self.app.act("draft")
        self.assertEqual(self.run_bot.call_args.args[0], ["--job", "a-1", "cv"])

    def test_no_key_opens_the_key_window_not_a_run(self):
        self.write("config.json", {"keywords": ["SEO"]})
        with mock.patch.object(gui.App, "keys") as keys:
            self.app.auto_draft()
        keys.assert_called_once()
        self.run_bot.assert_not_called()

    def test_filter_is_saved(self):
        self.app.kw.set("SEO, Content Writer")
        self.app.region.set("Pakistan, South Asia")
        self.app.age.set("21")
        self.app.find_jobs()
        cfg = self.config()
        self.assertEqual((cfg["keywords"], cfg["my_region_words"], cfg["max_job_age_days"]),
                         (["SEO", "Content Writer"], ["Pakistan", "South Asia"], 21))
        self.assertEqual(cfg["gemini_api_key"], "AIza-test")  # the keys are kept
        self.assertEqual(self.run_bot.call_args.args[0], ["--dry-run"])

    def test_job_type_fills_keywords(self):
        self.app.types["Finance / Accounting"].set(True)
        self.app.use_preset()
        self.assertTrue(self.app.kw.get().startswith("Accountant, Bookkeeper"))
        self.assertTrue(self.app.title_only.get())
        self.assertEqual(self.app.preset.get(), "Finance / Accounting")

    def test_bad_filter_is_refused(self):
        self.app.kw.set(" , ")
        self.app.find_jobs()
        self.app.age.set("abc")
        self.app.kw.set("SEO")
        self.app.find_jobs()
        self.run_bot.assert_not_called()

    def test_settings_check_ranges(self):
        self.app.settings()
        win = self.app.winfo_children()[-1]
        spins = [w for w in win.winfo_children()[0].winfo_children() if w.winfo_class() == "TSpinbox"]
        save = next(w for w in win.winfo_children()[0].winfo_children()[-1].winfo_children()
                    if w.cget("text") == "Save")
        spins[0].set("150")  # fit score above 100
        save.invoke()
        self.assertNotIn("min_fit_score", self.config())
        spins[0].set("70")
        save.invoke()
        self.assertEqual(self.config()["min_fit_score"], 70)

    def test_getting_started(self):
        self.app.tree.selection_set(())
        self.app.show_start()
        text = self.detail()
        self.assertIn("✔  Connect Gemini", text)
        self.assertIn("✔  Upload your CV  (Jane Doe)", text)
        self.assertIn("4.  Connect Gmail (optional)", text)

    def test_update_check(self):
        with mock.patch.object(gui, "latest_release", return_value="v9.0.0"), \
                mock.patch.object(gui.threading, "Thread") as thread:
            self.app.check_update()
            work = thread.call_args.kwargs["target"]
            work()
            self.app.update()
        self.assertEqual(self.app.update_btn.cget("text"), "⬆  Update to v9.0.0")
        self.assertGreater(gui.version_tuple("v1.10.0"), gui.version_tuple(bot.VERSION))


class LogLines(unittest.TestCase):
    def test_bot_lines_become_table_rows(self):
        pieces, is_row = gui.pretty("CANDIDATE [remotive] Acme | Backend Engineer | jobs@acme.io (https://x)")
        self.assertTrue(is_row)
        self.assertIn("READY", pieces[0][0])
        pieces, _ = gui.pretty("2026-10-29 16:41 | standalone dry-run | fetched 826 | candidates 0 | gemini 0 | "
                               "drafts 0")
        self.assertIn("826 jobs checked", pieces[0][0])
        self.assertEqual(gui.pretty("ERROR: boom")[0][0][1], "err")


if __name__ == "__main__":
    unittest.main()
