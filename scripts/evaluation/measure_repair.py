"""Controlled repair-round trial: term guidance in repair problems (arm B) vs v0.5 problems (arm A).

  .venv-embedding\\Scripts\\python.exe -B scripts/evaluation/measure_repair.py --units U --unit U1 --arm B --out reports/X \\
      --nvidia-key-file secrets/nvidia.env                          # one repetition (2 provider calls: repair, verify_repair)
  ... measure_repair.py --check [OUT ...]                           # cache-only replay of recorded repetitions
  ... measure_repair.py --review-sheet CRITERIA                     # blind review sheet of every displayed claim
  ... measure_repair.py --judge CRITERIA                            # rules, after the review file is filled in

Same input for both arms, by construction: the real v0.5 pipeline (rag.answer_layer.answer_from_trace, unchanged) runs
through RouterClient. The first round (generate + verify) is REPLAYED offline from a recorded bundle; a unit may derive
its first-round output from the recorded one by exact text replacements (held-out variants). A first-round request that
is not in the bundle stops the run before any provider call. Only the repair round is live. Arm B differs from arm A
ONLY in the repair request: problems with known_term_error reasons carry term_guidance (rag.answer_repair_terms).
Every rewritten claim goes through all v0.5 checks again (K1, gates, known terms, verifier on the NEW wording, status).
Run safety: measure_verifier.validate_out / preflight / Ledger / results.partial.json.
"""
import argparse
import json
import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evaluation"))
import measure_verifier as mv  # noqa: E402
import verify_answer_layer as va  # noqa: E402

COMPARED = va.COMPARED + ("route",)
REVIEW_FIELDS = ("concepts", "term_correct", "faithful", "contains_known_wrong_content", "note")


class FirstRoundMismatch(Exception):
    """The first-round request differs from the recorded bundle: the arms would not share the same input."""


class RouterClient:
    """Serves the first round from the bundle (or a derived fixture), the repair round live; arm B annotates problems."""

    def __init__(self, al, terms, replay, live, arm, guidance, canonical, generate_raw=None):
        self.al, self.terms, self.replay, self.live, self.arm = al, terms, replay, live, arm
        self.guidance, self.canonical, self.generate_raw = guidance, canonical, generate_raw
        self.repaired, self.sent_problems = False, None

    def _replayed(self, msgs):
        try:
            return self.replay.complete(msgs)
        except Exception as exc:
            if getattr(exc, "code", None) == "offline_cache_miss":
                raise FirstRoundMismatch("first-round request not in the recorded bundle") from None
            raise

    def complete(self, msgs):
        system = msgs[0]["content"]
        if system == self.al.GEN_SYSTEM:
            if self.generate_raw is None:
                return self._replayed(msgs)
            return dict(content=self.generate_raw, cache_hit=True, request_id="fixture", usage=None, fixture=True)
        if system == self.al.REPAIR_SYSTEM:
            self.repaired = True
            payload = json.loads(msgs[1]["content"])
            if self.arm == "B":
                annotated = self.terms.annotate_problems(payload["problems"], self.guidance)
                if annotated != payload["problems"]:
                    payload["problems"] = annotated
                    msgs = [msgs[0], dict(role="user", content=self.canonical(payload))]
            self.sent_problems = payload["problems"]
            return self.live.complete(msgs)
        if system == self.al.VERIFY_SYSTEM:
            return self.live.complete(msgs) if self.repaired else self._replayed(msgs)
        raise ValueError("unknown system prompt")


