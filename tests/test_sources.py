"""Job sources and matching: each parser with a saved sample answer from the site, so no network is needed."""
import datetime as dt
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402

NOW = dt.datetime.now(dt.timezone.utc)


def score(keyword, title, text=None):
    return bot.Matcher([keyword]).score(title, text)


class Matching(unittest.TestCase):
    def test_words_written_together_or_apart(self):
        for title in ("Full Stack Developer", "Senior Full-stack Engineer", "Fullstack Dev"):
            self.assertEqual(score("fullstack", title), bot.STRONG, title)
        self.assertEqual(score("Full Stack Developer", "Fullstack Developer"), bot.STRONG)
        self.assertEqual(score("front end", "Frontend Engineer"), bot.STRONG)
        self.assertEqual(score("e-commerce", "Ecommerce Manager"), bot.STRONG)
        self.assertEqual(score("wordpress", "Word Press Developer"), bot.STRONG)

    def test_partial_matches(self):
        self.assertEqual(score("React Developer", "Frontend Engineer (React)"), bot.PARTIAL)
        self.assertEqual(score("Full Stack Developer", "Full-Stack Engineer"), bot.PARTIAL)
        self.assertEqual(score("Kubernetes", "Platform Engineer", "You run Kubernetes clusters."), bot.PARTIAL)

    def test_no_match(self):
        self.assertEqual(score("fullstack", "Full Time Accountant"), 0)
        self.assertEqual(score("front end", "Front Desk Agent"), 0)
        self.assertEqual(score("React Developer", "Python Developer"), 0)  # "developer" alone is not enough
        self.assertEqual(score("Kubernetes", "Platform Engineer", None), 0)  # title only
        self.assertEqual(score("Entity Framework", "Manager, Legal Entity Governance"), 0)  # one name, not "entity"
        self.assertEqual(score(".NET", "English Teacher", "Apply at https://nativecamp.net/apply"), 0)  # web address

    def test_dotnet(self):
        for keyword in (".NET", "dotnet", "dotnet dev", ".net developer"):
            self.assertEqual(score(keyword, "Senior .NET Developer"), bot.STRONG, keyword)
        self.assertEqual(score("dotnet dev", "Dotnet Developer"), bot.STRONG)
        self.assertEqual(score(".NET", "Backend Engineer", "We use C#, .NET 8 and Azure."), bot.PARTIAL)
        self.assertEqual(score("dotnet dev", "DevOps Engineer"), 0)

    def test_strength_is_recorded(self):
        bot.apply_filters(dict(bot.DEFAULT_CONFIG, keywords=["React Developer"], worldwide_only=False))
        job = dict(source="remotive", id="1", title="Frontend Engineer (React)", company="A", url="",
                   location="Remote", text="", date=NOW)
        self.assertIsNone(bot.prefilter(job, NOW))
        self.assertEqual(job["match"], "partial")


class Location(unittest.TestCase):
    def setUp(self):
        bot.apply_filters(dict(bot.DEFAULT_CONFIG, keywords=["Engineer"], my_region_words=["Pakistan"]))

    def check(self, **kw):
        job = dict(dict(source="remotive", id="1", title="Engineer", company="A", url="", location="Remote",
                        text="Join us.", date=NOW), **kw)
        return bot.prefilter(job, NOW), job.get("note", "")

    def test_unstated_location_is_kept_with_a_note(self):
        why, note = self.check()
        self.assertIsNone(why)
        self.assertIn("location not stated", note)

    def test_clear_answers(self):
        self.assertEqual(self.check(location="Worldwide"), (None, ""))
        self.assertEqual(self.check(location="Remote", text="We hire in Pakistan."), (None, ""))
        self.assertEqual(self.check(location="Germany")[0], "not open worldwide/to my region")
        self.assertEqual(self.check(source="hn", location="Acme | Remote (US) | Engineer")[0],
                         "not open worldwide/to my region")

    def test_company_pages_list_office_jobs_too(self):
        self.assertEqual(self.check(any_job=True, location="San Francisco, CA")[0], "on-site job")
        self.assertIsNone(self.check(any_job=True, location="Remote, Worldwide")[0])


