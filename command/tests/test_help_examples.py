"""The chat's / menu entries (dashboard/holo/chat.js) must really reach the handler each one promises."""
import json, re, sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(ROOT / "prep"))
import phrasings as P  # noqa: E402
import route_preview as R  # noqa: E402
import capture  # noqa: E402
import prep as prep_agent  # noqa: E402

NOW = datetime(2026, 11, 10, 10, 0, tzinfo=timezone(timedelta(hours=-5)))


def slash():
    import subprocess
    src = (ROOT / "dashboard" / "holo" / "chat.js").read_text()
    body = src[src.index("var SLASH = ["):src.index("];", src.index("var SLASH = ["))] + "];"
    out = subprocess.run(["node", "-e", body + "\nprocess.stdout.write(JSON.stringify(SLASH))"], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


class SlashMenu(unittest.TestCase):
    """The chat's / menu (dashboard/holo/chat.js): each starter, finished with its sample ending, reaches its handler."""
    def test_starters_route_as_promised(self):
        bad = []
        for x in slash():
            text = x["s"] + x.get("t", "")
            got = R.decide(text, tasks=P.TASKS, now=NOW, prep_parse=prep_agent.parse_command)
            if got != x["to"]:
                bad.append((x["k"], got, text))
        self.assertEqual(bad, [])

    def test_the_menu_lists_what_was_decided(self):
        self.assertEqual([x["k"] for x in slash()], ["/now", "/due", "/add", "/done", "/stuck", "/find", "/where", "/park", "/prep"])


if __name__ == "__main__":
    unittest.main()
