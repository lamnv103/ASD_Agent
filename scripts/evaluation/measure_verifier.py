"""Measure the answer-layer checks (K1 + model verifier K2/K3) on a labelled fault set.

    # real run (needs secrets/nvidia.env); writes OUT/cache and OUT/results.json
    .venv-embedding\\Scripts\\python.exe -B scripts/evaluation/measure_verifier.py --out reports/verifier_eval_20261107_v0.2 --nvidia-key-file secrets/nvidia.env
    # cache-only replay of recorded measurements; fails if any verdict or score differs
    .venv-embedding\\Scripts\\python.exe -B scripts/evaluation/measure_verifier.py --check reports/verifier_eval_20261107_v0.2 [...]

Each case is ONE claim with catalog IDs from a committed reader-v3 trace (quotes re-derived from the
released corpus). The claim goes through exactly the pipeline's checks: K1, then one verifier call with
build_verify_payload / VERIFY_SYSTEM, then parse_verification. A case PASSES when no reason remains.

Scores:
  * clean cases (expected=pass): false rejects;
  * fault cases (expected=fail): caught or missed (a miss = the claim would have been shown); "right reason"
    = the verdict carries an expected support level or flag (secondary, informative only);
  * contested cases are reported but excluded from rates until a person adjudicates them;
  * faults whose measurable_from names a feature not in this contract version are listed separately.
Replay (--check) uses the code that produced the measurement: if the answer-layer modules or pinned files
differ now, the newest commit with the recorded fingerprint is extracted and replayed in a child process.
Limitations: labels are team drafts (chua_duyet); one claim per call (the pipeline batches claims).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evaluation"))
import verify_answer_layer as va  # noqa: E402  (imports no rag module at load time)

DEFAULT_CASES = "evaluation/answer_verifier_faults_v1/cases.jsonl"
DEFAULT_MEASUREMENTS = ["reports/verifier_eval_20261107_v0.2"]
# contract features each version provides; a fault needing a later feature is reported, not scored
FEATURES = {"answer_contract_v0.2": {"v0.2"}, "answer_contract_v0.3": {"v0.2", "v0.3", "B", "C", "D"}}


def load_cases(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class Runtime:
    """The rag modules of one code root (this checkout, or an extracted older commit)."""

    def __init__(self, code_root: Path = ROOT):
        sys.path.insert(0, str(code_root))
        from rag import answer_layer, answer_policy, answer_sources
        from rag.answer_client import AnswerNimClient
        from rag.retriever import atomic_json, canonical, sha
        from rag.tokenization import load_counter
        self.al, self.client_cls = answer_layer, AnswerNimClient
        self.atomic_json, self.canonical, self.sha = atomic_json, canonical, sha
        self.cfg = answer_policy.load_config()
        self.corpus = answer_sources.load_trusted_corpus()
        self.counter = load_counter(json.loads((code_root / "deployments/evidence_context.json").read_text(encoding="utf-8")))
        self.code_root = code_root

    def check_case(self, case, client):
        al = self.al
        trace = json.loads((ROOT / case["trace"]).read_text(encoding="utf-8"))
        catalog, sources = al.build_catalog(trace, self.cfg, self.corpus)
        needs = [dict(claim_id=n["claim_id"], text=n["text"], required=n.get("required", True))
                 for n in trace["assessment_after_selection"]["claims"]]
        claim = dict(claim_id="c1", role="chi_tiet", **case["claim"])
        k1 = al.check_claims_k1([claim], catalog, sources, {n["claim_id"] for n in needs}, self.cfg)["c1"]
        rec = dict(case_id=case["case_id"], k1_reasons=k1, verdict=None, reasons=list(k1), call=None)
        if not k1:
            payload = al.build_verify_payload(trace["question"], needs, [claim], [], catalog)
            msgs = [dict(role="system", content=al.VERIFY_SYSTEM), dict(role="user", content=self.canonical(payload))]
            out = client.complete(msgs)
            res = al.parse_verification(out["content"], [claim], [], needs, catalog, self.cfg)["claims"]["c1"]
            rec.update(verdict=res["verdict"], reasons=res["reasons"],
                       call=dict(request_id=out.get("request_id"), cache_hit=out.get("cache_hit"),
                                 elapsed_seconds=out.get("elapsed_seconds"), usage=out.get("usage")))
        rec["outcome"] = "pass" if not rec["reasons"] else "fail"
        return rec

    def result(self, cases, records, cases_file):
        cfg = self.cfg
        return dict(schema="verifier_measurement_v1", contract_version=cfg["contract_version"], check_version=cfg["check_version"],
                    verifier_model=cfg["verifier_model"], verify_system_sha256=self.sha(self.al.VERIFY_SYSTEM),
                    cases_file=cases_file, cases_sha256=self.sha((ROOT / cases_file).read_text(encoding="utf-8")),
                    code_fingerprint=va.fingerprint(self.code_root), pinned_files=va.fingerprint(self.code_root, va.PINNED_FILES),
                    review_status="chua_duyet",
                    note="Team-draft labels; not clinical adjudication. One claim per verifier call.",
                    summary=score(cases, records, cfg["contract_version"]), records=records)


def score(cases, records, contract):
    have = FEATURES.get(contract, {"v0.2"})
    by_id = {r["case_id"]: r for r in records}
    s = dict(clean=0, false_reject=[], faults_scored=0, caught=[], missed=[], right_reason=[],
             not_yet_measurable=[], contested=[])
    for c in cases:
        r = by_id[c["case_id"]]
        if c["expected"] == "contested":
            s["contested"].append(dict(case_id=c["case_id"], outcome=r["outcome"]))
        elif c["expected"] == "pass":
            s["clean"] += 1
            if r["outcome"] == "fail":
                s["false_reject"].append(c["case_id"])
        elif c["measurable_from"] not in have:
            s["not_yet_measurable"].append(dict(case_id=c["case_id"], needs=c["measurable_from"], outcome=r["outcome"]))
        else:
            s["faults_scored"] += 1
            (s["caught"] if r["outcome"] == "fail" else s["missed"]).append(c["case_id"])
            v = r["verdict"] or {}
            if r["outcome"] == "fail" and (set(v.get("flags", [])) & set(c["expected_flags_any"])
                                           or v.get("support") in c["expected_support_any"] or r["k1_reasons"]):
                s["right_reason"].append(c["case_id"])
    return s


def check_here(out: Path, code_root: Path = ROOT) -> list[str]:
    """Cache-only replay of one measurement with the rag package under code_root. Returns the differences."""
    rt = Runtime(code_root)
    expected = json.loads((out / "results.json").read_text(encoding="utf-8"))
    cases = load_cases(ROOT / expected["cases_file"])
    client = rt.client_cls(rt.counter, key_supplier=va.no_key, cache_dir=out / "cache", offline=True)
    try:
        with va.NoNetwork():
            records = [rt.check_case(c, client) for c in cases]
    except Exception as exc:  # cache miss / tampering
        return [f"replay failed: {getattr(exc, 'code', type(exc).__name__)}"]
    got = rt.result(cases, records, expected["cases_file"])
    strip = lambda rs: [{k: v for k, v in r.items() if k != "call"} for r in rs]  # noqa: E731
    diffs = [k for k in ("contract_version", "verify_system_sha256", "cases_sha256", "code_fingerprint", "pinned_files", "summary")
             if expected[k] != got[k]]
    if strip(expected["records"]) != strip(records):
        diffs.append("records")
    if not all(r["call"] is None or r["call"]["cache_hit"] for r in records):
        diffs.append("a call was not served from the cache")
    return diffs


def check(out: Path) -> tuple[str, list[str]]:
    expected = json.loads((out / "results.json").read_text(encoding="utf-8"))
    fp, pins = expected["code_fingerprint"], expected["pinned_files"]
    if va.fingerprint(ROOT) == fp and va.fingerprint(ROOT, tuple(pins)) == pins:
        return "current", check_here(out)
    commit = va.find_commit(fp, pins)
    if commit is None:
        return "legacy", ["no commit holds the code that produced this measurement"]
    report, err = va.run_child_at(commit, Path(__file__).resolve(), ["--check", str(out)])
    return f"legacy @ {commit[:7]}", (report["diffs"] if report else [f"legacy replay crashed: {err}"])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cases", default=DEFAULT_CASES)
    p.add_argument("--out", help="new measurement folder (cache/ and results.json)")
    p.add_argument("--nvidia-key-file")
    p.add_argument("--check", nargs="*", metavar="OUT", help="cache-only replay of recorded measurements")
    p.add_argument("--child-code-root", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.child_code_root:
        print(json.dumps(dict(diffs=check_here(Path(args.check[0]), Path(args.child_code_root))), ensure_ascii=False))
        return 0
    if args.check is not None:
        failed = False
        for m in args.check or DEFAULT_MEASUREMENTS:
            mode, diffs = check(ROOT / m)
            failed |= bool(diffs)
            print(f"VERIFIER MEASUREMENT {m} ({mode}) " + ("verified" if not diffs else "FAILED: " + ", ".join(diffs)))
        print(json.dumps(dict(status="failed" if failed else "verified")))
        return 1 if failed else 0
    if not args.out:
        p.error("--out or --check is required")
    out = ROOT / args.out
    if (out / "results.json").exists():
        raise SystemExit(f"{args.out}/results.json exists; measurements are written once (use --check to replay).")
    rt = Runtime()
    cases = load_cases(ROOT / args.cases)
    client = rt.client_cls(rt.counter, key_file=args.nvidia_key_file, cache_dir=out / "cache")
    records = []
    for c in cases:
        r = rt.check_case(c, client)
        records.append(r)
        v = r["verdict"] or {}
        print(f"{c['case_id']} expected={c['expected']:<9} outcome={r['outcome']:<4} {v.get('support', 'k1')} "
              f"{v.get('flags', r['k1_reasons'])}", flush=True)
    result = rt.result(cases, records, args.cases)
    rt.atomic_json(out / "results.json", result)
    n = result["summary"]
    print(f"clean: {n['clean']} | false rejects: {len(n['false_reject'])} {n['false_reject']}")
    print(f"faults scored: {n['faults_scored']} | caught: {len(n['caught'])} | missed: {len(n['missed'])} {n['missed']} "
          f"| right reason: {len(n['right_reason'])}")
    print(f"not yet measurable: {n['not_yet_measurable']}")
    print(f"contested: {n['contested']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
