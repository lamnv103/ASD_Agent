"""NVIDIA NIM client for the answer layer (internal prototype).

Differs from rag.semantic_reader.NimClient (hash-pinned, reader-only) in three ways:
  * its own config (deployments/answer_layer.json) and cache folder (reports/answer_cache, git-ignored);
  * the key comes ONLY from the NVIDIA_API_KEY environment variable or an explicit *.env dotenv file.
    YAML files (e.g. Continue's config.yaml) and the project-root .env are refused;
  * caching can be switched off (use_cache=False). Cache only synthetic questions: the data
    retention policy (MVP decision 9) is not decided yet;
  * offline=True is cache-only: a missing cache entry stops BEFORE the key is read or any
    connection is opened. offline + use_cache=False is an invalid configuration.
TLS: certificate and hostname verification are always on (certifi CA bundle); see tls_context().
"""
from __future__ import annotations

import copy
import json
import os
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

import certifi
from dotenv import dotenv_values

from .answer_policy import load_config
from .retriever import ROOT, NoRedirect, atomic_json, canonical, sha


class AnswerClientError(Exception):
    def __init__(self, code, message=""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def read_answer_key(path=None):
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        if not path:
            raise AnswerClientError("missing_nvidia_key", "Set NVIDIA_API_KEY or pass a *.env file (git-ignored).")
        p = Path(path).resolve()
        if p.suffix.lower() in {".yaml", ".yml"} or p == (ROOT / ".env").resolve() or not p.name.endswith(".env"):
            raise AnswerClientError("key_file_refused", "Only a dedicated *.env dotenv file is accepted (not YAML, not the root .env).")
        if not p.is_file():
            raise AnswerClientError("missing_nvidia_key", "Key file not found.")
        key = dotenv_values(p, interpolate=False).get("NVIDIA_API_KEY")
    if not (isinstance(key, str) and key.startswith("nvapi-") and "\n" not in key and "\r" not in key):
        raise AnswerClientError("invalid_nvidia_key", "Expected an NVIDIA credential (nvapi-...).")
    return key


def tls_context():
    """Verified TLS only. Never relax this: fix the CA configuration instead."""
    ctx = ssl.create_default_context(cafile=certifi.where())
    if ctx.verify_mode != ssl.CERT_REQUIRED or not ctx.check_hostname:
        raise AnswerClientError("tls_config", "TLS verification must stay enabled.")
    return ctx


class AnswerNimClient:
    def __init__(self, counter, *, config=None, key_file=None, key_supplier=None, cache_dir=None, use_cache=True,
                 offline=False):
        if offline and not use_cache:
            raise AnswerClientError("invalid_configuration", "offline mode replays the cache; it cannot be combined with no-cache.")
        self.offline = offline
        self.config = load_config(config)
        self.counter = counter
        self.key_file = key_file
        self.key_supplier = key_supplier
        self.use_cache = use_cache
        self.cache_dir = Path(cache_dir) if cache_dir else ROOT / "reports/answer_cache"
        if self.config["chat_template_kwargs"] != counter.config["tokenizer"]["request_profile"]["template_kwargs"]:
            raise AnswerClientError("answer_config", "Serving template flags and tokenizer differ.")

    def complete(self, msgs):
        cfg = self.config
        local = self.counter.count_messages(msgs)
        if local + cfg["max_output_tokens"] + cfg["safety_margin_tokens"] > cfg["context_window_tokens"]:
            raise AnswerClientError("answer_budget", "Prompt exceeds the configured token budget; no request sent.")
        model = cfg["verifier_model"] if msgs and "You check Vietnamese answer claims" in msgs[0]["content"] else cfg["model"]
        payload = dict(model=model, messages=msgs, max_tokens=cfg["max_output_tokens"], temperature=cfg["temperature"],
                       stream=False, chat_template_kwargs=cfg["chat_template_kwargs"], response_format={"type": "json_object"})
        identity = dict(endpoint=cfg["endpoint"], payload=payload, tokenizer=self.counter.profile)
        path = self.cache_dir / (sha(canonical(identity)) + ".json")
        if self.use_cache and path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("identity") != identity or record.get("content_sha256") != sha(record.get("content", "")):
                raise AnswerClientError("answer_cache_invalid", "Answer cache failed validation.")
            record = copy.deepcopy(record)
            record["cache_hit"] = True
            return record
        if self.offline:
            raise AnswerClientError("offline_cache_miss", "No cached response for this request; offline mode never reads the key or opens a connection.")
        key = self.key_supplier() if self.key_supplier else read_answer_key(self.key_file)
        req = request.Request(cfg["endpoint"], data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        opener = request.build_opener(NoRedirect(), request.HTTPSHandler(context=tls_context()))
        tick = time.monotonic()
        try:
            with opener.open(req, timeout=cfg["timeout_seconds"]) as response:
                body = json.loads(response.read(3_000_000))
        except error.HTTPError as exc:
            code = "nim_auth" if exc.code in (401, 403) else "nim_rate_limit" if exc.code == 429 else "nim_http"
            raise AnswerClientError(code, f"NVIDIA HTTP {exc.code}; body omitted; no automatic retry.") from None
        except (error.URLError, TimeoutError, OSError):
            raise AnswerClientError("nim_network", "NVIDIA request failed or timed out; no automatic retry.") from None
        except ValueError:
            raise AnswerClientError("nim_response", "NVIDIA returned invalid JSON.") from None
        finally:
            key = None
        elapsed = round(time.monotonic() - tick, 3)
        if not isinstance(body, dict) or body.get("model") != model:
            raise AnswerClientError("nim_model_mismatch", "Provider returned another model or an invalid body.")
        choices = body.get("choices") or []
        if not (len(choices) == 1 and isinstance(choices[0], dict) and choices[0].get("finish_reason") == "stop"):
            raise AnswerClientError("nim_incomplete", "Completion incomplete or unexpected finish reason.")
        content = (choices[0].get("message") or {}).get("content")
        if not (isinstance(content, str) and content.strip()):
            raise AnswerClientError("nim_response", "No visible content.")
        usage = body.get("usage") or {}
        record = dict(identity=identity, content=content, content_sha256=sha(content), request_id=body.get("id"), model=model,
                      usage=usage, local_prompt_tokens=local, provider_prompt_tokens=usage.get("prompt_tokens"),
                      elapsed_seconds=elapsed, cache_hit=False, recorded_at=datetime.now(timezone.utc).isoformat())
        if self.use_cache:
            atomic_json(path, record)
        return record
