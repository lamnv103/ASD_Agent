"""Run every test suite with the right import paths, count tests, fail on any deviation.

    .venv-embedding\\Scripts\\python.exe -B scripts/dev/run_all_tests.py

Fails (exit 1) if any suite fails, errors, skips, or if the total differs from
[tool.asd_agent].expected_tests in pyproject.toml. Each suite runs in its own process
from its own folder, exactly as it was written to run. Logs go to a new folder under
reports/verification_runs/ (git-ignored).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
SUITES = [
    # name, working dir, extra import path, unittest args
    ("tests", ROOT, ROOT / "tests", ["discover", "-s", "tests", "-p", "test_*.py", "-v"]),
    ("scripts/embedding", ROOT / "scripts/embedding", ROOT / "scripts/embedding",
     ["discover", "-s", ".", "-p", "test_*.py", "-v"]),
    ("scripts/source_library", ROOT / "scripts/source_library", ROOT / "scripts/source_library",
     ["discover", "-s", ".", "-p", "test_*.py", "-v"]),
]


def preflight() -> int:
    """0 = ready. Otherwise print the real cause (dependency / config / network / auth / integrity)."""
    sys.path.insert(0, str(ROOT / "scripts/dev"))
    import check_env
    import env_diagnose
    missing, mismatch, extra = check_env.compare(check_env.read_lock(), check_env.installed())
    if missing or mismatch:
        print("Environment differs from requirements.lock.txt; tests were not run.")
        for n in missing:
            print(f"  MISSING {n}")
        for n, want, have in mismatch:
            print(f"  VERSION {n}: lock {want}, installed {have}")
        print("Rebuild: rename the venv, then .\tasks.ps1 setup; check with scripts/dev/check_env.py")
        return 3
    result = env_diagnose.diagnose()
    if not result["ok"]:
        print("Database check failed; tests were not run: " + env_diagnose.describe(result))
        return 2
    if extra:
        print("Note: packages not in the lockfile are installed: " + ", ".join(extra))
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    expected = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["asd_agent"]["expected_tests"]
    status = preflight()
    if status:
        return status
    out = ROOT / "reports/verification_runs" / ("tests_" + datetime.now(timezone(timedelta(hours=7))).strftime("%Y%m%d_%H%M%S_%f"))
    out.mkdir(parents=True)
    total = failed = errors = skipped = 0
    print(f"{'suite':28s} {'ran':>5s} {'fail':>5s} {'err':>5s} {'skip':>5s}")
    for name, cwd, extra, args in SUITES:
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT), str(extra)]), PYTHONIOENCODING="utf-8")
        env.pop("CURL_CA_BUNDLE", None)  # system value points to a missing drive on this machine
        proc = subprocess.run([PY, "-B", "-m", "unittest", *args], cwd=cwd, env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        log = proc.stdout + proc.stderr
        (out / (name.replace("/", "_") + ".txt")).write_text(log, encoding="utf-8")
        ran = int(m.group(1)) if (m := re.search(r"^Ran (\d+) tests?", log, re.M)) else 0
        f = int(m.group(1)) if (m := re.search(r"failures=(\d+)", log)) else 0
        e = int(m.group(1)) if (m := re.search(r"errors=(\d+)", log)) else 0
        s = int(m.group(1)) if (m := re.search(r"skipped=(\d+)", log)) else 0
        if proc.returncode != 0 and not (f or e):
            e = max(e, 1)
        total, failed, errors, skipped = total + ran, failed + f, errors + e, skipped + s
        print(f"{name:28s} {ran:5d} {f:5d} {e:5d} {s:5d}")
    print(f"{'TOTAL':28s} {total:5d} {failed:5d} {errors:5d} {skipped:5d}   expected {expected}")
    print("logs:", out)
    ok = failed == errors == skipped == 0 and total == expected
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
