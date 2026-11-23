#!/usr/bin/env python3
"""Held-out evaluation and threshold tuning for the meaning matcher (embedding k-NN).

Run: python3 command/matcher_eval.py [--models all-minilm,nomic-embed-text] [--k 5] [--min-precision 0.95]

Embeds the example tables and command/tests/matcher_heldout.py with a local Ollama model, classifies every held-out
sentence by k-nearest cosine, sweeps threshold x margin and recommends the best coverage with zero MUST_NOT_ACT
sentences routed to action/capture and overall precision >= the floor. Vectors are cached under command/state/.
Stdlib only. Touches no other code.
"""
import argparse
import hashlib
import json
import math
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tests"))
import phrasings  # noqa: E402
import typed_cases  # noqa: E402
import matcher_heldout  # noqa: E402

OLLAMA = "http://127.0.0.1:11434"
CACHE = os.path.join(HERE, "state", "matcher_eval_vectors.json")
PREFIX = {"all-minilm": "", "nomic-embed-text": "classification: "}
RISKY = ("action", "capture")


def load_examples():
    """label -> [sentences], built the way the matcher will: free/jev -> general, ACTIONS -> action, NOT_ACTIONS -> noact."""
    ex = {}

    def add(label, items):
        seen = ex.setdefault(label, [])
        for s in items:
            if s not in seen:
                seen.append(s)

    for name in dir(phrasings):
        if name == "CASES" or name.startswith("MORE"):
            for k, v in getattr(phrasings, name).items():
                add("general" if k in ("free", "jev") else k, v)
    for v in typed_cases.ACTIONS.values():
        add("action", v)
    add("noact", typed_cases.NOT_ACTIONS)
    return ex


