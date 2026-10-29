"""End-to-end flows of bot.py with the network, Gemini, Edge and Gmail replaced by stand-ins.
Every file goes to a temporary folder, never to your real tracker, jobs or CVs."""
import contextlib
import csv
import datetime as dt
import email
import email.policy
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402
from test_bot import PROFILE  # noqa: E402

GOOD = {"eligible": True, "reason": "Good fit.", "fit_score": 85,
        "tailor": {"title": "Software Engineer | C#", "summary": "Software engineer building REST APIs in C# for "
                                                                 "20K users, with React dashboards on top.",
                   "skills_first": ["C#"], "bullets": {"acme": [1, 0]}, "projects": ["shop"]},
        "subject": "Application: Backend Engineer – Jane Doe", "body": "Hello team,\n\nMy CV is attached.",
        "cover_letter": "Dear team,\n\nI build REST APIs in C#.\n\nSincerely,\nJane Doe"}


def posting(n, **kw):
    return {"source": "remotive", "id": f"remotive-{n}", "title": f"Backend Engineer {n}", "company": f"Co{n}",
            "url": f"https://example.com/{n}", "location": "Worldwide",
            "text": f"Remote, worldwide. C# and REST APIs. Email your CV to jobs@co{n}.example.",
            "date": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1), **kw}