class WorkTypeAndPlace(unittest.TestCase):
    """Remote / hybrid / on-site, and whether the job is open where you live or would go."""

    def use(self, **cfg):
        bot.apply_filters(dict(bot.DEFAULT_CONFIG, keywords=["Engineer"], my_region_words=["Pakistan"], **cfg))

    def check(self, **kw):
        job = dict(dict(source="greenhouse", id="1", title="Engineer", company="A", url="", location="Remote",
                        text="Join us.", date=NOW, any_job=True), **kw)
        return bot.prefilter(job, NOW), job.get("mode"), job.get("note", "")

    def test_work_type(self):
        self.use(work_modes=["remote", "hybrid", "onsite"], open_to="anywhere")
        self.assertEqual(self.check(location="Lahore, Pakistan")[1], "onsite")
        self.assertEqual(self.check(location="Berlin (Hybrid)")[1], "hybrid")
        self.assertEqual(self.check(location="Remote - EMEA")[1], "remote")
        self.assertEqual(self.check(location="London", mode="hybrid")[1], "hybrid")  # the site said so
        self.assertEqual(self.check(source="himalayas", any_job=False, location="Philippines")[1], "remote")

    def test_only_the_ticked_work_types(self):
        self.use(work_modes=["onsite"])
        self.assertEqual(self.check(location="Remote, Worldwide")[0], "remote job")
        self.assertIsNone(self.check(location="Karachi, Pakistan")[0])

    def test_office_job_in_my_country_or_with_a_visa(self):
        self.use(work_modes=["onsite", "hybrid"])
        self.assertIsNone(self.check(location="Islamabad, Pakistan")[0])
        self.assertEqual(self.check(location="Dubai, UAE")[0], "on-site outside my region")
        self.use(work_modes=["onsite"], visa_sponsorship=True)
        why, _, note = self.check(location="Berlin, Germany", text="We offer visa sponsorship and relocation support.")
        self.assertIsNone(why)
        self.assertIn("visa", note)
        self.assertEqual(self.check(location="Berlin", text="We cannot offer visa sponsorship.")[0],
                         "on-site outside my region")

    def test_countries_i_pick(self):
        self.use(work_modes=["remote", "onsite"], open_to="countries", target_countries=["UAE", "Germany"])
        self.assertIsNone(self.check(location="Dubai, UAE")[0])
        self.assertIsNone(self.check(source="himalayas", any_job=False, location="Germany")[0])
        self.assertIsNone(self.check(location="Remote, Worldwide")[0])
        self.assertEqual(self.check(location="Lahore, Pakistan")[0], "on-site outside my countries")
        self.assertEqual(self.check(source="himalayas", any_job=False, location="Canada")[0],
                         "not open worldwide/to my countries")

    def test_any_country(self):
        self.use(work_modes=["onsite"], open_to="anywhere")
        self.assertIsNone(self.check(location="Austin, TX")[0])

    def test_old_worldwide_only_setting(self):
        self.assertEqual(bot.open_to({"worldwide_only": False, "open_to": "me"}), "anywhere")
        self.assertEqual(bot.open_to({"worldwide_only": True}), "me")
        self.assertEqual(bot.open_to({}), "me")

    def test_described_for_google_and_gemini(self):
        cfg = dict(my_region_words=["Pakistan"], work_modes=["remote", "onsite"], visa_sponsorship=True)
        self.assertEqual(bot.wanted_jobs(cfg), "remote jobs open to people in Pakistan or worldwide, or on-site jobs "
                                               "in Pakistan or in other countries with visa sponsorship or relocation")
        self.assertEqual(bot.wanted_jobs(dict(open_to="anywhere", work_modes=["hybrid"])), "hybrid jobs")


def rss(*items):
    return "<rss><channel>" + "".join(f"<item>{i}</item>" for i in items) + "</channel></rss>"


