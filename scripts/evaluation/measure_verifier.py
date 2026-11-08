"""Measure the answer-layer checks on a labelled fault set, LAYER BY LAYER.

    # new measurement (real NIM calls unless every request is already cached)
    .venv-embedding\\Scripts\\python.exe -B scripts/evaluation/measure_verifier.py --out reports/verifier_eval_X --nvidia-key-file secrets/nvidia.env [--seed-cache reports/verifier_eval_Y]
    # cache-only replay of recorded measurements (default: all committed ones)
    .venv-embedding\\Scripts\\python.exe -B scripts/evaluation/measure_verifier.py --check [OUT ...]
    # side-by-side tables with fixed denominators
    .venv-embedding\\Scripts\\python.exe -B scripts/evaluation/measure_verifier.py --compare [OUT ...]

Single cases (cases.jsonl): ONE claim per verifier call, built with the pipeline's own build_verify_payload,
VERIFY_SYSTEM and parse_verification. Groups (groups.jsonl, from v0.3 on): the same claims sent TOGETHER in one
call, as the pipeline does, to see whether a verdict depends on the company it keeps.

Layers are reported separately (an improvement of the combined system is not an improvement of the verifier):
  * deterministic: K1 incl. the pharmacological gate (when the code has one);
  * verifier: the model verdict. The verifier is called even when ONLY the gate blocked a claim, so the
    model's own blind spots stay visible (the pipeline itself never sends gate-blocked claims);
  * system: blocked by either layer.
Denominators are fixed per case file: "core" = faults measurable with v0.2 (measurable_from == "v0.2"; 16 in v1),
"all" = every fault case (18 in v1). Each case file is reported on its own; files are never pooled into one rate. "all" = every
fault case. Contested cases are listed, never scored. Labels are team drafts (chua_duyet).
Replay (--check) compares the recorded per-case records with the code that produced them: if the
answer-layer modules or pinned files differ now, the newest commit with that fingerprint is extracted and
replayed in a child process. Scores are derived from records and recomputed by --compare.
"""
from __future__ import annotations

import argparse
import os
import json
import shutil
from datetime import datetime, timezone
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evaluation"))
import verify_answer_layer as va  # noqa: E402  (imports no rag module at load time)

DEFAULT_CASES = "evaluation/answer_verifier_faults_v1/cases.jsonl"
DEFAULT_GROUPS = "evaluation/answer_verifier_faults_v1/groups.jsonl"
DEFAULT_MEASUREMENTS = ["reports/verifier_eval_20261107_v0.2", "reports/verifier_eval_20261107_v0.3", "reports/verifier_eval_20261107_v0.4",
                        "reports/verifier_eval_20261107_v0.5", "reports/verifier_eval_20261107_v0.5_addendum",
                        "reports/verifier_stability_20261107_v0.5/v1_rep1", "reports/verifier_stability_20261107_v0.5/v1_rep2",
                        "reports/verifier_stability_20261107_v0.5/addendum_rep1", "reports/verifier_stability_20261107_v0.5/addendum_rep2",
                        "reports/verifier_controls_20261107_v0.5/rep1", "reports/verifier_controls_20261107_v0.5/rep2",
                        "reports/verifier_controls_20261107_v0.5/rep3",
                        # v0.6 trial (not accepted)
                        "reports/verifier_eval_20261107_v0.6", "reports/verifier_eval_20261107_v0.6_addendum",
                        "reports/verifier_controls_20261107_v0.6/rep1", "reports/verifier_controls_20261107_v0.6/rep2",
                        "reports/verifier_controls_20261107_v0.6/rep3",
                        "reports/verifier_stability_20261107_v0.6/v1_rep1", "reports/verifier_stability_20261107_v0.6/v1_rep2",
                        "reports/verifier_stability_20261107_v0.6/addendum_rep1", "reports/verifier_stability_20261107_v0.6/addendum_rep2",
                        "reports/verifier_stability_20261107_v0.6/groups_v1_rep1", "reports/verifier_stability_20261107_v0.6/groups_v1_rep2",
                        "reports/verifier_stability_20261107_v0.6/groups_addendum_rep1",
                        "reports/verifier_stability_20261107_v0.6/groups_addendum_rep2",
                        "reports/verifier_trial_20261108_v0.7/singles_v1_rep1",
                        "reports/verifier_trial_20261108_v0.7/singles_v1_rep2",
                        "reports/verifier_trial_20261108_v0.7/singles_v1_rep3",
                        "reports/verifier_trial_20261108_v0.7/singles_addendum_rep1",
                        "reports/verifier_trial_20261108_v0.7/singles_addendum_rep2",
                        "reports/verifier_trial_20261108_v0.7/singles_addendum_rep3",
                        "reports/verifier_trial_20261108_v0.7/groups_v1_rep1",
                        "reports/verifier_trial_20261108_v0.7/groups_v1_rep2",
                        "reports/verifier_trial_20261108_v0.7/groups_addendum_rep1",
                        "reports/verifier_trial_20261108_v0.7/groups_addendum_rep2",
                        "reports/verifier_trial_c_small/baseline_singles_c_rep1",
                        "reports/verifier_trial_c_small/baseline_singles_c_rep2",
                        "reports/verifier_trial_c_small/baseline_singles_c_rep3",
                        "reports/verifier_trial_c_small/baseline_groups_c_rep1",
                        "reports/verifier_trial_c_small/baseline_groups_c_rep2",
                        "reports/verifier_trial_c_small/singles_v1_rep1",
                        "reports/verifier_trial_c_small/singles_addendum_rep1",
                        "reports/verifier_trial_c_small/singles_v1_rep2",
                        "reports/verifier_trial_c_small/singles_addendum_rep2",
                        "reports/verifier_trial_c_small/singles_v1_rep3",
                        "reports/verifier_trial_c_small/singles_addendum_rep3",
                        "reports/verifier_trial_c_small/singles_c_rep1",
                        "reports/verifier_trial_c_small/singles_c_rep2"]
