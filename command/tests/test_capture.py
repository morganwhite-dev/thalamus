import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture as C  # noqa

TZ = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 8, 10, 0, tzinfo=TZ)        # a Sunday
LISTS = ["Cloud Computing", "Network Security", "Internships", "Security Projects", "Personal", "Play", "General"]


def d(text):
    return C.detect(text, LISTS, NOW)


class TwoDays(unittest.TestCase):
    def test_tomorrow_and_wednesday(self):
        r = d("Remind me tomorrow and wednesday to study for exam 2 for network security")
        self.assertEqual(r["title"], "Study for exam 2")
        self.assertEqual(r["list"], "Network Security")
        self.assertTrue(r["due"].startswith("2026-11-09"))          # earliest day
        self.assertEqual(r["mode"], "reminder")                      # "remind me" on several days is texts, not a task
        self.assertEqual([x[:10] for x in r["extraDue"]], ["2026-11-11"])   # later day kept, not lost


class AlsoText(unittest.TestCase):
    def test_task_and_reminder(self):
        r = d("add lab 3 friday and remind me")
        self.assertEqual((r["mode"], r.get("alsoText"), r["title"]), ("task", True, "Lab 3"))
        self.assertFalse(d("add lab 3 friday").get("alsoText"))
        self.assertTrue(r["textAt"][0].endswith("09:00-05:00") or "T09:00" in r["textAt"][0])      # a day with no time: texts start at 9 AM
        self.assertIn("T15:00", d("add lab 3 friday at 3pm and remind me")["textAt"][0])          # a named time is kept


class Intent(unittest.TestCase):
    def test_tasks(self):
        for t in ["remind me to email Dr. Lee about the lab friday",
                  "I need to renew my ID",
                  "add buy groceries to my list",
                  "don't forget to call mom tomorrow",
                  "email Dr. Lee tomorrow",
                  "I have to finish the lab by friday at 5pm"]:
            self.assertIsNotNone(d(t), t)

    def test_not_tasks(self):
        for t in ["what's due friday?", "what should I do now", "how do I renew my ID", "summarize my week",
                  "is the lab due tomorrow", "email", "give me study tips", "", "tell me what to do tomorrow"]:
            self.assertIsNone(d(t), t)

    def test_plain_statement_without_trigger_is_not_captured(self):
        self.assertIsNone(d("the lab was hard"))
        self.assertIsNone(d("email drafts are in my inbox"))


class Dates(unittest.TestCase):
    def due(self, t):
        return d(t)["due"]

    def test_weekday_and_time(self):
        self.assertEqual(self.due("remind me to email Dr. Lee friday at 5pm"), "2026-11-13T17:00-05:00")

    def test_default_noon(self):
        self.assertEqual(self.due("remind me to call mom tomorrow"), "2026-11-09T12:00-05:00")

    def test_same_weekday_means_next_week(self):
        self.assertEqual(self.due("remind me to pay rent sunday"), "2026-11-15T12:00-05:00")

    def test_next_week_is_monday_and_in_days(self):
        self.assertEqual(self.due("remind me to plan next week")[:10], "2026-11-09")
        self.assertEqual(self.due("remind me to ship it in 3 days")[:10], "2026-11-11")

    def test_month_day_and_past_rolls_a_year(self):
        self.assertEqual(self.due("I need to register on nov 20")[:10], "2026-11-20")
        self.assertEqual(self.due("I need to file taxes on march 3")[:10], "2027-03-03")

    def test_no_date(self):
        self.assertIsNone(self.due("I need to renew my ID"))

    def test_bare_time_past_rolls_to_tomorrow(self):
        self.assertEqual(self.due("remind me to stretch at 9am")[:10], "2026-11-09")
        self.assertEqual(self.due("remind me to stretch at 3pm")[:10], "2026-11-08")


class TitleAndList(unittest.TestCase):
    def test_title_is_clean(self):
        p = d("remind me to email Dr. Lee about the lab friday at 5pm")
        self.assertEqual(p["title"], "Email Dr. Lee about the lab")

    def test_add_to_list_phrase_removed(self):
        self.assertEqual(d("add buy groceries to my list")["title"], "Buy groceries")

    def test_list_from_name(self):
        p = d("I need to finish the lab for network security by friday")
        self.assertEqual(p["list"], "Network Security")
        self.assertEqual(p["title"], "Finish the lab")

    def test_list_from_keywords(self):
        self.assertEqual(d("remind me to apply to Acme tomorrow")["list"], "Internships")
        self.assertEqual(d("remind me to email Dr. Lee")["list"], "Personal")

    def test_unknown_list_asks(self):
        p = d("I need to organize my desk")
        self.assertIsNone(p["list"])
        self.assertEqual(p["lists"], LISTS)

    def test_never_invents_a_list(self):
        self.assertNotIn(d("remind me to call the dentist")["list"], ["Health"])


