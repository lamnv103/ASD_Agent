"""Trusted source text and metadata for the answer layer.

A trace file is NOT trusted: anyone can edit a block and its quote consistently. The answer layer
therefore re-derives every citable quote and every displayed metadata field from the released corpus:

  deployments/retriever.json (hash-pinned by accepted evaluation runs)
      corpus_sha256            == sha256(knowledge/rag/source_library/documents.json bytes)
      sources[id].content_sha256 == sha256(document text)

build_catalog() then requires, for every selected evidence item:
  block.content_sha256 == pinned hash, block.text == corpus[block.start:block.end],
  evidence.quote == corpus[evidence.start:evidence.end].
"""
from __future__ import annotations

import json
from functools import lru_cache

from .retriever import ROOT, sha

RETRIEVER_CONFIG = ROOT / "deployments/retriever.json"
DOCUMENTS = ROOT / "knowledge/rag/source_library/documents.json"


class CorpusError(Exception):
    def __init__(self, code, message=""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


class TrustedCorpus:
    def __init__(self, collection_id, documents):
        """documents: {source_id: dict(text=..., sha256=..., title=..., source=..., dates=...)} (already verified)."""
        self.collection_id = collection_id
        self._docs = documents

    @classmethod
    def from_documents(cls, collection_id, docs, pinned_hashes):
        """Build from raw corpus records ({'id','noi_dung','ten_tai_lieu','nguon','ngay_thang'}) and pinned hashes."""
        out = {}
        for d in docs:
            sid = d["id"]
            if sid not in pinned_hashes:
                continue
            h = sha(d["noi_dung"])
            if h != pinned_hashes[sid]:
                raise CorpusError("corpus_content_mismatch", sid)
            out[sid] = dict(text=d["noi_dung"], sha256=h, title=d.get("ten_tai_lieu"), source=d.get("nguon") or {},
                            dates=d.get("ngay_thang") or {})
        missing = set(pinned_hashes) - set(out)
        if missing:
            raise CorpusError("corpus_incomplete", ", ".join(sorted(missing)))
        return cls(collection_id, out)

    def get(self, source_id):
        doc = self._docs.get(source_id)
        if doc is None:
            raise CorpusError("unknown_source", source_id)
        return doc


@lru_cache(maxsize=1)
def load_trusted_corpus():
    pins = json.loads(RETRIEVER_CONFIG.read_text(encoding="utf-8"))
    raw = DOCUMENTS.read_bytes()
    if sha(raw) != pins["corpus_sha256"]:
        raise CorpusError("corpus_hash_mismatch", "documents.json does not match deployments/retriever.json")
    docs = json.loads(raw)["tai_lieu"]
    return TrustedCorpus.from_documents(pins["collection_id"], docs,
                                        {sid: v["content_sha256"] for sid, v in pins["sources"].items()})