CONTENT_PREFIXES = ("support_", "flag_", "check:", "context_limit:")  # verifier reasons about the claim's content (vs schema/wording)
FLAG_TO_ASPECT = {"condition_dropped": "population_scope", "certainty_changed": "certainty",
                  "added_content": "conclusion_topic", "unrequested_medical_content": "question_fit"}
GATE_PREFIX = ("pharm_unrequested:", "known_term_error:")  # deterministic content gates; the verifier is still measured on these


class RunAbort(Exception):
    """A live measurement must stop before (or right after) a provider call."""


def validate_out(out: str) -> Path:
    """--out must be a clean relative path under reports/ (no control characters such as a stray CR, no surrounding
    whitespace). Checked BEFORE any provider call: a bad path once lost 10 paid responses (cache write failed after
    the call)."""
    if not out or out != out.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in out):
        raise RunAbort(f"invalid --out {out!r}: control character or surrounding whitespace")
    path = (ROOT / out).resolve()
    if (ROOT / "reports").resolve() not in path.parents:
        raise RunAbort(f"invalid --out {out!r}: must be a folder under reports/")
    return path


def preflight(out: Path, atomic_json):
    """Create out/cache and prove the cache and ledger are writable with the SAME writer the client uses."""
    if (out / "results.partial.json").exists():
        raise RunAbort(f"{out} holds an interrupted run (results.partial.json); inspect it and use a new --out")
    (out / "cache").mkdir(parents=True, exist_ok=True)
    probe = out / "cache" / ".preflight_probe.json"
    atomic_json(probe, dict(probe=True))
    if json.loads(probe.read_text(encoding="utf-8")) != dict(probe=True):
        raise RunAbort("cache probe did not read back")
    probe.unlink()
    Ledger(out / "calls.jsonl").append(dict(event="preflight_ok"))


class Ledger:
    """Append-only call log, written BEFORE each provider call (fsync), so every paid call is counted even if the
    response is lost. A call with "start" but no "done" is a lost or failed call."""

    def __init__(self, path: Path):
        self.path = path

    def append(self, row):
        row = dict(row, at=datetime.now(timezone.utc).isoformat())
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def summary(self):
        rows = [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()] if self.path.exists() else []
        """Counts kept apart on purpose. A "start" is not proof of a charge, and an error is not proof of no charge
        (e.g. the provider answered but the cache write failed, or the completion was truncated):
        started            calls the measurement began (ledger written before sending)
        saved_responses    fresh provider responses that were saved (certainly billed; tokens known)
        cache_hits         answered from the local cache (no provider call)
        errors             calls that raised; error_codes lists why
        unresolved         started with neither a saved response nor an error row (process killed mid-call)
        cost_unknown       errors + unresolved: may or may not have been billed; reported, never assumed free"""
        starts = {r["n"] for r in rows if r["event"] == "start"}
        done = {r["n"]: r for r in rows if r["event"] == "done"}
        errors = {r["n"]: r for r in rows if r["event"] == "error"}
        unresolved = starts - set(done) - set(errors)
        fresh = [r for r in done.values() if not r.get("cache_hit")]
        return dict(started=len(starts), saved_responses=len(fresh), cache_hits=len(done) - len(fresh), errors=len(errors),
                    error_codes=sorted({r["code"] for r in errors.values()}), unresolved=len(unresolved),
                    cost_unknown=len(errors) + len(unresolved),
                    completion_tokens_saved=sum(r.get("completion_tokens") or 0 for r in fresh))


