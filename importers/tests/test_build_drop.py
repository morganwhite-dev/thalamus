import sys, unittest, tempfile
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_drop as b

TRACKER = """# x
## Status tracker
| Item | Status |
|---|---|
| Prompt injection detector | Next up, not started |
| A1 pipeline | In progress |
| Security+ study | Done 2026-10-30 |
| Applications | Ongoing, tracked separately |

## Next
"""

class T(unittest.TestCase):
    def test_security_skips_done_and_applications(self):
        rows = b.security_rows(TRACKER)
        self.assertEqual([r["title"] for r in rows], ["Prompt injection detector", "A1 pipeline"])
        self.assertTrue(all(r["dueDate"] == "none" and r["course"] == "Security Projects" for r in rows))
        self.assertEqual(rows[0]["priority"], "high")

    def test_security_done_flip_removes_row(self):
        rows = b.security_rows(TRACKER.replace("In progress", "Done 2026-11-05"))
        self.assertEqual(len(rows), 1)

    def test_apply_by(self):
        self.assertEqual(b.apply_by("$40/hr, apply by Sep 28 2026, ATS", None), "2026-09-28")
        self.assertEqual(b.apply_by("DEADLINE Feb 15 2027", None), "2027-02-15")
        self.assertIsNone(b.apply_by("no date here", None))
        self.assertIsNone(b.apply_by("apply by Feb 31 2027", None))

    def test_internships_weekly_count_and_actionable(self):
        today = date(2026, 11, 5)  # Thursday; week is Nov 2-8
        csv_rows = [
            {"Date Applied": "2026-11-02", "Company": "A", "Job Title": "J", "Status": "Applied", "Notes": ""},
            {"Date Applied": "2026-10-30", "Company": "B", "Job Title": "J", "Status": "Applied", "Notes": ""},
            {"Date Applied": "2026-11-03", "Company": "C", "Job Title": "J", "Status": "Skipped - not a fit", "Notes": ""},
            {"Date Applied": "", "Company": "D", "Job Title": "Intern", "Status": "Ready to submit",
             "Notes": "apply by Nov 20 2026", "Handshake Link": "https://x", "Resume Version Used": "R"},
        ]
        rows = b.internship_rows(csv_rows, today)
        self.assertEqual(rows[0]["title"], "Apply to 10 internships (week of Nov 2)")
        self.assertEqual(rows[0]["dueDate"], "2026-11-08")
        self.assertTrue(rows[0]["notes"].startswith("1 of 10"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["title"], "Apply: D - Intern")
        self.assertEqual(rows[1]["dueDate"], "2026-11-20")

    def test_write_if_changed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x_assignments.json"
            self.assertTrue(b.write_if_changed(p, [{"title": "a"}]))
            self.assertFalse(b.write_if_changed(p, [{"title": "a"}]))
            self.assertTrue(b.write_if_changed(p, [{"title": "b"}]))

if __name__ == "__main__":
    unittest.main()
