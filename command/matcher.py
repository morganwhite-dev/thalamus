"""Meaning matcher for the command box: which kind of request is this sentence? (self-contained; not wired in yet)

Sits between the plain-code rules and a free model. A local Ollama embedding model turns the typed sentence into a vector;
the nearest known example sentences (from the phrase tables in command/tests) vote for a coarse label.

    Matcher().classify("what should i be doing")
    -> {"label": "now", "score": 0.91, "margin": 0.2, "routable": True, "top": [["now", 0.91], ["schedule", 0.71]]}   or None

Timing: the example cache is loaded (or built) only by a background loader started when the Matcher is made; classify
returns None until it is in memory. One long-lived worker thread runs the query embeds, one at a time: when it is busy,
classify returns None at once. timeout_ms bounds all of classify from entry.

How the score works (kNN, kept simple):
  1. embed the sentence, cosine against every example vector (vectors are normalised on build and on load and only
     the unit vectors are kept, so a dot product);
  2. take the `k` nearest examples;
  3. a label's score is its best similarity among those k (a label with no example in the k nearest scores 0);
  4. best label wins if score >= threshold AND score - (nearest example of any other label) >= margin. Otherwise None ("not sure": the caller
     falls through to its next step). None is also the answer when disabled, Ollama is down or slow, or the input is
     empty, over 500 characters (never embedded), or multi-line. classify never raises.
  5. `routable` is True only when the label is in config `route_labels` AND in the hard-coded SAFE set (config can narrow, never widen; by construction, it cleared threshold and margin)
     and the gap to the next label is above MARGIN_EPS (a tie or a rounding-error gap is never routable).
     Callers route only on routable. action, capture, park, stuck, lookup and noact are never routable by default: embeddings
     miss who a sentence is about ("my mom needs to buy a gift" looks like capture), so those go to the translator model.

Labels: now, schedule, capture, park, project, lookup, reminders, stuck, action, tiny, general, noact
(phrasings.py categories, with `free` and `jev` merged into `general`; typed_cases.py ACTIONS -> `action`, NOT_ACTIONS -> `noact`).
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import http.client
import json
import math
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_DIR = os.path.join(HERE, "state")
CACHE_PATH = os.path.join(STATE_DIR, "matcher-cache.json")
LOG_PATH = os.path.join(STATE_DIR, "matcher-log.jsonl")
LAUNCH_STAMP = os.path.join(STATE_DIR, "ollama-launch.stamp")
_LOG_KEY = os.urandom(32)  # never written anywhere
CONFIG_PATH = os.path.join(ROOT, "engine", "config.json")

OLLAMA_URL = "http://127.0.0.1:11434"
LAUNCH_EVERY_S = 120
MAX_CHARS = 500
LOG_MAX_BYTES = 1024 * 1024
LOG_QUEUE_MAX = 256   # lines waiting for the log writer; when full, new lines are dropped
DISABLE_S = 600
SLACK_S = 0.01
# The only labels a caller may ever route on. Config may narrow route_labels, never widen it.
SAFE = frozenset({"now", "schedule", "project", "reminders", "tiny", "general"})
# A gap to the next label must exceed this as well as the configured margin, so a one-ULP gap is never routable.
MARGIN_EPS = 1e-9
# Part of the cache signature. Bump it whenever the cache file's meaning changes, so every older file rebuilds.
# 2: full-precision unit vectors (format 1 stored rounded vectors).
CACHE_FORMAT = 2
BUILD_TIMEOUT_S = 120
BATCH = 64
# prefix: nomic-embed-text wants a task prefix on every text (examples and queries). It is applied only when configured, so
# all-minilm users set "prefix": "". route_labels: the only labels a caller may route on (see "routable" in classify).
DEFAULTS = {"enabled": True, "model": "nomic-embed-text", "prefix": "classification: ", "k": 5, "threshold": 0.85, "margin": 0.02,
            "timeout_ms": 300, "url": OLLAMA_URL, "route_labels": ["now", "schedule", "project", "reminders", "tiny", "general"]}
LABELS = ["now", "schedule", "capture", "park", "project", "lookup", "reminders", "stuck", "action", "tiny", "general", "noact"]
MERGE = {"free": "general", "jev": "general"}


# ---------------------------------------------------------------- Ollama

class ModelMissing(Exception):
    """The embedding model is not installed (HTTP 404 or "model not found"). An embed_fn may raise it."""


LOCAL_HOSTS = ("127.0.0.1", "::1", "localhost")


def is_local_url(url):
    try:
        return urllib.parse.urlparse(url).hostname in LOCAL_HOSTS
    except Exception:
        return False


MAX_BODY = 64 * 1024 * 1024


class HTTPStatusError(Exception):
    """The server answered with an HTTP error status (400 or above)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _read_json(url, body, timeout_s):
    """GET (body None) or POST JSON to a local URL and parse the reply. The whole call, from connect through the status
    line, headers and every byte of the body, must finish within timeout_s of wall-clock time: a watchdog timer shuts
    the socket down at the deadline, so a server that trickles bytes (even the status line) cannot stretch it.
    Plain http.client, so no proxy is ever used. None on timeout; raises HTTPStatusError on a 4xx or 5xx reply."""
    deadline = time.monotonic() + timeout_s
    u = urllib.parse.urlparse(url)
    if u.scheme != "http" or u.hostname not in LOCAL_HOSTS:
        return None
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=max(0.01, timeout_s))
    fired = []
    held = []                      # the raw socket, kept here because getresponse() can detach it from conn

    def kill():
        fired.append(1)            # first, so the main thread sees it even if the socket is not made yet
        s = held[0] if held else conn.sock
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)   # unblocks any read in progress
            except OSError:
                pass

    timer = threading.Timer(max(0.0, timeout_s), kill)
    timer.daemon = True
    timer.name = "matcher-deadline"
    timer.start()
    try:
        conn.connect()
        held.append(conn.sock)
        if fired:
            return None
        path = (u.path or "/") + ("?" + u.query if u.query else "")
        if body is None:
            conn.request("GET", path)
        else:
            conn.request("POST", path, body=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        r = conn.getresponse()
        if r.status >= 400:
            raise HTTPStatusError(r.status)
        chunks, total = [], 0
        while True:
            if fired or time.monotonic() >= deadline:
                return None
            b = r.read1(65536)
            if not b:
                break
            total += len(b)
            if total > MAX_BODY:
                return None
            chunks.append(b)
        if fired:
            return None
    except HTTPStatusError:
        raise
    except Exception:
        if fired:
            return None
        raise
    finally:
        timer.cancel()
        conn.close()
    return json.loads(b"".join(chunks))


def ollama_embed(texts, model, timeout_s, base_url=None):
    """POST /api/embed with a batch of texts; returns a list of vectors, or None on any error or timeout (timeout_s is a
    total wall-clock limit). Raises ModelMissing when Ollama says the model is not installed. Refuses any non-local URL."""
    base_url = base_url or OLLAMA_URL
    if not is_local_url(base_url):
        return None
    try:
        data = _read_json(base_url + "/api/embed", {"model": model, "input": list(texts)}, timeout_s)
    except HTTPStatusError as e:
        if e.code == 404:
            raise ModelMissing(model)
        return None
    except Exception:
        return None
    if isinstance(data, dict) and "not found" in str(data.get("error", "")).lower():
        raise ModelMissing(model)
    vecs = data.get("embeddings") if isinstance(data, dict) else None
    if not isinstance(vecs, list) or len(vecs) != len(texts) or not all(isinstance(v, list) and v for v in vecs):
        return None
    return vecs


def ollama_digest(model, base_url=None, timeout_s=5):
    """The installed model's digest from /api/tags (changes when the model is re-pulled), or None."""
    base_url = base_url or OLLAMA_URL
    if not is_local_url(base_url):
        return None
    try:
        data = _read_json(base_url + "/api/tags", None, timeout_s)
        models = (data.get("models") if isinstance(data, dict) else None) or []
        for m in models:
            name = m.get("name") or m.get("model") or ""
            if name == model or name.split(":")[0] == model:
                d = m.get("digest")
                return str(d) if d else None
    except Exception:
        pass
    return None


def _port_answers(timeout_s=0.3, base_url=None):
    base_url = base_url or OLLAMA_URL
    if not is_local_url(base_url):
        return False
    try:
        return _read_json(base_url + "/api/version", None, timeout_s) is not None
    except Exception:
        return False


def ensure_ollama(stamp_path=None):
    """If Ollama is not answering, start it once (`open -g -j -a Ollama`, no waiting); at most one attempt per 120 s,
    across threads and processes (flock on the stamp file; the stamp is written before the spawn). True if launched."""
    stamp_path = stamp_path or LAUNCH_STAMP
    fd = None
    try:
        os.makedirs(os.path.dirname(stamp_path), exist_ok=True)
        fd = os.open(stamp_path, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            last = float(os.pread(fd, 64, 0).decode().strip())
        except ValueError:
            last = None
        if last is not None and time.time() - last < LAUNCH_EVERY_S:
            return False
        if _port_answers():
            return False
        os.ftruncate(fd, 0)
        os.pwrite(fd, str(time.time()).encode(), 0)
        subprocess.Popen(["open", "-g", "-j", "-a", "Ollama"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False
    finally:
        if fd is not None:
            try:
                os.close(fd)  # closing releases the flock
            except OSError:
                pass


# ---------------------------------------------------------------- examples

def load_examples():
    """[(sentence, label)] from the phrase tables, de-duplicated (first label wins)."""
    sys.path.insert(0, os.path.join(HERE, "tests"))
    sys.path.insert(0, HERE)
    try:
        import phrasings
        import typed_cases
        try:
            import matcher_examples
        except ImportError:
            matcher_examples = None
    finally:
        sys.path.pop(0)
        sys.path.pop(0)
    seen, out = set(), []

    def add(text, label):
        key = " ".join(str(text).lower().split())
        if key and key not in seen:
            seen.add(key)
            out.append((str(text).strip(), label))

    dicts = [phrasings.CASES] + [getattr(phrasings, n) for n in sorted(dir(phrasings)) if n.startswith("MORE")]
    for d in dicts:
        for cat, sentences in d.items():
            for s in sentences:
                add(s, MERGE.get(cat, cat))
    # Rule: typed_cases.ACTIONS["stuck"] holds "I'm stuck" sentences that the typed layer treats as an action. For the matcher
    # they are `stuck`, so they are labelled stuck (and added first, so they win a duplicate against any action entry).
    # Any other action sentence that is exactly (normalised) a stuck example is dropped from action too.
    for s in typed_cases.ACTIONS.get("stuck", []):
        add(s, "stuck")
    for verb, sentences in typed_cases.ACTIONS.items():
        if verb == "stuck":
            continue
        for s in sentences:
            add(s, "action")
    for s in typed_cases.NOT_ACTIONS:
        add(s, "noact")
    if matcher_examples:
        for label, sentences in matcher_examples.EXTRA.items():
            for s in sentences:
                add(s, label)
    return out


def _unit(v):
    """Unit-length copy of v, or None when it is not a finite, non-zero list of numbers."""
    if not isinstance(v, list) or not v:
        return None
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            return None
    n = math.sqrt(sum(x * x for x in v))
    if not math.isfinite(n) or n < 1e-9:
        return None
    return [x / n for x in v]


def _atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp%d-%d-%s" % (path, os.getpid(), threading.get_ident(), os.urandom(4).hex())
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _disp(x):
    return round(max(-1.0, min(1.0, x)), 4)


# ---------------------------------------------------------------- matcher

class Matcher:
    """Thread-safe. Construction starts one background loader (read the cache file, check the model digest, rebuild if
    needed). classify() only ever reads the cache that is already in memory; until then it returns None."""

    RETRY_S = 15  # after a failed load or build, classify waits this long before it starts another one

    def __init__(self, embed_fn=None, config=None, cache_path=None, log_path=None, examples=None, digest_fn=None):
        if config is None:
            try:
                with open(CONFIG_PATH) as f:
                    config = json.load(f).get("matcher") or {}
            except Exception:
                config = {}
        self.cfg = {**DEFAULTS, **config}
        self.url = self.cfg.get("url") or OLLAMA_URL
        self._url_ok = is_local_url(self.url)
        self._default_embed = embed_fn is None
        self.embed_fn = embed_fn or self._ollama
        self.digest_fn = digest_fn or (self._ollama_digest if self._default_embed else (lambda: ""))
        self.cache_path = cache_path or CACHE_PATH
        self.log_path = log_path or LOG_PATH
        self._examples = examples
        self._sig_value = None
        # cache state. _cache is only ever replaced whole, by _publish, under _build_lock.
        self._cache = None            # {"labels", "vecs" (unit length), "dim", "sig", "digest"}
        self._build_lock = threading.Lock()   # owns load, digest check, build and publish
        self._gen = 0                 # bumped at the start of every refresh (under _build_lock)
        self._pub_gen = 0             # generation of the published cache; an older one never replaces it
        self._loaded = threading.Event()
        self._bg_lock = threading.Lock()      # guards _bg_thread (at most one refresh thread at a time)
        self._bg_thread = None
        self._last_ok = False
        self._next_try = 0.0
        # query worker: one long-lived thread, at most one embed in flight
        self._q_cv = threading.Condition(threading.Lock())
        self._q_job = None
        self._q_busy = False
        self._q_thread = None
        self._disabled_until = 0.0
        self._log_lock = threading.Lock()     # held only by the log writer thread
        self._log_q = queue.Queue(LOG_QUEUE_MAX)
        try:
            threading.Thread(target=self._log_writer, name="matcher-log", daemon=True).start()
        except Exception:
            self._log_q = None                # no writer: log lines are dropped
        if self._active():
            self._kick(force=True)

    def _active(self):
        return bool(self.cfg.get("enabled")) and self._url_ok

    def _ollama(self, texts, model, timeout_s):
        return ollama_embed(texts, model, timeout_s, self.url)

    def _ollama_digest(self):
        return ollama_digest(self.cfg["model"], self.url)

    # -- cache
    def _embed(self, texts, timeout_s):
        """embed_fn on the texts with the configured prefix (applied to examples and queries alike)."""
        pre = self.cfg.get("prefix") or ""
        return self.embed_fn([pre + t for t in texts], self.cfg["model"], timeout_s)

    def _get_examples(self):
        if self._examples is None:
            self._examples = load_examples()
        return self._examples

    def _signature(self, examples):
        h = hashlib.sha256("\n".join("%s\t%s" % (l, t) for t, l in examples).encode()).hexdigest()
        return "v%d|%s|%s|%s" % (CACHE_FORMAT, self.cfg["model"], self.cfg.get("prefix") or "", h)

    def _sig(self):
        if self._sig_value is None:
            self._sig_value = self._signature(self._get_examples())
        return self._sig_value

    def _load_disk(self):
        """The cache file, normalised, if it is fully valid for the current model, prefix and examples; else None.
        Every vector is re-normalised here and only the unit vectors are kept, so a scaled vector in the file cannot skew
        a score. Non-finite or near-zero vectors make the whole file invalid."""
        try:
            with open(self.cache_path) as f:
                c = json.load(f)
            examples = self._get_examples()
            sig = self._sig()
            if not isinstance(c, dict) or not isinstance(c.get("digest", ""), str):
                return None
            digest = c.get("digest", "")
            if c.get("sig") != sig or c.get("key") != "%s|%s" % (sig, digest):
                return None
            labels, raw = c.get("labels"), c.get("vecs")
            if not isinstance(labels, list) or not isinstance(raw, list):
                return None
            if not (len(raw) == len(labels) == len(examples)) or labels != [l for _, l in examples]:
                return None
            vecs = []
            for v in raw:
                u = _unit(v)
                if u is None or (vecs and len(u) != len(vecs[0])):
                    return None
                vecs.append(u)
            if not vecs:
                return None
            return {"labels": labels, "vecs": vecs, "dim": len(vecs[0]), "sig": sig, "digest": digest}
        except Exception:
            return None

    def _publish(self, c, gen):
        """Make c the live cache unless a newer generation is already live. Call with _build_lock held."""
        if gen < self._pub_gen:
            return False
        self._pub_gen = gen
        self._cache = c
        self._loaded.set()
        return True

    def _kick(self, force=False):
        """The running refresh thread, or a new one. Without force, a new one is not started within RETRY_S of a failure."""
        with self._bg_lock:
            t = self._bg_thread
            if t is not None and t.is_alive():
                return t
            if not force and time.time() < self._next_try:
                return None
            t = threading.Thread(target=self._refresh_body, name="matcher-loader", daemon=True)
            self._bg_thread = t
            t.start()
            return t

    def _refresh_body(self):
        ok = False
        try:
            ok = self._refresh()
        except Exception:
            ok = False
        self._last_ok = ok
        if not ok:
            self._next_try = time.time() + self.RETRY_S

    def _refresh(self):
        """Load the cache file, check the model digest, rebuild if needed, publish. The slow part; never on the hot path.
        The whole thing holds _build_lock, so a load or build can never interleave with another one."""
        if not self._active():
            return False
        with self._build_lock:
            self._gen += 1
            gen = self._gen
            try:
                examples = self._get_examples()
                sig = self._sig()
                cur = self._cache
                if cur is None or cur["sig"] != sig:
                    disk = self._load_disk()
                    if disk is not None:
                        self._publish(disk, gen)
                        cur = disk
                try:
                    got_digest = self.digest_fn()
                except Exception:
                    got_digest = None
                # None means the check failed (Ollama down). Keep serving the cache, but report not-ok so the
                # check runs again every RETRY_S and a re-pulled model is noticed once Ollama is back.
                unknown = got_digest is None
                digest = got_digest or ""
                if cur and cur["sig"] == sig and (unknown or not digest or cur["digest"] == digest):
                    return not unknown
                vecs = []
                for i in range(0, len(examples), BATCH):
                    batch = examples[i:i + BATCH]
                    got = self._embed([t for t, _ in batch], BUILD_TIMEOUT_S)
                    if not got or len(got) != len(batch):
                        if self._default_embed:
                            ensure_ollama()
                        return False
                    for v in got:
                        u = _unit(v)
                        if u is None or (vecs and len(u) != len(vecs[0])):
                            return False
                        vecs.append(u)  # full precision: rounding could move a cosine across the threshold
                if not vecs:
                    return False
                labels = [l for _, l in examples]
                c = {"labels": labels, "vecs": vecs, "dim": len(vecs[0]), "sig": sig, "digest": digest}
                if not self._publish(c, gen):
                    return True
                try:
                    _atomic_write(self.cache_path, {"key": "%s|%s" % (sig, digest), "sig": sig, "digest": digest, "model": self.cfg["model"],
                                                    "prefix": self.cfg.get("prefix") or "", "labels": labels, "vecs": vecs})
                except Exception:
                    pass  # read-only state dir: the cache still works in memory
                return not unknown  # built without a known digest: check again later
            except ModelMissing:
                self._disable("model-missing")
                return False

    def warm(self):
        """Make the cache ready now and wait for it (a one-off, slow the first time). Joins a refresh that is already
        running instead of starting a second one. True when ready. Never used by classify."""
        try:
            if not self._active():
                return False
            t = self._kick(force=True)
            t.join()
            return self._last_ok and self._cache is not None
        except Exception:
            return False

    def wait_loaded(self, timeout=None):
        """Wait until a cache is in memory (scripts and tests). True when it is."""
        return self._loaded.wait(timeout)

    def _disable(self, why):
        self._disabled_until = time.time() + DISABLE_S
        self._log_raw({"ts": round(time.time(), 1), "event": why, "model": self.cfg["model"], "disabled_s": DISABLE_S})

    # -- query worker
    def _submit(self, text, deadline, cache):
        """Hand one query to the worker. None when an embed is already in flight (nothing is queued)."""
        with self._q_cv:
            if self._q_busy:
                return None
            job = {"text": text, "deadline": deadline, "cache": cache, "done": threading.Event(), "out": (None, [])}
            self._q_busy = True
            self._q_job = job
            if self._q_thread is None or not self._q_thread.is_alive():
                t = threading.Thread(target=self._worker, name="matcher-query", daemon=True)
                try:
                    t.start()
                except Exception:
                    self._q_busy = False    # no worker: leave nothing behind, so a later call can try again
                    self._q_job = None
                    return None
                self._q_thread = t
            self._q_cv.notify()
            return job

    def _worker(self):
        while True:
            with self._q_cv:
                while self._q_job is None:
                    self._q_cv.wait()
                job, self._q_job = self._q_job, None
            try:
                budget = max(0.01, job["deadline"] - time.monotonic())
                v = self._embed([job["text"]], budget)
                if not v:
                    if self._default_embed:
                        ensure_ollama()
                elif time.monotonic() < job["deadline"]:   # late: the caller has gone, skip the scoring
                    job["out"] = self._score(v[0], job["cache"])
            except ModelMissing:
                self._disable("model-missing")  # even when the reply came after the caller gave up
            except Exception:
                job["out"] = (None, [])
            finally:
                with self._q_cv:
                    self._q_busy = False
                job["done"].set()

    def wait_idle(self, timeout=None):
        """Wait until no query embed is in flight (tests). True when idle."""
        end = time.monotonic() + (timeout if timeout is not None else 1e9)
        while time.monotonic() < end:
            with self._q_cv:
                if not self._q_busy:
                    return True
            time.sleep(0.005)
        return False

    # -- classify
    def classify(self, text):
        """{label, score, margin, routable, top} or None. Never raises, never takes longer than timeout_ms (the log
        line is handed to a background writer), never touches the disk cache or Ollama's version endpoint, makes at most
        one embed call."""
        try:
            t0 = time.monotonic()
            result, top = None, []
            try:
                # the wait ends SLACK_S early, so queueing the log line and the thread wake-up still fit inside timeout_ms
                result, top = self._classify(text, t0 + float(self.cfg["timeout_ms"]) / 1000.0 - SLACK_S)
            except Exception:
                result, top = None, []
            self._log(text, top, result, int((time.monotonic() - t0) * 1000))
            return result
        except Exception:
            return None

    def _classify(self, text, deadline):
        if not isinstance(text, str) or not self._active():
            return None, []
        text = text.strip()
        if not text or len(text) > MAX_CHARS or "\n" in text or "\r" in text:
            return None, []
        if time.time() < self._disabled_until:
            return None, []
        c = self._cache
        if c is None:
            self._kick()           # no-op while the loader runs or just failed
            return None, []
        if not self._last_ok:
            self._kick()           # the published cache may be stale (a rebuild failed): retry every RETRY_S, keep serving it
        job = self._submit(text, deadline, c)
        if job is None:
            return None, []
        if not job["done"].wait(max(0.0, deadline - time.monotonic())):
            return None, []
        return job["out"]

    def _score(self, vec, c):
        """(result or None, top) for one query vector against cache c. Runs on the worker, inside the deadline."""
        cfg = self.cfg
        q = _unit(vec)
        if q is None or len(q) != c["dim"]:
            return None, []
        allsims = sorted(((sum(a * b for a, b in zip(q, v)), l) for v, l in zip(c["vecs"], c["labels"])), reverse=True)
        sims = allsims[:max(1, int(cfg["k"]))]
        scores = {}
        for s, l in sims:
            scores[l] = s if l not in scores else max(scores[l], s)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top = [[l, _disp(s)] for l, s in ranked]
        best, bs = ranked[0]
        # margin = best score minus the nearest example of ANY other label (not just within the k): this is what the
        # held-out tuning (matcher_eval.py) measured, so the tuned numbers mean the same thing here. Unrounded.
        second = next((s for s, l in allsims if l != best), 0.0)
        gap = bs - second
        if bs >= cfg["threshold"] and gap >= cfg["margin"]:
            # a tie, or a gap of a rounding error (gap <= MARGIN_EPS), is never routable, whatever margin the config allows
            routable = gap > MARGIN_EPS and best in (set(cfg.get("route_labels") or []) & SAFE)
            return {"label": best, "score": _disp(bs), "margin": _disp(gap), "routable": routable, "top": top}, top
        return None, top

    # -- log
    def _log_raw(self, entry):
        """Hand one line to the log writer thread. Never blocks and never raises: when the queue is full (or there is
        no writer) the line is dropped."""
        try:
            self._log_q.put_nowait(entry)
        except Exception:
            pass

    def _log_writer(self):
        while True:
            item = self._log_q.get()
            if isinstance(item, threading.Event):
                item.set()             # flush_log marker: every line before it is written
                continue
            self._write_line(item)

    def flush_log(self, timeout=5):
        """Wait until every line queued so far is written (scripts and tests). True when done."""
        try:
            ev = threading.Event()
            self._log_q.put(ev, timeout=timeout)
            return ev.wait(timeout)
        except Exception:
            return False

    def _write_line(self, entry):
        """Append one line (writer thread only). Never grows the file past LOG_MAX_BYTES: when it is full it rotates to
        .1, and when rotating fails (for example .1 is a directory) the line is dropped."""
        try:
            line = json.dumps(entry) + "\n"
            with self._log_lock:
                os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
                try:
                    size = os.path.getsize(self.log_path)
                except OSError:
                    size = 0
                if size + len(line) > LOG_MAX_BYTES:
                    try:
                        os.replace(self.log_path, self.log_path + ".1")
                    except OSError:
                        return
                    try:
                        if os.path.getsize(self.log_path) + len(line) > LOG_MAX_BYTES:
                            return
                    except OSError:
                        pass
                with open(self.log_path, "a") as f:
                    f.write(line)
        except Exception:
            pass

    def _log(self, text, top, result, ms):
        """Log policy: the sentence's text is never stored, only its length and a 12-character hash, plus the top labels
        with their scores and the outcome."""
        try:
            entry = {"ts": round(time.time(), 1), "top": top[:3], "result": result["label"] if result else None,
                     "routable": bool(result and result.get("routable")), "ms": ms}
            if isinstance(text, str):
                entry["len"] = len(text)
                # Keyed with a random per-process secret, so a short passphrase cannot be found by hashing guesses.
                # Repeats still group together within one server run.
                entry["hash"] = hmac.new(_LOG_KEY, text.encode("utf-8", "replace"), hashlib.sha256).hexdigest()[:12]
            else:
                entry["type"] = type(text).__name__
            self._log_raw(entry)
        except Exception:
            pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('usage: python3 command/matcher.py "<sentence>"')
    m = Matcher()
    print("examples: %d, labels: %s" % (len(load_examples()), ", ".join("%s=%d" % kv for kv in sorted({l: sum(1 for _, x in load_examples() if x == l) for l in LABELS}.items()))), file=sys.stderr)
    if not m.warm():
        print("could not build the example cache (is Ollama running with %s pulled?)" % m.cfg["model"], file=sys.stderr)
    r = m.classify(" ".join(sys.argv[1:]))
    print(json.dumps(r) if r else "None (not sure, or Ollama unavailable)")
