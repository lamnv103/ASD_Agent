"""Judge a pre-registered verifier trial (criteria.json) against its recorded measurements. No provider calls.

  python scripts/evaluation/check_trial.py evaluation/trials/<trial>/criteria.json            # verdict
  python scripts/evaluation/check_trial.py evaluation/trials/<trial>/criteria.json --commands # run plan (display only;
                                                                                              # run it with run_trial.py)
The criteria file is committed before the first provider call; this script only reads it.
Exit code 0 = every rule passed, 1 = at least one rule failed,
2 = measurements missing, incomplete (a case, group or repetition absent) or from another contract.

Two criteria formats:
* "rules" as an object: the v0.7 small stage (kept so its recorded verdict stays reproducible);
* "rules" as a list of typed rules (v0.8 / C onward), applied to runs of stage "trial" only:
  detected_limit every selected row rejected with EXACTLY the reason context_limit:<id>, with NO mechanical reason, and
                 the recorded other_passage_issue span containing one of the pre-registered accepted_sentences
                 (right id is not enough: the right sentence is required)
  rejected_for   every selected row rejected AND carrying a reason equal to one of reasons_exact (or starting with one of
                 reasons_prefix); with "clean": true a row that also has a mechanical reason does not count
  never_rejected no selected row rejected, for any reason
  no_reason      no row of any trial run carries a reason starting with one of prefixes
  max_tokens     every fresh call at most `limit` completion tokens
  Selections: {"where": "single" | "<group_id>" | "<group_id>/pipeline", "cases": [...]}.
Mechanical reasons (schema, truncation, non-verbatim quotes) are listed separately and never count as a catch
unless a rule names them explicitly.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rag.answer_layer import _span_norm  # noqa: E402  (same normalization as the verbatim checks)
ERROR_PREFIX = "verifier_output_"
MECHANICAL = ("verifier_output_", "span_not_in_cited_evidence", "context_id_invalid", "context_span_not_verbatim",
              "context_span_not_whole_sentence", "verdict_missing")


def load(run):
    p = ROOT / run["out"] / "results.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load_jsonl(path):
    return [json.loads(x) for x in (ROOT / path).read_text(encoding="utf-8").splitlines() if x.strip()]


def tokens(call):
    return (call or {}).get("usage", {}).get("completion_tokens") if call and not call.get("cache_hit") else None


def collect(crit):
    """Flatten every recorded run into rows (run, stage, where, case_id, rejected, reasons) plus call token counts."""
    rows, toks, problems = [], [], []
    for run in crit["runs"]:
        res = load(run)
        if res is None:
            problems.append(f"missing measurement {run['out']}")
            continue
        want = run.get("contract", crit["contract_version"])
        if res["contract_version"] != want:
            problems.append(f"{run['out']}: contract {res['contract_version']} != {want}")
        stage = run.get("stage", "trial")
        for r in res.get("records", []):
            reasons = r.get("verifier_reasons", r["reasons"])
            rows.append(dict(run=run["out"], stage=stage, group=None, where="single", case_id=r["case_id"],
                             rejected=r["outcome"] == "fail", reasons=list(r["reasons"]), verifier_reasons=list(reasons or []),
                             verdict=r.get("verdict")))
            toks.append((run["out"], stage, r["case_id"], tokens(r.get("call"))))
        for kind, gs in (("", res.get("groups", [])), ("/pipeline", res.get("pipeline_groups", []))):
            for g in gs:
                toks.append((run["out"], stage, g["group_id"] + kind, tokens(g.get("call"))))
                for r in g["records"]:
                    if r["verifier_outcome"] is None:  # removed before the verifier in the pipeline group (not sent)
                        continue
                    reasons = r.get("verifier_reasons") or []
                    rows.append(dict(run=run["out"], stage=stage, group=g["group_id"], where=g["group_id"] + kind,
                                     case_id=r["case_id"], rejected=r["verifier_outcome"] in ("fail", "error"),
                                     reasons=list(reasons), verifier_reasons=list(reasons), verdict=r.get("verdict")))
    return rows, toks, problems


def completeness(crit, rows):
    """Every planned case of every run must be present: singles from "only", groups from the groups file (+ the
    pipeline groups the run declares in "pipeline")."""
    missing = []
    have = {(r["run"], r["where"], r["case_id"]) for r in rows}
    for run in crit["runs"]:
        if load(run) is None:
            continue
        if "groups" in run:
            for g in load_jsonl(run["groups"]):
                for c in g["case_ids"]:
                    if (run["out"], g["group_id"], c) not in have:
                        missing.append(f"{run['out']}: {g['group_id']}/{c}")
            for gid, cases in run.get("pipeline", {}).items():
                for c in cases:
                    if (run["out"], gid + "/pipeline", c) not in have:
                        missing.append(f"{run['out']}: {gid}/pipeline/{c}")
        else:
            for c in run["only"].split(","):
                if (run["out"], "single", c) not in have:
                    missing.append(f"{run['out']}: single/{c}")
    return missing


def _mechanical(row):
    return [x for x in row["reasons"] + row["verifier_reasons"] if x.startswith(MECHANICAL)]


def _rejected_for(row, rule):
    if not row["rejected"] or (rule.get("clean") and _mechanical(row)):
        return False
    return any(x in rule.get("reasons_exact", []) or x.startswith(tuple(rule.get("reasons_prefix", [])))
               for x in row["verifier_reasons"])


def _detected(row, rule):
    """Right passage AND right sentence, and nothing mechanical alongside."""
    if not row["rejected"] or _mechanical(row) or ("context_limit:" + rule["passage_id"]) not in row["verifier_reasons"]:
        return False
    issue = (row.get("verdict") or {}).get("other_passage_issue") or {}
    span = _span_norm(issue.get("span") or "")
    return issue.get("id") == rule["passage_id"] and any(_span_norm(s) in span for s in rule["accepted_sentences"])


def _selected(rows, select):
    keys = {(s["where"], c) for s in select for c in s["cases"]}
    return [r for r in rows if (r["where"], r["case_id"]) in keys]


def judge_list(crit):
    rows, toks, problems = collect(crit)
    problems += completeness(crit, rows)
    trial = [r for r in rows if r["stage"] == "trial"]
    out = {}
    for rule in crit["rules"]:
        t, rid = rule["type"], rule["id"]
        if t in ("detected_limit", "rejected_for", "never_rejected"):
            sel = _selected(trial, rule["select"])
            expected = sum(len(s["cases"]) * rule.get("reps", {}).get(s["where"], 1) for s in rule["select"])
            if t == "detected_limit":
                bad = [r for r in sel if not _detected(r, rule)]
            elif t == "rejected_for":
                bad = [r for r in sel if not _rejected_for(r, rule)]
            else:
                bad = [r for r in sel if r["rejected"]]
            ok = bool(sel) and not bad and len(sel) == expected
            out[rid] = dict(ok=ok, n=len(sel), expected=expected,
                            detail=[(r["where"], r["case_id"], r["verifier_reasons"] or r["reasons"],
                                     ((r.get("verdict") or {}).get("other_passage_issue") or {}).get("span")) for r in bad])
        elif t == "no_reason":
            bad = [(r["where"], r["case_id"], x) for r in trial for x in r["reasons"] if x.startswith(tuple(rule["prefixes"]))]
            out[rid] = dict(ok=not bad, detail=bad)
        elif t == "max_tokens":
            mine = [x for x in toks if x[1] == "trial"]
            fresh = [x for x in mine if x[3] is not None]
            over = [x for x in fresh if x[3] > rule["limit"]]
            out[rid] = dict(ok=bool(fresh) and not over and len(fresh) == len(mine), detail=over,
                            max=max((x[3] for x in fresh), default=None), calls=len(mine), fresh=len(fresh))
        else:
            raise ValueError(f"unknown rule type {t}")
    mech = [(r["stage"], r["where"], r["case_id"], x) for r in rows for x in r["reasons"] if x.startswith(MECHANICAL)]
    named = {(s["where"], c) for rule in crit["rules"] for s in rule.get("select", []) for c in s["cases"]}
    report = [(r["stage"], r["where"], r["case_id"], "fail" if r["rejected"] else "pass", r["verifier_reasons"] or r["reasons"])
              for r in rows if r["stage"] != "trial" or (r["where"], r["case_id"]) not in named]
    return out, dict(report_only=report, mechanical=mech), problems


# ---------------------------------------------------------------- v0.7 small stage (object rules), unchanged
def judge_legacy(crit):
    rows, toks, problems = collect(crit)
    R = crit["rules"]
    table = set(R["R1_focal_single"]["table_reasons"])
    out = {}

    def has_table(row):
        return row["rejected"] and bool(table & set(row["verifier_reasons"]))

    single = [r for r in rows if r["group"] is None]
    grouped = [r for r in rows if r["group"] is not None]
    r1 = [r for r in single if r["case_id"] in R["R1_focal_single"]["cases"]]
    out["R1_focal_single"] = dict(ok=bool(r1) and all(has_table(r) for r in r1),
                                  detail=[(r["case_id"], has_table(r), r["verifier_reasons"]) for r in r1])
    r2 = [r for r in grouped if r["case_id"] in R["R2_focal_group"]["members"].get(r["group"], [])]
    out["R2_focal_group"] = dict(ok=bool(r2) and all(has_table(r) for r in r2),
                                 detail=[(r["group"], r["case_id"], has_table(r), r["verifier_reasons"]) for r in r2])
    r3 = ([r for r in single if r["case_id"] in R["R3_clean"]["single"]]
          + [r for r in grouped if r["case_id"] in R["R3_clean"]["group"].get(r["group"], [])])
    out["R3_clean"] = dict(ok=bool(r3) and not any(r["rejected"] for r in r3),
                           detail=[(r["group"] or "single", r["case_id"], r["reasons"]) for r in r3 if r["rejected"]],
                           n=len(r3))
    errs = [(r["group"] or "single", r["case_id"], x) for r in rows for x in r["reasons"] if x.startswith(ERROR_PREFIX)]
    out["R4_format"] = dict(ok=not errs, detail=errs)
    limit = R["R5_length"]["max_completion_tokens"]
    fresh = [t for t in toks if t[3] is not None]
    over = [t for t in fresh if t[3] > limit]
    out["R5_length"] = dict(ok=bool(fresh) and not over and len(fresh) == len(toks), detail=over,
                            max=max((t[3] for t in fresh), default=None), calls=len(toks), fresh=len(fresh))
    report = [(r["group"] or "single", r["case_id"], "fail" if r["rejected"] else "pass", r["verifier_reasons"])
              for r in rows if r["case_id"] not in R["R1_focal_single"]["cases"] + R["R3_clean"]["single"] + ["P08"]]
    return out, report, problems


def judge(crit):
    return judge_list(crit) if isinstance(crit["rules"], list) else judge_legacy(crit)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("criteria")
    p.add_argument("--commands", action="store_true", help="print the run plan (display only; use run_trial.py to run it)")
    a = p.parse_args()
    crit = json.loads((ROOT / a.criteria).read_text(encoding="utf-8"))
    if a.commands:
        for run in crit["runs"]:
            sel = f"--groups {run['groups']} --groups-only" if "groups" in run else f"--only {run['only']} --no-groups"
            print(f"python scripts/evaluation/measure_verifier.py --cases {run['cases']} {sel} --out {run['out']}")
        return 0
    out, report, problems = judge(crit)
    if problems:
        print("INCOMPLETE OR INVALID (not judged):")
        print("\n".join("  " + x for x in problems))
        return 2
    for name, r in out.items():
        print(f"{name}: {'PASS' if r['ok'] else 'FAIL'}")
        extra = {k: v for k, v in r.items() if k not in ("ok", "detail")}
        if extra:
            print("   ", extra)
        for d in r["detail"]:
            print("   ", d)
    if isinstance(report, dict):
        print("mechanical reasons (reported separately, never a catch):")
        for row in report["mechanical"]:
            print("   ", row)
        report = report["report_only"]
    print("report-only:")
    for row in report:
        print("   ", row)
    ok = all(r["ok"] for r in out.values())
    print("DECISION:", crit["decision"]["all_rules_pass" if ok else "any_rule_fails"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
