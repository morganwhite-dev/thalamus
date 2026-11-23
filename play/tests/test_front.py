import sys, unittest
from datetime import datetime, timezone
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(R / "play"), str(R / "engine")]
import play as P

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)


class Front(unittest.TestCase):
    def test_front_newest_first_and_unfront(self):
        st = P.apply(P.empty(), "front", NOW, id="a")
        st = P.apply(st, "front", NOW, id="b")
        st = P.apply(st, "front", NOW, id="a")          # pinning again moves it to the front, no duplicate
        self.assertEqual(st["front"], ["a", "b"])
        self.assertEqual(P.apply(st, "unfront", NOW, id="a")["front"], ["b"])

    def test_cap_and_offer_refused(self):
        st = P.empty()
        for i in "abcd":
            st = P.apply(st, "front", NOW, id=i)
        with self.assertRaises(ValueError):
            P.apply(st, "front", NOW, id="e")
        with self.assertRaises(ValueError):
            P.apply(P.empty(), "front", NOW, id="offer:x")

    def test_drop_clears_front(self):
        st = P.apply(P.empty(), "park", NOW, text="thing")
        pid = st["projects"][0]["id"]
        st = P.apply(st, "front", NOW, id=pid)
        self.assertEqual(P.apply(st, "dropproject", NOW, id=pid)["front"], [])

    def test_old_state_files_load(self):
        self.assertEqual(P.apply({"parking": [], "leftOff": {}}, "front", NOW, id="a")["front"], ["a"])


class StudyPlan(unittest.TestCase):
    def mk(self):
        st = P.apply(P.empty(), "addhabit", NOW, title="Tryhackme", plan="Pre Security; Linux Fundamentals\n3. Nmap")
        return st, st["habits"][0]["id"]

    def row(self, st, when=NOW):
        return P.habit_rows(st, when)[0]

    def test_pick_stays_day_after_day_until_it_is_done(self):
        st, hid = self.mk()
        first = self.row(st)["planToday"]
        for d in (13, 14, 20):
            self.assertEqual(self.row(st, NOW.replace(day=d))["planToday"], first)
        st = P.apply(st, "habitdone", NOW, id=hid)
        nxt = self.row(st, NOW.replace(day=13))["planToday"]
        self.assertNotEqual(nxt, first)
        self.assertEqual(self.row(st, NOW.replace(day=19))["planToday"], nxt)    # and that one stays until it is done

    def test_pick_is_one_of_the_items_and_stable_all_day(self):
        st, hid = self.mk()
        r = self.row(st)
        self.assertEqual(r["title"], "Tryhackme: " + r["planToday"])
        self.assertIn(r["planToday"], ["Pre Security", "Linux Fundamentals", "Nmap"])
        later = NOW.replace(hour=22)
        self.assertEqual(self.row(st, later)["planToday"], r["planToday"])
        st = P.apply(st, "planadd", NOW, id=hid, items="Wireshark; OSINT; Burp; XSS; SQLi")    # adding items never changes today's pick
        self.assertEqual(self.row(st)["planToday"], r["planToday"])

    def test_done_removes_it_from_the_cycle_for_good(self):
        st, hid = self.mk()
        first = self.row(st)["planToday"]
        st = P.apply(st, "habitdone", NOW, id=hid)
        st = P.apply(st, "habitdone", NOW, id=hid)                 # a second tap does not finish another item
        r = self.row(st)
        self.assertEqual((r["planDone"], r["planToday"]), (1, first))
        seen = set()
        day = NOW
        for _ in range(3):
            day = day.replace(day=day.day + 1)
            seen.add(self.row(st, day)["planToday"])
        self.assertNotIn(first, seen)

    def test_cycle_finishes_each_item_once(self):
        st, hid = self.mk()
        done = []
        day = NOW
        for _ in range(3):
            done.append(self.row(st, day)["planToday"])
            st = P.apply(st, "habitdone", day, id=hid)
            day = day.replace(day=day.day + 1)
        self.assertEqual(sorted(done), ["Linux Fundamentals", "Nmap", "Pre Security"])
        r = self.row(st, day)
        self.assertEqual((r["planToday"], r["title"], r["planDone"]), (None, "Tryhackme", 3))

    def test_undo_gives_the_item_back(self):
        st, hid = self.mk()
        first = self.row(st)["planToday"]
        st = P.apply(P.apply(st, "habitdone", NOW, id=hid), "habitundo", NOW, id=hid)
        r = self.row(st)
        self.assertEqual((r["planDone"], r["planToday"]), (0, first))

    def test_pick_another_changes_today_but_loses_nothing(self):
        st, hid = self.mk()
        first = self.row(st)["planToday"]
        st = P.apply(st, "planskip", NOW, id=hid)
        r = self.row(st)
        self.assertNotEqual(r["planToday"], first)
        self.assertEqual(r["planTotal"], 3)

    def test_existing_habit_gets_the_plan_without_a_second_reminder(self):
        st = P.apply(P.empty(), "addhabit", NOW, title="Tryhackme")
        st = P.apply(st, "addhabit", NOW, title="tryhackme", plan=["Nmap", "nmap", "Burp"])
        self.assertEqual((len(st["habits"]), [i["t"] for i in st["habits"][0]["plan"]]), (1, ["Nmap", "Burp"]))

    def test_add_remove(self):
        st, hid = self.mk()
        st = P.apply(st, "planadd", NOW, id=hid, items="Wireshark\nOSINT")
        st = P.apply(st, "planremove", NOW, id=hid, index=0)
        self.assertEqual(len(st["habits"][0]["plan"]), 4)
        with self.assertRaises(ValueError):
            P.apply(st, "planadd", NOW, id=hid, items="  ")

    def test_plain_habit_unchanged(self):
        st = P.apply(P.empty(), "addhabit", NOW, title="Stretch")
        r = P.habit_rows(st, NOW)[0]
        self.assertEqual((r["title"], "plan" in r), ("Stretch", False))


if __name__ == "__main__":
    unittest.main()