class LedgerClient:
    """Wraps the provider client for live runs: ledger entry first (a ledger failure means no call), then the call."""

    def __init__(self, client, ledger: Ledger):
        self.client, self.ledger, self.n = client, ledger, 0

    def complete(self, msgs):
        self.n += 1
        self.ledger.append(dict(event="start", n=self.n))
        try:
            out = self.client.complete(msgs)
        except Exception as exc:
            try:  # best effort: the "start" row already counts this call
                self.ledger.append(dict(event="error", n=self.n, code=getattr(exc, "code", None) or type(exc).__name__))
            except OSError:
                pass
            raise
        self.ledger.append(dict(event="done", n=self.n, cache_hit=bool(out.get("cache_hit")), request_id=out.get("request_id"),
                                completion_tokens=(out.get("usage") or {}).get("completion_tokens")))
        return out


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


load_cases = load_jsonl


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
        self.replay_incomplete_ok = False
        self.gate = None
        if "pharm_gate" in self.cfg:  # contract v0.3+
            from rag.answer_pharm import load_pharm_gate
            self.gate = load_pharm_gate(self.cfg["pharm_gate"])
        # change C (trial): only when the configuration enables it; otherwise the v0.5 prompt/payload/parser, byte for byte
        self.ctx = None
        if (self.cfg.get("verifier_context") or {}).get("enabled"):
            from rag import answer_verify_context
            self.ctx = answer_verify_context
        src = self.ctx or self.al
        self.verify_system, self.verify_payload, self.parse = src.VERIFY_SYSTEM, src.build_verify_payload, src.parse_verification

    def _setup(self, trace_path):
        trace = json.loads((ROOT / trace_path).read_text(encoding="utf-8"))
        catalog, sources = self.al.build_catalog(trace, self.cfg, self.corpus)
        needs = [dict(claim_id=n["claim_id"], text=n["text"], required=n.get("required", True))
                 for n in trace["assessment_after_selection"]["claims"]]
        pharm = None
        if self.gate is not None:
            scope = self.gate.scope(trace["question"])
            pharm = lambda text: self.gate.check(text, scope)  # noqa: E731
        return trace, catalog, sources, needs, pharm

    def _k1(self, claims, catalog, sources, needs, pharm):
        need_ids = {n["claim_id"] for n in needs}
        if pharm is None:
            return self.al.check_claims_k1(claims, catalog, sources, need_ids, self.cfg)
        return self.al.check_claims_k1(claims, catalog, sources, need_ids, self.cfg, pharm)

    def _verify(self, client, trace, needs, claims, catalog):
        """Invalid verifier output is a RESULT (the pipeline would show a system error), recorded per claim with the
        mechanical reason "verifier_output_invalid:<check>"; provider/cache errors still propagate."""
        payload = self.verify_payload(trace["question"], needs, claims, [], catalog)
        msgs = [dict(role="system", content=self.verify_system), dict(role="user", content=self.canonical(payload))]
        try:
            out = client.complete(msgs)
        except Exception as exc:  # a truncated completion is a result (pipeline: system_error); other errors propagate
            ok = {"nim_incomplete"} | ({"offline_cache_miss"} if self.replay_incomplete_ok else set())
            if getattr(exc, "code", None) not in ok:  # replay: truncated completions were never cached
                raise
            return {c["claim_id"]: dict(reasons=["verifier_output_incomplete"], verdict=None) for c in claims}, None
        call = dict(request_id=out.get("request_id"), cache_hit=out.get("cache_hit"),
                    elapsed_seconds=out.get("elapsed_seconds"), usage=out.get("usage"))
        try:
            res = self.parse(out["content"], claims, [], needs, catalog, self.cfg)["claims"]
        except self.al.AnswerError as exc:
            if exc.code != "verifier_output_invalid":
                raise
            reason = "verifier_output_invalid:" + str(exc).split(": ", 1)[-1]
            res = {c["claim_id"]: dict(reasons=[reason], verdict=None) for c in claims}
        return res, call

    def check_case(self, case, client):
        trace, catalog, sources, needs, pharm = self._setup(case["trace"])
        claim = dict(claim_id="c1", role="chi_tiet", **case["claim"])
        k1_all = self._k1([claim], catalog, sources, needs, pharm)["c1"]
        gate = [r for r in k1_all if r.startswith(GATE_PREFIX)]
        k1 = [r for r in k1_all if not r.startswith(GATE_PREFIX)]
        rec = dict(case_id=case["case_id"], k1_reasons=k1, verdict=None, reasons=list(k1), call=None)
        if gate:
            rec["gate_reasons"] = gate
        if not k1:  # the verifier is measured even when only the gate blocked the claim
            res, call = self._verify(client, trace, needs, [claim], catalog)
            rec.update(verdict=res["c1"]["verdict"], reasons=res["c1"]["reasons"], call=call)
            if res["c1"]["verdict"] is None:
                rec["verifier_error"] = True
            if gate:
                rec["verifier_reasons"] = res["c1"]["reasons"]
                rec["reasons"] = gate + res["c1"]["reasons"]
        rec["outcome"] = "pass" if not rec["reasons"] else "fail"
        return rec

    def check_group(self, group, cases_by_id, client, pipeline=False):
        """pipeline=False: every structurally valid claim is sent (measures the verifier, incl. gate-blocked claims).
        pipeline=True: only claims passing ALL of K1 (incl. the deterministic gates) are sent, as the pipeline does."""
        members = [cases_by_id[c] for c in group["case_ids"]]
        trace, catalog, sources, needs, pharm = self._setup(members[0]["trace"])
        claims = [dict(claim_id=f"c{i}", role="chi_tiet", **m["claim"]) for i, m in enumerate(members, 1)]
        k1 = self._k1(claims, catalog, sources, needs, pharm)
        if pipeline:
            sent = [c for c in claims if not k1[c["claim_id"]]]
        else:
            sent = [c for c in claims if not [r for r in k1[c["claim_id"]] if not r.startswith(GATE_PREFIX)]]
        res, call = self._verify(client, trace, needs, sent, catalog) if sent else ({}, None)
        recs = []
        for m, c in zip(members, claims):
            v = res.get(c["claim_id"])
            if v is not None and v["verdict"] is None:  # invalid verifier output for the whole group
                recs.append(dict(case_id=m["case_id"], claim_id=c["claim_id"], verdict=None, verifier_reasons=v["reasons"],
                                 verifier_outcome="error"))
                continue
            recs.append(dict(case_id=m["case_id"], claim_id=c["claim_id"], verdict=(v or {}).get("verdict"),
                             verifier_reasons=(v or {}).get("reasons"),
                             verifier_outcome=None if v is None else ("pass" if not v["reasons"] else "fail")))
        return dict(group_id=group["group_id"], call=call, records=recs, sent=[c["claim_id"] for c in sent])

    def blocked_in(self, group, cases_by_id):
        members = [cases_by_id[c] for c in group["case_ids"]]
        trace, catalog, sources, needs, pharm = self._setup(members[0]["trace"])
        claims = [dict(claim_id=f"c{i}", role="chi_tiet", **m["claim"]) for i, m in enumerate(members, 1)]
        k1 = self._k1(claims, catalog, sources, needs, pharm)
        return [m["case_id"] for m, c in zip(members, claims) if k1[c["claim_id"]]]

    def pipeline_groups(self, groups_def, cases_by_id, client):
        """Groups re-sent without the claims the deterministic layer removes (only where that changes the group)."""
        return [self.check_group(g, cases_by_id, client, pipeline=True) for g in groups_def if self.blocked_in(g, cases_by_id)]

    def result(self, cases_file, records, groups_file=None, groups=None, seeded_from=None, pinned_keys=None, code_keys=None,
               pipeline_groups=None):
        cfg = self.cfg
        pins = tuple(pinned_keys) if pinned_keys else tuple(p for p in va.PINNED_FILES if (self.code_root / p).exists())
        code = tuple(code_keys) if code_keys else tuple(p for p in va.CODE_FILES if (self.code_root / p).exists())
        out = dict(schema="verifier_measurement_v2", contract_version=cfg["contract_version"], check_version=cfg["check_version"],
                   verifier_model=cfg["verifier_model"], verify_system_sha256=self.sha(self.verify_system),
                   pharm_gate_version=self.gate.version if self.gate else None,
                   verifier_context=self.ctx.VERSION if self.ctx else None,
                   cases_file=cases_file, cases_sha256=self.sha((ROOT / cases_file).read_text(encoding="utf-8")),
                   code_fingerprint=va.fingerprint(self.code_root, code), pinned_files=va.fingerprint(self.code_root, pins),
                   review_status="chua_duyet", cache_seeded_from=seeded_from,
                   note="Team-draft labels; not clinical adjudication. Single cases: one claim per verifier call.",
                   records=records)
        if groups is not None:
            out.update(groups_file=groups_file, groups_sha256=self.sha((ROOT / groups_file).read_text(encoding="utf-8")),
                       groups=groups)
        if pipeline_groups is not None:
            out["pipeline_groups"] = pipeline_groups
        return out


