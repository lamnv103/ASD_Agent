"""Fail if a credential is in a file that git would commit.

    .venv-embedding\\Scripts\\python.exe -B scripts/dev/secret_scan.py            # working tree + index
    .venv-embedding\\Scripts\\python.exe -B scripts/dev/secret_scan.py --staged   # index only (pre-commit hook)

Scanned: (1) working-tree copies of tracked and not-ignored untracked files, and (2) the STAGED
blob of every file in the index (what `git commit` would record), which can differ from disk.
Not scanned: earlier commits in history, ignored files, binary formats listed in SKIP_SUFFIXES.

Rules: NVIDIA keys (nvapi-...), PostgreSQL URLs with a password, `*_API_KEY=<value>` assignments,
private key blocks. Placeholders (USER:PASSWORD, CHANGE_ME, <...>, ***) are allowed, except for
nvapi- keys. Output is file:line and rule name only, never the secret.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER = re.compile(r"(CHANGE_ME|PASSWORD|<[^>]*>|\*{3}|\$?\{[^}]*\}|example|dummy)", re.I)
RULES = [
    ("nvidia_api_key", re.compile(r"nvapi-[A-Za-z0-9_-]{20,}")),
    ("postgres_password", re.compile(r"postgres(?:ql)?://[^:/\s]+:([^@\s]+)@")),
    ("api_key_assignment", re.compile(r"\b[A-Z][A-Z0-9_]*API_KEY\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{16,})")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
SKIP_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".docx", ".dump", ".xml"}
MAX_BYTES = 30_000_000


def git(*args) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def scan_text(label: str, text: str, findings: list[str]) -> None:
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rule in RULES:
            m = rule.search(line)
            if not m:
                continue
            value = m.group(1) if m.groups() else m.group(0)
            if name != "nvidia_api_key" and PLACEHOLDER.search(value):
                continue
            findings.append(f"{label}:{lineno}: {name}")


def skip(path: str) -> bool:
    return Path(path).suffix.lower() in SKIP_SUFFIXES


def main() -> int:
    staged_only = "--staged" in sys.argv[1:]
    findings: list[str] = []
    if not staged_only:
        for rel in git("ls-files", "-z", "--cached", "--others", "--exclude-standard").decode("utf-8").split("\0"):
            path = ROOT / rel
            if not rel or skip(rel) or not path.is_file() or path.stat().st_size > MAX_BYTES:
                continue
            try:
                scan_text(rel, path.read_text(encoding="utf-8"), findings)
            except UnicodeDecodeError:
                continue
    # Index blobs: `git ls-files -s` -> "<mode> <sha> <stage>\t<path>".
    entries = []
    for entry in git("ls-files", "-s", "-z").decode("utf-8").split("\0"):
        if entry:
            meta, rel = entry.split("\t", 1)
            if not skip(rel):
                entries.append((meta.split()[1], rel))
    if staged_only:
        # Only entries that differ from HEAD (new or modified in the index).
        changed = set(git("diff", "--cached", "--name-only", "-z").decode("utf-8").split("\0"))
        entries = [(b, r) for b, r in entries if r in changed]
    if entries:
        # One `git cat-file --batch` call for all blobs: "<sha> blob <size>\n<data>\n" per object.
        out = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT, capture_output=True, check=True,
                             input="".join(b + "\n" for b, _ in entries).encode()).stdout
        pos = 0
        for _, rel in entries:
            nl = out.index(b"\n", pos)
            size = int(out[pos:nl].split()[2])
            data = out[nl + 1:nl + 1 + size]
            pos = nl + 1 + size + 1
            if size > MAX_BYTES:
                continue
            try:
                scan_text(f"[index] {rel}", data.decode("utf-8"), findings)
            except UnicodeDecodeError:
                continue
    for f in findings:
        print("SECRET?", f)
    print("secret scan:", "FAIL" if findings else "PASS", f"({len(findings)} finding(s))")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
