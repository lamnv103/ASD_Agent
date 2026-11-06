"""Where verification scripts write their evidence.

Historical report folders are inputs to an audit, never its output. Each verification run
gets a new folder under reports/verification_runs/, and frozen evaluation inputs are only
compared byte-for-byte with what the verifier would regenerate; they are never rewritten.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "reports" / "verification_runs"
VN_TIME = timezone(timedelta(hours=7))


def serialize(value) -> bytes:
    """Same bytes as rag.retriever.atomic_json writes."""
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def new_run_dir(name: str) -> Path:
    stamp = datetime.now(VN_TIME).strftime("%Y%m%d_%H%M%S_%f")
    out = RUNS / f"{name}_{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    return out


RELEASE_DB = ROOT / "deployments" / "database.release.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"


def local_connection_ok(name: str, pinned: str) -> tuple[bool, str]:
    """deployments/database.env holds a per-machine connection; check only its release settings.

    Exact historical hash -> ok. Otherwise every functional key must equal database.release.json,
    and the URL must be postgresql://.../asd_rag. Host, port, user and password are local.
    """
    release = json.loads(RELEASE_DB.read_text(encoding="utf-8"))
    path = ROOT / name
    if _sha(path) == pinned:
        return True, "exact historical pin"
    if pinned != release["historical_pin_sha256"]:
        return False, "pin does not belong to this release"
    if not path.is_file():
        return False, "missing local file"
    settings = dotenv_values(path, interpolate=False)
    url = urlsplit(settings.get("RAG_DATABASE_URL") or "")
    if url.scheme != release["url"]["scheme"] or url.path != "/" + release["url"]["database"]:
        return False, "RAG_DATABASE_URL must point to the release database"
    wrong = [k for k, v in release["functional"].items() if settings.get(k) != v]
    if wrong:
        return False, "functional settings differ: " + ", ".join(wrong)
    return True, "local connection differs; release settings match"


def protected_ok(name: str, pinned: str) -> tuple[bool, str]:
    if name == "deployments/database.env":
        return local_connection_ok(name, pinned)
    return (_sha(ROOT / name) == pinned), "exact"


def assert_protected(mapping: dict) -> None:
    """Replacement for `all(sha(file)==h ...)` that allows a per-machine database connection."""
    bad = [f"{n} ({why})" for n, h in mapping.items() for ok, why in [protected_ok(n, h)] if not ok]
    if bad:
        raise AssertionError("Protected files changed: " + "; ".join(bad))


def assert_frozen_json(path: Path, value) -> None:
    """Fail if a frozen input differs from the regenerated value; write nothing."""
    path = Path(path)
    if not path.is_file():
        raise AssertionError(f"Frozen input is missing: {path.relative_to(ROOT).as_posix()}")
    if path.read_bytes() != serialize(value):
        raise AssertionError(
            f"Frozen input differs from regenerated value: {path.relative_to(ROOT).as_posix()}"
        )