# ------------------------------------------------------------------ scoring (derived from records)

def layers(rec):
    """(deterministic_fail, verifier_fail or None if not called, system_fail) for one single-case record.
    Invalid verifier output counts as a verifier rejection with a mechanical (non-content) reason."""
    det = bool(rec["k1_reasons"] or rec.get("gate_reasons"))
    if rec.get("verifier_error"):
        ver = True
    elif rec["verdict"] is None:
        ver = None
    else:
        ver = bool(rec.get("verifier_reasons", rec["reasons"]))
    return det, ver, rec["outcome"] == "fail"


def score(cases, records, groups=None, pipeline_groups=None):
    by_id = {r["case_id"]: r for r in records}
    faults = [c for c in cases if c["expected"] == "fail"]
    sets = {"core": [c for c in faults if c["measurable_from"] == "v0.2"], "all": faults}
    s = dict(clean=dict(n=0, false_reject_system=[], false_reject_verifier=[], false_reject_deterministic=[],
                        false_reject_verifier_mechanical=[]),
             contested=[], faults={})
    for c in cases:
        if c["expected"] == "pass":
            det, ver, sysf = layers(by_id[c["case_id"]])
            s["clean"]["n"] += 1
            for name, flag in (("system", sysf), ("verifier", ver), ("deterministic", det)):
                if flag:
                    s["clean"][f"false_reject_{name}"].append(c["case_id"])
            r = by_id[c["case_id"]]
            if ver and not any(x.startswith(CONTENT_PREFIXES) for x in r.get("verifier_reasons", r["reasons"])):
                s["clean"]["false_reject_verifier_mechanical"].append(c["case_id"])
        elif c["expected"] == "contested":
            s["contested"].append(dict(case_id=c["case_id"], outcome=by_id[c["case_id"]]["outcome"]))
    for name, fs in sets.items():
        row = dict(n=len(fs), blocked_deterministic=[], caught_verifier=[], caught_system=[], missed_system=[],
                   missed_verifier=[], right_reason_verifier=[], caught_verifier_mechanical_only=[])
        for c in fs:
            r = by_id[c["case_id"]]
            det, ver, sysf = layers(r)
            if det:
                row["blocked_deterministic"].append(c["case_id"])
            if ver:
                row["caught_verifier"].append(c["case_id"])
                v = r["verdict"] or {}
                vreasons = r.get("verifier_reasons", r["reasons"])
                if not any(x.startswith(CONTENT_PREFIXES) for x in vreasons):
                    row["caught_verifier_mechanical_only"].append(c["case_id"])  # schema / broken wording, not the fault
                aspects = {FLAG_TO_ASPECT[f] for f in c["expected_flags_any"] if f in FLAG_TO_ASPECT}
                failed_aspects = {x.split(":")[1] for x in vreasons if x.startswith("check:")}
                if (set(v.get("flags", [])) & set(c["expected_flags_any"]) or v.get("support") in c["expected_support_any"]
                        or aspects & failed_aspects):
                    row["right_reason_verifier"].append(c["case_id"])
            elif ver is False:
                row["missed_verifier"].append(c["case_id"])
            (row["caught_system"] if sysf else row["missed_system"]).append(c["case_id"])
        s["faults"][name] = row
    if groups:
        expected = {c["case_id"]: c["expected"] for c in cases}
        rows = []
        for g in groups:
            for r in g["records"]:
                single = layers(by_id[r["case_id"]])[1]
                single_o = None if single is None else ("fail" if single else "pass")
                rows.append(dict(group_id=g["group_id"], case_id=r["case_id"], expected=expected[r["case_id"]],
                                 verifier_single=single_o, verifier_group=r["verifier_outcome"]))
        s["groups"] = dict(compared=len(rows), disagree=[x for x in rows if x["verifier_single"] != x["verifier_group"]],
                           rows=rows)
    if pipeline_groups:
        full = {(g["group_id"], r["case_id"]): r["verifier_outcome"] for g in groups or [] for r in g["records"]}
        rows = [dict(group_id=g["group_id"], case_id=r["case_id"], expected=expected[r["case_id"]],
                     verifier_full_group=full.get((g["group_id"], r["case_id"])), verifier_pipeline_group=r["verifier_outcome"])
                for g in pipeline_groups for r in g["records"] if r["verifier_outcome"] is not None]
        s["pipeline_groups"] = dict(compared=len(rows), rows=rows,
                                    changed=[x for x in rows if x["verifier_full_group"] != x["verifier_pipeline_group"]])
    return s