class Parsers(unittest.TestCase):
    """Each source turns the site's answer into jobs with a title, company, link, date and text."""

    def run_source(self, src, answers):
        def fetch(url, as_json=False, **kw):
            for part, body in answers.items():
                if part in url:
                    return body
            raise AssertionError(f"unexpected request: {url}")
        with mock.patch.object(bot, "fetch", fetch):
            jobs = src()
        for j in jobs:
            for k in ("source", "id", "title", "company", "url", "location", "text", "date"):
                self.assertIn(k, j)
        return jobs

    def test_rss_boards(self):
        item = ("<title>Data Analyst at Acme</title><link>https://x.example/jobs/data-analyst-1</link>"
                "<description>&lt;p&gt;Use SQL &amp;amp; Python.&lt;/p&gt;</description>"
                "<pubDate>Thu, 29 Oct 2026 06:49:20 +0000</pubDate>")
        j = self.run_source(bot.src_remotefirstjobs, {"remotefirstjobs": rss(item)})[0]
        self.assertEqual((j["title"], j["company"], j["text"]), ("Data Analyst", "Acme", "Use SQL & Python."))
        self.assertEqual(j["date"].day, 29)
        cdata = item.replace("<description>&lt;p&gt;Use SQL &amp;amp; Python.&lt;/p&gt;</description>",
                             "<description><![CDATA[<p>Remote <b>anywhere</b></p>]]></description>")
        j = self.run_source(bot.src_realworkfromanywhere, {"realworkfromanywhere": rss(cdata)})[0]
        self.assertEqual((j["location"], j["text"]), ("Anywhere", "Remote anywhere"))

    def test_workew_company_from_link(self):
        item = ("<title>IT Support Specialist</title><link>https://workew.com/job/it-support-specialist-6sense/</link>"
                "<pubDate>Wed, 28 Oct 2026 05:55:10 +0000</pubDate><description><![CDATA[<p>Help users.</p>"
                "<p>The post IT Support appeared first on Workew.</p>]]></description>")
        j = self.run_source(bot.src_workew, {"workew": rss(item)})[0]
        self.assertEqual((j["company"], j["text"].strip()), ("6Sense", "Help users."))

    def test_jobicy_feed(self):
        item = ("<title>HR Partner</title><id>157809</id><link>https://jobicy.com/jobs/157809-hr</link>"
                "<pubDate>Thu, 29 Oct 2026 08:45:02 +0000</pubDate><job_listing:company><![CDATA[Thumbtack]]>"
                "</job_listing:company><job_listing:location><![CDATA[USA]]></job_listing:location>"
                "<content:encoded><![CDATA[<p>People work.</p>]]></content:encoded>")
        j = self.run_source(bot.src_jobicy_feed, {"jobicy": rss(item)})[0]
        self.assertEqual((j["id"], j["company"], j["location"]), ("jobicy-157809", "Thumbtack", "USA"))

    def test_4dayweek_keeps_remote_jobs_only(self):
        page = {"has_more": False, "jobs": [
            {"id_str": "a", "title": "Dev", "company_name": "W", "url": "https://4dw.example/a", "is_remote": True,
             "location_original": "Remote in Bengaluru (India)", "description": "**Code**", "posted": 1793106419},
            {"id_str": "b", "title": "Office", "is_remote": False}]}
        jobs = self.run_source(bot.src_4dayweek, {"4dayweek": page})
        self.assertEqual([j["id"] for j in jobs], ["4dayweek-a"])
        self.assertEqual(jobs[0]["date"].year, 2026)

    def test_company_career_pages(self):
        bot.apply_filters(dict(bot.DEFAULT_CONFIG, keywords=["Backend Engineer"]))
        gh = {"jobs": [{"id": 1, "title": "Backend Engineer", "company_name": "GitLab", "location": {"name": "Remote"},
                        "absolute_url": "https://gh.example/1", "first_published": "2026-10-20T10:00:00-04:00"},
                       {"id": 2, "title": "Chef", "location": {"name": "Remote"}, "updated_at": "2026-10-20T10:00:00Z"}]}
        answers = {"greenhouse.io/v1/boards/gitlab/jobs/1": {"content": "&lt;p&gt;Go &amp;amp; APIs&lt;/p&gt;"},
                   "greenhouse.io": gh,
                   "ashbyhq.com": {"jobs": [{"id": "x", "title": "SRE", "location": "Remote, Global", "isRemote": True,
                                             "jobUrl": "https://ashby.example/x", "descriptionPlain": "Ops",
                                             "publishedAt": "2026-10-01T00:00:00Z"}]},
                   "lever.co": [{"id": "y", "text": "Lead", "hostedUrl": "https://lever.example/y",
                                 "categories": {"location": "Singapore"}, "workplaceType": "remote",
                                 "createdAt": 1757626668528, "descriptionPlain": "Lead", "additionalPlain": ""}]}
        with mock.patch.object(bot, "BOARDS", [("greenhouse", "gitlab"), ("ashby", "supabase"), ("lever", "anchorage")]):
            jobs = {j["id"]: j for j in self.run_source(bot.src_companies, answers)}
        self.assertEqual(jobs["greenhouse-1"]["text"], "Go & APIs")  # read because the title matches
        self.assertEqual(jobs["greenhouse-2"]["text"], "")           # not read: saves a request
        self.assertEqual(jobs["ashby-x"]["location"], "Remote, Global, Remote")
        self.assertEqual(jobs["lever-y"]["date"].year, 2025)        # milliseconds
        self.assertEqual(jobs["lever-y"]["company"], "Anchorage")
        self.assertTrue(all(j["any_job"] for j in jobs.values()))

    def test_smartrecruiters(self):
        bot.apply_filters(dict(bot.DEFAULT_CONFIG, keywords=["Backend Engineer"]))
        page = {"totalFound": 2, "content": [
            {"id": "11", "name": "Backend Engineer", "company": {"name": "Wise"}, "releasedDate": "2026-11-20T10:00:00Z",
             "location": {"city": "London", "country": "gb", "remote": True}, "typeOfEmployment": {"label": "Full-time"}},
            {"id": "12", "name": "Backend Engineer", "company": {"name": "Wise"}, "releasedDate": "2026-11-20T10:00:00Z",
             "location": {"city": "Austin", "country": "us", "remote": False}}]}
        ad = {"postingUrl": "https://jobs.smartrecruiters.com/Wise/11-backend-engineer", "jobAd": {"sections": {
            "companyDescription": {"text": "About Wise"}, "jobDescription": {"text": "<p>Build APIs</p>"},
            "qualifications": {"text": "<ul><li>Go</li></ul>"}}}}
        jobs = self.run_source(lambda: bot.smartrecruiters_jobs("Wise"),
                               {"postings/11": ad, "smartrecruiters.com/v1/companies/Wise/postings?": page})
        remote, office = jobs
        self.assertEqual((remote["company"], remote["location"], remote["mode"]), ("Wise", "London, GB, Remote", "remote"))
        self.assertEqual(remote["text"], "Build APIs\n\nGo")       # the company blurb is left out
        self.assertEqual(remote["url"], ad["postingUrl"])
        self.assertEqual((office["mode"], office["text"]), ("onsite", ""))  # remote only: not read

    def test_country_boards(self):
        sweden = {"hits": [{"id": "31", "headline": "Python-utvecklare", "employer": {"name": "Acme AB"},
                            "webpage_url": "https://arbetsformedlingen.se/platsbanken/annonser/31",
                            "workplace_address": {"municipality": "Stockholm"}, "workplace_model": {"label": "Distans"},
                            "description": {"text": "Python och Django"}, "publication_date": "2026-11-23T10:00:00",
                            "application_details": {"email": "jobb@acme.se", "url": None}}]}
        bot.apply_filters(dict(bot.DEFAULT_CONFIG, keywords=["Python", "Django"]))
        jobs = self.run_source(bot.src_jobtech, {"jobtechdev.se": sweden})
        self.assertEqual(len(jobs), 1)                               # the same post under both keywords
        j = jobs[0]
        self.assertEqual((j["company"], j["location"], j["mode"]), ("Acme AB", "Stockholm, Sweden", "remote"))
        self.assertIn("jobb@acme.se", j["text"])                     # the email is used for a draft
        landing = [{"id": 5, "title": "Java Developer", "url": "https://landing.jobs/at/in-scale/java-developer",
                    "remote": True, "locations": [{"city": "Lisbon", "country_code": "PT"}],
                    "role_description": "<p>Spring</p>", "main_requirements": "<ul><li>Java</li></ul>",
                    "published_at": "2026-11-03T09:00:00Z", "gross_salary_low": 50000, "gross_salary_high": 60000,
                    "currency_code": "EUR", "tags": ["Java"]}]
        j = self.run_source(bot.src_landingjobs, {"landing.jobs": landing})[0]
        self.assertEqual((j["company"], j["location"], j["mode"]), ("In Scale", "Lisbon, PT, Remote", "remote"))
        self.assertEqual(j["salary"], "50k–60k EUR / year")

    def test_more_rss_boards(self):
        vue = ("<title>Senior Vue Developer</title><guid>https://vuejobs.com/jobs/acme-senior-vue-developer</guid>"
               "<description><![CDATA[<p><strong>Employer:</strong> Acme</p>\n<p><strong>Location:</strong> Remote (EU)</p>"
               "<p>Build the app</p>]]></description><pubDate>Mon, 23 Nov 2026 22:12:56 +0000</pubDate>")
        j = self.run_source(bot.src_vuejobs, {"vuejobs": rss(vue)})[0]
        self.assertEqual((j["company"], j["location"], j["text"]), ("Acme", "Remote (EU)", "Build the app"))
        presso = ("<title>Support Agent</title><link>https://jobspresso.co/job/support-agent-whatnot/</link>"
                  "<dc:creator><![CDATA[Whatnot<br>⚲\xa0United States]]></dc:creator>"
                  "<description>Help buyers</description><pubDate>Mon, 23 Nov 2026 21:12:50 +0000</pubDate>")
        j = self.run_source(bot.src_jobspresso, {"jobspresso": rss(presso)})[0]
        self.assertEqual((j["company"], j["location"]), ("Whatnot", "United States"))
        lara = ("<title>Laravel Developer</title><link>https://larajobs.com/job/39</link>"
                "<job:company>Acme</job:company><job:location>Remote</job:location><job:tags>Laravel,Vue</job:tags>"
                "<job:salary>$70k</job:salary><pubDate>Mon, 16 Nov 2026 16:51:21 +0000</pubDate>")
        j = self.run_source(bot.src_larajobs, {"larajobs": rss(lara)})[0]
        self.assertEqual((j["company"], j["salary"], j["text"]), ("Acme", "$70k", "Laravel, Vue"))


