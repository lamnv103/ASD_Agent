"""Cache-only replay of the answer layer (G) for a committed NIM run bundle. No provider, no network.

    .venv-embedding\\Scripts\\python.exe -B scripts/evaluation/verify_answer_layer.py
    .venv-embedding\\Scripts\\python.exe -B scripts/evaluation/verify_answer_layer.py --create-manifest reports/answer_eval_20261107  # once

A bundle folder holds: <QID>.result.json (canonical results), cache/ (exactly the NIM responses of
that run) and manifest.json (hashes of inputs, config, cache and results; pinned as_of; code commit).

Replay checks, per case:
  * every hash in the manifest still matches (trace, config, corpus pin, cache files, results);
  * the answer layer re-runs OFFLINE (AnswerNimClient offline=True) inside a socket-level
    no-network guard; a missing/tampered cache entry fails the case;
  * the final rendered text is byte-identical; catalog, sources, final and removed claims,
    status, route, needs, as_of and repairs are identical. Timings / cache_hit are not compared.
Output: a new folder under reports/verification_runs/ (never writes into the bundle).
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/evaluation"))
from audit_output import new_run_dir  # noqa: E402

from rag.answer_client import AnswerNimClient  # noqa: E402
from rag.answer_layer import answer_from_trace  # noqa: E402
from rag.retriever import atomic_json, sha  # noqa: E402
from rag.tokenization import load_counter  # noqa: E402

DEFAULT_BUNDLES = ["reports/answer_eval_20261107"]
COMPARED = ("route", "status", "reader_status", "proposed_status", "repairs", "as_of", "catalog", "claims_final",
            "claims_removed", "needs_addressed", "needs_missing", "uncovered", "error", "contract_version", "check_version")
PINNED_FILES = ("deployments/answer_layer.json", "deployments/retriever.json", "knowledge/rag/source_library/documents.json",
                "deployments/evidence_context.json")


def file_sha(path: Path) -> str:
    return sha(path.read_bytes())


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def create_manifest(bundle: Path, cases: dict[str, str], as_of: str) -> Path:
    out = bundle / "manifest.json"
    if out.exists():
        raise SystemExit(f"{rel(out)} already exists; manifests are written once.")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    manifest = dict(
        schema="answer_replay_bundle_v1", as_of=as_of, code_commit_at_run=commit,
        note="Internal prototype run (chua_duyet). Results are technical evidence, not clinical validation.",
        pinned_files={p: file_sha(ROOT / p) for p in PINNED_FILES},
        cache={p.name: file_sha(p) for p in sorted((bundle / "cache").glob("*.json"))},
        cases=[])
    for qid, trace in cases.items():
        result = bundle / f"{qid}.result.json"
        manifest["cases"].append(dict(question_id=qid, trace=trace, trace_sha256=file_sha(ROOT / trace),
                                      result=rel(result), result_sha256=file_sha(result)))
    atomic_json(out, manifest)
    return out


class NoNetwork:
    def __enter__(self):
        def refuse(*a, **k):
            raise ConnectionError("network access attempted during cache-only replay")
        self.patches = [mock.patch.object(socket.socket, "connect", refuse), mock.patch.object(socket, "create_connection", refuse)]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self.patches:
            p.stop()


def no_key():
    raise AssertionError("cache-only replay must not read a key")


def verify_bundle(bundle: Path, counter) -> dict:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    problems = []
    for p, h in manifest["pinned_files"].items():
        if file_sha(ROOT / p) != h:
            problems.append(f"pinned file changed since the run: {p}")
    cache_dir = bundle / "cache"
    actual = {p.name: file_sha(p) for p in sorted(cache_dir.glob("*.json"))}
    if actual != manifest["cache"]:
        problems.append("cache files differ from the manifest (added, removed or edited)")
    as_of = date.fromisoformat(manifest["as_of"])
    cases = []
    for case in manifest["cases"]:
        qid = case["question_id"]
        res = dict(question_id=qid, problems=[])
        trace_path, result_path = ROOT / case["trace"], ROOT / case["result"]
        if file_sha(trace_path) != case["trace_sha256"]:
            res["problems"].append("trace changed")
        if file_sha(result_path) != case["result_sha256"]:
            res["problems"].append("canonical result changed")
        expected = json.loads(result_path.read_text(encoding="utf-8"))
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        client = AnswerNimClient(counter, key_supplier=no_key, cache_dir=cache_dir, offline=True)
        with NoNetwork():
            got = answer_from_trace(trace, client=client, as_of=as_of)
        if got["route"] == "system_error":
            res["problems"].append(f"replay failed: {got['error']}")
        if got["render"]["text"].encode("utf-8") != expected["render"]["text"].encode("utf-8"):
            res["problems"].append("rendered text is not byte-identical")
        if got["render"]["sources"] != expected["render"]["sources"]:
            res["problems"].append("sources differ")
        for k in COMPARED:
            if got.get(k) != expected.get(k):
                res["problems"].append(f"field differs: {k}")
        if not all(c.get("cache_hit") for c in got["calls"]):
            res["problems"].append("a call was not served from the cache")
        res.update(status=got["status"], route=got["route"], calls=len(got["calls"]),
                   claims_final=len(got["claims_final"]), claims_removed=len(got["claims_removed"]))
        cases.append(res)
    ok = not problems and all(not c["problems"] for c in cases)
    return dict(bundle=rel(bundle), verified=ok, problems=problems, cases=cases, as_of=manifest["as_of"],
                code_commit_at_run=manifest["code_commit_at_run"])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("bundles", nargs="*", default=DEFAULT_BUNDLES)
    p.add_argument("--create-manifest", metavar="BUNDLE")
    p.add_argument("--as-of", default="2026-11-07")
    p.add_argument("--case", action="append", default=[], metavar="QID=TRACE", help="with --create-manifest")
    args = p.parse_args()
    if args.create_manifest:
        cases = dict(c.split("=", 1) for c in args.case)
        print(rel(create_manifest(ROOT / args.create_manifest, cases, args.as_of)))
        return 0
    counter = load_counter(json.loads((ROOT / "deployments/evidence_context.json").read_text(encoding="utf-8")))
    out = new_run_dir("answer_layer")
    reports = [verify_bundle(ROOT / b, counter) for b in args.bundles]
    summary = dict(status="verified" if all(r["verified"] for r in reports) else "failed",
                   provider_calls=0, network_guard="socket.connect and socket.create_connection blocked",
                   bundles=reports,
                   limitations=["Replay proves reproducibility of a recorded run, not answer quality or clinical correctness.",
                                "Generator and verifier are the same model; verifier passes are provisional."])
    atomic_json(out / "summary.json", summary)
    for r in reports:
        for c in r["cases"]:
            print(f"ANSWER AUDIT {c['question_id']} {'verified' if not c['problems'] else 'FAILED: ' + '; '.join(c['problems'])}")
        for prob in r["problems"]:
            print(f"ANSWER AUDIT bundle FAILED: {prob}")
    print(f"AUDIT_DIR={out}")
    print(json.dumps(dict(status=summary["status"]), ensure_ascii=False))
    return 0 if summary["status"] == "verified" else 1


if __name__ == "__main__":
    sys.exit(main())
