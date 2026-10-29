"""Tests for the parts of bot.py and cv.py that need no network: run with  python -m unittest"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402
import cv  # noqa: E402

PROFILE = {
    "name": "Jane Doe", "default_title": "Software Engineer | C# | React",
    "contact": {"email": "jane@example.com"}, "location": "Lahore, Pakistan", "years": "5+",
    "default_summary": "Software engineer with 5+ years of C# and React. Builds REST APIs on Azure.",
    "experience": [{"id": "acme", "company": "Acme", "place": "Remote", "title": "Software Engineer",
                    "dates": "2021 - now", "bullets": ["Built REST APIs with C# for 20K users.",
                                                       "Wrote React dashboards."]}],
    "projects": [{"id": "shop", "name": "Shop", "text": "A small store in React."}],
    "skills": {"Backend": ["C#", "REST APIs"], "Frontend": ["React"]},
    "education": "BSc Computer Science",
}


def job(**kw):
    now = dt.datetime.now(dt.timezone.utc)
    return {"source": "remotive", "id": "x-1", "title": "Software Engineer", "company": "Acme",
            "url": "https://example.com/job", "location": "Worldwide", "text": "We hire anywhere.",
            "date": now - dt.timedelta(days=1), **kw}


class ParseDate(unittest.TestCase):
    def test_seconds_and_milliseconds(self):
        self.assertEqual(bot.parse_date(1761400000), bot.parse_date(1761400000000))
        self.assertEqual(bot.parse_date("1761400000000").year, 2025)

    def test_out_of_range_is_no_date_not_a_crash(self):
        self.assertIsNone(bot.parse_date(10 ** 20))

    def test_text_dates(self):
        self.assertEqual(bot.parse_date("2026-10-01").day, 1)
        self.assertEqual(bot.parse_date("Mon, 20 Oct 2026 10:00:00 +0000").day, 20)
        self.assertIsNone(bot.parse_date("not a date"))
        self.assertIsNone(bot.parse_date(""))


class Keywords(unittest.TestCase):
    def matches(self, keyword, title):
        return bot.Matcher([keyword])(title)

    def test_job_words_and_ranks(self):
        self.assertTrue(self.matches("remote SEO expert jobs", "SEO Specialist"))
        self.assertTrue(self.matches("seo", "Search Engine Optimization Lead"))
        self.assertTrue(self.matches("Account Manager", "Senior Account Manager"))

    def test_typos_and_word_forms(self):
        self.assertTrue(self.matches("seo speciliest", "SEO Specialist"))
        self.assertTrue(self.matches("recruiter", "Recruiting Coordinator"))

    def test_no_false_friends(self):
        self.assertFalse(self.matches("accountant", "Account Executive"))
        self.assertFalse(self.matches("marketing", "Markets Analyst"))

    def test_symbols(self):
        self.assertTrue(self.matches(".NET", "Senior .NET Developer"))
        self.assertTrue(self.matches("C#", "C# Engineer"))
        self.assertFalse(self.matches("C#", "C++ Engineer"))


class Prefilter(unittest.TestCase):
    def setUp(self):
        bot.apply_filters(dict(bot.DEFAULT_CONFIG, keywords=["Software Engineer"], worldwide_only=False))
        self.now = dt.datetime.now(dt.timezone.utc)

    def test_remote_board_with_a_country_is_remote(self):
        self.assertIsNone(bot.prefilter(job(source="himalayas", location="Philippines"), self.now))

    def test_hn_post_must_say_remote(self):
        self.assertEqual(bot.prefilter(job(source="hn", location="Berlin | onsite", text="Berlin office"),
                                       self.now), "not remote")

    def test_worldwide_only(self):
        bot.apply_filters(dict(bot.DEFAULT_CONFIG, keywords=["Software Engineer"], my_region_words=["Pakistan"]))
        self.assertEqual(bot.prefilter(job(location="USA", text="US only"), self.now),
                         "location/work-auth restricted")
        self.assertIsNone(bot.prefilter(job(location="Pakistan"), self.now))

    def test_too_old_and_no_date(self):
        self.assertEqual(bot.prefilter(job(date=self.now - dt.timedelta(days=60)), self.now), "too old")
        self.assertEqual(bot.prefilter(job(date=None), self.now), "no post date")

    def test_years_asked(self):
        self.assertEqual(bot.years_asked("You have 5+ years of C# experience."), [5])
        self.assertEqual(bot.years_asked("A company with over 30+ years of experience in gaming."), [])
        self.assertEqual(bot.years_asked("We have been in business for 12 years."), [])


class Emails(unittest.TestCase):
    def test_finds_plain_and_obfuscated(self):
        found = bot.find_emails_in_text("Send your CV to jobs@acme.io or careers [at] acme [dot] com.")
        self.assertIn("jobs@acme.io", found)
        self.assertIn("careers@acme.com", found)

    def test_skips_no_reply_and_department_addresses(self):
        self.assertEqual(bot.find_emails_in_text("noreply@acme.io support@acme.io"), [])


class CheckTailor(unittest.TestCase):
    def setUp(self):
        self.profile = bot.normalise_profile(json.loads(json.dumps(PROFILE)))
        self.job = "We need C++ and forensic data recovery skills. Kubernetes a plus."

    def test_drops_only_the_bad_sentence(self):
        t = {"title": "Software Engineer | C#",
             "summary": "Software engineer with 5+ years building REST APIs in C#. "
                        "Experienced in forensic recovery tooling. Builds React dashboards for 20K users."}
        bot.check_tailor(t, self.profile, self.job)
        self.assertNotIn("forensic", t["summary"])
        self.assertIn("REST APIs in C#", t["summary"])

    def test_falls_back_when_nothing_is_left(self):
        t = {"title": "C++ Engineer | Kubernetes", "summary": "Expert in forensic recovery with Kubernetes."}
        bot.check_tailor(t, self.profile, self.job)
        self.assertEqual(t["title"], PROFILE["default_title"])
        self.assertEqual(t["summary"], PROFILE["default_summary"])

    def test_rewrites_that_add_facts_are_dropped(self):
        t = {"rewrites": {"acme": {"0": "Built REST APIs with C# and Kubernetes.", "1": "Wrote React dashboards.",
                                   "9": "Out of range."}, "nobody": {"0": "x"}}}
        bot.check_tailor(t, self.profile, self.job)
        self.assertEqual(t["rewrites"], {"acme": {"1": "Wrote React dashboards."}})


class Profile(unittest.TestCase):
    def test_missing_fields_are_filled(self):
        p = bot.normalise_profile({"name": "Ali", "experience": [{"company": "X Ltd", "bullets": ["Did a thing"]}],
                                   "skills": {"Tools": "Excel, Word"}, "projects": [{"name": "Site"}]})
        self.assertEqual(p["experience"][0]["id"], "x-ltd")
        self.assertEqual(p["skills"]["Tools"], ["Excel", "Word"])
        self.assertEqual(p["projects"][0]["id"], "site")
        self.assertEqual(p["contact"], {})

    def test_no_experience_is_allowed(self):
        self.assertEqual(bot.normalise_profile({"name": "Student"})["experience"], [])

    def test_no_name_is_an_error(self):
        with self.assertRaises(RuntimeError):
            bot.normalise_profile({"experience": []})


class Config(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(bot, "HERE", self.dir.name)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.dir.cleanup()

    def write(self, text):
        with open(os.path.join(self.dir.name, "config.json"), "w", encoding="utf-8") as f:
            f.write(text)

    def test_hand_edited_numbers(self):
        self.write('{"max_drafts_per_run": "5", "min_fit_score": "", "gemini_api_key": " AIza1 "}')
        cfg = bot.load_config()
        self.assertEqual((cfg["max_drafts_per_run"], cfg["min_fit_score"]), (5, 60))
        self.assertEqual(cfg["gemini_api_key"], "AIza1")

    def test_broken_json_says_so(self):
        self.write('{"gemini_api_key": "x",}')
        with self.assertRaisesRegex(RuntimeError, "not valid JSON"):
            bot.load_config()

    def test_gmail_is_optional(self):
        self.write('{"gemini_api_key": "AIza1"}')
        cfg = bot.load_config()
        bot.check_config(cfg)  # making CVs needs only Gemini
        self.assertFalse(bot.has_gmail(cfg))
        with self.assertRaisesRegex(RuntimeError, "Gmail is not connected"):
            bot.check_config(cfg, gmail=True)

    def test_no_gemini_key(self):
        self.write('{"gemini_api_key": "PUT-GEMINI-API-KEY-HERE"}')
        with self.assertRaisesRegex(RuntimeError, "Gemini is not connected"):
            bot.check_config(bot.load_config())


class Files(unittest.TestCase):
    def test_two_roles_at_one_company_get_two_files(self):
        self.assertNotEqual(bot.job_slug("Acme", "Backend Engineer"), bot.job_slug("Acme", "Frontend Engineer"))
        self.assertEqual(bot.letter_of("Jane-CV-acme-dev.pdf"), "Jane-Cover-Letter-acme-dev.pdf")

    def test_cv_files(self):
        with tempfile.TemporaryDirectory() as d:
            doc = os.path.join(d, "cv.doc")
            open(doc, "wb").close()
            with self.assertRaisesRegex(RuntimeError, "Save As"):
                bot.read_cv_file(doc)
            docx = os.path.join(d, "cv.docx")
            with zipfile.ZipFile(docx, "w") as z:
                z.writestr("word/document.xml", "<w:p><w:t>Jane</w:t><w:tab/><w:t>Doe</w:t></w:p>"
                                                "<w:p><w:t>C# &amp; SQL</w:t></w:p>")
            self.assertEqual(bot.read_cv_file(docx), ("Jane\tDoe\nC# & SQL\n", None))
            png = os.path.join(d, "cv.png")
            open(png, "wb").close()
            self.assertEqual(bot.read_cv_file(png)[1][0], "image/png")


class CvHtml(unittest.TestCase):
    def test_tailored_cv(self):
        page = cv.build(PROFILE, {"summary": "Tailored.", "bullets": {"acme": ["1", 0, "x", 7]},
                                  "rewrites": {"acme": {"1": "Wrote React dashboards for ops."}},
                                  "skills_first": ["React"], "projects": ["shop", "missing"]})
        self.assertLess(page.index("Wrote React dashboards for ops."), page.index("Built REST APIs"))
        self.assertIn("Tailored.", page)
        self.assertIn("<b>Shop</b>", page)

    def test_no_experience_shows_projects(self):
        page = cv.build({"name": "Student", "projects": PROFILE["projects"], "skills": {"Tools": "Excel, Word"}}, {})
        self.assertNotIn("EXPERIENCE", page)
        self.assertIn("PROJECTS", page)
        self.assertIn("Excel, Word", page)

    def test_letter(self):
        page = cv.build_letter(PROFILE, {"company": "Acme", "role": "Dev", "text": "Dear team,\n\nHello <b>."})
        self.assertIn("Re: Dev", page)
        self.assertIn("Hello &lt;b&gt;.", page)


if __name__ == "__main__":
    unittest.main()
