import json, os, subprocess, sys, tempfile, time, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(R / "play"), str(R / "engine")]
import project_status as S


def git(d, *a):
    subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)


class Status(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.d = Path(self.t.name)
        self.now = datetime.now(timezone.utc).astimezone()

    def tearDown(self): self.t.cleanup()

    def repo(self, name="proj"):
        r = self.d / name; r.mkdir(); git(r, "init", "-q"); (r / "a.py").write_text("x")
        git(r, "add", "."); git(r, "commit", "-qm", "add parser"); return r

    def test_git_active_and_dirty(self):
        r = self.repo(); (r / "b.py").write_text("y")
        line = S.status_line(r, self.now)
        self.assertEqual(line, "Building parser · just now · unsaved work")
        self.assertNotIn("commit", line.lower()); self.assertLessEqual(len(line), 140)

    def test_narrate_wording(self):
        n = self.now; t = n - timedelta(days=2)
        W = lambda subs, dirty=0: S.narrate(subs, dirty, t, n)
        self.assertEqual(W(["Phase 12: add automatic left-off lines"]), "On Phase 12, building automatic left-off lines · 2 days ago")
        self.assertEqual(W(["fix: handle empty pcap"], 2), "Fixing bugs: handle empty pcap · 2 days ago · unsaved work")
        self.assertEqual(W(["Priority brain: phases 0 to 12 (engine, dashboard)"]), "On Phase 12 · 2 days ago")
        self.assertEqual(W(["Initial commit"]), "Setting it up · 2 days ago")
        self.assertEqual(W(["Refactor router config"]), "Cleaning up router config · 2 days ago")
        self.assertEqual(W(["feat(ui): add dark mode toggle"]), "Building dark mode toggle · 2 days ago")
        self.assertEqual(S._phase(["wip", "Step 3: wire importer"]), "Phase 3")     # phase found in an older message

    def test_no_git_folder_uses_files_and_skips_junk(self):
        f = self.d / "plain"; f.mkdir(); (f / "parser.py").write_text("x")
        (f / "node_modules").mkdir(); (f / "node_modules" / "big.js").write_text("x")
        (f / ".hidden").write_text("x")
        old = time.time() - 5 * 86400 - 3600
        os.utime(f / "parser.py", (old, old)); os.utime(f / "node_modules" / "big.js", None)
        line = S.status_line(f, self.now)
        self.assertEqual(line, "Editing parser.py · 5 days ago · 1 file changed this week")

    def test_empty_or_missing_gives_none(self):
        e = self.d / "empty"; e.mkdir()
        self.assertIsNone(S.status_line(e, self.now)); self.assertIsNone(S.status_line(self.d / "nope", self.now))
        self.assertIsNone(S.status_line(None, self.now))

    def test_resolve_folder(self):
        (self.d / "NetworkTrafficAnalyzer").mkdir()
        (self.d / "Other").mkdir(); (self.d / "Other2").mkdir()
        f, how = S.resolve_folder("Network traffic analyzer", roots=[str(self.d)])
        self.assertEqual((f.name, how), ("NetworkTrafficAnalyzer", "name"))
        self.assertEqual(S.resolve_folder("Nothing like it", roots=[str(self.d)])[0], None)
        (self.d / "Network-Traffic-Analyzer").mkdir()
        self.assertEqual(S.resolve_folder("Network traffic analyzer", roots=[str(self.d)])[1], "ambiguous")
        self.assertEqual(S.resolve_folder("x", f"path: {self.d}")[1], "path")
        self.assertEqual(S.resolve_folder("x", f"path: {self.d}/missing")[1], "bad-path")
        (self.d / "afile").write_text("")
        self.assertIsNone(S.resolve_folder("afile", roots=[str(self.d)])[0])   # a plain file is not a project folder

    def test_intent_and_matching(self):
        for text, want in [('Update the status of "Network traffic analyzer" project', "Network traffic analyzer"),
                           ("update the status of packet sniffer", "packet sniffer"),
                           ("what's the status of my sniffer project?", "sniffer"),
                           ("where did I leave off on the analyzer", "analyzer")]:
            self.assertEqual(S.parse_intent(text), want, text)
        self.assertIsNone(S.parse_intent("what should I do now"))
        self.assertIsNone(S.parse_intent("write a status report email"))
        c = [{"id": "1", "title": "Network traffic analyzer"}, {"id": "2", "title": "Packet sniffer"}]
        self.assertEqual(S.find_project("analyzer", c)[0]["id"], "1")
        self.assertEqual(S.find_project("zzz", c), (None, "none"))
        c.append({"id": "3", "title": "Traffic analyzer v2"})
        self.assertEqual(S.find_project("analyzer", c), (None, "ambiguous"))


if __name__ == "__main__":
    unittest.main()