def print_summary(label, res, cases):
    s = score(cases, res["records"], res.get("groups"), res.get("pipeline_groups"))
    c = s["clean"]
    print(f"== {label}: {res['contract_version']} / verifier prompt {res['verify_system_sha256'][:8]} / gate {res.get('pharm_gate_version')}")
    print(f"  clean {c['n']}: false rejects system {len(c['false_reject_system'])} {c['false_reject_system']} | "
          f"verifier {len(c['false_reject_verifier'])} (mechanical only {c['false_reject_verifier_mechanical']}) | "
          f"deterministic {len(c['false_reject_deterministic'])}")
    for name, row in s["faults"].items():
        print(f"  faults {name} (n={row['n']}): system caught {len(row['caught_system'])}/{row['n']} | "
              f"deterministic blocked {len(row['blocked_deterministic'])} {row['blocked_deterministic']} | "
              f"verifier caught {len(row['caught_verifier'])}/{row['n']} (right reason {len(row['right_reason_verifier'])}, "
              f"mechanical only {row['caught_verifier_mechanical_only']}) | "
              f"system missed {row['missed_system']} | verifier missed {row['missed_verifier']}")
    print(f"  contested: {s['contested']}")
    if "groups" in s:
        g = s["groups"]
        print(f"  single vs group (verifier): {g['compared']} compared, {len(g['disagree'])} disagree")
        for x in g["disagree"]:
            print(f"    {x['group_id']} {x['case_id']} ({x['expected']}): single={x['verifier_single']} group={x['verifier_group']}")
    if "pipeline_groups" in s:
        g = s["pipeline_groups"]
        print(f"  groups as the pipeline sends them (deterministic blocks removed): {g['compared']} verdicts, "
              f"{len(g['changed'])} differ from the full group")
        for x in g["rows"]:
            mark = " <- changed" if x in g["changed"] else ""
            print(f"    {x['group_id']} {x['case_id']} ({x['expected']}): full={x['verifier_full_group']} pipeline={x['verifier_pipeline_group']}{mark}")
    return s


