"""Fast check (seconds, no database) that no hash-pinned file was edited.

    .venv-embedding\\Scripts\\python.exe -B scripts/dev/check_pins.py

Accepted evaluation runs record SHA-256 hashes of the code/config/inputs they used; the
verifiers refuse to run if any of those files change. Editing a pinned file is allowed only
as a NEW release with new evaluation runs and a new verification baseline.
Pre-final development runs (not in evaluation_selection.json) used older code by design and
are not checked.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(path: str):
    data = json.loads((ROOT / path).read_text(encoding="utf-8"))
    return data.get("files", data) if isinstance(data, dict) else data


def manifests():
    yield "reports/reader_refinement_20261101_232742/protected_before.json"
    yield "reports/semantic_reader_20261101_111654/protected_before.json"
    yield "reports/evidence_context_20261031_175633/protected_code_before.json"
    for run in load("reports/reader_refinement_20261101_232742/evaluation_selection.json")["runs"]:
        yield f"{run}/implementation.json"


def main() -> int:
    pins: dict[str, tuple[str, str]] = {}
    for manifest in manifests():
        for name, digest in load(manifest).items():
            pins.setdefault(name, (digest, manifest))
    bad = []
    for name, (digest, manifest) in sorted(pins.items()):
        path = ROOT / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"
        if actual != digest:
            bad.append(f"{name}  (pinned by {manifest})")
    for b in bad:
        print("CHANGED", b)
    print(f"pins: {len(pins)} files checked,", "FAIL" if bad else "PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
