"""What the window does (backend.py), on a temporary folder. No run, browser, dialog or window is started."""
import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backend  # noqa: E402
import bot  # noqa: E402
from test_bot import PROFILE  # noqa: E402

JOBS = [
    {"id": "a-1", "status": "ready", "why": "", "title": "Backend Engineer", "company": "Acme", "source": "remotive",
     "location": "Worldwide", "date": "2026-10-28T10:00:00+00:00", "text": "C# APIs", "url": "https://a.example/1",
     "email": "jobs@acme.example", "email_src": "https://a.example/1", "match": "strong"},
    {"id": "b-2", "status": "apply on site", "why": "no published email", "title": "SEO Specialist",
     "company": "Beta", "source": "himalayas", "location": "Pakistan", "date": "2026-10-27T10:00:00+00:00",
     "text": "SEO", "url": "https://b.example/2", "email": "", "salary": "40k USD", "match": "partial"},
    {"id": "c-3", "status": "rejected", "why": "too old", "title": "Designer", "company": "Gamma",
     "source": "jobicy", "location": "USA", "date": "2026-08-01T10:00:00+00:00", "text": "Figma",
     "url": "https://c.example/3", "email": ""},
]
FILTER = {"keywords": "SEO", "exclude": "", "maxAge": 14, "modes": ["remote"], "openTo": "me", "region": "Pakistan",
          "countries": "", "visa": False, "google": True, "titleOnly": False, "jobTypes": [], "presetKeywords": ""}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.dir = self.tmp.name
        self.stack = contextlib.ExitStack()
        for mod, names in ((backend, dict(HERE=d, CONFIG="config.json", PROFILE="profile.json", JOBS_FILE="jobs.json",
                                          TRACKER="tracker.csv", LOCK="bot.lock", UI_PREFS="ui.json")),
                           (bot, dict(HERE=d, GEMINI_STATE="gemini_state.json", TRACKER="tracker.csv", RUNS_LOG="runs.log",
                                      USAGE_FILE="usage.json"))):
            for k, v in names.items():
                self.stack.enter_context(mock.patch.object(mod, k, v if k == "HERE" else os.path.join(d, v)))
        self.popen = self.stack.enter_context(mock.patch.object(backend.subprocess, "Popen"))
        self.popen.return_value.stdout = []
        self.popen.return_value.wait.return_value = 0
        self.popen.return_value.returncode = 0
        self.stack.enter_context(mock.patch.object(backend.Api, "autorun_state", return_value=None))
        self.stack.enter_context(mock.patch.object(backend.threading, "Thread"))  # no reader threads
        self.write("config.json", {"gemini_api_key": "AIza-test", "keywords": ["SEO"], "my_region_words": ["Pakistan"]})
        self.write("profile.json", PROFILE)
        self.write("jobs.json", {"updated": "2026-10-29 10:00", "jobs": JOBS})
        self.api = backend.Api()

    def tearDown(self):
        self.stack.close()
        self.tmp.cleanup()

    def write(self, name, data):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def config(self):
        with open(os.path.join(self.dir, "config.json"), encoding="utf-8") as f:
            return json.load(f)

    def started(self):
        """The bot options of the last run started, or None."""
        if not self.popen.call_args:
            return None
        return self.popen.call_args.args[0][len(backend.BOT):]

    def finish(self):
        self.api._proc = None


