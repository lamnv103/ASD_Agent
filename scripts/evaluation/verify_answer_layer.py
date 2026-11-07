"""Cache-only replay of the answer layer (G) for committed NIM run bundles. No provider, no network.

    .venv-embedding\\Scripts\\python.exe -B scripts/evaluation/verify_answer_layer.py
    .venv-embedding\\Scripts\\python.exe -B scripts/evaluation/verify_answer_layer.py --create-manifest BUNDLE --case QID=TRACE ...

A bundle folder holds: <QID>.result.json (canonical results), cache/ (exactly the NIM responses of
that run) and manifest.json (hashes of inputs, config, cache and results; pinned as_of; code commit;
code fingerprint of the answer-layer modules for bundles created from v0.3 on).

Replay checks, per case:
  * every hash in the manifest still matches (trace, config, corpus pin, cache files, results);
  * the answer layer re-runs OFFLINE (AnswerNimClient offline=True) inside a socket-level
    no-network guard; a missing/tampered cache entry fails the case;
  * the final rendered text is byte-identical; catalog, sources, final and removed claims,
    status, route, needs, as_of and repairs are identical. Timings / cache_hit are not compared.

Which code replays a bundle: the code that produced it. If the answer-layer modules or the pinned
config/corpus files differ from the bundle's run commit (e.g. the contract moved on), the files of
that commit are extracted with `git archive` into a temporary folder and the replay runs there
("legacy" mode). Old bundles therefore stay verifiable after the contract changes; they are never
re-labelled as results of newer code.
Output: a new folder under reports/verification_runs/ (never writes into the bundle).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BUNDLES = ["reports/answer_eval_20261107", "reports/answer_eval_20261107_v0.3_offline"]
COMPARED = ("route", "status", "reader_status", "proposed_status", "repairs", "as_of", "catalog", "claims_final",
            "claims_removed", "verifier_observations", "needs_addressed", "needs_missing", "uncovered", "error",
            "contract_version", "check_version")
PINNED_FILES = ("deployments/answer_layer.json", "deployments/retriever.json", "knowledge/rag/source_library/documents.json",
                "deployments/evidence_context.json", "deployments/answer_pharm_gate.json")
CODE_FILES = ("rag/answer_layer.py", "rag/answer_render.py", "rag/answer_policy.py", "rag/answer_sources.py",
              "rag/answer_client.py", "rag/retriever.py", "rag/tokenization.py", "rag/answer_pharm.py")
# A fingerprint is a {path: sha256 or None (file absent)} map. Comparisons always use the paths a manifest or
# measurement RECORDED, so files added to these lists later do not invalidate older evidence.
ARCHIVE_PATHS = ("rag", "deployments", "knowledge/rag/source_library")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def git(*args, binary=False):
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode("utf-8").strip()


def fingerprint(root: Path, files=CODE_FILES) -> dict:
    return {p: file_sha(root / p) if (root / p).exists() else None for p in files}


def fingerprint_at(commit: str, files=CODE_FILES) -> dict:
    out = {}
    for p in files:
        proc = subprocess.run(["git", "show", f"{commit}:{p}"], cwd=ROOT, capture_output=True)
        out[p] = sha_bytes(proc.stdout) if proc.returncode == 0 else None
    return out


def create_manifest(bundle: Path, cases: dict[str, str], as_of: str) -> Path:
    from rag.retriever import atomic_json
    out = bundle / "manifest.json"
    if out.exists():
        raise SystemExit(f"{rel(out)} already exists; manifests are written once.")
    commit = git("rev-parse", "HEAD")
    code = fingerprint(ROOT)
    if code != fingerprint_at(commit) or fingerprint(ROOT, PINNED_FILES) != fingerprint_at(commit, PINNED_FILES):
        raise SystemExit("Answer-layer code or pinned config differs from HEAD; commit the code that produced the run first.")
    cfg = json.loads((ROOT / "deployments/answer_layer.json").read_text(encoding="utf-8"))
    manifest = dict(
        schema="answer_replay_bundle_v2", as_of=as_of, code_commit_at_run=commit, code_fingerprint=code,
        contract_version=cfg["contract_version"], check_version=cfg["check_version"],
        note="Internal prototype run (chua_duyet). Results are technical evidence, not clinical validation.",
        pinned_files=fingerprint(ROOT, PINNED_FILES),
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


def replay_mode(manifest: dict) -> str:
    """'current' when this checkout holds the run's code and pinned files; otherwise 'legacy'."""
    commit = manifest["code_commit_at_run"]
    expected = manifest.get("code_fingerprint") or {p: v for p, v in fingerprint_at(commit).items() if v is not None}
    same_code = fingerprint(ROOT, tuple(expected)) == expected
    same_pins = fingerprint(ROOT, tuple(manifest["pinned_files"])) == manifest["pinned_files"]
    return "current" if same_code and same_pins else "legacy"


