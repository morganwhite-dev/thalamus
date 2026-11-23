"""index.html is generated from dashboard/skin/*; keep it in sync and free of the Design runtime."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"


class BuildTests(unittest.TestCase):
    def test_index_is_up_to_date(self):
        r = subprocess.run([sys.executable, str(ROOT / "skin" / "build.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_no_design_runtime_dependency(self):
        html = INDEX.read_text(encoding="utf-8")
        self.assertNotIn("support.js", html)
        self.assertNotIn("dc-runtime", html)
        self.assertNotIn("<x-dc", html)

    def test_skins_present_and_old_one_gone(self):
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn("id=\"toHolo\"", html)          # Plain page has the way back
        self.assertIn("window.Holo", html)             # the skin is bundled
        self.assertIn("thalamusSkin", html)            # choice is remembered
        self.assertNotIn("window.Thalamus", html)      # the old skin is retired
        self.assertNotIn("Brain3D", html)

    def test_hologram_skin_bundled_and_separate(self):
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn("id=\"toHolo\"", html)          # Plain page can open it
        self.assertIn("window.Holo", html)
        holo = "".join((ROOT / "holo" / n).read_text(encoding="utf-8") for n in ("holo.js", "brain.js", "sector.js"))
        # the hard rule: the hologram skin never draws with the old engine
        for old in ("new Eng(", "new Brain3D(", "S.eng", "TH_HTML", "TH_CSS"):
            self.assertNotIn(old, holo)


if __name__ == "__main__":
    unittest.main()
