"""Check that the running Python environment matches requirements.lock.txt exactly.

    .venv-embedding\\Scripts\\python.exe -B scripts/dev/check_env.py

Names are normalized (PEP 503: case-insensitive, runs of - _ . are equal), so "huggingface_hub" and
"huggingface-hub" are the same package. Reports missing packages, version mismatches and extra
packages (pip/setuptools/wheel ignored), plus the Python version. Exit 1 on any missing/mismatch/extra.
"""
from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "requirements.lock.txt"
PYTHON = (3, 13)
IGNORED = {"pip", "setuptools", "wheel"}


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_lock(path=LOCK):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)", line)
        if not m:
            raise SystemExit(f"Unsupported lockfile line: {line!r}")
        out[norm(m.group(1))] = m.group(2)
    return out


def installed():
    out = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            out[norm(name)] = dist.version
    return out


def compare(lock, inst):
    missing = sorted(n for n in lock if n not in inst)
    mismatch = sorted((n, lock[n], inst[n]) for n in lock if n in inst and inst[n] != lock[n])
    extra = sorted(n for n in inst if n not in lock and n not in IGNORED)
    return missing, mismatch, extra


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    lock, inst = read_lock(), installed()
    missing, mismatch, extra = compare(lock, inst)
    py_ok = sys.version_info[:2] == PYTHON
    print(f"python {sys.version.split()[0]} at {sys.prefix} ({'OK' if py_ok else 'expected %d.%d' % PYTHON})")
    print(f"lockfile packages: {len(lock)}; installed (excluding pip/setuptools/wheel): "
          f"{len([n for n in inst if n not in IGNORED])}")
    for n in missing:
        print(f"  MISSING  {n}=={lock[n]}")
    for n, want, have in mismatch:
        print(f"  VERSION  {n}: lock {want}, installed {have}")
    for n in extra:
        print(f"  EXTRA    {n}=={inst[n]}")
    ok = py_ok and not (missing or mismatch or extra)
    print("environment: " + ("MATCHES requirements.lock.txt" if ok else
                             "DIFFERS from requirements.lock.txt (rebuild: rename the venv, then .\\tasks.ps1 setup)"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
