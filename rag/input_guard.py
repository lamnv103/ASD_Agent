"""Local input screening that runs BEFORE any provider call (Cohere, NVIDIA) or cache write.

Scope (deliberately narrow and deterministic):
  * reject empty or over-long questions;
  * remove control characters;
  * redact common direct identifiers: e-mail, Vietnamese phone numbers, 9/12-digit ID numbers,
    and FULL calendar dates (day + month + year, likely dates of birth) in these forms:
      12/03/2019, 12-03-2019, 12.03.2019   (day-month-year)
      2019-03-12, 2019/03/12, 2019.03.12   (ISO / year-month-day)
      ngày 12 tháng 3 năm 2019, 12 tháng 3, năm 2019   (Vietnamese words)

Kept on purpose: ages ("3 tuổi"), bare years ("năm 2019"), year ranges ("2015–2024"),
month + year without a day ("tháng 3/2019"), and other numbers.
Not covered: personal names, addresses, school names and free-text descriptions of a child.
This reduces direct identifiers; it is not anonymisation.
Those still reach providers; the data policy (MVP step 6) must decide how to handle them.
Redaction values are never logged or returned, only their type and count.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .evidence import EvidenceError

GUARD_VERSION = "input_guard_v1"
MAX_QUESTION_CHARS = 2000

# Order matters: phone numbers are redacted before the generic 9/12-digit ID rule.
_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("email", "[EMAIL]", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("phone", "[SỐ ĐIỆN THOẠI]", re.compile(r"(?<![\w])(?:\+?84|0)(?:[\s.-]?\d){8,10}(?![\w])")),
    ("national_id", "[SỐ ĐỊNH DANH]", re.compile(r"(?<!\d)(?:\d{12}|\d{9})(?!\d)")),
    ("full_date", "[NGÀY]", re.compile(
        r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])[/.-](?:0?[1-9]|1[0-2])[/.-](?:19|20)\d{2}(?!\d)")),
    ("full_date", "[NGÀY]", re.compile(
        r"(?<!\d)(?:19|20)\d{2}[/.-](?:0?[1-9]|1[0-2])[/.-](?:0?[1-9]|[12]\d|3[01])(?!\d)")),
    ("full_date", "[NGÀY]", re.compile(
        r"(?:\bngày\s+)?(?<!\d)(?:0?[1-9]|[12]\d|3[01])\s+tháng\s+(?:0?[1-9]|1[0-2])\s*,?\s+năm\s+(?:19|20)\d{2}(?!\d)",
        re.IGNORECASE)),
]
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class ScreenedQuestion:
    text: str                                   # the only text allowed to reach providers/caches
    redactions: dict[str, int] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.redactions)


def screen_question(question: object, *, max_chars: int = MAX_QUESTION_CHARS) -> ScreenedQuestion:
    if not isinstance(question, str):
        raise EvidenceError("input_rejected", "Question must be text.")
    text = _CONTROL.sub(" ", question).strip()
    if not text:
        raise EvidenceError("input_rejected", "Question is empty.")
    if len(text) > max_chars:
        raise EvidenceError("input_rejected", f"Question exceeds {max_chars} characters; nothing was sent.")
    redactions: dict[str, int] = {}
    for kind, placeholder, pattern in _PATTERNS:
        text, n = pattern.subn(placeholder, text)
        if n:
            redactions[kind] = redactions.get(kind, 0) + n
    return ScreenedQuestion(text=text, redactions=redactions)


def is_nfc(text: str) -> bool:
    """Diagnostics only: the guard does not re-normalise text, so cache keys stay stable."""
    return unicodedata.normalize("NFC", text) == text