class Window(Base):
    def test_bootstrap_has_everything_to_draw(self):
        b = self.api.bootstrap()
        self.assertEqual(b["version"], bot.VERSION)
        self.assertEqual(b["filter"]["keywords"], "SEO")
        self.assertEqual(b["profile"]["name"], "Jane Doe")
        self.assertIn("Software / .NET", b["presets"])
        self.assertEqual([v["value"] for v in b["views"]], ["ready", "site", "matches", "done", "all"])
        json.dumps(b)  # all of it crosses to the page as JSON

    def test_lists_matches_with_counts(self):
        r = self.api.jobs("matches")
        self.assertEqual([j["id"] for j in r["rows"]], ["a-1", "b-2"])  # strong match first; rejected hidden
        self.assertEqual((r["total"], r["ready"], r["site"]), (3, 1, 1))
        self.assertEqual(len(self.api.jobs("all")["rows"]), 3)
        self.assertEqual([j["id"] for j in self.api.jobs("all", "pakistan")["rows"]], ["b-2"])
        self.assertEqual([j["id"] for j in self.api.jobs("matches", "", "company", True)["rows"]], ["b-2", "a-1"])
        self.assertNotIn("text", r["rows"][0])  # long texts come one job at a time

    def test_no_matches_gives_advice(self):
        self.write("jobs.json", {"updated": "x", "jobs": [JOBS[2]]})
        r = self.api.jobs("matches")
        self.assertEqual(r["rows"], [])
        self.assertTrue(r["hint"])

    def test_few_matches_say_what_to_loosen(self):
        old = dict(JOBS[2], why="too old", match="strong")
        far = dict(JOBS[2], id="d-4", why="not open worldwide/to my region", match="partial")
        self.write("jobs.json", {"updated": "x", "jobs": [old, far]})
        hint = self.api.jobs("matches")["hint"]
        self.assertIn("1 more are older than", hint)
        self.assertIn("1 more are limited to other countries", hint)

    def test_job_detail(self):
        j = self.api.job("a-1")
        self.assertEqual((j["email"], j["link"], j["cv"], j["letterText"]), ("jobs@acme.example", "https://a.example/1",
                                                                            "", False))
        self.assertIsNone(self.api.job("nope"))

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
        j = self.api.job("a-1")
        self.assertTrue(j["cv"].endswith("Jane-CV-acme.pdf"))
        self.assertTrue(j["letterText"])
        self.assertTrue(self.api.jobs("matches")["rows"][0]["hasCv"])
        self.assertEqual(self.api.cover_letter("a-1"), "Dear team,")
        self.assertIsNone(self.api.cover_letter("b-2"))

    def test_actions_start_the_right_run(self):
        self.assertTrue(self.api.job_action("b-2", "applied")["ok"])
        self.assertEqual(self.started(), ["--job", "b-2", "applied"])
        self.assertEqual(self.api._sent[-1], {"kind": "run", "data": {"state": "start",
                                                                      "what": "Marking Beta as applied"}})
        self.assertIn("already in progress", self.api.job_action("b-2", "cv")["error"])
        self.finish()
        self.api.job_action("b-2", "cv")
        self.assertEqual(self.started(), ["--job", "b-2", "cv"])
        self.finish()
        self.assertIn("no longer in the list", self.api.job_action("gone", "cv")["error"])

    def test_draft_without_gmail_asks_for_gmail(self):
        self.assertEqual(self.api.job_action("a-1", "draft"), {"need": "gmail"})
        self.assertIsNone(self.started())

    def test_no_key_asks_for_the_key_not_a_run(self):
        self.write("config.json", {"keywords": ["SEO"]})
        self.assertEqual(self.api.auto_draft(FILTER), {"need": "gemini"})
        self.assertEqual(self.api.import_cv(os.path.join(self.dir, "profile.json")), {"need": "gemini"})
        self.assertIsNone(self.started())

    def test_no_profile_asks_for_the_cv(self):
        os.remove(os.path.join(self.dir, "profile.json"))
        self.assertEqual(self.api.job_action("b-2", "cv"), {"need": "profile"})

    def test_filter_is_saved(self):
        f = dict(FILTER, keywords="SEO, Content Writer", region="Pakistan, South Asia", maxAge=21)
        self.assertTrue(self.api.find_jobs(f)["ok"])
        cfg = self.config()
        self.assertEqual((cfg["keywords"], cfg["my_region_words"], cfg["max_job_age_days"]),
                         (["SEO", "Content Writer"], ["Pakistan", "South Asia"], 21))
        self.assertEqual(cfg["gemini_api_key"], "AIza-test")  # the keys are kept
        self.assertEqual(self.started(), ["--dry-run"])

    def test_work_type_and_countries_are_saved(self):
        f = dict(FILTER, modes=["remote", "onsite"], openTo="countries")
        self.assertEqual(self.api.find_jobs(f)["field"], "countries")  # says so instead of searching
        self.assertIsNone(self.started())
        self.api.find_jobs(dict(f, countries="UAE, Germany", visa=True))
        cfg = self.config()
        self.assertEqual((cfg["work_modes"], cfg["open_to"], cfg["target_countries"], cfg["visa_sponsorship"]),
                         (["remote", "onsite"], "countries", ["UAE", "Germany"], True))
        self.assertNotIn("worldwide_only", cfg)

    def test_job_type_fills_keywords(self):
        r = self.api.job_types(["Finance / Accounting"])
        self.assertTrue(r["keywords"].startswith("Accountant, Bookkeeper"))
        self.assertTrue(r["titleOnly"])
        self.api.save_filter(dict(FILTER, keywords=r["keywords"], jobTypes=["Finance / Accounting"]))
        self.assertEqual(self.config()["job_types"], ["Finance / Accounting"])
        self.assertEqual(self.api.filter_state()["jobTypes"], ["Finance / Accounting"])
        self.api.save_filter(dict(FILTER, keywords="Accountant", jobTypes=["Finance / Accounting"]))
        self.assertEqual(self.config()["job_types"], [])  # own keywords: no longer the job type

    def test_bad_filter_is_refused(self):
        self.assertEqual(self.api.find_jobs(dict(FILTER, keywords=" , "))["field"], "keywords")
        self.assertEqual(self.api.find_jobs(dict(FILTER, maxAge="abc"))["field"], "maxAge")
        self.assertEqual(self.api.find_jobs(dict(FILTER, modes=[]))["field"], "modes")
        self.assertEqual(self.api.find_jobs(dict(FILTER, modes=["onsite"], region=""))["field"], "region")
        self.assertIsNone(self.started())

    def test_settings_check_ranges(self):
        values = {s["key"]: s["value"] for s in self.api.settings()}
        self.assertEqual(self.api.save_settings(dict(values, min_fit_score=150))["field"], "min_fit_score")
        self.assertNotIn("min_fit_score", self.config())
        self.assertTrue(self.api.save_settings(dict(values, min_fit_score="70"))["ok"])
        self.assertEqual(self.config()["min_fit_score"], 70)

    def test_keys_are_tested_before_saving(self):
        self.assertIn("Paste", self.api.test_keys({})["error"])
        self.assertIn("both", self.api.test_keys({"gemini_api_key": "k", "gmail_address": "a@b.c"})["error"])
        with mock.patch.object(backend, "test_gemini", return_value=None):
            self.assertEqual(self.api.test_keys({"gemini_api_key": "k"}), {"errors": {"gemini_api_key": None}})
        r = self.api.save_keys({"gemini_api_key": "AIza-new", "gmail_address": "me@gmail.com",
                                "gmail_app_password": "abcd efgh"})
        self.assertTrue(r["setup"][3]["done"])
        self.assertEqual(self.config()["gemini_api_key"], "AIza-new")

    def test_getting_started(self):
        steps = {s["id"]: s for s in self.api.setup()}
        self.assertTrue(steps["gemini"]["done"])
        self.assertEqual(steps["cv"]["title"], "Upload your CV  (Jane Doe)")
        self.assertTrue(steps["find"]["done"])
        self.assertFalse(steps["gmail"]["done"])

    def test_prefs(self):
        self.assertEqual(self.api.prefs(), {"sounds": True, "theme": "auto"})
        self.api.set_prefs({"sounds": False, "theme": "nonsense", "other": 1})
        self.assertEqual(self.api.prefs(), {"sounds": False, "theme": "auto"})
        self.api.set_prefs({"theme": "light"})
        self.assertEqual(self.api.prefs()["theme"], "light")

    def test_diagnostics_hide_email_addresses(self):
        with open(bot.RUNS_LOG, "w", encoding="utf-8") as f:
            f.write("2026-11-24 | drafts 1 | sent to jobs@acme.example\n")
        d = self.api.diagnostics()
        self.assertNotIn("acme.example", d["runs"])
        self.assertEqual(d["version"], bot.VERSION)

    def test_open_path_only_inside_the_data_folder(self):
        inside = os.path.join(self.dir, "cvs", "a.pdf")
        os.makedirs(os.path.dirname(inside))
        open(inside, "wb").close()
        with mock.patch.object(backend.os, "startfile", create=True) as start:
            self.assertTrue(self.api.open_path(inside))
            self.assertFalse(self.api.open_path(os.path.join(os.path.dirname(self.dir), "x.pdf")))
            self.assertFalse(self.api.open_path(None))
        start.assert_called_once()

    def test_run_output_reaches_the_window(self):
        proc = mock.Mock(stdout=["src_remotive (Remotive): 4 jobs\n", "CANDIDATE [remotive] Acme | Dev | a@b.c\n",
                                 "2026-11-24 02:29 | standalone dry-run | fetched 4 | candidates 1 | gemini 0 | "
                                 "drafts 0\n"], returncode=0)
        self.api._proc = proc
        self.api._read(proc, "Searching")
        logs = [e for ev in self.api._sent if ev["kind"] == "log" for e in ev["data"]]
        self.assertEqual([e["type"] for e in logs], ["source", "job", "summary"])
        end = self.api._sent[-1]["data"]
        self.assertEqual((end["state"], end["code"], end["summary"]["candidates"]), ("end", 0, 1))
        self.assertIsNone(self.api._proc)

    def test_update_check(self):
        with mock.patch.object(backend, "latest_release", return_value="v9.0.0"):
            r = self.api.check_update()
        self.assertTrue(r["newer"])
        with mock.patch.object(backend, "latest_release", return_value=None):
            self.assertFalse(self.api.check_update()["reachable"])
        self.assertGreater(backend.version_tuple("v1.10.0"), backend.version_tuple("1.9.9"))

    def test_one_click_update(self):
        window = mock.Mock()
        self.api._window = window
        with mock.patch.object(backend, "FROZEN", True), \
                mock.patch.object(backend, "download_setup", return_value="C:\\t\\JobHunterSetup-update.exe"), \
                mock.patch.object(backend.time, "sleep"):
            self.assertEqual(self.api.update_now(), {"state": "downloading"})
            backend.threading.Thread.call_args.kwargs["target"]()
        args = self.popen.call_args.args[0]
        self.assertEqual(args[0], "C:\\t\\JobHunterSetup-update.exe")
        self.assertIn("/SILENT", args)
        self.assertIn("/UPDATE", args)  # the installer opens Job Hunter again
        window.destroy.assert_called_once()

    def test_update_from_source_opens_the_download_page(self):
        with mock.patch.object(backend, "FROZEN", False), mock.patch.object(backend.webbrowser, "open") as browser:
            self.assertEqual(self.api.update_now(), {"state": "source"})
        browser.assert_called_once_with(backend.DOWNLOAD_PAGE)

    def test_update_download_must_be_an_installer(self):
        class Answer(io.BytesIO):
            headers = {"Content-Length": "12"}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch.object(backend.urllib.request, "urlopen", return_value=Answer(b"<html>404</h")), \
                mock.patch.object(backend.tempfile, "gettempdir", return_value=self.dir):
            with self.assertRaises(ValueError):
                backend.download_setup(lambda pct: None)


