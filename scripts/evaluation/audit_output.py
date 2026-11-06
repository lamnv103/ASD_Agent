"""Where verification scripts write their evidence.

Historical report folders are inputs to an audit, never its output. Each verification run
gets a new folder under reports/verification_runs/, and frozen evaluation inputs are only
compared byte-for-byte with what the verifier would regenerate; they are never rewritten.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def assert_frozen_json(path: Path, value) -> None:
    """Fail if a frozen input differs from the regenerated value; write nothing."""
    path = Path(path)
    if not path.is_file():
        raise AssertionError(f"Frozen input is missing: {path.relative_to(ROOT).as_posix()}")
    if path.read_bytes() != serialize(value):
        raise AssertionError(
            f"Frozen input differs from regenerated value: {path.relative_to(ROOT).as_posix()}"
        )