def stability(results):
    """Per case: the verifier outcome and support level in each measurement that contains it (order = arguments)."""
    cases = {}
    for res in results:
        expected = {c["case_id"]: c["expected"] for c in load_jsonl(ROOT / res["cases_file"])}
        for r in res["records"]:
            ver = layers(r)[1]
            row = cases.setdefault(r["case_id"], dict(case_id=r["case_id"], expected=expected[r["case_id"]], verifier=[], support=[]))
            row["verifier"].append(None if ver is None else ("fail" if ver else "pass"))
            row["support"].append((r["verdict"] or {}).get("support"))
    rows = [r for r in cases.values() if len(r["verifier"]) > 1]
    for r in rows:
        r["stable"] = len(set(r["verifier"])) == 1
    return rows


# ------------------------------------------------------------------ replay

def _strip(rec):
    return {k: v for k, v in rec.items() if k != "call"}


def check_here(out: Path, code_root: Path = ROOT) -> list[str]:
    """Cache-only replay of one measurement with the rag package under code_root. Returns the differences."""
    rt = Runtime(code_root)
    expected = json.loads((out / "results.json").read_text(encoding="utf-8"))
    # truncated completions are not cached; their records must then match exactly (compared below)
    rt.replay_incomplete_ok = "verifier_output_incomplete" in json.dumps(expected)
    cases = load_jsonl(ROOT / expected["cases_file"])
    if expected.get("case_ids"):
        cases = [c for c in cases if c["case_id"] in expected["case_ids"]]
    client = rt.client_cls(rt.counter, key_supplier=va.no_key, cache_dir=out / "cache", offline=True)
    groups_def = load_jsonl(ROOT / expected["groups_file"]) if expected.get("groups_file") else None
    pipe = None
    try:
        with va.NoNetwork():
            records = [] if expected.get("groups_only") else [rt.check_case(c, client) for c in cases]
            by_id = {c["case_id"]: c for c in cases}
            groups = [rt.check_group(g, by_id, client) for g in groups_def] if groups_def else None
            pipe = rt.pipeline_groups(groups_def, by_id, client) if "pipeline_groups" in expected else None
    except Exception as exc:  # cache miss / tampering
        return [f"replay failed: {getattr(exc, 'code', type(exc).__name__)}"]
    got = rt.result(expected["cases_file"], records, expected.get("groups_file"), groups,
                    pinned_keys=expected["pinned_files"], code_keys=expected["code_fingerprint"])
    diffs = [k for k in ("contract_version", "verify_system_sha256", "cases_sha256", "code_fingerprint", "pinned_files")
             if expected[k] != got[k]]
    # compare the fields each recorded record has (older schemas record fewer fields)
    if len(expected["records"]) != len(records) or any({k: g.get(k) for k in _strip(e)} != _strip(e)
                                                       for e, g in zip(expected["records"], records)):
        diffs.append("records")
    if groups_def and [[_strip(r) for r in g["records"]] for g in expected["groups"]] != [[_strip(r) for r in g["records"]] for g in groups]:
        diffs.append("groups")
    if pipe is not None and [[_strip(r) for r in g["records"]] for g in expected["pipeline_groups"]] != [[_strip(r) for r in g["records"]] for g in pipe]:
        diffs.append("pipeline_groups")
    calls = [r["call"] for r in records] + ([g["call"] for g in groups] if groups else []) + ([g["call"] for g in pipe] if pipe else [])
    if not all(c is None or c["cache_hit"] for c in calls):
        diffs.append("a call was not served from the cache")
    return diffs