class Sandbox(unittest.TestCase):
    """Points every bot.py file at a temporary folder and stubs out the outside world."""
    gmail = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.dir = self.tmp.name
        paths = dict(HERE=d, TRACKER=os.path.join(d, "tracker.csv"), JOBS_FILE=os.path.join(d, "jobs.json"),
                     RUNS_LOG=os.path.join(d, "runs.log"), LOCK=os.path.join(d, "bot.lock"),
                     GEMINI_STATE=os.path.join(d, "gemini_state.json"),
                     REMOTIVE_CACHE=os.path.join(d, "remotive_cache.json"))
        self.stack = contextlib.ExitStack()
        for k, v in paths.items():
            self.stack.enter_context(mock.patch.object(bot, k, v))
        self.write("profile.json", PROFILE)
        cfg = {"gemini_api_key": "AIza-test", "keywords": ["Backend Engineer"], "worldwide_only": True}
        if self.gmail:
            cfg.update(gmail_address="me@gmail.com", gmail_app_password="abcd efgh ijkl mnop")
        self.write("config.json", cfg)
        self.answer = dict(GOOD)
        self.gemini = self.stack.enter_context(mock.patch.object(bot, "gemini", side_effect=lambda *a, **k: json.loads(
            json.dumps(self.answer))))
        self.stack.enter_context(mock.patch.object(bot, "run_cv_py", side_effect=self.fake_pdf))
        self.draft = self.stack.enter_context(mock.patch.object(bot, "save_draft"))
        self.out = self.stack.enter_context(mock.patch("sys.stdout", new_callable=io.StringIO))

    def tearDown(self):
        self.stack.close()
        self.tmp.cleanup()

    def write(self, name, data):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f) if not isinstance(data, str) else f.write(data)

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as f:
            return f.read()

    def fake_pdf(self, data, json_path, pdf, *flags):
        os.makedirs(os.path.dirname(pdf), exist_ok=True)
        open(pdf, "wb").close()
        return pdf

    def tracker(self):
        with open(bot.TRACKER, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def jobs(self):
        return {j["id"]: j for j in bot.load_jobs()["jobs"]}

    def run_main(self, *args, jobs=()):
        def source():
            return [dict(j) for j in jobs]
        with mock.patch.object(bot, "SOURCES", [source]), mock.patch.object(bot, "careers_page_email",
                                                                         return_value=(None, None)), \
                mock.patch.object(sys, "argv", ["bot.py", *args]):
            bot.main()
        return self.out.getvalue()


class FullRun(Sandbox):
    def test_drafts_best_matches_and_records_them(self):
        log = self.run_main(jobs=[posting(1), posting(2)])
        self.assertEqual(self.draft.call_count, 2)
        to, subject, body, pdf = self.draft.call_args_list[0].args[1:]
        self.assertEqual(to, "jobs@co1.example")
        self.assertTrue(pdf.endswith("Jane-Doe-CV-co1-backend-engineer-1.pdf"))
        self.assertEqual([r["status"] for r in self.tracker()], ["draft-attached"] * 2)
        self.assertEqual(self.jobs()["remotive-1"]["why"], "drafted")
        self.assertIn("drafts 2", self.read("runs.log"))
        self.assertIn("DRAFT saved: Co1 -> jobs@co1.example (fit 85)", log)

    def test_same_job_on_two_boards_is_handled_once(self):
        self.run_main(jobs=[posting(1), posting(1, source="remoteok", id="remoteok-9")])
        self.assertEqual(self.draft.call_count, 1)

    def test_run_limit_and_already_done(self):
        self.write("config.json", {**json.loads(self.read("config.json")), "max_drafts_per_run": 1})
        self.run_main(jobs=[posting(1), posting(2)])
        self.run_main(jobs=[posting(1), posting(2)])
        self.assertEqual([c.args[1] for c in self.draft.call_args_list], ["jobs@co1.example", "jobs@co2.example"])

    def test_daily_limit_counts_drafts_not_skips(self):
        today = dt.date.today().isoformat()
        with open(bot.TRACKER, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "company", "role", "email", "poster", "post_url", "cv_file", "draft_id", "status"])
            for i in range(25):
                w.writerow([today, f"Old{i}", "r", "", "", f"u{i}", "", f"x{i}", "skipped: low fit"])
        self.run_main(jobs=[posting(1)])
        self.assertEqual(self.draft.call_count, 1)

    def test_low_fit_is_skipped_and_recorded(self):
        self.answer.update(fit_score=30, reason="Needs Go.")
        log = self.run_main(jobs=[posting(1)])
        self.draft.assert_not_called()
        self.assertEqual(self.tracker()[0]["status"], "skipped: Needs Go.")
        self.assertEqual(self.jobs()["remotive-1"]["why"], "skipped by Gemini")
        self.assertIn("skip Co1: eligible=True fit=30 Needs Go.", log)

    def test_garbage_answer_does_not_crash(self):
        self.answer = ["not", "a", "dict"]
        self.run_main(jobs=[posting(1)])
        self.draft.assert_not_called()
        self.assertTrue(self.tracker()[0]["status"].startswith("skipped"))

    def test_no_model_left_stops_the_run(self):
        self.gemini.side_effect = RuntimeError(f"{bot.NO_MODEL}: every free model is out of quota.")
        self.run_main(jobs=[posting(1), posting(2)])
        self.assertEqual(self.gemini.call_count, 1)
        self.assertIn("out of quota", self.read("runs.log"))

    def test_search_only_needs_no_keys_or_profile(self):
        os.remove(os.path.join(self.dir, "profile.json"))
        self.write("config.json", {"keywords": ["Backend Engineer"]})
        self.run_main("--dry-run", jobs=[posting(1)])
        self.gemini.assert_not_called()
        self.assertEqual(self.jobs()["remotive-1"]["status"], bot.STATUS_READY)
        self.assertIn("dry-run | fetched 1 | candidates 1", self.read("runs.log"))

    def test_a_crashing_source_is_noted_and_the_rest_still_run(self):
        def broken():
            raise ValueError("bad JSON")
        with mock.patch.object(bot, "SOURCES", [broken, lambda: [posting(1)]]), \
                mock.patch.object(sys, "argv", ["bot.py", "--dry-run"]):
            bot.main()
        self.assertIn("broken failed (ValueError)", self.read("runs.log"))
        self.assertIn("remotive-1", self.jobs())

    def test_busy_lock_refuses_a_second_run(self):
        with open(bot.LOCK, "w") as f:
            f.write(str(os.getpid()))  # this process is alive
        log = self.run_main(jobs=[posting(1)])
        self.assertIn("Another run is in progress", log)
        os.remove(bot.LOCK)

    def test_lock_of_a_dead_run_is_taken_over(self):
        with open(bot.LOCK, "w") as f:
            f.write("999999")
        self.run_main(jobs=[posting(1)])
        self.assertEqual(self.draft.call_count, 1)
        self.assertFalse(os.path.exists(bot.LOCK))


class NoGmail(Sandbox):
    gmail = False

    def test_auto_run_makes_files_instead_of_drafts(self):
        log = self.run_main(jobs=[posting(1)])
        self.draft.assert_not_called()
        self.assertIn("Gmail is not connected", log)
        cvs = sorted(os.listdir(os.path.join(self.dir, "cvs")))
        self.assertEqual(cvs, ["Jane-Doe-CV-co1-backend-engineer-1-email.txt",
                               "Jane-Doe-CV-co1-backend-engineer-1.pdf",
                               "Jane-Doe-Cover-Letter-co1-backend-engineer-1.pdf",
                               "Jane-Doe-Cover-Letter-co1-backend-engineer-1.txt"])
        self.assertIn("To: jobs@co1.example", self.read("cvs/Jane-Doe-CV-co1-backend-engineer-1-email.txt"))
        self.assertEqual(self.tracker()[0]["status"], "cv-made")
        self.assertEqual(self.jobs()["remotive-1"]["why"], "CV made")

    def test_draft_button_says_gmail_is_needed(self):
        self.run_main("--dry-run", jobs=[posting(1)])
        with mock.patch.object(sys, "argv", ["bot.py", "--job", "remotive-1", "draft"]):
            bot.main()
        self.assertIn("Gmail is not connected", self.out.getvalue())
        self.gemini.assert_not_called()

    def test_cv_button_and_pasted_job_work(self):
        self.run_main("--dry-run", jobs=[posting(1)])
        with mock.patch.object(sys, "argv", ["bot.py", "--job", "remotive-1", "cv"]):
            bot.main()
        self.assertEqual(self.jobs()["remotive-1"]["why"], "CV made")
        self.write("pasted.json", {"company": "Pasted Inc", "title": "Dev", "text": "Mail cv@pasted.example now."})
        with mock.patch.object(sys, "argv", ["bot.py", "--custom", os.path.join(self.dir, "pasted.json")]):
            bot.main()
        self.assertEqual(self.tracker()[-1]["email"], "cv@pasted.example")
        self.assertIn("Cover letter saved", self.out.getvalue())