class UsagePing(Base):
    def urlopen(self, fail=False):
        sent = []

        class Answer:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"monthly": 1240}'

        def fake(req, timeout=None):
            if fail:
                raise OSError("offline")
            sent.append(req)
            return Answer()
        return sent, mock.patch.object(bot.urllib.request, "urlopen", fake)

    def test_once_a_day_with_only_an_id_and_the_version(self):
        sent, patch = self.urlopen()
        with patch:
            self.assertTrue(bot.ping_usage())
            self.assertFalse(bot.ping_usage())  # already counted today
        self.assertEqual(len(sent), 1)
        body = json.loads(sent[0].data)
        self.assertEqual(set(body), {"id", "version"})
        self.assertRegex(body["id"], r"^[0-9a-f]{32}$")
        self.assertTrue(sent[0].full_url.endswith("/ping"))

    def test_can_be_turned_off(self):
        self.api.set_usage_stats(False)
        self.assertFalse(self.api.bootstrap()["usageStats"])
        sent, patch = self.urlopen()
        with patch:
            self.assertFalse(bot.ping_usage())
        self.assertEqual(sent, [])

    def test_offline_tries_again_later(self):
        _, patch = self.urlopen(fail=True)
        with patch:
            self.assertFalse(bot.ping_usage())
        sent, patch = self.urlopen()
        with patch:
            self.assertTrue(bot.ping_usage())

    def test_user_count_for_the_about_box(self):
        _, patch = self.urlopen()
        with patch:
            self.assertEqual(self.api.users(), 1240)
        _, patch = self.urlopen(fail=True)
        with patch:
            self.assertIsNone(self.api.users())


