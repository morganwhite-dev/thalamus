import json, sys, unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(R / "play"), str(R / "engine")]
import play as P
from brain_engine import category_for

CFG = json.loads((R / "engine" / "config.json").read_text())
NOW = datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)
REC = {"dayLoad": {"level": "light", "freeMinutes": 600, "plannedMinutes": 60}, "current": {"band": "undated", "dueDate": None}, "queue": []}
T = lambda i, t, l, **k: {"id": i, "title": t, "list": l, **k}


class Projects(unittest.TestCase):
    def flow(self):
        st = P.apply(P.empty(), "park", NOW, text="packet sniffer")
        return st, st["projects"][0]["id"]

    def test_park_makes_a_not_started_project(self):
        st, pid = self.flow()
        self.assertEqual((st["parking"], st["projects"][0]["title"], st["projects"][0]["state"]), ([], "packet sniffer", "idea"))

    def test_start_then_left_off_touches_it(self):
        st, pid = self.flow()
        st = P.apply(st, "startproject", NOW, id=pid)
        self.assertEqual(st["projects"][0]["state"], "started")
        later = NOW + timedelta(days=1)
        st = P.apply(st, "leftoff", later, taskId=pid, text="parser done")
        self.assertEqual(st["projects"][0]["touchedAt"], later.isoformat())
        v = P.view(st, [], CFG, category_for, None)
        self.assertEqual((v["projects"][0]["leftOff"], v["count"]), ("parser done", 1))

    def test_drop_removes_project_and_line(self):
        st, pid = self.flow()
        st = P.apply(P.apply(st, "leftoff", NOW, taskId=pid, text="x"), "dropproject", NOW, id=pid)
        self.assertEqual((st["projects"], st["leftOff"]), ([], {}))
        with self.assertRaises(ValueError): P.apply(st, "startproject", NOW, id=pid)

    def test_games_and_golf_are_hidden_and_carry_no_left_off(self):
        tasks = [T("g", "Golf", "Play"), T("v", "Video games", "Play"), T("n", "Analyzer", "Side Projects")]
        v = P.view(P.empty(), tasks, CFG, category_for, None)
        self.assertEqual([i["taskId"] for i in v["items"]], ["n"])
        st = P.apply(P.empty(), "leftoff", NOW, taskId="generic:game", text="x")   # stale line from before: ignored
        o = P.offer(REC, [T("g", "Golf", "Play")], st, CFG, category_for, "idle", NOW, autos={"g": "auto"})
        self.assertEqual(o["taskId"], "g"); self.assertIsNone(o["leftOff"])

    def test_started_project_is_offered_with_its_line_idea_is_not(self):
        st, pid = self.flow()
        self.assertNotEqual(P.offer(REC, [], st, CFG, category_for, "idle", NOW)["taskId"], pid)
        st = P.apply(P.apply(st, "startproject", NOW, id=pid), "leftoff", NOW, taskId=pid, text="parser done")
        st = P.apply(P.apply(st, "accept", NOW, taskId="generic:game"), "accept", NOW, taskId="generic:golf")
        o = P.offer(REC, [], st, CFG, category_for, "idle", NOW + timedelta(hours=1))
        self.assertEqual((o["taskId"], o["leftOff"]), (pid, "parser done"))

    def test_accept_rotates_without_showing(self):
        st = P.apply(P.empty(), "accept", NOW, taskId="generic:game")
        v = P.view(st, [], CFG, category_for, None)
        self.assertEqual(v["count"], 0)


if __name__ == "__main__":
    unittest.main()


class BareAndUpdate(unittest.TestCase):
    def test_where_was_i_means_the_project_in_focus(self):
        import project_status as ps
        for t in ["where was i", "where did i leave off", "what was i doing", "ok where was i?", "where am i at"]:
            self.assertTrue(ps.is_bare(t), t)
        for t in ["where was i born", "where did i leave off on my analyzer project", "what's due friday"]:
            self.assertFalse(ps.is_bare(t), t)

    def test_only_update_saves_the_line(self):
        import project_status as ps
        self.assertTrue(ps.is_update("update the status of my analyzer"))
        self.assertTrue(ps.is_update("refresh the status of X project"))
        self.assertFalse(ps.is_update("where did i leave off on my analyzer"))
        self.assertFalse(ps.is_update("how's my analyzer going"))
