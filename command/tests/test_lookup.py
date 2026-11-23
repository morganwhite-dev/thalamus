import os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lookup as L  # noqa

TREE = [
    "Network Security/Week 5/1 Readings/COASP Module 5.pptx",
    "Network Security/Week 5/1 Readings/COASP Module 6.pptx",
    "Network Security/Week 5/1 Readings/My Notes/Teaching Notes - Module 5.html",
    "Network Security/Week 5/1 Readings/My Notes/Teaching Notes - Module 6.html",
    "Network Security/Week 5/1 Readings/My Notes/Outline Notes - Module 5.html",
    "Network Security/Week 1/My Notes/Module 2/Teaching Notes - Module 2.pdf",
    "Network Security/_Course Info/CIS_8088_Syllabus.docx",
    "Network Security/notes.py",
    "Cloud Computing and Security/Week 3/Module 3 - Teaching Notes.html",
    "Cloud Computing and Security/Week 3/Module 3 Slides.pptx",
]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for rel in TREE:
            p = self.tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")
        self.cfg = {"lookup": {"roots": [str(self.tmp / "Network Security"), str(self.tmp / "Cloud Computing and Security")],
                               "extensions": ["pdf", "pptx", "docx", "html", "md"], "maxResults": 12, "maxFiles": 1000}}

    def ask(self, text):
        q = L.detect(text)
        self.assertIsNotNone(q, text)
        return L.search(q, self.cfg)


class Intent(unittest.TestCase):
    def test_file_questions(self):
        for t in ["do you have teaching notes for module 5 and 6 for network security", "find the quiz for module 3",
                  "where is the syllabus", "show me the slides for week 5", "is there an outline for module 4"]:
            self.assertIsNotNone(L.detect(t), t)

    def test_not_file_questions(self):
        for t in ["what's due friday?", "what should I do now", "remind me to email Dr. Lee",
                  "explain module 5 to me", "", "what is a firewall?"]:
            self.assertIsNone(L.detect(t), t)

    def test_number_ranges(self):
        self.assertEqual(L._numbers("modules 1, 2 and 3", "module"), [1, 2, 3])
        self.assertEqual(L._numbers("module 5 and 6", "module"), [5, 6])
        self.assertEqual(L._numbers("modules 2 to 4", "module"), [2, 3, 4])


class Generic(Base):
    def test_generic_name_search_finds_by_words(self):
        q = L.detect("find the syllabus docx")
        self.assertIsNotNone(q)
        r = L.search(q, self.cfg)
        self.assertEqual([f["name"] for f in r["files"]], ["CIS_8088_Syllabus.docx"])

    def test_generic_with_no_match_has_no_files_so_the_box_falls_through(self):
        q = L.detect("do you have time")
        self.assertTrue(q is None or L.search(q, self.cfg)["files"] == [])

    def test_course_narrowing_uses_the_path_when_root_is_wider(self):
        wide = {"lookup": {**self.cfg["lookup"], "roots": [str(self.tmp)]}}
        r = L.search(L.detect("teaching notes for module 3 for cloud"), wide)
        self.assertEqual([f["name"] for f in r["files"]], ["Module 3 - Teaching Notes.html"])


class Search(Base):
    def test_teaching_notes_for_two_modules(self):
        r = self.ask("do you have teaching notes for module 5 and 6 for network security")
        names = [f["name"] for f in r["files"]]
        self.assertEqual(names, ["Teaching Notes - Module 5.html", "Teaching Notes - Module 6.html"])
        self.assertIn("module 5 and 6", r["answer"])
        self.assertNotIn("Not found", r["answer"])

    def test_says_what_is_missing(self):
        r = self.ask("do you have teaching notes for module 5 and 9")
        self.assertEqual(len(r["files"]), 1)
        self.assertIn("Not found: module 9", r["answer"])

    def test_chapter_means_the_same_week_and_says_so(self):
        r = self.ask("where are the teaching notes for chapter 5")
        self.assertEqual(sorted(f["name"] for f in r["files"]), ["Teaching Notes - Module 5.html", "Teaching Notes - Module 6.html"])
        self.assertIn("filed by week and module, not chapter", r["answer"])
        self.assertNotIn("Module 2", r["answer"])

    def test_nothing_found_is_plain(self):
        r = self.ask("find the quiz for module 3")
        self.assertEqual(r["files"], [])
        self.assertIn("didn't find", r["answer"])

    def test_course_narrows(self):
        r = self.ask("teaching notes for module 3 in cloud")
        self.assertEqual([f["name"] for f in r["files"]], ["Module 3 - Teaching Notes.html"])
        r2 = self.ask("teaching notes for module 3 for network security")
        self.assertEqual(r2["files"], [])

    def test_slides_means_decks(self):
        r = self.ask("do you have the slides for module 5")
        self.assertEqual([f["name"] for f in r["files"]], ["COASP Module 5.pptx"])

    def test_week_filter_and_syllabus(self):
        r = self.ask("where is the syllabus")
        self.assertEqual([f["name"] for f in r["files"]], ["CIS_8088_Syllabus.docx"])

    def test_only_allowed_extensions(self):
        names = [f["name"] for f in self.ask("find the notes for module 5")["files"]]
        self.assertNotIn("notes.py", names)


class OpenSafety(Base):
    def test_inside_root_ok(self):
        p = self.tmp / "Network Security/Week 5/1 Readings/My Notes/Teaching Notes - Module 5.html"
        self.assertEqual(L.safe_open_path(p, self.cfg), Path(os.path.realpath(p)))

    def test_outside_root_refused(self):
        out = self.tmp / "secret.html"
        out.write_text("x")
        self.assertIsNone(L.safe_open_path(out, self.cfg))
        self.assertIsNone(L.safe_open_path("/etc/hosts", self.cfg))

    def test_bad_extension_and_missing_and_dirs(self):
        self.assertIsNone(L.safe_open_path(self.tmp / "Network Security/notes.py", self.cfg))
        self.assertIsNone(L.safe_open_path(self.tmp / "Network Security/nope.html", self.cfg))
        self.assertIsNone(L.safe_open_path(self.tmp / "Network Security", self.cfg))

    def test_symlink_escape_refused(self):
        outside = self.tmp / "outside.html"
        outside.write_text("x")
        link = self.tmp / "Network Security" / "link.html"
        link.symlink_to(outside)
        self.assertIsNone(L.safe_open_path(link, self.cfg))

    def test_dotdot_refused(self):
        p = str(self.tmp / "Network Security" / ".." / "secret.html")
        (self.tmp / "secret.html").write_text("x")
        self.assertIsNone(L.safe_open_path(p, self.cfg))


if __name__ == "__main__":
    unittest.main()


class GiveMe(unittest.TestCase):
    def test_give_me_and_cloud_class_number(self):
        import lookup as L
        q = L.detect("give me the cloud class 5 teaching notes")
        self.assertEqual(q["weeks"], [5])
        self.assertEqual(q["kinds"][0][0], "teaching notes")
        self.assertIsNotNone(L.detect("give me the module 5 and 6 teaching notes for network security"))
