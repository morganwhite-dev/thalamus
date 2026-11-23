"""command/matcher.py with a fake embedder (bag of words), so no Ollama is needed. One live test skips unless Ollama answers."""
import http.server
import json
import math
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import matcher  # noqa: E402

DIM = 64


def fake_embed(texts, model, timeout_s):
    """Deterministic bag-of-words vectors: each word adds weight to one of DIM slots."""
    out = []
    for t in texts:
        v = [0.0] * DIM
        for w in t.lower().replace("?", " ").split():
            v[sum(ord(c) * (i + 1) for i, c in enumerate(w)) % DIM] += 1.0
        out.append(v)
    return out


EXAMPLES = [
    ("what should i do now", "now"), ("what do i do next", "now"),
    ("whats due friday", "schedule"), ("what is due this week", "schedule"),
    ("done", "action"), ("mark it done", "action"),
    ("tell me about volcanoes", "general"),
]


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cache = os.path.join(self.d, "cache.json")
        self.log = os.path.join(self.d, "log.jsonl")
        self.calls = []

    def make(self, embed=None, examples=EXAMPLES, warm=True, digest="", **cfg):
        """A matcher with a counting fake embedder. classify never builds the cache itself, so it is warmed here."""
        def counting(texts, model, timeout_s):
            self.calls.append(list(texts))
            return (embed or fake_embed)(texts, model, timeout_s)
        config = {"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": "", **cfg}
        m = matcher.Matcher(embed_fn=counting, config=config, cache_path=self.cache, log_path=self.log, examples=examples,
                            digest_fn=lambda: digest)
        if warm:
            m.warm()
        return m

    def settle(self, m):
        t = m._bg_thread
        if t:
            t.join(10)