class Runtime:
    def __init__(self, code_root: Path = ROOT):
        sys.path.insert(0, str(code_root))
        from rag import answer_layer, answer_repair_terms
        from rag.answer_client import AnswerNimClient
        from rag.answer_policy import load_config
        from rag.answer_sources import load_trusted_corpus
        from rag.retriever import atomic_json, canonical, sha
        from rag.tokenization import load_counter
        self.al, self.terms, self.client_cls = answer_layer, answer_repair_terms, AnswerNimClient
        self.atomic_json, self.canonical, self.sha = atomic_json, canonical, sha
        self.cfg = load_config()
        self.counter = load_counter(json.loads((code_root / "deployments/evidence_context.json").read_text(encoding="utf-8")))
        self.guidance = answer_repair_terms.load_term_guidance(code_root / "deployments/answer_term_guidance.json",
                                                               self.cfg["known_term_errors"]["terms"])
        self.corpus = load_trusted_corpus()
        self.code_root = code_root

    def unit_inputs(self, unit):
        manifest = json.loads((ROOT / unit["bundle"] / "manifest.json").read_text(encoding="utf-8"))
        case = next(c for c in manifest["cases"] if c["question_id"] == unit["question_id"])
        trace = json.loads((ROOT / case["trace"]).read_text(encoding="utf-8"))
        raw = None
        if unit.get("derive"):
            raw = recorded_generate(ROOT / unit["bundle"], trace["question"], self.al.GEN_SYSTEM)
            for r in unit["derive"]:
                if raw.count(r["old"]) != 1:
                    raise ValueError(f"{unit['unit_id']}: replacement text must occur exactly once")
                raw = raw.replace(r["old"], r["new"])
        return trace, date.fromisoformat(manifest["as_of"]), raw

    def run(self, unit, arm, live):
        trace, as_of, raw = self.unit_inputs(unit)
        replay = self.client_cls(self.counter, key_supplier=va.no_key, cache_dir=ROOT / unit["bundle"] / "cache", offline=True)
        router = RouterClient(self.al, self.terms, replay, live, arm, self.guidance, self.canonical, raw)
        res = self.al.answer_from_trace(trace, client=router, as_of=as_of)
        if res["route"] == "system_error" and not router.repaired:
            raise FirstRoundMismatch(f"first round did not replay from the bundle: {res.get('error')}")
        catalog, _ = self.al.build_catalog(trace, self.cfg, self.corpus)
        res["quotes"] = {k: v["quote"] for k, v in catalog.items()}
        return res, router.sent_problems

    def record(self, unit, arm, res, sent):
        pins = tuple(p for p in va.PINNED_FILES if (self.code_root / p).exists())
        code = tuple(p for p in va.CODE_FILES if (self.code_root / p).exists())
        return dict(schema="repair_measurement_v1", unit_id=unit["unit_id"], arm=arm, contract_version=self.cfg["contract_version"],
                    term_guidance_version=self.guidance["version"], review_status="chua_duyet",
                    code_fingerprint=va.fingerprint(self.code_root, code), pinned_files=va.fingerprint(self.code_root, pins),
                    sent_problems=sent, result={k: res.get(k) for k in COMPARED + ("claims_removed", "calls", "error", "quotes")})


