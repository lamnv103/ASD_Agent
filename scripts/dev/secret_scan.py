"""Fail if any git-tracked (or staged) file contains a credential.

    .venv-embedding\\Scripts\\python.exe -B scripts/dev/secret_scan.py

Checks: NVIDIA keys (nvapi-...), PostgreSQL URLs with a real password, generic
`*_API_KEY=<value>` assignments, private key blocks. Placeholders such as USER:PASSWORD,
CHANGE_ME or <redacted> are allowed. Prints file:line only, never the secret itself.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER = re.compile(r"(CHANGE_ME|PASSWORD|<[^>]*>|\*{3}|\$\{|example|dummy)", re.I)
RULES = [
    ("nvidia_api_key", re.compile(r"nvapi-[A-Za-z0-9_-]{20,}")),
    ("postgres_password", re.compile(r"postgres(?:ql)?://[^:/\s]+:([^@\s]+)@")),
    ("api_key_assignment", re.compile(r"\b[A-Z][A-Z0-9_]*API_KEY\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{16,})")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
SKIP_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".docx", ".dump", ".xml"}


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, check=True).stdout
    return [ROOT / p for p in out.decode("utf-8").split("\0") if p]


def main() -> int:
    findings = []
    for path in tracked_files():
        if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file() or path.stat().st_size > 30_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, rule in RULES:
                m = rule.search(line)
                if not m:
                    continue
                value = m.group(1) if m.groups() else m.group(0)
                if name != "nvidia_api_key" and PLACEHOLDER.search(value):
                    continue
                findings.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}: {name}")
    for f in findings:
        print("SECRET?", f)
    print("secret scan:", "FAIL" if findings else "PASS", f"({len(findings)} finding(s))")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
