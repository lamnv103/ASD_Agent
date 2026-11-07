"""Judge a pre-registered verifier trial (criteria.json) against its recorded measurements. No provider calls.

  python scripts/evaluation/check_trial.py evaluation/trials/verifier_v0.7_small/criteria.json            # verdict
  python scripts/evaluation/check_trial.py evaluation/trials/verifier_v0.7_small/criteria.json --commands # run plan

The criteria file is committed before the first provider call; this script only reads it.
Exit code 0 = every rule passed, 1 = at least one rule failed, 2 = measurements missing or from another contract.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ERROR_PREFIX = "verifier_output_"


def load(run):
    p = ROOT / run["out"] / "results.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def tokens(call):
    return (call or {}).get("usage", {}).get("completion_tokens") if call and not call.get("cache_hit") else None


def collect(crit):
    """Flatten every recorded run into rows: (kind, group_id or None, case_id, rejected, reasons) plus call token counts."""
    rows, toks, problems = [], [], []
    for run in crit["runs"]:
        res = load(run)
        if res is None:
            problems.append(f"missing measurement {run['out']}")
            continue
        if res["contract_version"] != crit["contract_version"]:
            problems.append(f"{run['out']}: contract {res['contract_version']} != {crit['contract_version']}")
        for r in res.get("records", []):
            reasons = r.get("verifier_reasons", r["reasons"])
            rows.append(dict(run=run["out"], group=None, case_id=r["case_id"], rejected=r["outcome"] == "fail",
                             reasons=list(r["reasons"]), verifier_reasons=list(reasons or [])))
            toks.append((run["out"], r["case_id"], tokens(r.get("call"))))
        for g in res.get("groups", []) + res.get("pipeline_groups", []):
            toks.append((run["out"], g["group_id"], tokens(g.get("call"))))
            for r in g["records"]:
                reasons = r.get("verifier_reasons") or []
                rows.append(dict(run=run["out"], group=g["group_id"], case_id=r["case_id"],
                                 rejected=r["verifier_outcome"] in ("fail", "error"), reasons=list(reasons),
                                 verifier_reasons=list(reasons)))
    return rows, toks, problems


def judge(crit):
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
    fresh = [t for t in toks if t[2] is not None]
    over = [t for t in fresh if t[2] > limit]
    out["R5_length"] = dict(ok=bool(fresh) and not over and len(fresh) == len(toks), detail=over,
                            max=max((t[2] for t in fresh), default=None), calls=len(toks), fresh=len(fresh))
    report = [(r["group"] or "single", r["case_id"], "fail" if r["rejected"] else "pass", r["verifier_reasons"])
              for r in rows if r["case_id"] not in R["R1_focal_single"]["cases"] + R["R3_clean"]["single"] + ["P08"]]
    return out, report, problems


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("criteria")
    p.add_argument("--commands", action="store_true", help="print the measurement commands of the run plan")
    a = p.parse_args()
    crit = json.loads((ROOT / a.criteria).read_text(encoding="utf-8"))
    if a.commands:
        for run in crit["runs"]:
            sel = f"--groups {run['groups']} --groups-only" if "groups" in run else f"--only {run['only']} --no-groups"
            print(f"python scripts/evaluation/measure_verifier.py --cases {run['cases']} {sel} --out {run['out']}")
        return 0
    out, report, problems = judge(crit)
    if problems:
        print("\n".join(problems))
        return 2
    for name, r in out.items():
        print(f"{name}: {'PASS' if r['ok'] else 'FAIL'}")
        extra = {k: v for k, v in r.items() if k not in ("ok", "detail")}
        if extra:
            print("   ", extra)
        for d in r["detail"]:
            print("   ", d)
    print("report-only:")
    for row in report:
        print("   ", row)
    ok = all(r["ok"] for r in out.values())
    print("DECISION:", crit["decision"]["all_rules_pass" if ok else "any_rule_fails"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