class Labels(unittest.TestCase):
    def test_label_set_and_free_jev_merge(self):
        ex = matcher.load_examples()
        labels = {l for _, l in ex}
        self.assertEqual(labels, set(matcher.LABELS))
        self.assertNotIn("free", labels)
        self.assertNotIn("jev", labels)
        import phrasings
        self.assertIn((phrasings.CASES["free"][0], "general"), ex)
        self.assertIn((phrasings.CASES["jev"][0], "general"), ex)

    def test_actions_and_not_actions_labels(self):
        import typed_cases
        ex = dict(matcher.load_examples())
        self.assertEqual(ex[typed_cases.ACTIONS["pin"][0]], "action")
        self.assertEqual(ex[typed_cases.NOT_ACTIONS[1]], "noact")

    def test_extra_examples_are_included(self):
        import matcher_examples
        ex = dict(matcher.load_examples())
        for label, sentences in matcher_examples.EXTRA.items():
            self.assertEqual(ex[sentences[0]], label)
        self.assertGreaterEqual(len(matcher_examples.EXTRA["general"]), 40)

    def test_stuck_sentences_are_not_action(self):
        import typed_cases
        ex = dict(matcher.load_examples())
        for sent in typed_cases.ACTIONS["stuck"]:
            self.assertNotEqual(ex.get(sent), "action", sent)
        self.assertEqual(ex[typed_cases.ACTIONS["stuck"][0]], "stuck")
        self.assertEqual(ex[typed_cases.ACTIONS["pin"][0]], "action")

    def test_no_duplicate_sentences(self):
        keys = [" ".join(t.lower().split()) for t, _ in matcher.load_examples()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_more_tables_are_included(self):
        import phrasings
        texts = {t for t, _ in matcher.load_examples()}
        self.assertIn(phrasings.MORE["now"][0], texts)
        self.assertIn(phrasings.MORE7["capture"][0], texts)


class Cache(Base):
    def test_builds_once_then_loads(self):
        m = self.make()
        self.assertTrue(m.warm())
        built = len(self.calls)
        self.assertGreaterEqual(built, 1)
        self.assertTrue(os.path.exists(self.cache))
        m2 = self.make()
        self.assertIsNotNone(m2.classify("what should i do now"))
        self.assertEqual(len(self.calls), built + 1)  # only the query was embedded

    def test_rebuilds_when_model_changes(self):
        self.make().warm()
        n = len(self.calls)
        self.make(model="other-model").warm()
        self.assertGreater(len(self.calls), n)
        self.assertEqual(json.load(open(self.cache))["model"], "other-model")

    def test_rebuilds_when_examples_change(self):
        self.make().warm()
        n = len(self.calls)
        self.make(examples=EXAMPLES + [("pin it", "action")]).warm()
        self.assertGreater(len(self.calls), n)
        self.assertEqual(len(json.load(open(self.cache))["labels"]), len(EXAMPLES) + 1)

    def test_corrupt_cache_rebuilds(self):
        open(self.cache, "w").write("{not json")
        self.assertTrue(self.make().warm())
        json.load(open(self.cache))

    def test_batches(self):
        many = [("sentence %d" % i, "now") for i in range(matcher.BATCH * 2 + 5)]
        self.make(examples=many).warm()
        self.assertEqual([len(c) for c in self.calls], [matcher.BATCH, matcher.BATCH, 5])

    def test_failed_build_is_not_cached(self):
        m = self.make(embed=lambda *a: None)
        self.assertFalse(m.warm())
        self.assertFalse(os.path.exists(self.cache))
        self.assertIsNone(m.classify("what should i do now"))


class Prefix(Base):
    def test_prefix_on_examples_and_query(self):
        m = self.make(prefix="classification: ")
        m.classify("what should i do now")
        sent = [t for call in self.calls for t in call]
        self.assertTrue(all(t.startswith("classification: ") for t in sent))
        self.assertEqual(sent[-1], "classification: what should i do now")

    def test_no_prefix_when_configured_empty(self):
        self.make(prefix="").classify("what should i do now")
        self.assertTrue(all(not t.startswith("classification:") for call in self.calls for t in call))

    def test_cache_key_includes_prefix_and_model(self):
        self.make(prefix="").warm()
        n = len(self.calls)
        self.make(prefix="").warm()
        self.assertEqual(len(self.calls), n)  # same prefix: loaded from cache
        self.make(prefix="classification: ").warm()
        self.assertGreater(len(self.calls), n)  # new prefix: rebuilt
        key = json.load(open(self.cache))["key"]
        self.assertIn("classification: ", key)
        self.assertIn("nomic-embed-text", self.make(model="nomic-embed-text")._signature(EXAMPLES))

    def test_defaults(self):
        d = matcher.DEFAULTS
        self.assertEqual((d["model"], d["prefix"], d["threshold"], d["margin"], d["k"]), ("nomic-embed-text", "classification: ", 0.85, 0.02, 5))
        import json as _j
        cfg = _j.load(open(matcher.CONFIG_PATH))["matcher"]
        self.assertEqual(cfg["route_labels"], ["now", "schedule", "project", "reminders", "tiny", "general"])


class Routable(Base):
    def test_routable_only_for_route_labels(self):
        m = self.make(route_labels=["now", "schedule"])
        self.assertTrue(m.classify("what should i do now")["routable"])
        r = m.classify("mark it done")
        self.assertEqual(r["label"], "action")
        self.assertFalse(r["routable"])

    def test_default_route_labels_exclude_risky(self):
        for l in ("action", "capture", "park", "stuck", "lookup", "noact"):
            self.assertNotIn(l, matcher.DEFAULTS["route_labels"])

    def test_empty_route_labels_routes_nothing(self):
        self.assertFalse(self.make(route_labels=[]).classify("what should i do now")["routable"])


class Thresholds(Base):
    def test_clear_match(self):
        r = self.make().classify("what should i do now")
        self.assertEqual(r["label"], "now")
        self.assertGreaterEqual(r["score"], 0.5)
        self.assertEqual(r["top"][0][0], "now")

    def test_below_threshold_is_none(self):
        self.assertIsNone(self.make().classify("zebra giraffe okapi"))

    def test_high_threshold_rejects(self):
        self.assertIsNone(self.make(threshold=0.999).classify("what should i do"))

    def test_margin_rejects_a_tie(self):
        ex = [("alpha beta", "now"), ("alpha beta", "schedule")]
        m = self.make(examples=ex, margin=0.05)
        self.assertIsNone(m.classify("alpha beta"))
        self.assertEqual(self.make(examples=ex, margin=0.0).classify("alpha beta")["label"] in ("now", "schedule"), True)

    def test_margin_is_gap_to_nearest_other_label(self):
        # all neighbours in the k share one label, yet the margin still measures the nearest example of another label
        r = self.make(k=1).classify("whats due friday")
        self.assertEqual(r["label"], "schedule")
        self.assertEqual(len(r["top"]), 1)
        ex = [("alpha beta gamma", "now"), ("alpha beta delta", "schedule"), ("alpha beta gamma", "now")]
        r2 = self.make(examples=ex, k=1, margin=0.0).classify("alpha beta gamma")
        self.assertLess(r2["margin"], r2["score"])  # the schedule example is close, so the gap is small

    def test_k_limits_neighbours(self):
        r = self.make(k=1).classify("what should i do now")
        self.assertEqual(len(r["top"]), 1)


class Declines(Base):
    def test_disabled(self):
        self.assertIsNone(self.make(enabled=False).classify("what should i do now"))
        self.assertEqual(self.calls, [])  # warm() is a no-op when disabled

    def test_empty_long_multiline_nonstring(self):
        m = self.make()
        n = len(self.calls)
        for bad in ["", "   ", "x " * 300, "line one\nline two", None, 42]:
            self.assertIsNone(m.classify(bad), repr(bad))
        self.assertEqual(len(self.calls), n)

    def test_ollama_down(self):
        m = self.make()  # warm: the cache is in memory, so the failing call is the query embed itself
        self.assertIsNotNone(m.classify("what should i do now"))
        tried = []
        m.embed_fn = lambda texts, model, t: tried.append(texts) and None
        self.assertIsNone(m.classify("what should i do now"))
        self.assertEqual(len(tried), 1)

    def test_slow_embedding_is_discarded_within_budget(self):
        m = self.make()
        def slow(texts, model, timeout_s):
            time.sleep(1.5)
            return fake_embed(texts, model, timeout_s)
        m.embed_fn = slow
        m.cfg["timeout_ms"] = 100
        t = time.time()
        self.assertIsNone(m.classify("what should i do now"))
        self.assertLess(time.time() - t, 0.4)
        self.assertTrue(m.wait_idle(5))  # the late embed finishes in the background and is thrown away
        m.embed_fn = fake_embed
        m.cfg["timeout_ms"] = 2000
        self.assertIsNotNone(m.classify("what should i do now"))

    def test_never_raises(self):
        def boom(*a):
            raise RuntimeError("bang")
        m = self.make(embed=boom)
        self.assertIsNone(m.classify("what should i do now"))
        bad_cache = self.make()
        bad_cache.cache_path = os.path.join(self.d, "no", "such", "dir", "c.json")
        bad_cache.log_path = "/nonexistent-root-dir/x/log.jsonl"
        self.assertIsNotNone(bad_cache.classify("what should i do now"))

    def test_vector_size_mismatch(self):
        m = self.make()
        m.warm()
        m.embed_fn = lambda texts, model, t: [[1.0, 2.0] for _ in texts]
        self.assertIsNone(m.classify("what should i do now"))


class Launch(unittest.TestCase):
    def test_rate_limited(self):
        stamp = os.path.join(tempfile.mkdtemp(), "stamp")
        with mock.patch.object(matcher, "_port_answers", return_value=False), mock.patch.object(matcher.subprocess, "Popen") as popen:
            self.assertTrue(matcher.ensure_ollama(stamp))
            self.assertFalse(matcher.ensure_ollama(stamp))
            self.assertEqual(popen.call_count, 1)
            self.assertEqual(popen.call_args[0][0], ["open", "-g", "-j", "-a", "Ollama"])
            old = time.time() - matcher.LAUNCH_EVERY_S - 1
            open(stamp, "w").write(str(old))
            self.assertTrue(matcher.ensure_ollama(stamp))
            self.assertEqual(popen.call_count, 2)

    def test_not_launched_when_running(self):
        stamp = os.path.join(tempfile.mkdtemp(), "stamp")
        with mock.patch.object(matcher, "_port_answers", return_value=True), mock.patch.object(matcher.subprocess, "Popen") as popen:
            self.assertFalse(matcher.ensure_ollama(stamp))
            popen.assert_not_called()

    def test_classify_with_ollama_down_launches_and_returns_none(self):
        d = tempfile.mkdtemp()
        with mock.patch.object(matcher, "ollama_embed", return_value=None), mock.patch.object(matcher, "ollama_digest", return_value=None), \
                mock.patch.object(matcher, "ensure_ollama") as ens:
            m = matcher.Matcher(config={}, cache_path=os.path.join(d, "c.json"), log_path=os.path.join(d, "l.jsonl"), examples=EXAMPLES)
            m._bg_thread.join(10)  # the loader started at construction finds Ollama down and launches it
            self.assertIsNone(m.classify("what should i do now"))  # no cache, and no second load within RETRY_S
            self.assertIsNone(m._bg_thread.join(0.5))
            ens.assert_called_once()

    def test_ollama_embed_returns_none_on_error(self):
        with mock.patch.object(matcher.http.client.HTTPConnection, "connect", side_effect=OSError("down")):
            self.assertIsNone(matcher.ollama_embed(["a"], "all-minilm", 0.1))


class Log(Base):
    def test_one_line_per_call(self):
        m = self.make()
        m.classify("what should i do now")
        m.classify("zebra giraffe okapi")
        m.classify("")
        self.assertTrue(m.flush_log())
        lines = [json.loads(l) for l in open(self.log)]
        self.assertEqual(len(lines), 3)
        self.assertNotIn("text", lines[0])
        self.assertEqual(lines[0]["len"], len("what should i do now"))
        self.assertEqual(lines[0]["result"], "now")
        self.assertTrue(lines[0]["routable"])
        self.assertIsNone(lines[1]["result"])
        self.assertTrue(lines[0]["top"])
        for l in lines:
            self.assertIn("ms", l)


class Stub:
    """A local HTTP server standing in for Ollama. mode: "ok" (embeddings), "404", "trickle" (body: one byte every 50 ms),
    "trickle-status" (the status line and headers, one byte every 20 ms)."""

    def __init__(self, mode="ok"):
        outer = self
        self.hits = 0

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                outer.hits += 1
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                if mode == "404":
                    self.send_response(404)
                    self.end_headers()
                    return
                if mode == "trickle-status":
                    try:  # no status line yet: send it, then a header, one byte every 20 ms (about 4 s in all)
                        for ch in b"HTTP/1.1 200 OK\r\nX-Pad: " + b"a" * 200:
                            self.wfile.write(bytes([ch]))
                            self.wfile.flush()
                            time.sleep(0.02)
                    except OSError:
                        pass
                    self.close_connection = True
                    return
                if mode == "trickle-chunked-close":
                    # Codex repro: a chunked reply with Connection: close, whose first chunk-size line trickles in.
                    # getresponse() detaches the socket from the connection, so the watchdog must hold its own copy.
                    self.send_response(200)
                    self.send_header("Transfer-Encoding", "chunked")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    try:
                        for _ in range(150):   # about 3 s of "0000..." with no newline
                            self.wfile.write(b"0")
                            self.wfile.flush()
                            time.sleep(0.02)
                    except OSError:
                        pass
                    self.close_connection = True
                    return
                if mode == "trickle":
                    self.send_response(200)
                    self.send_header("Content-Length", "100000")
                    self.end_headers()
                    try:
                        for _ in range(100):
                            self.wfile.write(b" ")
                            self.wfile.flush()
                            time.sleep(0.05)
                    except OSError:
                        pass
                    return
                out = json.dumps({"embeddings": fake_embed(body["input"], "m", 1)}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            do_GET = do_POST

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class SafeLabels(Base):
    def test_config_cannot_widen_route_labels(self):
        self.assertEqual(matcher.SAFE, {"now", "schedule", "project", "reminders", "tiny", "general"})
        m = self.make(route_labels=["now", "action", "capture", "park", "stuck", "lookup", "noact"])
        r = m.classify("mark it done")
        self.assertEqual(r["label"], "action")
        self.assertFalse(r["routable"])
        self.assertTrue(m.classify("what should i do now")["routable"])


class Budget(Base):
    def test_no_version_probe_and_one_embed_call(self):
        m = self.make()
        n = len(self.calls)
        with mock.patch.object(matcher, "_port_answers", side_effect=AssertionError("probe on the hot path")):
            self.assertIsNotNone(m.classify("what should i do now"))
        self.assertEqual(len(self.calls), n + 1)

    def test_trickling_server_cannot_extend_the_budget(self):
        self.make()  # writes a valid cache file
        stub = Stub("trickle")
        try:
            m = matcher.Matcher(config={"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": "", "timeout_ms": 150, "url": stub.url},
                                cache_path=self.cache, log_path=self.log, examples=EXAMPLES)
            t = time.time()
            self.assertIsNone(m.classify("what should i do now"))
            self.assertLess(time.time() - t, 0.4)
        finally:
            stub.close()

    def test_missing_cache_never_builds_on_the_hot_path(self):
        started = threading.Event()
        def slow_build(texts, model, timeout_s):
            started.set()
            if len(texts) > 1:
                time.sleep(0.6)  # only the example batch is slow, not the one-sentence query
            return fake_embed(texts, model, timeout_s)
        m = self.make(embed=slow_build, warm=False)
        t = time.time()
        for _ in range(5):
            self.assertIsNone(m.classify("what should i do now"))
        self.assertLess(time.time() - t, 0.4)
        self.settle(m)
        built = [c for c in self.calls if len(c) > 1]
        self.assertEqual(len(built), 1)  # one warm thread, one batch (7 examples), not one per classify
        self.assertIsNotNone(m.classify("what should i do now"))


class BadCache(Base):
    def _corrupt(self, fn):
        self.make()
        c = json.load(open(self.cache))
        fn(c)
        json.dump(c, open(self.cache, "w"))

    def _expect_rebuild(self, fn):
        self._corrupt(fn)
        n = len(self.calls)
        m = self.make(warm=False)
        self.settle(m)
        self.assertGreater(len(self.calls), n)  # discarded and rebuilt in the background
        self.assertIsNotNone(m.classify("what should i do now"))

    def test_fewer_vectors_than_labels(self):
        self._expect_rebuild(lambda c: c["vecs"].pop())

    def test_more_labels_than_vectors(self):
        self._expect_rebuild(lambda c: c["labels"].append("action"))

    def test_nan_vector(self):
        self._expect_rebuild(lambda c: c["vecs"][0].__setitem__(0, float("nan")))

    def test_mixed_dimension(self):
        self._expect_rebuild(lambda c: c["vecs"][2].pop())

    def test_zero_vector(self):
        self._expect_rebuild(lambda c: c["vecs"].__setitem__(1, [0.0] * len(c["vecs"][1])))

    def test_wrong_key(self):
        self._expect_rebuild(lambda c: c.__setitem__("key", "other"))

    def test_swapped_labels(self):
        self._expect_rebuild(lambda c: c["labels"].reverse())

    def test_bad_query_vectors_are_none(self):
        m = self.make(threshold=0.0, margin=0.0)
        for bad in ([0.0] * DIM, [float("nan")] * DIM, [float("inf")] * DIM, [1.0] * (DIM + 1), [1.0, 2.0]):
            m.embed_fn = lambda texts, model, t, bad=bad: [bad for _ in texts]
            self.assertIsNone(m.classify("what should i do now"), bad[:2])


class Network(unittest.TestCase):
    def test_no_proxy_for_localhost(self):
        stub, proxy = Stub("ok"), Stub("ok")
        old = {k: os.environ.get(k) for k in ("http_proxy", "HTTP_PROXY")}
        try:
            os.environ["http_proxy"] = os.environ["HTTP_PROXY"] = proxy.url
            self.assertEqual(len(matcher.ollama_embed(["hello"], "m", 2, stub.url)), 1)
            self.assertEqual(stub.hits, 1)
            self.assertEqual(proxy.hits, 0)
        finally:
            for k, v in old.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            stub.close()
            proxy.close()

    def test_non_local_url_refused(self):
        for url in ("http://example.com:11434", "http://10.0.0.5:11434", "http://127.0.0.1.evil.com:80"):
            with mock.patch.object(matcher.http.client, "HTTPConnection") as hc:
                self.assertIsNone(matcher.ollama_embed(["a"], "m", 1, url))
                self.assertFalse(matcher._port_answers(0.1, url))
                self.assertIsNone(matcher._read_json(url + "/api/tags", None, 0.1))
                hc.assert_not_called()
        calls = []
        d = tempfile.mkdtemp()
        m = matcher.Matcher(embed_fn=lambda *a: calls.append(a), config={"url": "http://example.com"}, cache_path=os.path.join(d, "c"),
                            log_path=os.path.join(d, "l"), examples=EXAMPLES)
        self.assertIsNone(m.classify("what should i do now"))
        self.assertFalse(m.warm())
        self.assertEqual(calls, [])
        for ok in ("http://127.0.0.1:1", "http://localhost:1", "http://[::1]:1"):
            self.assertTrue(matcher.is_local_url(ok), ok)

    def test_404_means_model_missing(self):
        stub = Stub("404")
        try:
            with self.assertRaises(matcher.ModelMissing):
                matcher.ollama_embed(["a"], "m", 2, stub.url)
        finally:
            stub.close()


class LaunchRace(unittest.TestCase):
    def test_threads_spawn_exactly_once(self):
        stamp = os.path.join(tempfile.mkdtemp(), "stamp")
        results = []
        barrier = threading.Barrier(8)
        def go():
            barrier.wait()
            results.append(matcher.ensure_ollama(stamp))
        with mock.patch.object(matcher, "_port_answers", side_effect=lambda *a, **k: time.sleep(0.05) or False), \
                mock.patch.object(matcher.subprocess, "Popen") as popen:
            ts = [threading.Thread(target=go) for _ in range(8)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(results.count(True), 1)
        self.assertEqual(popen.call_args[0][0], ["open", "-g", "-j", "-a", "Ollama"])
        self.assertFalse(popen.call_args[1].get("shell"))


class LogLimits(Base):
    def test_long_text_not_embedded_and_not_logged(self):
        m = self.make()
        n = len(self.calls)
        long = "word " * 120  # 600 chars
        self.assertIsNone(m.classify(long))
        self.assertEqual(len(self.calls), n)
        self.assertTrue(m.flush_log())
        line = json.loads(open(self.log).read().splitlines()[-1])
        self.assertNotIn("text", line)
        self.assertEqual(line["len"], len(long))

    def test_text_over_200_chars_is_hashed_not_logged(self):
        m = self.make()
        text = "volcano " * 40  # 320 chars, embedded
        m.classify(text)
        self.assertTrue(m.flush_log())
        line = json.loads(open(self.log).read().splitlines()[-1])
        self.assertNotIn("text", line)
        self.assertEqual(line["len"], len(text))
        self.assertEqual(len(line["hash"]), 12)

    def test_log_rotates_at_1mb(self):
        m = self.make()
        open(self.log, "w").write("x" * (matcher.LOG_MAX_BYTES + 10))
        m.classify("what should i do now")
        self.assertTrue(m.flush_log())
        self.assertTrue(os.path.exists(self.log + ".1"))
        self.assertLess(os.path.getsize(self.log), 2000)
        self.assertFalse(os.path.exists(self.log + ".2"))


class Digest(Base):
    def test_digest_change_rebuilds_and_is_in_the_key(self):
        self.make(digest="d1")
        self.assertTrue(json.load(open(self.cache))["key"].endswith("|d1"))
        n = len(self.calls)
        self.make(digest="d1")
        self.assertEqual(len(self.calls), n)
        self.make(digest="d2")
        self.assertGreater(len(self.calls), n)
        self.assertTrue(json.load(open(self.cache))["key"].endswith("|d2"))

    def test_digest_checked_in_background_after_hot_path_load(self):
        self.make(digest="d1")
        n = len(self.calls)
        gate = threading.Event()
        def counting(texts, model, t):
            self.calls.append(list(texts))
            return fake_embed(texts, model, t)
        m = matcher.Matcher(embed_fn=counting, config={"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": ""}, cache_path=self.cache,
                            log_path=self.log, examples=EXAMPLES, digest_fn=lambda: gate.wait(5) and "d2")
        self.assertTrue(m.wait_loaded(5))
        self.assertEqual(m._cache["digest"], "d1")
        self.assertIsNotNone(m.classify("what should i do now"))  # old cache still serves while it verifies
        gate.set()
        self.settle(m)
        self.assertEqual(m._cache["digest"], "d2")
        self.assertGreater(len(self.calls), n + 1)
        self.assertTrue(json.load(open(self.cache))["key"].endswith("|d2"))

    def test_temp_names_are_unique_per_thread(self):
        target = os.path.join(self.d, "w.json")
        names = []
        real = os.replace
        def spy(a, b):
            names.append(a)
            return real(a, b)
        with mock.patch.object(matcher.os, "replace", side_effect=spy):
            ts = [threading.Thread(target=matcher._atomic_write, args=(target, {"i": i})) for i in range(8)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        self.assertEqual(len(set(names)), 8)
        json.load(open(target))
        self.assertEqual([f for f in os.listdir(self.d) if ".tmp" in f], [])


class Unrounded(Base):
    def test_threshold_compares_unrounded(self):
        ex = [("a", "now"), ("b", "schedule")]
        embed = lambda texts, model, t: [[1.0, 0.0] if x.strip() == "a" else [0.0, 1.0] if x.strip() == "b" else [1.0, 0.0045] for x in texts]
        # cosine is 0.99998987: rounds to 1.0 for display but is below a threshold of 1.0
        self.assertIsNone(self.make(embed=embed, examples=ex, threshold=1.0, margin=0.0).classify("q"))
        r = self.make(embed=embed, examples=ex, threshold=0.9999, margin=0.0).classify("q")
        self.assertEqual(r["score"], 1.0)

    def test_negative_scores_shown_honestly(self):
        ex = [("a", "now")]
        embed = lambda texts, model, t: [[1.0, 0.0] if x.strip() == "a" else [-1.0, 0.0] for x in texts]
        r = self.make(embed=embed, examples=ex, threshold=-2.0, margin=-5.0, k=1).classify("q")
        self.assertEqual(r["score"], -1.0)
        self.assertEqual(r["top"][0][1], -1.0)


class MissingModel(Base):
    def test_disabled_for_ten_minutes_and_logged_once(self):
        m = self.make()
        n = [0]
        def gone(texts, model, t):
            n[0] += 1
            raise matcher.ModelMissing(model)
        m.embed_fn = gone
        self.assertIsNone(m.classify("what should i do now"))
        for _ in range(5):
            self.assertIsNone(m.classify("what should i do now"))
        self.assertEqual(n[0], 1)
        self.assertTrue(m.flush_log())
        events = [json.loads(l) for l in open(self.log) if '"event"' in l]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "model-missing")
        m._disabled_until = time.time() - 1  # after the 10 minutes it tries again
        m.embed_fn = fake_embed
        self.assertIsNotNone(m.classify("what should i do now"))
        self.assertAlmostEqual(matcher.DISABLE_S, 600)


class Round2(Base):
    """One test (or more) per finding from the second Codex re-check. Each fails on the code before the fix."""

    # 1. cold cache load never on the calling thread; classify is bounded from entry
    def test_cold_load_is_never_on_the_calling_thread(self):
        self.make()  # a valid cache file on disk
        loaders = []
        main = threading.get_ident()

        class Slow(matcher.Matcher):
            def _load_disk(inner):
                loaders.append(threading.get_ident())
                time.sleep(0.5)
                return matcher.Matcher._load_disk(inner)
        m = Slow(embed_fn=fake_embed, config={"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": "", "timeout_ms": 100},
                 cache_path=self.cache, log_path=self.log, examples=EXAMPLES, digest_fn=lambda: "")
        t = time.monotonic()
        for _ in range(3):
            self.assertIsNone(m.classify("what should i do now"))  # not in memory yet
        self.assertLess(time.monotonic() - t, 0.15)
        self.assertTrue(m.wait_loaded(5))
        self.assertTrue(loaders)
        self.assertNotIn(main, loaders)
        self.assertIsNotNone(m.classify("what should i do now"))

    def test_deadline_covers_scoring_too(self):
        m = self.make(timeout_ms=200)
        def embed(texts, model, t):
            time.sleep(0.15)
            return fake_embed(texts, model, t)
        m.embed_fn = embed
        real = m._score
        m._score = lambda v, c: time.sleep(0.2) or real(v, c)
        t = time.monotonic()
        self.assertIsNone(m.classify("what should i do now"))
        self.assertLess(time.monotonic() - t, 0.26)

    # 2. one worker, at most one embed in flight, no queue; a late model-missing still disables
    def test_busy_worker_returns_none_without_queueing(self):
        m = self.make(timeout_ms=100)
        n = len(self.calls)
        release = threading.Event()
        def slow(texts, model, t):
            self.calls.append(list(texts))
            release.wait(5)
            return fake_embed(texts, model, t)
        m.embed_fn = slow
        self.assertIsNone(m.classify("what should i do now"))  # waits its 100 ms, embed still in flight
        t = time.monotonic()
        for _ in range(5):
            self.assertIsNone(m.classify("what should i do now"))
        self.assertLess(time.monotonic() - t, 0.05)  # busy: answered at once, nothing queued
        self.assertEqual(len(self.calls), n + 1)
        release.set()
        self.assertTrue(m.wait_idle(5))
        self.assertEqual(len(self.calls), n + 1)

    def test_late_model_missing_still_sets_the_cooldown(self):
        m = self.make(timeout_ms=50)
        hits = []
        def late_missing(texts, model, t):
            hits.append(1)
            time.sleep(0.2)
            raise matcher.ModelMissing(model)
        m.embed_fn = late_missing
        self.assertIsNone(m.classify("what should i do now"))
        self.assertTrue(m.wait_idle(5))
        self.assertGreater(m._disabled_until, time.time() + matcher.DISABLE_S - 30)
        m.embed_fn = fake_embed
        self.assertIsNone(m.classify("what should i do now"))  # still cooling down
        self.assertEqual(len(hits), 1)

    def test_trickling_server_leaves_one_worker_thread(self):
        self.make()  # valid cache file
        stub = Stub("trickle")
        try:
            before = set(threading.enumerate())
            m = matcher.Matcher(config={"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": "", "timeout_ms": 150, "url": stub.url},
                                cache_path=self.cache, log_path=self.log, examples=EXAMPLES)
            self.assertTrue(m.wait_loaded(5))
            for _ in range(12):
                t = time.monotonic()
                self.assertIsNone(m.classify("what should i do now"))
                self.assertLess(time.monotonic() - t, 0.25)
                time.sleep(0.1)  # spaced out, so the worker frees up and each call can start a new embed
            self.assertGreaterEqual(stub.hits, 4)
            mine = [th for th in threading.enumerate() if th not in before and th.is_alive()
                    and "process_request" not in th.name and th.name not in ("matcher-loader", "matcher-log", "matcher-deadline")]
            self.assertLessEqual(len(mine), 1, [th.name for th in mine])
        finally:
            stub.close()

    # 3. only normalised vectors are scored; an exact tie is never routable
    def test_scaled_vector_in_cache_cannot_break_a_tie(self):
        ex = [("alpha beta", "now"), ("alpha beta", "schedule")]
        self.make(examples=ex)
        c = json.load(open(self.cache))
        c["vecs"][0] = [2.0 * x for x in c["vecs"][0]]
        json.dump(c, open(self.cache, "w"))
        m = self.make(examples=ex, warm=False, margin=0.05)
        self.assertTrue(m.wait_loaded(5))
        self.assertIsNone(m.classify("alpha beta"))
        self.assertAlmostEqual(sum(x * x for x in m._cache["vecs"][0]), 1.0, places=9)

    def test_exact_tie_is_never_routable(self):
        r = self.make(examples=[("alpha beta", "now"), ("alpha beta", "schedule")], margin=0.0).classify("alpha beta")
        self.assertEqual(r["margin"], 0.0)
        self.assertFalse(r["routable"])

    # 4. one lock for load, digest, build and publish; warm joins; an older generation never wins
    def test_warm_joins_the_running_build(self):
        gate = threading.Event()
        builds = []
        def gated(texts, model, t):
            if len(texts) > 1:
                builds.append(1)
                gate.wait(5)
            return fake_embed(texts, model, t)
        m = self.make(embed=gated, warm=False)
        results = []
        ts = [threading.Thread(target=lambda: results.append(m.warm())) for _ in range(3)]
        [th.start() for th in ts]
        time.sleep(0.1)
        gate.set()
        [th.join(5) for th in ts]
        self.assertEqual(results, [True, True, True])
        self.assertEqual(len(builds), 1)
        self.assertEqual(m._gen, 1)  # the three warm() calls joined the constructor's refresh, none started its own

    def test_paused_disk_reader_cannot_restore_an_old_digest(self):
        self.make(digest="d1")
        gate = threading.Event()
        builds = []

        class Paused(matcher.Matcher):
            def _load_disk(inner):
                c = matcher.Matcher._load_disk(inner)
                gate.wait(5)  # read the old (d1) file, then stall
                return c
        def counting(texts, model, t):
            if len(texts) > 1:
                builds.append(1)
            return fake_embed(texts, model, t)
        m = Paused(embed_fn=counting, config={"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": ""}, cache_path=self.cache,
                   log_path=self.log, examples=EXAMPLES, digest_fn=lambda: "d2")
        out = []
        ts = [threading.Thread(target=lambda: out.append(m.warm())) for _ in range(3)]
        [th.start() for th in ts]
        time.sleep(0.1)
        gate.set()
        [th.join(5) for th in ts]
        self.settle(m)
        self.assertEqual(out, [True, True, True])
        self.assertEqual(m._cache["digest"], "d2")
        self.assertTrue(json.load(open(self.cache))["key"].endswith("|d2"))
        self.assertEqual(len(builds), 1)
        self.assertTrue(m.warm())  # a later refresh keeps d2
        self.assertEqual(m._cache["digest"], "d2")

    def test_concurrent_refreshes_are_serialised(self):
        self.make(digest="d1")
        gate = threading.Event()
        builds = []

        class Paused(matcher.Matcher):
            def _load_disk(inner):
                c = matcher.Matcher._load_disk(inner)
                gate.wait(5)
                return c
        def counting(texts, model, t):
            if len(texts) > 1:
                builds.append(1)
            return fake_embed(texts, model, t)
        m = Paused(embed_fn=counting, config={"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": ""}, cache_path=self.cache,
                   log_path=self.log, examples=EXAMPLES, digest_fn=lambda: "d2")
        ts = [threading.Thread(target=m._refresh) for _ in range(3)]  # bypass the one-thread guard on purpose
        [th.start() for th in ts]
        time.sleep(0.1)
        gate.set()
        [th.join(5) for th in ts]
        self.settle(m)
        self.assertEqual(len(builds), 1)  # one lock owns load, digest check, build and publish
        self.assertEqual(m._cache["digest"], "d2")

    def test_older_generation_never_replaces_newer(self):
        m = self.make()
        new = dict(m._cache, digest="new")
        old = dict(m._cache, digest="old")
        with m._build_lock:
            self.assertTrue(m._publish(new, m._pub_gen + 2))
            self.assertFalse(m._publish(old, m._pub_gen - 1))
        self.assertEqual(m._cache["digest"], "new")

    # 5. log policy and a hard size cap
    def test_rotation_failure_stops_the_log_growing(self):
        m = self.make()
        os.mkdir(self.log + ".1")  # os.replace onto a directory fails
        open(self.log, "w").write("x" * (matcher.LOG_MAX_BYTES - 10))
        for _ in range(5):
            m.classify("what should i do now")
        self.assertTrue(m.flush_log())
        self.assertLessEqual(os.path.getsize(self.log), matcher.LOG_MAX_BYTES)

    # 6. nothing escapes classify, not even a broken __repr__
    def test_bad_repr_never_raises(self):
        class Evil:
            def __repr__(self):
                raise RuntimeError("repr")
            __str__ = __repr__
        m = self.make()
        self.assertIsNone(m.classify(Evil()))
        self.assertTrue(m.flush_log())
        self.assertEqual(json.loads(open(self.log).read().splitlines()[-1])["type"], "Evil")

    # 7. stored vectors are full precision
    def test_vectors_stored_at_full_precision(self):
        ex = [("q", "now")]
        self.make(examples=ex, embed=lambda texts, model, t: [[1.0, 1.0, 1.0] for _ in texts])
        v = json.load(open(self.cache))["vecs"][0]
        self.assertEqual(v[0], 1.0 / math.sqrt(3.0))

    # still true: a read-only state dir works in memory
    def test_read_only_state_dir_works_in_memory(self):
        ro = os.path.join(self.d, "ro")
        os.mkdir(ro)
        os.chmod(ro, 0o500)
        try:
            m = matcher.Matcher(embed_fn=fake_embed, config={"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": ""},
                                cache_path=os.path.join(ro, "c.json"), log_path=os.path.join(ro, "l.jsonl"), examples=EXAMPLES,
                                digest_fn=lambda: "")
            self.assertTrue(m.warm())
            self.assertFalse(os.path.exists(os.path.join(ro, "c.json")))
            self.assertEqual(m.classify("what should i do now")["label"], "now")
        finally:
            os.chmod(ro, 0o700)


class Round3(Base):
    """One test per finding from the third Codex re-check. Each fails on the code before the fix."""

    # 1. logging never blocks the caller
    def test_log_never_blocks_the_caller(self):
        m = self.make(timeout_ms=100)
        held = threading.Event()
        def hold():
            with m._log_lock:   # the writer is busy (or the disk is slow) for half a second
                held.set()
                time.sleep(0.5)
        th = threading.Thread(target=hold)
        th.start()
        self.assertTrue(held.wait(5))
        t = time.monotonic()
        r = m.classify("what should i do now")
        took = time.monotonic() - t
        th.join()
        self.assertLess(took, 0.1)
        self.assertEqual(r["label"], "now")
        self.assertTrue(m.flush_log())
        self.assertEqual(len(open(self.log).read().splitlines()), 1)  # written once the writer was free

    def test_full_log_queue_drops_instead_of_blocking(self):
        m = self.make()
        m._log_q = matcher.queue.Queue(1)   # full, and no writer reads this one
        m._log_q.put_nowait({"x": 1})
        t = time.monotonic()
        self.assertEqual(m.classify("what should i do now")["label"], "now")
        self.assertLess(time.monotonic() - t, 0.1)

    # 2. the HTTP deadline covers connect, the status line and headers too
    def test_trickling_status_line_is_cut_at_the_deadline(self):
        stub = Stub("trickle-status")
        try:
            t = time.monotonic()
            try:
                out = matcher._read_json(stub.url + "/api/embed", {"model": "m", "input": ["a"]}, 0.2)
            except Exception:
                out = None
            self.assertIsNone(out)
            self.assertLess(time.monotonic() - t, 0.35)
            t = time.monotonic()
            self.assertIsNone(matcher.ollama_embed(["a"], "m", 0.2, stub.url))
            self.assertLess(time.monotonic() - t, 0.35)
        finally:
            stub.close()

    def test_trickling_status_line_frees_the_worker(self):
        self.make()  # valid cache file
        stub = Stub("trickle-status")
        try:
            m = matcher.Matcher(config={"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": "", "timeout_ms": 150, "url": stub.url},
                                cache_path=self.cache, log_path=self.log, examples=EXAMPLES)
            self.assertTrue(m.wait_loaded(5))
            with mock.patch.object(matcher, "ensure_ollama"):
                t = time.monotonic()
                self.assertIsNone(m.classify("what should i do now"))
                self.assertLess(time.monotonic() - t, 0.25)
                self.assertTrue(m.wait_idle(0.3))   # the worker is free right after the deadline, not after the trickle
                m.url = "unused"
                m.embed_fn = fake_embed             # the next call works
                self.assertEqual(m.classify("what should i do now")["label"], "now")
        finally:
            stub.close()

    def test_chunked_close_reply_is_cut_at_the_deadline(self):
        stub = Stub("trickle-chunked-close")
        try:
            t = time.monotonic()
            try:
                out = matcher._read_json(stub.url + "/api/embed", {"model": "m", "input": ["a"]}, 0.2)
            except Exception:
                out = None
            self.assertIsNone(out)
            self.assertLess(time.monotonic() - t, 0.35)
        finally:
            stub.close()

    # 3. a failed worker start leaves nothing busy
    def test_worker_start_failure_clears_busy(self):
        m = self.make()
        real = threading.Thread.start
        failed = []
        def flaky(th):
            if th.name == "matcher-query" and not failed:
                failed.append(1)
                raise RuntimeError("can't start new thread")
            return real(th)
        with mock.patch.object(threading.Thread, "start", flaky):
            self.assertIsNone(m.classify("what should i do now"))
            self.assertEqual(failed, [1])
            self.assertFalse(m._q_busy)
            self.assertIsNone(m._q_job)
            self.assertEqual(m.classify("what should i do now")["label"], "now")
        self.assertEqual(m.classify("what should i do now")["label"], "now")

    # 4. a stale cache (failed rebuild for a new digest) keeps serving and retries on the normal interval
    def test_stale_cache_retries_the_rebuild(self):
        self.make(digest="d1")
        fail = [True]
        def flaky(texts, model, t):
            if len(texts) > 1 and fail[0]:
                return None
            return fake_embed(texts, model, t)

        class Quick(matcher.Matcher):
            RETRY_S = 0.05
        m = Quick(embed_fn=flaky, config={"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": ""}, cache_path=self.cache,
                  log_path=self.log, examples=EXAMPLES, digest_fn=lambda: "d2")
        self.settle(m)
        self.assertEqual(m._cache["digest"], "d1")   # the rebuild failed; the old cache still serves
        self.assertFalse(m._last_ok)
        fail[0] = False
        time.sleep(0.1)
        self.assertIsNotNone(m.classify("what should i do now"))
        self.settle(m)
        self.assertEqual(m._cache["digest"], "d2")
        self.assertTrue(json.load(open(self.cache))["key"].endswith("|d2"))

    def test_digest_check_failing_at_startup_is_retried(self):
        # Ollama down at startup: the cache keeps serving, but the digest check runs again, and a model re-pulled
        # under the same name (new digest) triggers a rebuild once Ollama is back.
        self.make(digest="d1")
        digest = [None]
        builds = []
        def counting(texts, model, t):
            if len(texts) > 1:
                builds.append(1)
            return fake_embed(texts, model, t)

        class Quick(matcher.Matcher):
            RETRY_S = 0.05
        m = Quick(embed_fn=counting, config={"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": ""}, cache_path=self.cache,
                  log_path=self.log, examples=EXAMPLES, digest_fn=lambda: digest[0])
        self.settle(m)
        self.assertEqual(m._cache["digest"], "d1")
        self.assertFalse(m._last_ok)                   # unverified, so it will check again
        self.assertEqual(m.classify("what should i do now")["label"], "now")   # still serving meanwhile
        digest[0] = "d2"
        time.sleep(0.1)
        m.classify("what should i do now")
        self.settle(m)
        self.assertEqual(m._cache["digest"], "d2")
        self.assertTrue(builds)
        self.assertTrue(m._last_ok)

    # 5. the log never stores raw text
    def test_log_never_stores_text(self):
        m = self.make()
        texts = ["sk-abc123", "AKIA9QX2", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl", "correct horse battery staple",
                 "i forgot my password again", "what should i do now", "volcano " * 40]
        for t in texts:
            m.classify(t)
        if hasattr(m, "flush_log"):  # (the old code wrote synchronously, so this test also runs against it)
            self.assertTrue(m.flush_log())
        raw = open(self.log).read()
        for t in texts:
            self.assertNotIn(t.strip(), raw)
        lines = [json.loads(l) for l in raw.splitlines()]
        self.assertEqual(len(lines), len(texts))
        for t, line in zip(texts, lines):
            self.assertNotIn("text", line)
            self.assertEqual(line["len"], len(t))
            self.assertEqual(len(line["hash"]), 12)
            # keyed hash: hashing a guess with plain sha256 must not reveal the text
            self.assertNotEqual(line["hash"], matcher.hashlib.sha256(t.encode()).hexdigest()[:12])
            for k in ("top", "result", "routable", "ms"):
                self.assertIn(k, line)
        self.assertFalse(hasattr(matcher, "_SECRET"))

    # 6. a cache in an older format (no format version in its signature) rebuilds
    def test_old_format_cache_rebuilds(self):
        cfg = {"threshold": 0.5, "margin": 0.05, "k": 3, "prefix": ""}
        h = matcher.hashlib.sha256("\n".join("%s\t%s" % (l, t) for t, l in EXAMPLES).encode()).hexdigest()
        old_sig = "%s|%s|%s" % (matcher.DEFAULTS["model"], "", h)   # the format-1 signature
        vecs = [[round(x, 4) for x in matcher._unit(v)] for v in fake_embed([t for t, _ in EXAMPLES], "m", 1)]
        with open(self.cache, "w") as f:
            json.dump({"key": old_sig + "|", "sig": old_sig, "digest": "", "labels": [l for _, l in EXAMPLES], "vecs": vecs}, f)
        m = self.make()
        self.assertTrue(any(len(c) > 1 for c in self.calls))   # rebuilt, not loaded
        self.assertTrue(json.load(open(self.cache))["sig"].startswith("v%d|" % matcher.CACHE_FORMAT))
        self.assertEqual(m.classify("what should i do now")["label"], "now")

    # 7. a one-ULP gap is never routable, even with margin 0
    def test_one_ulp_gap_is_never_routable(self):
        ex = [("a", "now"), ("b", "schedule")]
        embed = lambda texts, model, t: [[1.0, 0.0] if x.strip() in ("a", "q") else [1.0, 2e-8] for x in texts]
        m = self.make(embed=embed, examples=ex, threshold=0.5, margin=0.0)
        gap = 1.0 - sum(a * b for a, b in zip(m._cache["vecs"][0], m._cache["vecs"][1]))
        self.assertTrue(0 < gap < 1e-9, gap)
        r = m.classify("q")
        self.assertEqual(r["label"], "now")
        self.assertFalse(r["routable"])
        self.assertEqual(matcher.MARGIN_EPS, 1e-9)


def _ollama_up():
    try:
        return matcher._port_answers(1.0) and bool(matcher.ollama_embed(["hi"], matcher.DEFAULTS["model"], 5))
    except Exception:
        return False


@unittest.skipUnless(_ollama_up(), "Ollama (default model) is not answering")
class Live(unittest.TestCase):
    def test_real_sentences(self):
        d = tempfile.mkdtemp()
        m = matcher.Matcher(config={"timeout_ms": 2000}, cache_path=os.path.join(d, "c.json"), log_path=os.path.join(d, "l.jsonl"))
        self.assertTrue(m.warm())
        # "kick this to later" is an action: never routable by the matcher, whatever it scores
        r = m.classify("kick this to later")
        self.assertTrue(r is None or not r["routable"], r)
        r = m.classify("how do volcanoes work")
        self.assertTrue(r is None or r["label"] == "general", r)
        r = m.classify("my mom needs to buy a gift")
        self.assertTrue(r is None or not r["routable"], r)
        r = m.classify("what should i be doing")
        self.assertIsNotNone(r)
        self.assertEqual(r["label"], "now")
        self.assertTrue(r["routable"])


if __name__ == "__main__":
    unittest.main()
