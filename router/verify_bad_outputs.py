"""Feeds deliberately bad free-model outputs to the real validator (layer 1 + live Jev
layer 2) and prints which layer caught each. Free: Jev costs nothing, no Claude call.

  python3 verify_bad_outputs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from router import validator  # noqa: E402
from router.core import load_config  # noqa: E402
from router.opencode_client import OpenCodeClient  # noqa: E402

SRC = ("Lab 3 for CIS 8087 is due Nov 12 at 11:59 PM. It covers VPC peering and needs a screenshot "
       "of each step. Late work loses 10% per day, and the lab is worth 50 points.")
SUM = "summarize this in two sentences: " + SRC
JSON_TASK = "extract the title and due fields as JSON from: Lab 3 for CIS 8087 is due Nov 12"

CASES = [
    # (label, task, output, task_type, fields, should_pass)
    ("control: good summary", SUM,
     "CIS 8087 Lab 3 on VPC peering is due Nov 12 at 11:59 PM and needs a screenshot of each step. "
     "It is worth 50 points and loses 10% per day late.", "summary", None, True),
    ("empty", SUM, "   ", "summary", None, False),
    ("refusal", SUM, "I'm sorry, but as an AI I can't summarize course materials.", "summary", None, False),
    ("truncated", SUM, "CIS 8087 Lab 3 on VPC peering is due Nov 12 at 11:59 PM and needs a screenshot of each",
     "summary", None, False),
    ("invented fact (date)", SUM,
     "CIS 8087 Lab 3 on VPC peering is due Nov 14 at 11:59 PM and needs a screenshot of each step. "
     "It is worth 50 points and loses 10% per day late.", "summary", None, False),
    ("invented fact (no numbers; Jev only)", SUM,
     "CIS 8087 Lab 3 on VPC peering is due Nov 12 at 11:59 PM and must be done with a lab partner. "
     "It is worth 50 points and loses 10% per day late.", "summary", None, False),
    ("wrong format (not JSON)", JSON_TASK, "title: Lab 3, due: Nov 12", "extraction", ["title", "due"], False),
    ("wrong format (missing field)", JSON_TASK, '{"title": "Lab 3"}', "extraction", ["title", "due"], False),
    ("control: good JSON", JSON_TASK, '{"title": "Lab 3", "due": "Nov 12"}', "extraction", ["title", "due"], True),
]


def main() -> int:
    cfg = load_config()
    client = OpenCodeClient(cfg["opencode_cli"], cfg["workspace"])
    wrong = 0
    for label, task, out, tt, fields, should_pass in CASES:
        v = validator.validate(client, cfg, task, out, tt, None, fields)
        right = v.passed == should_pass
        wrong += not right
        caught = "passed" if v.passed else f"caught by layer {v.failed_layer}"
        print(f"{'ok' if right else 'XX'}  {label:40} {caught:18} {'; '.join(v.failures)[:110]}")
    print(f"\n{len(CASES) - wrong}/{len(CASES)} as expected")
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