class JobButtons(Sandbox):
    def setUp(self):
        super().setUp()
        self.run_main("--dry-run", jobs=[posting(1), posting(2)])

    def act(self, job_id, mode):
        with mock.patch.object(sys, "argv", ["bot.py", "--job", job_id, mode]):
            bot.main()

    def test_skip_and_applied(self):
        self.act("remotive-1", "skip")
        self.act("remotive-2", "applied")
        self.assertEqual([r["status"] for r in self.tracker()], ["skipped: by you", "applied"])
        self.assertEqual(self.jobs()["remotive-2"]["why"], "applied by you")
        self.gemini.assert_not_called()

    def test_draft_one_job(self):
        self.act("remotive-2", "draft")
        self.assertEqual(self.draft.call_args.args[1], "jobs@co2.example")
        self.assertEqual(self.jobs()["remotive-2"]["why"], "drafted")

    def test_unknown_job(self):
        self.act("gone-1", "draft")
        self.assertIn("no longer in jobs.json", self.out.getvalue())

    def test_no_gemini_key(self):
        self.write("config.json", {"keywords": ["Backend Engineer"]})
        self.act("remotive-1", "cv")
        self.assertIn("Gemini is not connected", self.out.getvalue())


class ImportCv(Sandbox):
    def cv_file(self):
        path = os.path.join(self.dir, "my cv.txt")
        self.write("my cv.txt", "Jane Doe\nSoftware Engineer\n" + "Built things with C#. " * 20)
        return path

    def run_import(self, answer):
        self.gemini.side_effect = lambda *a, **k: answer
        with mock.patch.object(sys, "argv", ["bot.py", "--import-cv", self.cv_file()]):
            bot.main()
        return self.out.getvalue()

    def test_imports_and_keeps_a_backup(self):
        new = {"name": "Jane Doe", "experience": [{"company": "Acme", "bullets": ["A", " "]},
                                                  {"company": "Acme", "bullets": ["B"]}],
               "projects": [{"name": "X Y"}], "skills": {"Tools": ["Git"], "Empty": []}}
        log = self.run_import(new)
        p = bot.load_profile()
        self.assertEqual([e["id"] for e in p["experience"]], ["acme", "acme-2"])
        self.assertEqual(p["experience"][0]["bullets"], ["A"])
        self.assertEqual(p["contact"]["email"], "jane@example.com")  # kept from the old profile
        self.assertTrue(any(f.startswith("profile.backup-") for f in os.listdir(self.dir)))
        self.assertIn("Profile saved: Jane Doe | 2 roles", log)

    def test_student_cv_and_broken_old_profile(self):
        self.write("profile.json", "{broken")
        log = self.run_import({"name": "Sam Student", "education": "BSc", "projects": [{"name": "App"}]})
        self.assertIn("No work experience found", log)
        self.assertEqual(bot.load_profile()["name"], "Sam Student")

    def test_not_a_cv(self):
        log = self.run_import({"something": "else"})
        self.assertIn("ERROR: Gemini could not find your name", log)
        self.assertEqual(bot.load_profile()["name"], "Jane Doe")  # the old profile is untouched


