"""Usage (from priority-brain/router):
  python3 -m router "fix the typo in README line 3"          route and run
  python3 -m router --dry-run "refactor the import layer"    classify only, no task model call
  python3 -m router --conversation c1 "..."                  stay on one model within c1
  python3 -m router --source notes.txt "summarize this"      grounding source for the validator
  python3 -m router usage | log [N] | models
"""

from __future__ import annotations

import argparse
import json
import sys

from .core import Router


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("usage", "log", "models"):
        r = Router()
        if argv[0] == "usage":
            print(json.dumps(r.usage.totals(), indent=1))
            for w in r.usage.warnings():
                print("WARN", w)
        elif argv[0] == "log":
            n = int(argv[1]) if len(argv) > 1 else 10
            for row in r.log.tail(n):
                print(json.dumps(row))
        else:
            ro = r.roster
            print("free:", ", ".join(m.key for m in ro.free))
            print("claude:", ", ".join(f"{t}={m.key} ({m.multiplier}x)" for t, m in ro.claude.items()))
            print("excluded:\n  " + "\n  ".join(ro.excluded))
        return 0

    p = argparse.ArgumentParser(prog="router")
    p.add_argument("task", nargs="+")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--conversation")
    p.add_argument("--source", help="file whose text is the grounding source")
    p.add_argument("--file", action="append", dest="files", help="attachment (pdf, image...)")
    a = p.parse_args(argv)
    source = open(a.source).read() if a.source else None
    res = Router().route(" ".join(a.task), source=source, conversation=a.conversation,
                         attachments=a.files, dry_run=a.dry_run)
    print(f"[{res.handled_by} | tier={res.tier} | model={res.model} | effort={res.effort} | {res.outcome}]")
    print(f"reason: {res.reason}")
    for at in res.attempts:
        print("  attempt:", json.dumps(at.to_log()))
    for w in res.warnings:
        print("WARN", w)
    if res.answer:
        print("\n" + res.answer)
    return 0 if not res.outcome.startswith("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