class Google(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [mock.patch.object(bot, "GOOGLE_CACHE", os.path.join(self.tmp.name, "google_cache.json")),
                        mock.patch("sys.stdout", new_callable=io.StringIO)]
        for p in self.patches:
            p.start()
        bot.apply_filters(dict(bot.DEFAULT_CONFIG, keywords=["SEO"], gemini_api_key="AIza-test",
                               my_region_words=["Pakistan"]))
        self.answer = {"_sites": ["linkedin.com", "acme.io"], "jobs": [
            {"title": "SEO Specialist", "company": "Acme", "url": "https://www.linkedin.com/jobs/view/1",
             "location": "Remote", "posted": "2026-10-28", "description": "Email cv@acme.io"},
            {"title": "SEO Lead", "company": "Beta", "url": "https://careers.acme.io/2", "posted": ""},
            {"title": "Made up", "company": "Nope", "url": "https://not-in-results.example/3"},
            {"title": "No link", "url": "not a url"}]}

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_keeps_only_links_google_returned_and_caches(self):
        with mock.patch.object(bot, "gemini", return_value=self.answer) as ask:
            jobs = bot.src_google()
            again = bot.src_google()
        self.assertEqual([j["title"] for j in jobs], ["SEO Specialist", "SEO Lead"])
        self.assertEqual(jobs[0]["date"].day, 28)
        self.assertIsNotNone(jobs[1]["date"])  # no date given: counted as found today
        self.assertEqual(ask.call_count, 1)    # the second search used the cache
        self.assertEqual(len(again), 2)
        prompt = ask.call_args.args[1]
        self.assertIn("open to people in Pakistan or worldwide", prompt)
        self.assertTrue(ask.call_args.kwargs["search"])

    def test_key_without_search_quota_is_left_alone_for_a_day(self):
        with mock.patch.object(bot, "gemini", side_effect=RuntimeError(bot.NO_SEARCH)) as ask:
            for _ in range(2):  # a plain note, not an error, and Gemini is asked only once a day
                with self.assertRaisesRegex(bot.SourceSkipped, "needs billing"):
                    bot.src_google()
        self.assertEqual(ask.call_count, 1)

    def test_off_without_key_or_when_unticked(self):
        bot.apply_filters(dict(bot.DEFAULT_CONFIG, keywords=["SEO"], gemini_api_key=""))
        self.assertEqual(bot.src_google(), [])
        bot.apply_filters(dict(bot.DEFAULT_CONFIG, keywords=["SEO"], gemini_api_key="AIza", search_google=False))
        self.assertEqual(bot.src_google(), [])


if __name__ == "__main__":
    unittest.main()
