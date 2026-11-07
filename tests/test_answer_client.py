"""AnswerNimClient against a fake HTTP layer: request shape, provider errors, cache and no-cache. No network."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib import error

from rag.answer_client import AnswerClientError, AnswerNimClient
from rag.answer_layer import GEN_SYSTEM, VERIFY_SYSTEM
from rag.answer_policy import load_config

CFG = load_config()
KEY = "nvapi-test-key-not-real"


class FakeCounter:
    def __init__(self, tokens=100):
        self.tokens = tokens
        self.config = {"tokenizer": {"request_profile": {"template_kwargs": copy.deepcopy(CFG["chat_template_kwargs"])}}}
        self.profile = {"kind": "fake"}

    def count_messages(self, msgs):
        return self.tokens


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeOpener:
    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append((req, timeout))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return FakeResponse(self.outcome if isinstance(self.outcome, bytes) else json.dumps(self.outcome).encode("utf-8"))


def body(content='{"ok": true}', model=None, finish="stop"):
    return dict(id="req-1", model=model or CFG["model"], usage=dict(prompt_tokens=99, completion_tokens=5),
                choices=[dict(finish_reason=finish, message=dict(content=content))])


def msgs(system=GEN_SYSTEM):
    return [dict(role="system", content=system), dict(role="user", content='{"question":"q"}')]


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def client(self, *, use_cache=True, tokens=100, key_supplier=lambda: KEY, config=None):
        return AnswerNimClient(FakeCounter(tokens), config=config, key_supplier=key_supplier, cache_dir=self.cache, use_cache=use_cache)

    def call(self, client, outcome, m=None):
        opener = FakeOpener(outcome)
        with mock.patch("rag.answer_client.request.build_opener", return_value=opener):
            return client.complete(m or msgs()), opener

    def test_request_shape_and_record_without_key(self):
        rec, opener = self.call(self.client(), body())
        req, timeout = opener.requests[0]
        self.assertEqual((req.full_url, req.get_method(), timeout), (CFG["endpoint"], "POST", CFG["timeout_seconds"]))
        self.assertEqual(req.get_header("Authorization"), "Bearer " + KEY)
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["model"], CFG["model"])
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["chat_template_kwargs"], CFG["chat_template_kwargs"])
        self.assertFalse(payload["stream"])
        self.assertEqual((rec["content"], rec["cache_hit"], rec["provider_prompt_tokens"]), ('{"ok": true}', False, 99))
        self.assertNotIn(KEY, json.dumps(rec))
        for f in self.cache.glob("*.json"):
            self.assertNotIn(KEY, f.read_text(encoding="utf-8"))

    def test_verifier_prompt_uses_verifier_model(self):
        cfg = copy.deepcopy(CFG)
        cfg["verifier_model"] = "test/verifier-model"
        rec, opener = self.call(self.client(config=cfg), body(model="test/verifier-model"), msgs(VERIFY_SYSTEM))
        self.assertEqual(json.loads(opener.requests[0][0].data)["model"], "test/verifier-model")
        self.assertEqual(rec["model"], "test/verifier-model")

    def test_cache_write_then_hit_without_network_or_key(self):
        self.call(self.client(), body())
        self.assertEqual(len(list(self.cache.glob("*.json"))), 1)

        def no_key():
            raise AssertionError("key must not be read on a cache hit")
        rec, opener = self.call(self.client(key_supplier=no_key), AssertionError("network must not be used"))
        self.assertTrue(rec["cache_hit"])
        self.assertEqual(opener.requests, [])

    def test_no_cache_neither_reads_nor_writes(self):
        self.call(self.client(use_cache=False), body())
        self.assertEqual(list(self.cache.glob("*.json")), [])  # nothing written on an empty cache
        self.call(self.client(), body())  # seed a cache entry
        before = {p.name: p.read_bytes() for p in self.cache.glob("*.json")}
        rec, opener = self.call(self.client(use_cache=False), body(content='{"fresh": 1}'))
        self.assertEqual((rec["content"], rec["cache_hit"], len(opener.requests)), ('{"fresh": 1}', False, 1))
        self.assertEqual({p.name: p.read_bytes() for p in self.cache.glob("*.json")}, before)  # not overwritten

    def test_tampered_cache_is_rejected(self):
        self.call(self.client(), body())
        path = next(self.cache.glob("*.json"))
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["content"] = '{"forged": true}'
        path.write_text(json.dumps(rec), encoding="utf-8")
        with self.assertRaises(AnswerClientError) as ctx:
            self.call(self.client(), body())
        self.assertEqual(ctx.exception.code, "answer_cache_invalid")

    def test_http_and_network_errors(self):
        cases = [(error.HTTPError(CFG["endpoint"], 401, "x", {}, None), "nim_auth"),
                 (error.HTTPError(CFG["endpoint"], 403, "x", {}, None), "nim_auth"),
                 (error.HTTPError(CFG["endpoint"], 429, "x", {}, None), "nim_rate_limit"),
                 (error.HTTPError(CFG["endpoint"], 500, "x", {}, None), "nim_http"),
                 (error.URLError("down"), "nim_network"),
                 (TimeoutError(), "nim_network"),
                 (b"not json", "nim_response")]
        for outcome, code in cases:
            with self.assertRaises(AnswerClientError, msg=code) as ctx:
                self.call(self.client(), outcome)
            self.assertEqual(ctx.exception.code, code)
        self.assertEqual(list(self.cache.glob("*.json")), [])

    def test_incomplete_or_unexpected_responses(self):
        for outcome, code in [(body(finish="length"), "nim_incomplete"), (body(model="other/model"), "nim_model_mismatch"),
                              (body(content="   "), "nim_response"), (dict(model=CFG["model"], choices=[]), "nim_incomplete")]:
            with self.assertRaises(AnswerClientError, msg=code) as ctx:
                self.call(self.client(), outcome)
            self.assertEqual(ctx.exception.code, code)
        self.assertEqual(list(self.cache.glob("*.json")), [])

    def test_budget_is_checked_before_key_or_network(self):
        def no_key():
            raise AssertionError("key must not be read when over budget")
        with self.assertRaises(AnswerClientError) as ctx:
            self.call(self.client(tokens=CFG["context_window_tokens"], key_supplier=no_key), AssertionError("no network"))
        self.assertEqual(ctx.exception.code, "answer_budget")


class NoNetwork:
    """Blocks every socket connection in the process; records attempts."""

    def __init__(self):
        self.attempts = 0

    def __enter__(self):
        import socket

        def refuse(*a, **k):
            self.attempts += 1
            raise AssertionError("network access attempted")
        self._patches = [mock.patch.object(socket.socket, "connect", refuse),
                         mock.patch.object(socket, "create_connection", refuse),
                         mock.patch("rag.answer_client.request.build_opener", side_effect=refuse)]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self._patches:
            p.stop()


def no_key():
    raise AssertionError("the key must not be read")


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def offline(self):
        return AnswerNimClient(FakeCounter(), key_supplier=no_key, cache_dir=self.cache, offline=True)

    def test_offline_cache_miss_stops_before_key_and_network(self):
        with NoNetwork() as net:
            with self.assertRaises(AnswerClientError) as ctx:
                self.offline().complete(msgs())
        self.assertEqual((ctx.exception.code, net.attempts), ("offline_cache_miss", 0))
        self.assertEqual(list(self.cache.glob("*.json")), [])

    def test_offline_replays_cache_without_network(self):
        online = AnswerNimClient(FakeCounter(), key_supplier=lambda: KEY, cache_dir=self.cache)
        with mock.patch("rag.answer_client.request.build_opener", return_value=FakeOpener(body())):
            first = online.complete(msgs())
        with NoNetwork() as net:
            again = self.offline().complete(msgs())
        self.assertEqual((again["content"], again["cache_hit"], net.attempts), (first["content"], True, 0))

    def test_offline_tampered_cache_is_rejected(self):
        online = AnswerNimClient(FakeCounter(), key_supplier=lambda: KEY, cache_dir=self.cache)
        with mock.patch("rag.answer_client.request.build_opener", return_value=FakeOpener(body())):
            online.complete(msgs())
        path = next(self.cache.glob("*.json"))
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["content"] = '{"forged": 1}'
        path.write_text(json.dumps(rec), encoding="utf-8")
        with NoNetwork() as net, self.assertRaises(AnswerClientError) as ctx:
            self.offline().complete(msgs())
        self.assertEqual((ctx.exception.code, net.attempts), ("answer_cache_invalid", 0))

    def test_offline_with_no_cache_is_invalid(self):
        with self.assertRaises(AnswerClientError) as ctx:
            AnswerNimClient(FakeCounter(), key_supplier=no_key, cache_dir=self.cache, offline=True, use_cache=False)
        self.assertEqual(ctx.exception.code, "invalid_configuration")

    def test_answer_layer_offline_on_real_trace_is_system_error_without_network(self):
        from datetime import date
        from rag.answer_layer import answer_from_trace
        from rag.retriever import ROOT
        trace = json.loads((ROOT / "reports/reader_refinement_20261101_232742/run_20261102_004612_154953/traces/S05.json")
                           .read_text(encoding="utf-8"))
        with NoNetwork() as net:
            r = answer_from_trace(trace, client=self.offline(), as_of=date(2026, 11, 7))
        self.assertEqual((r["route"], r["error"], net.attempts, r["as_of"]), ("system_error", "offline_cache_miss", 0, "2026-11-07"))
        self.assertEqual(r["claims_final"], [])

    def test_cli_rejects_offline_with_no_cache(self):
        import subprocess
        import sys
        from rag.retriever import ROOT
        p = subprocess.run([sys.executable, "-B", "-m", "rag.answer", "--from-trace", "x.json", "--offline", "--no-cache"],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 2)
        self.assertIn("not allowed with argument", p.stderr)


class TlsTests(unittest.TestCase):
    def test_tls_context_verifies_certificate_and_hostname(self):
        import ssl
        from rag.answer_client import tls_context
        ctx = tls_context()
        self.assertEqual((ctx.verify_mode, ctx.check_hostname), (ssl.CERT_REQUIRED, True))

    def test_client_uses_verified_tls_context(self):
        import ssl
        from urllib import request as urlrequest
        captured = []

        def fake_build_opener(*handlers):
            captured.extend(handlers)
            return FakeOpener(body())
        client = AnswerNimClient(FakeCounter(), key_supplier=lambda: KEY, use_cache=False)
        with mock.patch("rag.answer_client.request.build_opener", side_effect=fake_build_opener):
            client.complete(msgs())
        https = [h for h in captured if isinstance(h, urlrequest.HTTPSHandler)]
        self.assertEqual(len(https), 1)
        self.assertEqual((https[0]._context.verify_mode, https[0]._context.check_hostname), (ssl.CERT_REQUIRED, True))

    def test_no_tls_disabling_in_project_code(self):
        import re
        from rag.retriever import ROOT
        pattern = re.compile(r"verify\s*=\s*False|CERT_NONE|_create_unverified_context|check_hostname\s*=\s*False|"
                             r"InsecureRequestWarning|disable_warnings|(REQUESTS_CA_BUNDLE|SSL_CERT_FILE)\"\]\s*=\s*\"\"")
        files = [ROOT / "app.py"] + [p for d in ("rag", "scripts") for p in (ROOT / d).rglob("*.py")]
        hits = [f"{p.relative_to(ROOT)}:{i}" for p in files if p.is_file()
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1) if pattern.search(line)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