def check(out: Path) -> tuple[str, list[str]]:
    expected = json.loads((out / "results.json").read_text(encoding="utf-8"))
    fp, pins = expected["code_fingerprint"], expected["pinned_files"]
    if va.fingerprint(ROOT, tuple(fp)) == fp and va.fingerprint(ROOT, tuple(pins)) == pins:
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
    p.add_argument("--groups", default=DEFAULT_GROUPS)
    p.add_argument("--no-groups", action="store_true", help="single cases only")
    p.add_argument("--groups-only", action="store_true", help="groups (and pipeline groups) only, no single cases")
    p.add_argument("--only", help="comma-separated case ids (e.g. a stability repetition)")
    p.add_argument("--out", help="new measurement folder (cache/ and results.json)")
    p.add_argument("--nvidia-key-file")
    p.add_argument("--seed-cache", metavar="OUT", help="copy the cache of an earlier measurement first (identical requests are not re-sent)")
    p.add_argument("--check", nargs="*", metavar="OUT", help="cache-only replay of recorded measurements")
    p.add_argument("--compare", nargs="*", metavar="OUT", help="print layer tables for recorded measurements")
    p.add_argument("--stability", nargs="+", metavar="OUT",
                   help="per-case verifier outcome across measurements of the same cases (repeated runs)")
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
    if args.stability:
        for row in stability([json.loads((ROOT / m / "results.json").read_text(encoding="utf-8")) for m in args.stability]):
            flag = "" if row["stable"] else "  <- UNSTABLE"
            print(f"{row['case_id']} ({row['expected']}): verifier {row['verifier']} support {row['support']}{flag}")
        return 0
    if args.compare is not None:
        for m in args.compare or DEFAULT_MEASUREMENTS:
            res = json.loads((ROOT / m / "results.json").read_text(encoding="utf-8"))
            print_summary(m, res, load_jsonl(ROOT / res["cases_file"]))
        return 0
    if not args.out:
        p.error("--out, --check or --compare is required")
    try:
        out = validate_out(args.out)
    except RunAbort as exc:
        raise SystemExit(f"preflight: {exc}") from None
    if (out / "results.json").exists():
        raise SystemExit(f"{args.out}/results.json exists; measurements are written once (use --check to replay).")
    if out.exists() and any(p.name != "cache" for p in out.iterdir()):
        raise SystemExit(f"preflight: {args.out} is not empty; measurements go to a new folder.")
    rt = Runtime()
    try:
        preflight(out, rt.atomic_json)
    except (RunAbort, OSError) as exc:
        raise SystemExit(f"preflight: cache or ledger not writable ({exc}); no provider call was made.") from None
    if args.seed_cache:
        (out / "cache").mkdir(parents=True, exist_ok=True)
        for f in (ROOT / args.seed_cache / "cache").glob("*.json"):
            shutil.copy2(f, out / "cache" / f.name)
    cases = load_jsonl(ROOT / args.cases)
    only = args.only.split(",") if args.only else None
    if only:
        unknown = set(only) - {c["case_id"] for c in cases}
        if unknown:
            raise SystemExit(f"unknown case ids: {sorted(unknown)}")
        cases = [c for c in cases if c["case_id"] in only]
    groups_def = [] if args.no_groups else load_jsonl(ROOT / args.groups)
    ledger = Ledger(out / "calls.jsonl")
    client = LedgerClient(rt.client_cls(rt.counter, key_file=args.nvidia_key_file, cache_dir=out / "cache"), ledger)
    records, groups, pipe = [], [], []
    try:
        return _live(args, rt, client, cases, only, groups_def, records, groups, pipe, out, ledger)
    except BaseException as exc:  # stop at once; keep what was measured; never continue a batch silently
        partial = dict(schema="verifier_measurement_partial_v1", error=f"{type(exc).__name__}: {exc}", argv=sys.argv[1:],
                       records=records, groups=groups, pipeline_groups=pipe, ledger=ledger.summary())
        try:
            rt.atomic_json(out / "results.partial.json", partial)
        except OSError:
            print(json.dumps(partial, ensure_ascii=False), file=sys.stderr)
        print(f"STOPPED: {partial['error']} | ledger {partial['ledger']}", file=sys.stderr)
        raise