def verify_bundle(bundle: Path, code_root: Path = ROOT) -> dict:
    """Replay one bundle with the rag package found under code_root (the run's code)."""
    sys.path.insert(0, str(code_root))
    from rag.answer_client import AnswerNimClient
    from rag.answer_layer import answer_from_trace
    from rag.tokenization import load_counter
    counter = load_counter(json.loads((code_root / "deployments/evidence_context.json").read_text(encoding="utf-8")))
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    problems = []
    for p, h in manifest["pinned_files"].items():
        if file_sha(code_root / p) != h:
            problems.append(f"pinned file differs from the run: {p}")
    if manifest.get("code_fingerprint") and manifest["code_fingerprint"] != fingerprint(code_root, tuple(manifest["code_fingerprint"])):
        problems.append("answer-layer code differs from the manifest fingerprint")
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


def find_commit(code_fp: dict, pins: dict) -> str | None:
    """Newest commit whose answer-layer code and pinned files match the given hashes (None if never committed)."""
    for commit in git("rev-list", "HEAD", "--", *code_fp, *pins).split():
        if fingerprint_at(commit, tuple(code_fp)) == code_fp and fingerprint_at(commit, tuple(pins)) == pins:
            return commit
    return None


def run_child_at(commit: str, script: Path, args: list[str]) -> tuple[dict | None, str]:
    """Extract the commit's code and pinned files with `git archive` and run `script --child-code-root TMP args`
    in a child process, so the child imports only that commit's rag package. Returns (last JSON line, stderr)."""
    tmp = Path(tempfile.mkdtemp(prefix="answer_replay_"))
    try:
        tar = git("archive", "--format=tar", commit, *ARCHIVE_PATHS, binary=True)
        with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
            tf.extractall(tmp, filter="data")
        proc = subprocess.run([sys.executable, "-B", str(script), "--child-code-root", str(tmp), *args],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
        return (json.loads(lines[-1]) if lines else None), proc.stderr.strip()[-400:]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def verify_legacy(bundle: Path, commit: str) -> dict:
    report, err = run_child_at(commit, Path(__file__).resolve(), [str(bundle)])
    return report or dict(bundle=rel(bundle), verified=False, problems=[f"legacy replay crashed: {err}"],
                          cases=[], code_commit_at_run=commit)


def run_bundle(bundle: Path) -> dict:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    mode = replay_mode(manifest)
    report = verify_bundle(bundle) if mode == "current" else verify_legacy(bundle, manifest["code_commit_at_run"])
    report["replay_mode"] = mode
    return report


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("bundles", nargs="*", default=DEFAULT_BUNDLES)
    p.add_argument("--create-manifest", metavar="BUNDLE")
    p.add_argument("--as-of", default="2026-11-07")
    p.add_argument("--case", action="append", default=[], metavar="QID=TRACE", help="with --create-manifest")
    p.add_argument("--child-code-root", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.child_code_root:
        print(json.dumps(verify_bundle(Path(args.bundles[0]).resolve(), Path(args.child_code_root)), ensure_ascii=False))
        return 0
    sys.path.insert(0, str(ROOT))
    if args.create_manifest:
        cases = dict(c.split("=", 1) for c in args.case)
        print(rel(create_manifest(ROOT / args.create_manifest, cases, args.as_of)))
        return 0
    sys.path.insert(0, str(ROOT / "scripts/evaluation"))
    from audit_output import new_run_dir
    from rag.retriever import atomic_json
    out = new_run_dir("answer_layer")
    reports = [run_bundle(ROOT / b) for b in args.bundles]
    summary = dict(status="verified" if all(r["verified"] for r in reports) else "failed",
                   provider_calls=0, network_guard="socket.connect and socket.create_connection blocked",
                   bundles=reports,
                   limitations=["Replay proves reproducibility of a recorded run, not answer quality or clinical correctness.",
                                "Generator and verifier are the same model; verifier passes are provisional."])
    atomic_json(out / "summary.json", summary)
    for r in reports:
        mode = r["replay_mode"] + ("" if r["replay_mode"] == "current" else f" @ {r['code_commit_at_run'][:7]}")
        for c in r["cases"]:
            print(f"ANSWER AUDIT {c['question_id']} ({mode}) {'verified' if not c['problems'] else 'FAILED: ' + '; '.join(c['problems'])}")
        for prob in r["problems"]:
            print(f"ANSWER AUDIT bundle {r['bundle']} FAILED: {prob}")
    print(f"AUDIT_DIR={out}")
    print(json.dumps(dict(status=summary["status"]), ensure_ascii=False))
    return 0 if summary["status"] == "verified" else 1


if __name__ == "__main__":
    sys.exit(main())