class GeminiFallback(unittest.TestCase):
    """bot.gemini(): free-quota handling across models, with Google's API replaced."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "gemini_state.json")
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(mock.patch.object(bot, "GEMINI_STATE", self.state))
        self.stack.enter_context(mock.patch("sys.stdout", new_callable=io.StringIO))
        self.stack.enter_context(mock.patch("time.sleep"))
        self.cfg = dict(bot.DEFAULT_CONFIG, gemini_api_key="AIza-test", gemini_model="")
        bot.save_gemini_state({"key": bot.key_id("AIza-test"), "listed": 9e12,
                               "models": ["gemini-flash-latest", "gemini-2.5-flash", "gemma-3-27b-it"]})

    def tearDown(self):
        self.stack.close()
        self.tmp.cleanup()

    def reply(self, model_answers):
        """urlopen stand-in: model name -> HTTP code, or a dict answer."""
        calls = []

        def urlopen(req, timeout=None):
            model = req.full_url.rsplit("/", 1)[-1].split(":")[0]
            calls.append(model)
            got = model_answers[model]
            if isinstance(got, int):
                body = {"error": {"message": "limit: 0" if got == 429 else "nope", "details": [
                    {"violations": [{"quotaId": "PerDay"}]}] if got == 429 else []}}
                raise urllib.error.HTTPError(req.full_url, got, "err", {}, io.BytesIO(json.dumps(body).encode()))
            text = json.dumps(got)
            resp = mock.MagicMock()
            resp.__enter__.return_value.read.return_value = json.dumps(
                {"candidates": [{"content": {"parts": [{"text": f"```json\n{text}\n```"}]}}]}).encode()
            return resp
        return calls, mock.patch("urllib.request.urlopen", urlopen)

    def test_out_of_quota_moves_to_the_next_model_and_remembers(self):
        calls, patch = self.reply({"gemini-flash-latest": 429, "gemini-2.5-flash": {"ok": 1}})
        with patch:
            self.assertEqual(bot.gemini(self.cfg, "hi"), {"ok": 1})
            self.assertEqual(bot.gemini(self.cfg, "hi"), {"ok": 1})
        self.assertEqual(calls, ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-flash"])
        state = bot.gemini_state()
        self.assertEqual(state["why"]["gemini-flash-latest"], "no free tier for your key")
        self.assertEqual(state["usage"]["gemini-2.5-flash"]["calls"], 2)
        self.assertTrue(bot.model_status(state, "gemini-2.5-flash")[0])

    def test_refused_key_stops_at_once(self):
        calls, patch = self.reply({"gemini-flash-latest": 403})
        with patch, self.assertRaisesRegex(RuntimeError, "refused this Gemini key"):
            bot.gemini(self.cfg, "hi")
        self.assertEqual(calls, ["gemini-flash-latest"])

    def test_every_model_blocked(self):
        calls, patch = self.reply({m: 429 for m in ("gemini-flash-latest", "gemini-2.5-flash", "gemma-3-27b-it")})
        with patch, self.assertRaisesRegex(RuntimeError, bot.NO_MODEL):
            bot.gemini(self.cfg, "hi")
        with patch, self.assertRaisesRegex(RuntimeError, "every free model is out of quota"):
            bot.gemini(self.cfg, "hi")
        self.assertEqual(len(calls), 3)  # the second call asked nobody

    def test_files_never_go_to_gemma(self):
        calls, patch = self.reply({"gemini-flash-latest": 404, "gemini-2.5-flash": 500, "gemma-3-27b-it": {"x": 1}})
        with patch, self.assertRaises(RuntimeError):
            bot.gemini(self.cfg, "read this", attach=("application/pdf", b"%PDF"))
        self.assertNotIn("gemma-3-27b-it", calls)


class GmailDraft(unittest.TestCase):
    def test_draft_goes_to_the_drafts_folder_with_the_cv(self):
        with tempfile.TemporaryDirectory() as d:
            pdf = os.path.join(d, "cv.pdf")
            with open(pdf, "wb") as f:
                f.write(b"%PDF-1.4")
            imap = mock.MagicMock()
            imap.list.return_value = ("OK", [b'(\\HasNoChildren \\Drafts) "/" "[Gmail]/Drafts"'])
            imap.append.return_value = ("OK", [b"done"])
            with mock.patch("imaplib.IMAP4_SSL", return_value=imap) as conn, \
                    mock.patch.object(bot, "load_profile", return_value=PROFILE):
                bot.save_draft({"gmail_address": "me@gmail.com", "gmail_app_password": "ab cd",
                                "imap_host": "imap.gmail.com"}, "jobs@acme.io", "Subject", "Body", pdf)
        conn.assert_called_once_with("imap.gmail.com", timeout=60)
        imap.login.assert_called_once_with("me@gmail.com", "abcd")
        folder, flags, _, raw = imap.append.call_args.args
        self.assertEqual((folder, flags), ('"[Gmail]/Drafts"', "\\Draft"))
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        self.assertEqual((msg["To"], msg["Subject"]), ("jobs@acme.io", "Subject"))
        self.assertEqual([p.get_filename() for p in msg.iter_attachments()], ["Jane-Doe-CV.pdf"])
        imap.logout.assert_called_once()


if __name__ == "__main__":
    unittest.main()
