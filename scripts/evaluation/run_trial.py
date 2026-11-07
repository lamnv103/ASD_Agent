"""Run the measurement plan of a REGISTERED trial (criteria.json), safely. Makes provider calls.

  .venv-embedding\\Scripts\\python.exe -B scripts/evaluation/run_trial.py evaluation/trials/<trial>/criteria.json \\
      --nvidia-key-file secrets/nvidia.env [--dry-run]

Safety (added after a shell loop passed paths ending in CR and lost 10 paid responses):
* refuses criteria whose "status" is not "registered" (drafts are reviewed first);
* every run is checked BEFORE the first call: clean path under reports/, folder new or empty, contract of the
  checked-out code equals the run's contract;
* runs start as subprocesses with an argument list (no shell parsing), one after another;
* the first failing run stops the batch; trial_state.json records done / failed / pending runs and every run's
  call ledger (attempted, completed, unaccounted), so lost calls are counted in the cost report;
* --resume skips runs that already have results.json; a run with results.partial.json is never resumed silently.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evaluation"))
import measure_verifier as mv  # noqa: E402

SCRIPT = ROOT / "scripts/evaluation/measure_verifier.py"


def argv_for(run, key_file):
    a = [sys.executable, "-B", str(SCRIPT), "--cases", run["cases"]]
    a += ["--groups", run["groups"], "--groups-only"] if "groups" in run else ["--only", run["only"], "--no-groups"]
    return a + ["--out", run["out"]] + (["--nvidia-key-file", key_file] if key_file else [])


def state_path(crit):
    return ROOT / crit["state_file"]


def ledger(run):
    return mv.Ledger(ROOT / run["out"] / "calls.jsonl").summary()


def plan(crit, resume=False, contract=None, stage=None):
    """Return (todo, skipped) or raise RunAbort before any provider call."""
    if crit.get("status") != "registered":
        raise mv.RunAbort(f"criteria status is {crit.get('status')!r}, not 'registered': review and register it first")
    if contract is None:  # the contract of the checked-out configuration
        contract = json.loads((ROOT / "deployments/answer_layer.json").read_text(encoding="utf-8"))["contract_version"]
    todo, skipped = [], []
    for run in crit["runs"]:
        if stage and run.get("stage") != stage:
            continue
        out = mv.validate_out(run["out"])
        if run.get("contract", crit.get("contract_version")) != contract:
            raise mv.RunAbort(f"{run['out']}: plan expects {run.get('contract', crit.get('contract_version'))}, "
                              f"checked-out code is {contract}")
        if (out / "results.partial.json").exists():
            raise mv.RunAbort(f"{run['out']} was interrupted (results.partial.json); inspect it before going on")
        if (out / "results.json").exists():
            if not resume:
                raise mv.RunAbort(f"{run['out']} already measured; use --resume to skip finished runs")
            skipped.append(run)
            continue
        if out.exists() and any(out.iterdir()):
            raise mv.RunAbort(f"{run['out']} is not empty")
        for f in (run["cases"], run.get("groups")):
            if f and not (ROOT / f).exists():
                raise mv.RunAbort(f"missing {f}")
        todo.append(run)
    return todo, skipped


def write_state(crit, rows):
    st = dict(trial_id=crit["trial_id"], updated=datetime.now(timezone.utc).isoformat(), runs=rows,
              totals={k: sum((r.get("ledger") or {}).get(k, 0) for r in rows)
                      for k in ("attempted", "completed", "provider_calls", "unaccounted", "completion_tokens")})
    path = state_path(crit)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return st


def execute(crit, key_file, resume=False, runner=subprocess.run, contract=None, stage=None):
    todo, skipped = plan(crit, resume, contract, stage)
    rows = [dict(out=r["out"], status="skipped_done", ledger=ledger(r)) for r in skipped]
    pending = [dict(out=r["out"], status="pending") for r in todo]
    write_state(crit, rows + pending)
    for i, run in enumerate(todo):
        print("###", run["out"], flush=True)
        proc = runner(argv_for(run, key_file), cwd=str(ROOT))
        row = dict(out=run["out"], status="done" if proc.returncode == 0 else "failed", exit_code=proc.returncode,
                   ledger=ledger(run))
        rows.append(row)
        if proc.returncode != 0:
            write_state(crit, rows + [dict(out=r["out"], status="pending") for r in todo[i + 1:]])
            print(f"STOPPED at {run['out']} (exit {proc.returncode}); later runs not started. State: {crit['state_file']}")
            return 1
        write_state(crit, rows + [dict(out=r["out"], status="pending") for r in todo[i + 1:]])
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("criteria")
    p.add_argument("--nvidia-key-file")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--stage", help="only the runs of this stage (e.g. baseline, trial); each stage is checked against the "
                                   "contract of the checked-out code")
    p.add_argument("--dry-run", action="store_true", help="check the plan and print the argument lists; no calls")
    a = p.parse_args()
    crit = json.loads((ROOT / a.criteria).read_text(encoding="utf-8"))
    try:
        if a.dry_run:
            todo, skipped = plan(crit, a.resume, stage=a.stage)
            for r in todo:
                print(argv_for(r, a.nvidia_key_file))
            return 0
        return execute(crit, a.nvidia_key_file, a.resume, stage=a.stage)
    except mv.RunAbort as exc:
        print("REFUSED (no provider call):", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