def recorded_generate(bundle: Path, question: str, gen_system: str) -> str:
    for f in sorted((bundle / "cache").glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        msgs = rec["identity"]["payload"]["messages"]
        if msgs[0]["content"] == gen_system and json.loads(msgs[1]["content"])["question"] == question:
            return rec["content"]
    raise FileNotFoundError("no recorded first-round generation for this question")


def load_units(path):
    return {u["unit_id"]: u for u in mv.load_jsonl(ROOT / path)}


def live_run(args):
    out = mv.validate_out(args.out)
    if (out / "results.json").exists() or (out.exists() and any(p.name != "cache" for p in out.iterdir())):
        raise SystemExit(f"preflight: {args.out} is not new")
    rt = Runtime()
    mv.preflight(out, rt.atomic_json)
    unit = load_units(args.units)[args.unit]
    ledger = mv.Ledger(out / "calls.jsonl")
    live = mv.LedgerClient(rt.client_cls(rt.counter, key_file=args.nvidia_key_file, cache_dir=out / "cache"), ledger)
    try:
        res, sent = rt.run(unit, args.arm, live)
        if res["route"] == "system_error":
            raise RuntimeError(f"system_error: {res.get('error')}")
        rec = dict(rt.record(unit, args.arm, res, sent), units_file=args.units)
        rt.atomic_json(out / "results.json", rec)
    except BaseException as exc:
        rt.atomic_json(out / "results.partial.json", dict(schema="repair_measurement_partial_v1", error=f"{type(exc).__name__}: {exc}",
                                                         unit_id=args.unit, arm=args.arm, ledger=ledger.summary()))
        print(f"STOPPED: {type(exc).__name__}: {exc} | ledger {ledger.summary()}", file=sys.stderr)
        raise
    print(f"{args.unit} arm {args.arm}: status={res['status']} final={[c['claim_id'] for c in res['claims_final']]} "
          f"| ledger {json.dumps(ledger.summary())}")
    return 0


def check_here(out: Path, code_root: Path = ROOT):
    exp = json.loads((out / "results.json").read_text(encoding="utf-8"))
    rt = Runtime(code_root)
    unit = load_units(exp["units_file"])[exp["unit_id"]]
    live = rt.client_cls(rt.counter, key_supplier=va.no_key, cache_dir=out / "cache", offline=True)
    with va.NoNetwork():
        res, sent = rt.run(unit, exp["arm"], live)
    got = rt.record(unit, exp["arm"], res, sent)
    diffs = [k for k in ("contract_version", "term_guidance_version", "sent_problems") if got[k] != exp[k]]
    diffs += [f"result.{k}" for k in COMPARED if got["result"].get(k) != exp["result"].get(k)]
    return diffs


def check(out: Path):
    exp = json.loads((out / "results.json").read_text(encoding="utf-8"))
    fp, pins = exp["code_fingerprint"], exp["pinned_files"]
    if va.fingerprint(ROOT, tuple(fp)) == fp and va.fingerprint(ROOT, tuple(pins)) == pins:
        return "current", check_here(out)
    commit = va.find_commit(fp, pins)
    if commit is None:
        return "legacy", ["no commit holds the code that produced this measurement"]
    report, err = va.run_child_at(commit, Path(__file__).resolve(), ["--check", str(out)])
    return f"legacy @ {commit[:7]}", (report["diffs"] if report else [f"legacy replay crashed: {err}"])


# ---------------------------------------------------------------- blind review and judging
def displayed(crit):
    """Every displayed claim of every arm run, with its run identity (for the key) and its cited quotes."""
    rows, missing = [], []
    for run in crit["runs"]:
        p = ROOT / run["out"] / "results.json"
        if not p.exists():
            missing.append(run["out"])
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        cat = rec["result"]["quotes"]
        for c in rec["result"]["claims_final"]:
            rows.append(dict(out=run["out"], unit_id=rec["unit_id"], arm=rec["arm"], claim_id=c["claim_id"], text=c["text"],
                             cited=[dict(id=e, quote=cat[e]) for e in c["evidence_ids"]]))
    return rows, missing


def review_sheet(crit):
    rows, missing = displayed(crit)
    if missing:
        raise SystemExit(f"runs missing: {missing}")
    rng = random.Random(crit["review"]["seed"])
    order = list(range(len(rows)))
    rng.shuffle(order)
    sheet, key = [], {}
    for i, k in enumerate(order, 1):
        rid = f"R{i:03d}"
        r = rows[k]
        sheet.append(dict(review_id=rid, question_id=crit["question_id"], text=r["text"], cited=r["cited"],
                          concept_choices=crit["review"]["concepts"], **{f: None for f in REVIEW_FIELDS}))
        key[rid] = {x: r[x] for x in ("out", "unit_id", "arm", "claim_id")}
    return sheet, key


def judge(crit, reviews, key):
    """Rules on the blind review (unblinded with the key). Returns (rules, report, problems)."""
    rows, missing = displayed(crit)
    problems = [f"missing run {m}" for m in missing]
    by_run = {}
    for rid, k in key.items():
        rv = reviews.get(rid)
        if rv is None or any(rv.get(f) is None for f in ("concepts", "term_correct", "faithful", "contains_known_wrong_content")):
            problems.append(f"review incomplete: {rid}")
            continue
        by_run.setdefault(k["out"], []).append(dict(k, **rv))
    for run in crit["runs"]:
        if run["out"] not in missing:
            by_run.setdefault(run["out"], [])  # a run that displays nothing still counts (as a failure where content is required)
    runs = {r["out"]: r for r in crit["runs"]}
    good = lambda c: c["faithful"] == "y" and c["term_correct"] in ("y", "na")  # noqa: E731

    def covers(claims, concept):
        return any(concept in c["concepts"] and good(c) for c in claims)

    out, rep = {}, {}
    rules = {r["id"]: r for r in crit["rules"]}
    for rid, rule in rules.items():
        sel = [o for o in by_run if runs[o]["unit"] == rule["unit"] and runs[o]["arm"] in rule["arms"]]
        if rule["type"] == "covers_all":
            bad = [(o, cn) for o in sel for cn in rule["concepts"] if not covers(by_run[o], cn)]
        elif rule["type"] == "no_bad_on_concepts":
            bad = [(o, c["claim_id"]) for o in sel for c in by_run[o] if set(c["concepts"]) & set(rule["concepts"]) and not good(c)]
        elif rule["type"] == "no_known_wrong_content":
            bad = [(o, c["claim_id"]) for o in sel for c in by_run[o] if c["contains_known_wrong_content"] == "y"]
        else:
            raise ValueError(rule["type"])
        out[rid] = dict(ok=bool(sel) and len(sel) == rule["reps"] and not bad, n=len(sel), expected=rule["reps"], detail=bad)
    # attribution: arm B covers the term concepts in every repetition AND arm A does not
    att = crit["attribution"]
    fixed = {arm: sum(all(covers(by_run[o], cn) for cn in att["concepts"]) for o in by_run
                      if runs[o]["unit"] == att["unit"] and runs[o]["arm"] == arm) for arm in ("A", "B")}
    out["attribution"] = dict(ok=fixed["B"] == att["reps"] and fixed["A"] < att["reps"], fixed_reps=fixed)
    for o, claims in by_run.items():
        rep[o] = dict(arm=runs[o]["arm"], unit=runs[o]["unit"], displayed=len(claims), acceptable=sum(good(c) for c in claims),
                      term_fixed_concepts=[cn for cn in att["concepts"] if covers(claims, cn)])
    return out, rep, problems


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--units")
    p.add_argument("--unit")
    p.add_argument("--arm", choices=("A", "B"))
    p.add_argument("--out")
    p.add_argument("--nvidia-key-file")
    p.add_argument("--check", nargs="*", metavar="OUT")
    p.add_argument("--review-sheet", metavar="CRITERIA")
    p.add_argument("--judge", metavar="CRITERIA")
    p.add_argument("--child-code-root", help=argparse.SUPPRESS)
    a = p.parse_args()
    if a.child_code_root:
        print(json.dumps(dict(diffs=check_here(Path(a.check[0]), Path(a.child_code_root))), ensure_ascii=False))
        return 0
    if a.check is not None:
        failed = False
        for o in a.check:
            mode, diffs = check(ROOT / o)
            failed |= bool(diffs)
            print(f"REPAIR MEASUREMENT {o} ({mode}) " + ("verified" if not diffs else "FAILED: " + ", ".join(diffs)))
        print(json.dumps(dict(status="failed" if failed else "verified")))
        return 1 if failed else 0
    if a.review_sheet:
        crit = json.loads((ROOT / a.review_sheet).read_text(encoding="utf-8"))
        sheet, key = review_sheet(crit)
        for path, data in ((crit["review"]["sheet"], sheet), (crit["review"]["key"], key)):
            (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
            (ROOT / path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{len(sheet)} claims -> {crit['review']['sheet']} (blind); key -> {crit['review']['key']}")
        return 0
    if a.judge:
        crit = json.loads((ROOT / a.judge).read_text(encoding="utf-8"))
        reviews = {r["review_id"]: r for r in json.loads((ROOT / crit["review"]["filled"]).read_text(encoding="utf-8"))}
        key = json.loads((ROOT / crit["review"]["key"]).read_text(encoding="utf-8"))
        out, rep, problems = judge(crit, reviews, key)
        if problems:
            print("INCOMPLETE (not judged):\n  " + "\n  ".join(problems))
            return 2
        for k, r in out.items():
            print(f"{k}: {'PASS' if r['ok'] else 'FAIL'} {({x: y for x, y in r.items() if x != 'ok'})}")
        for o, r in rep.items():
            print("  ", o, r)
        ok = all(r["ok"] for r in out.values())
        print("DECISION:", crit["decision"]["all_rules_pass" if ok else "any_rule_fails"])
        return 0 if ok else 1
    if not (a.units and a.unit and a.arm and a.out):
        p.error("--units, --unit, --arm and --out are required for a live repetition")
    try:
        mv.validate_out(a.out)
    except mv.RunAbort as exc:
        raise SystemExit(f"preflight: {exc}") from None
    return live_run(a)


if __name__ == "__main__":
    sys.exit(main())
