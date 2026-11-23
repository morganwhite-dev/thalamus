#!/bin/bash
# Publish a cleaned snapshot of main to the public GitHub repo (morganwhite-dev/thalamus).
# The local repo keeps its full history and private notes; the public repo gets one snapshot commit per run.
#   scripts/publish.sh            build, check and push
#   scripts/publish.sh --dry-run  build and check only (prints where the snapshot is)
set -euo pipefail

REMOTE="https://github.com/morganwhite-dev/thalamus.git"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
PUB="${THALAMUS_PUBLISH_DIR:-$HOME/.local/share/thalamus-publish}"
# Paths that never go public: private notes and the Claude Design export (not ours to redistribute).
PRIVATE=("CLAUDE.md" "Ui Designs" "Claude outputs")

ref="$(git -C "$SRC" rev-parse --short main)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -C "$SRC" archive main | tar -x -C "$tmp"
for p in "${PRIVATE[@]}"; do rm -rf "$tmp/$p"; done

# Resume facts: keep location and public profiles, drop the phone number and email.
python3 - "$tmp/prep/facts.json" <<'EOF'
import json, re, sys
p = sys.argv[1]
f = json.load(open(p))
parts = [x.strip() for x in f["contact"]["line"].split("·")]
f["contact"]["line"] = " · ".join(x for x in parts if not re.search(r"\d{3}\D{0,2}\d{3}\D\d{4}|@", x))
json.dump(f, open(p, "w"), indent=1, ensure_ascii=False)
open(p, "a").write("\n")
EOF

# Last line of defence: refuse to publish if a private value slipped in.
# Extra words to block, one per line, live in scripts/private-words.txt (gitignored, so they are never published).
python3 - "$tmp" "$SRC/push/config.json" "$SRC/scripts/private-words.txt" <<'EOF'
import json, pathlib, re, sys
root, cfg, words = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
needles = [r"\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b", r"[\w.+-]+@gmail\.com"]
if words.exists():
    needles += [re.escape(w.strip()) for w in words.read_text().splitlines() if w.strip() and not w.startswith("#")]
topic = json.loads(cfg.read_text()).get("ntfyTopic") if cfg.exists() else None
bad = []
for f in root.rglob("*"):
    if not f.is_file() or f.suffix in (".png", ".icns", ".jpg", ".zip", ".pdf"):
        continue
    t = f.read_text(errors="ignore")
    if topic and topic in t:
        bad.append(f"{f.relative_to(root)}: the ntfy topic")
    for n in needles:
        if re.search(n, t, re.I):
            bad.append(f"{f.relative_to(root)}: matches {n}")
if bad:
    print("Not publishing; private data found:\n  " + "\n  ".join(bad))
    sys.exit(1)
EOF

if [ ! -d "$PUB/.git" ]; then
  mkdir -p "$PUB"
  git -C "$PUB" init -q -b main
  git -C "$PUB" remote add origin "$REMOTE"
  git -C "$PUB" config user.name "Morgan White"
  git -C "$PUB" config user.email "morganwhite-dev@users.noreply.github.com"   # no personal email on public commits
  git -C "$PUB" fetch -q origin 2>/dev/null && git -C "$PUB" reset -q origin/main 2>/dev/null || true
fi
rsync -a --delete --exclude .git "$tmp/" "$PUB/"
git -C "$PUB" add -A
if git -C "$PUB" diff --cached --quiet; then
  echo "Nothing new to publish."
  exit 0
fi
if [ "${1:-}" = "--dry-run" ]; then
  echo "Dry run: snapshot of $ref staged in $PUB (not committed or pushed)."
  git -C "$PUB" diff --cached --stat | tail -1
  exit 0
fi
git -C "$PUB" commit -q -m "Snapshot of $ref ($(date +%Y-%m-%d))"
git -C "$PUB" push -q -u origin main
echo "Published $ref to $REMOTE"