class LogLines(unittest.TestCase):
    def test_bot_lines_become_structured_entries(self):
        e = backend.parse_line("CANDIDATE [remotive] Acme | Backend Engineer | jobs@acme.io (https://x)")
        self.assertEqual((e["type"], e["status"], e["company"], e["link"]), ("job", "READY", "Acme", "jobs@acme.io"))
        e = backend.parse_line("2026-10-29 16:41 | standalone dry-run | fetched 826 | candidates 0 | gemini 0 | "
                               "drafts 0")
        self.assertEqual((e["type"], e["dry"], e["fetched"]), ("summary", True, 826))
        e = backend.parse_line("ERROR: boom")
        self.assertEqual((e["tone"], e["text"]), ("error", "boom"))
        e = backend.parse_line("skip Acme: eligible=True fit=40 not senior enough")
        self.assertEqual((e["status"], e["reason"]), ("NOT A FIT", "not senior enough"))

    def test_source_lines_use_readable_names_and_hide_technical_details(self):
        e = backend.parse_line("src_weworkremotely (We Work Remotely): 218 jobs")
        self.assertEqual((e["name"], e["count"], e["state"]), ("We Work Remotely", 218, "ok"))
        e = backend.parse_line("NOT SEARCHED src_remoteok (RemoteOK): the site is having problems on its side right "
                               "now. The other sites were searched as usual. [details: HTTPError: HTTP Error 502]")
        self.assertEqual((e["name"], e["state"]), ("RemoteOK", "failed"))
        self.assertNotIn("HTTP", e["note"])
        e = backend.parse_line("SKIPPED src_google (Google Search): free Gemini keys cannot use Google Search")
        self.assertEqual(e["state"], "skipped")
        e = backend.parse_line("2026-11-24 02:29 | standalone dry-run | fetched 10 | candidates 0 | gemini 0 | "
                               "drafts 0 | RemoteOK not searched (the site is having problems on its side right now)")
        self.assertEqual(e["notes"], ["RemoteOK not searched (the site is having problems on its side right now)"])

    def test_saved_files_become_links(self):
        e = backend.parse_line(r"CV saved: C:\Users\me\AppData\Roaming\Job Hunter\cvs\Jane-CV-acme.pdf")
        self.assertEqual((e["tone"], e["files"]), ("good", [r"C:\Users\me\AppData\Roaming\Job Hunter\cvs\Jane-CV-acme.pdf"]))


if __name__ == "__main__":
    unittest.main()
