import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(R / "play"), str(R / "engine")]
import json, play as P
from brain_engine import category_for

CFG = json.loads((R / "engine" / "config.json").read_text())
NOW = datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)
T = lambda i, t, l, **k: {"id": i, "title": t, "list": l, **k}
TASKS = [T("g", "Golf range", "Play", estimatedMinutes=45), T("n", "Traffic analyzer", "Side Projects"), T("e", "Send email", "Personal")]
REC = {"dayLoad": {"level": "light", "freeMinutes": 600, "plannedMinutes": 60}, "current": {"band": "undated", "dueDate": None}, "queue": []}


class T_(unittest.TestCase):
    def off(self, rec=REC, st=None, phase="idle", tasks=TASKS):
        return P.offer(rec, tasks, st or P.empty(), CFG, category_for, phase, NOW)

    def test_park_unpark_and_limits(self):
        st = P.apply(P.empty(), "park", NOW, text="  try   scapy  ")
        # an idea is a side project that has not started (2026-11-12): "park" makes one, the parking lot stays empty
        self.assertEqual((st["projects"][0]["title"], st["projects"][0]["state"], st["parking"]), ("try scapy", "idea", []))
        self.assertEqual(P.empty()["projects"], [])         # input state untouched
        st2 = P.apply(st, "dropproject", NOW, id=st["projects"][0]["id"])
        self.assertEqual(st2["projects"], [])
        with self.assertRaises(ValueError): P.apply(st, "park", NOW, text="  ")
        with self.assertRaises(ValueError): P.apply(st, "dropproject", NOW, id="zzz")
        self.assertEqual(len(P.apply(P.empty(), "park", NOW, text="x" * 500)["projects"][0]["title"]), P.MAX_LINE)

    def test_old_parked_ideas_become_projects_on_load(self):
        import json, tempfile
        d = Path(tempfile.mkdtemp()) / "play.json"
        d.write_text(json.dumps({"parking": [{"id": "p1", "text": "idea one", "at": "2026-11-10T10:00:00-05:00"},
                                             {"id": "p2", "text": "idea two", "at": "2026-11-10T11:00:00-05:00"}]}))
        st = P.load(d)
        self.assertEqual([(p["title"], p["state"]) for p in st["projects"]], [("idea one", "idea"), ("idea two", "idea")])
        self.assertEqual(len({p["id"] for p in st["projects"]}), 2)
        self.assertEqual(st["parking"], [])
        self.assertEqual(json.loads(d.read_text())["parking"], [])      # saved, so it only happens once
        self.assertEqual(len(P.load(d)["projects"]), 2)

    def test_leftoff_set_and_clear(self):
        st = P.apply(P.empty(), "leftoff", NOW, taskId="n", text="stopped at the pcap parser")
        self.assertEqual(st["leftOff"]["n"]["text"], "stopped at the pcap parser")
        self.assertNotIn("n", P.apply(st, "leftoff", NOW, taskId="n", text="")["leftOff"])

    def test_personal_errands_are_not_play(self):
        v = P.view(P.empty(), TASKS, CFG, category_for, None)
        self.assertEqual({i["taskId"] for i in v["items"]}, {"n"})      # golf is offer-only, never listed

    def test_offer_only_on_light_idle_days(self):
        self.assertIsNotNone(self.off())
        self.assertIsNone(self.off(phase="work"))
        normal = {**REC, "dayLoad": {"level": "normal", "freeMinutes": 600, "plannedMinutes": 300}}
        self.assertEqual(self.off(rec=normal, tasks=[T("n", "Traffic analyzer", "Side Projects")])["taskId"], "generic:golf")   # a project needs a light day; only golf passes
        self.assertIsNone(self.off(rec={**REC, "current": {"band": "escalated", "dueDate": None}}))
        soon = (NOW + timedelta(hours=5)).isoformat()
        self.assertIsNone(self.off(rec={**REC, "queue": [{"band": "dated", "dueDate": soon}]}))
        o = self.off(tasks=[T("e", "Send email", "Personal")])     # no Play items: only the generic game offer
        self.assertEqual(o["taskId"], "generic:game")

    def test_offer_prefers_longest_untouched_and_shows_left_off(self):
        st = P.apply(P.empty(), "leftoff", NOW, taskId="g", text="at hole 4")
        o = self.off(st=st)
        self.assertEqual(o["taskId"], "n")                   # g was touched, n never
        st2 = P.apply(P.apply(P.empty(), "leftoff", NOW, taskId="n", text="parser"), "leftoff", NOW + timedelta(days=1), taskId="g", text="at hole 4")
        o2 = self.off(st=st2, tasks=[t for t in TASKS if t["id"] != "e"])
        self.assertEqual(o2["taskId"], "generic:game")                   # never offered yet, so it rotates in
        st3 = P.apply(st2, "leftoff", NOW + timedelta(days=2), taskId="generic:game", text="played")
        o3 = self.off(st=st3)
        self.assertEqual((o3["taskId"], o3["leftOff"]), ("n", "parser"))  # n is now the longest untouched

    def test_kind_minimums(self):
        game = T("v", "Zelda", "Games", estimatedMinutes=20)
        self.assertEqual(P.kind_of(game, CFG)["name"], "game")
        self.assertEqual(P.effective_minutes(game, CFG), 90)                                  # a game is at least 90
        self.assertEqual(P.effective_minutes(T("n", "Traffic analyzer", "Side Projects"), CFG), 60)
        self.assertEqual(P.effective_minutes(T("t", "x", "Play", notes="#game night"), CFG), 90)  # tag
        self.assertEqual(P.effective_minutes(T("g", "Golf range", "Play", estimatedMinutes=45), CFG), 240)   # a round, not a range session
        self.assertEqual(P.effective_minutes(T("w2", "Yoga", "Play", estimatedMinutes=45), CFG), 45)
        self.assertEqual(P.effective_minutes(T("w", "Walk", "Play"), CFG), 30)
        self.assertIsNone(P.kind_of(T("b", "Gamebook notes", "Play"), CFG))                     # whole words only

    def test_offer_must_fit_the_free_time_left(self):
        games = [T("v", "Zelda", "Games")]
        tight = {**REC, "dayLoad": {"level": "light", "freeMinutes": 150, "plannedMinutes": 90}}   # 60 left
        self.assertIsNone(self.off(rec=tight, tasks=games))
        roomy = {**REC, "dayLoad": {"level": "light", "freeMinutes": 400, "plannedMinutes": 100}}
        self.assertEqual(self.off(rec=roomy, tasks=games)["minutes"], 90)
        mixed = games + [T("n", "Traffic analyzer", "Side Projects")]
        self.assertEqual(self.off(rec=tight, tasks=mixed)["taskId"], "n")                       # project (60) fits, game does not

    def test_generic_game_offer_when_no_game_item_and_it_fits(self):
        o = self.off(tasks=[T("g", "Golf range", "Play", estimatedMinutes=45)], st=P.apply(P.empty(), "leftoff", NOW, taskId="g", text="x"))
        self.assertEqual(o["taskId"], "generic:game")                  # golf was touched, generic never
        self.assertIn("game session", o["text"]); self.assertEqual(o["minutes"], 90)
        tight = {**REC, "dayLoad": {"level": "light", "freeMinutes": 100, "plannedMinutes": 60}}
        self.assertIsNone(self.off(rec=tight, tasks=[]))               # 40 min left: no game session
        real = [T("v", "Zelda", "Games")]
        self.assertEqual(self.off(tasks=real)["taskId"], "v")          # a real game item replaces the generic one
        self.assertIn("game session", self.off(tasks=real)["text"])    # and still reads as a game session

    def test_golf_needs_daylight_and_four_free_hours_but_not_a_light_day(self):
        golf = [T("g", "Golf", "Play")]
        normal = lambda free, planned: {**REC, "dayLoad": {"level": "normal", "freeMinutes": free, "plannedMinutes": planned}}
        o = self.off(rec=normal(600, 300), tasks=golf)               # 5 h left, 10:00 am, normal day
        self.assertEqual((o["taskId"], o["minutes"]), ("g", 240))
        self.assertIsNone(self.off(rec=normal(500, 300), tasks=golf))   # only 3 h 20 left
        late = lambda h, m=0: P.offer(normal(600, 300), golf, P.empty(), CFG, category_for, "idle", NOW.replace(hour=h, minute=m))
        self.assertIsNotNone(late(16, 59)); self.assertIsNone(late(17)); self.assertIsNone(late(19))
        o2 = self.off(rec=normal(600, 300), tasks=[])                  # no golf item: the built-in offer
        self.assertEqual(o2["taskId"], "generic:golf"); self.assertIn("golf", o2["text"])


if __name__ == "__main__":
    unittest.main()