def _live(args, rt, client, cases, only, groups_def, records, groups, pipe, out, ledger):
    for c in ([] if args.groups_only else cases):
        r = rt.check_case(c, client)
        records.append(r)
        v = r["verdict"] or {}
        print(f"{c['case_id']} expected={c['expected']:<9} outcome={r['outcome']:<4} gate={r.get('gate_reasons', [])} "
              f"{v.get('support', 'k1')} {v.get('flags', r['k1_reasons'])}", flush=True)
    by_id = {c["case_id"]: c for c in cases}
    for g in groups_def:
        groups.append(rt.check_group(g, by_id, client))
        print(f"{g['group_id']} " + " ".join(f"{r['case_id']}={r['verifier_outcome']}" for r in groups[-1]["records"]), flush=True)
    pipe.extend(rt.pipeline_groups(groups_def, by_id, client))
    for g in pipe:
        print(f"{g['group_id']} (pipeline) " + " ".join(f"{r['case_id']}={r['verifier_outcome']}" for r in g["records"]), flush=True)
    if args.seed_cache:  # keep only the cache entries this measurement used (each is identity-validated on read)
        hits ={r["call"]["request_id"] for r in records if r["call"]} | {g["call"]["request_id"] for g in groups + pipe if g["call"]}
        for f in (out / "cache").glob("*.json"):
            if json.loads(f.read_text(encoding="utf-8")).get("request_id") not in hits:
                f.unlink()
    result = rt.result(args.cases, records, None if args.no_groups else args.groups, None if args.no_groups else groups,
                       seeded_from=args.seed_cache, pipeline_groups=None if args.no_groups else pipe)
    if only:
        result["case_ids"] = [c["case_id"] for c in cases]
    if args.groups_only:
        result["groups_only"] = True
    rt.atomic_json(out / "results.json", result)
    print("ledger:", json.dumps(ledger.summary()))
    if not args.groups_only:
        print_summary(args.out, result, cases)
    return 0


if __name__ == "__main__":
    sys.exit(main())
