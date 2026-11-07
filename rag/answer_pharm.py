"""Deterministic gate for UNREQUESTED pharmacological content in answer claims (pharm_gate_v0.1).

Narrow by design (docs/answer_layer/DAC_TA_KIEM_TRA.md, K1 section):
  * drug names     -> allowed only if the question names the SAME drug (any listed alias);
  * supplements    -> allowed only if the question mentions a supplement term;
  * drug classes, dosing, generic medication wording -> allowed only if the question mentions medication
    (a drug name, drug class, dosing or generic medication term);
  * a question mention preceded by a negation cue ("không hỏi về thuốc", "không dùng thuốc", "ngoài thuốc")
    does NOT open permission;
  * words such as "điều trị" / "can thiệp" are NOT pharmacological terms here (core project content).
Matching is NFC + casefold on word boundaries, with exclusions ("thuốc lá"...) blanked first. Accent-less
text is not matched ("thuoc" may be "thuộc"): an accent-less question opens no permission (conservative).
It is a supplementary layer, not a drug recognizer: unlisted drug names still rely on the model verifier.
The term list is versioned and marked chua_duyet; the loader refuses any other review status.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from .retriever import ROOT

DEFAULT_PATH = "deployments/answer_pharm_gate.json"
REASON_PREFIX = "pharm_unrequested:"
_MEDICATION_GROUPS = ("drug_class", "dosing", "medication_generic")


def _norm(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).casefold())


def _rx(term):
    return re.compile(r"(?<![\w])" + re.escape(_norm(term)) + r"(?![\w])")


class PharmGate:
    def __init__(self, data):
        if data.get("review_status") != "chua_duyet":
            raise ValueError("pharm gate term list must stay chua_duyet")
        self.version = data["gate_version"]
        self.exclusions = [_rx(t) for t in data["exclusions"]]
        # (group, canonical, compiled) ; drug names keep their canonical name
        self.terms = [("drug_name", canon, _rx(a)) for canon, aliases in data["drug_names"].items() for a in aliases]
        for group, spec in data["groups"].items():
            self.terms += [(group, _norm(t), _rx(t)) for t in spec["terms"]]
        self.allowed_if = {g: s["allowed_if"] for g, s in data["groups"].items()}
        self.negation = [re.compile(c) for c in data["question_negation_cues"]]

    def _hits(self, text):
        t = _norm(text)
        for ex in self.exclusions:
            t = ex.sub(lambda m: " " * len(m.group(0)), t)
        return t, [(g, canon, m.start()) for g, canon, rx in self.terms for m in rx.finditer(t)]

    def scope(self, question):
        """What the question asks about (non-negated mentions only)."""
        t, hits = self._hits(question)
        names, supplement, medication, negated = set(), False, False, []
        for g, canon, pos in hits:
            before = t[max(0, pos - 40):pos]
            if any(c.search(before) for c in self.negation):
                negated.append(canon)
                continue
            if g == "drug_name":
                names.add(canon)
                medication = True
            elif g == "supplement":
                supplement = True
            else:
                medication = True
        return dict(gate_version=self.version, drug_names=sorted(names), supplement=supplement,
                    medication=medication, negated_mentions=sorted(set(negated)))

    def check(self, text, scope):
        """Reasons ("pharm_unrequested:<group>:<term>") for pharmacological content the question did not ask for."""
        _, hits = self._hits(text)
        reasons = []
        for g, canon, _ in hits:
            if g == "drug_name":
                ok = canon in scope["drug_names"]
            elif g == "supplement":
                ok = scope["supplement"]
            else:
                ok = scope["medication"]
            r = f"{REASON_PREFIX}{g}:{canon}"
            if not ok and r not in reasons:
                reasons.append(r)
        return reasons


@lru_cache(maxsize=4)
def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_pharm_gate(path=None):
    p = Path(path) if path else ROOT / DEFAULT_PATH
    if not p.is_absolute():
        p = ROOT / p
    return PharmGate(_load(str(p)))


def is_gate_reason(reason):
    return reason.startswith(REASON_PREFIX)