class SectorDefault(unittest.TestCase):
    """A task typed inside an open sector joins that sector's list unless the words name a list."""

    def test_personal_sector_fills_personal_list(self):
        d = C.detect("remind me to finish the report Friday", LISTS, NOW, sector="personal")
        self.assertEqual(d["list"], "Personal")
        self.assertEqual(d["why"], "the sector you're in")

    def test_words_naming_a_list_still_win(self):
        d = C.detect("remind me to finish the cloud computing lab Friday", LISTS, NOW, sector="personal")
        self.assertEqual(d["list"], "Cloud Computing")

    def test_without_a_sector_nothing_changes(self):
        d = C.detect("remind me to finish the report Friday", LISTS, NOW)
        self.assertIsNone(d["list"])

    def test_schoolwork_has_no_default(self):
        d = C.detect("remind me to finish the report Friday", LISTS, NOW, sector="school")
        self.assertIsNone(d["list"])

    def test_play_files_into_play(self):
        d = C.detect("remind me to finish the report Friday", LISTS, NOW, sector="play")
        self.assertEqual(d["list"], "Play")

    def test_bare_statement_in_open_sector_is_a_task(self):
        d = C.detect("bandit wargame levels 0-10", LISTS, NOW, sector="play")
        self.assertEqual((d["title"], d["list"]), ("Bandit wargame levels 0-10", "Play"))
        self.assertIsNone(C.detect("bandit wargame levels 0-10", LISTS, NOW))
        self.assertIsNone(C.detect("what's due friday?", LISTS, NOW, sector="play"))
        for sec in ("school", "intern", "personal", "security", "play"):      # every open sector, not just one
            self.assertIsNotNone(C.detect("read the new lab notes", LISTS, NOW, sector=sec), sec)
            self.assertIsNone(C.detect("what is due friday?", LISTS, NOW, sector=sec), sec)


if __name__ == "__main__":
    unittest.main()


class ProjectPhrase(unittest.TestCase):
    def test_project_goes_to_play_not_a_model(self):
        d = C.detect("do giannas bday python project", ["Play", "Personal"])
        self.assertEqual(d["list"], "Play")
        d = C.detect("do giannas bday python project", ["Play", "Side Projects"])
        self.assertEqual(d["list"], "Side Projects")
        self.assertIsNone(C.detect("what is my python project", ["Play"]))


class Wording(unittest.TestCase):
    def test_morgans_phrases(self):
        lists = ["Play", "Personal", "Network Security", "Internships"]
        d = C.detect("add make a network anlayzer to side projects", lists)
        self.assertEqual((d["title"], d["list"]), ("Make a network anlayzer", "Play"))
        d = C.detect("finish module 6 notes for network security", lists)
        self.assertEqual(d["list"], "Network Security")
        d = C.detect("apply to wells fargo by 12/24", lists)
        self.assertEqual(d["list"], "Internships")
        self.assertTrue(d["due"].startswith("2026-12-24") or d["due"][5:10] == "12-24")


class StudyPlan(unittest.TestCase):
    def test_plan_with_items(self):
        d = C.detect("study plan for tryhackme: Pre Security, Linux Fundamentals Part 1, Nmap", LISTS, NOW)
        self.assertEqual((d["title"], d["habit"]["label"], d["plan"]), ("Tryhackme", "daily", ["Pre Security", "Linux Fundamentals Part 1", "Nmap"]))

    def test_other_shapes(self):
        d = C.detect("make a tryhackme study plan every weekday for 30 minutes: 1. Pre Security 2. Nmap", LISTS, NOW)
        self.assertEqual((d["habit"]["label"], d["habit"]["minutes"], d["plan"]), ("weekdays", 30, ["Pre Security", "Nmap"]))
        self.assertEqual(C.detect("network security final plan:\nch 1\nch 2", LISTS, NOW)["plan"], ["ch 1", "ch 2"])
        self.assertEqual(C.detect("make me a study plan for golf", LISTS, NOW)["plan"], [])

    def test_not_a_plan(self):
        for s in ["plan for friday", "i need a plan", "what's my plan for today?", "make a plan for the weekend"]:
            self.assertFalse((C.detect(s, LISTS, NOW) or {}).get("plan"), s)
