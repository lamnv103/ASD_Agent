"""Fast check (seconds, no database) that no hash-pinned file was edited.

    .venv-embedding\\Scripts\\python.exe -B scripts/dev/check_pins.py

Accepted evaluation runs record SHA-256 hashes of the code/config/inputs they used; the
verifiers refuse to run if any of those files change. Editing a pinned file is allowed only
as a NEW release with new evaluation runs and a new verification baseline.
Pre-final development runs (not in evaluation_selection.json) used older code by design and
are not checked.

Exception: deployments/database.env is a per-machine connection file. It passes if it matches
the historical pin exactly, or if its release settings match deployments/database.release.json
(collection, embedding space, model, dimensions, database name); host/port/user/password may differ.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))
from audit_output import protected_ok  # noqa: E402


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
        ok, why = protected_ok(name, digest)
        if not ok:
            bad.append(f"{name}  ({why}; pinned by {manifest})")
        elif why not in ("exact", "exact historical pin"):
            print(f"NOTE {name}: {why}")
    for b in bad:
        print("CHANGED", b)
    print(f"pins: {len(pins)} files checked,", "FAIL" if bad else "PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