def _load_cache():
    try:
        with open(CACHE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def embed(model, texts, batch=64):
    """Vectors for texts (cached per model + exact text). Uses POST /api/embed."""
    cache = _load_cache()
    pre = PREFIX.get(model, "")
    key = lambda t: hashlib.sha1((model + "\0" + pre + t).encode()).hexdigest()
    todo = [t for t in dict.fromkeys(texts) if key(t) not in cache]
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        body = json.dumps({"model": model, "input": [pre + t for t in chunk]}).encode()
        req = urllib.request.Request(OLLAMA + "/api/embed", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            vecs = json.load(r)["embeddings"]
        for t, v in zip(chunk, vecs):
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            cache[key(t)] = [round(x / n, 5) for x in v]
    if todo:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as f:
            json.dump(cache, f)
    return [cache[key(t)] for t in texts]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def label_scores(vec, examples, k=5):
    """examples: [(label, vec)] (unit vectors). Returns {label: best similarity among the k nearest}, best first."""
    sims = sorted(((dot(vec, v), l) for l, v in examples), reverse=True)[:k]
    best = {}
    for s, l in sims:
        best.setdefault(l, s)
    return best


def classify(vec, examples, k=5, threshold=0.5, margin=0.0):
    """-> (label | None, score, margin). Label = best label among the k nearest; margin = its score minus the runner-up label's
    score (the runner-up is 0 when all k neighbours share a label... use the k nearest of OTHER labels instead, see below).
    None when score < threshold or margin < margin_min."""
    sims = sorted(((dot(vec, v), l) for l, v in examples), reverse=True)
    top = sims[:k]
    best = {}
    for s, l in top:
        best.setdefault(l, s)
    label = max(best, key=best.get)
    score = best[label]
    other = next((s for s, l in sims if l != label), 0.0)  # nearest example of any other label
    m = score - other
    if score < threshold or m < margin:
        return None, score, m
    return label, score, m


def evaluate(model, k):
    ex = load_examples()
    ex_items = [(l, s) for l, ss in ex.items() for s in ss]
    ex_vecs = embed(model, [s for _, s in ex_items])
    examples = [(l, v) for (l, _), v in zip(ex_items, ex_vecs)]
    tests = [(l, s) for l, ss in matcher_heldout.HELDOUT.items() for s in ss]
    nots = list(matcher_heldout.MUST_NOT_ACT)
    vecs = embed(model, [s for _, s in tests] + nots)
    raw = []  # (true, sentence, raw label, score, margin) with threshold 0, margin 0 (all fields kept)
    for (l, s), v in zip(tests, vecs):
        raw.append((l, s) + classify(v, examples, k, -1, -9))
    nraw = [(s,) + classify(v, examples, k, -1, -9) for s, v in zip(nots, vecs[len(tests):])]
    return raw, nraw


def sweep(raw, nraw, floor):
    rows = []
    th = [round(0.30 + 0.025 * i, 3) for i in range(27)]  # 0.30..0.95 (spec says to 0.80; nomic similarities run higher)
    mg = [round(0.01 * i, 2) for i in range(16)]
    n = len(raw)
    for t in th:
        for m in mg:
            routed = [(a, p) for a, s, p, sc, mm in raw if sc >= t and mm >= m]
            ok = sum(1 for a, p in routed if a == p)
            bad = sum(1 for s, p, sc, mm in nraw if sc >= t and mm >= m and p in RISKY)
            rows.append({"t": t, "m": m, "prec": ok / len(routed) if routed else 1.0, "cov": len(routed) / n, "bad": bad,
                         "routed": len(routed)})
    return rows


def per_label(raw, t, m):
    out = {}
    for a, s, p, sc, mm in raw:
        if sc >= t and mm >= m:
            d = out.setdefault(p, [0, 0])
            d[1] += 1
            d[0] += a == p
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="all-minilm,nomic-embed-text")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--min-precision", type=float, default=0.95)
    ap.add_argument("--t", type=float, help="show this threshold instead of the recommendation")
    ap.add_argument("--m", type=float, default=0.0)
    ap.add_argument("--overlap", action="store_true", help="only report held-out sentences that copy an example")
    a = ap.parse_args()
    if a.overlap:
        for r in matcher_heldout.overlap_report(load_examples()):
            print(r)
        return
    print("held-out:", {l: len(s) for l, s in matcher_heldout.HELDOUT.items()}, "must-not-act:", len(matcher_heldout.MUST_NOT_ACT))
    for model in a.models.split(","):
        raw, nraw = evaluate(model, a.k)
        rows = sweep(raw, nraw, a.min_precision)
        ok = [r for r in rows if r["bad"] == 0 and r["prec"] >= a.min_precision]
        print(f"\n===== {model} (k={a.k}, prefix {PREFIX.get(model, '')!r}) =====")
        print("no-threshold top-1 accuracy: %.1f%%" % (100 * sum(1 for x in raw if x[0] == x[2]) / len(raw)))
        print("best coverage allowing N risky routes (precision >= %.0f%%):" % (100 * a.min_precision))
        print("  N  threshold margin | precision coverage routed")
        for n in range(0, 5):
            c = [r for r in rows if r["bad"] <= n and r["prec"] >= a.min_precision]
            if c:
                r = max(c, key=lambda r: (r["cov"], r["prec"]))
                print("  %d   %.3f   %.2f   | %.3f   %.3f  %d" % (n, r["t"], r["m"], r["prec"], r["cov"], r["routed"]))
        if ok:
            rec = max(ok, key=lambda r: (r["cov"], r["prec"]))
        else:
            print("  -> NO setting gives 0 risky routes at >=%.0f%% precision. Showing the lowest-risk setting instead." % (100 * a.min_precision))
            c = [r for r in rows if r["prec"] >= a.min_precision] or rows
            rec = min(c, key=lambda r: (r["bad"], -r["cov"]))
        if a.t is not None:
            rec = [r for r in rows if r["t"] == a.t and r["m"] == a.m][0]
        print("RECOMMENDED: threshold=%.3f margin=%.2f k=%d -> precision %.1f%%, coverage %.1f%%, risky routes %d" % (
            rec["t"], rec["m"], a.k, 100 * rec["prec"], 100 * rec["cov"], rec["bad"]))
        print("per-label precision (correct/routed):")
        pl = per_label(raw, rec["t"], rec["m"])
        tot = {}
        for x in raw:
            tot[x[0]] = tot.get(x[0], 0) + 1
        for l in matcher_heldout.HELDOUT:
            c, r_ = pl.get(l, [0, 0])
            hit = sum(1 for x in raw if x[0] == l and x[2] == l and x[3] >= rec["t"] and x[4] >= rec["m"])
            print("  %-9s precision %s  recall %d/%d" % (l, ("%d/%d" % (c, r_)) if r_ else "-", hit, tot[l]))
        conf = {}
        for tr, s, p, sc, mm in raw:
            if sc >= rec["t"] and mm >= rec["m"] and p != tr:
                conf.setdefault((tr, p), []).append(s)
        print("confusions at the recommended setting (true -> predicted):")
        for (tr, p), ss in sorted(conf.items(), key=lambda kv: -len(kv[1])):
            print("  %s -> %s x%d  e.g. %r" % (tr, p, len(ss), ss[0]))
        bads = [(s, p, sc) for s, p, sc, mm in nraw if sc >= rec["t"] and mm >= rec["m"] and p in RISKY]
        for s, p, sc in bads:
            print("  MUST_NOT_ACT routed as %s (%.2f): %r" % (p, sc, s))
        print("MUST_NOT_ACT sentences that would have been routed risky with NO threshold:",
              sum(1 for s, p, sc, mm in nraw if p in RISKY), "of", len(nraw))
        print("misses at the recommended setting (not routed): %d of %d" % (
            sum(1 for x in raw if not (x[3] >= rec["t"] and x[4] >= rec["m"])), len(raw)))


if __name__ == "__main__":
    main()
