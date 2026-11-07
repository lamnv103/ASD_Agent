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


if __name__ == "__main__":
    unittest.main()
