"""Repair-term guidance (trial; not wired into the answer pipeline).

The ONLY change under test: a repair-round problem whose reasons include known_term_error:<wrong> also carries
term_guidance = [{"wrong", "source_term", "use"}]. Everything else stays as in v0.5:
* reason codes are kept unchanged (traceability);
* the answer text is never edited here: the generator rewrites the claim and the rewritten claim goes through every
  check again (K1, pharm gate, known terms, verifier on the new wording, status);
* problems without a known_term_error reason are returned unchanged, so a repair request with no term error is
  byte-identical to v0.5.
"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "deployments/answer_term_guidance.json"
PREFIX = "known_term_error:"


def load_term_guidance(path=None, known_terms=None):
    data = json.loads(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))
    if data.get("review_status") != "chua_duyet" or not isinstance(data.get("terms"), dict):
        raise ValueError("term guidance must be a chua_duyet trial file with a terms map")
    for wrong, g in data["terms"].items():
        if set(g) != {"source_term", "use"} or not all(isinstance(g[k], str) and g[k].strip() for k in g):
            raise ValueError(f"term guidance entry for {wrong!r} needs source_term and use")
    if known_terms is not None and set(data["terms"]) != set(known_terms):
        raise ValueError("term guidance keys must equal the known_term_errors terms")
    return data


def annotate_problems(problems, guidance):
    """Return a deep copy of problems; entries with known_term_error reasons get term_guidance. Never edits claims."""
    out = copy.deepcopy(problems)
    for p in out:
        add = []
        for r in p.get("reasons") or []:
            if r.startswith(PREFIX) and r[len(PREFIX):] in guidance["terms"]:
                g = guidance["terms"][r[len(PREFIX):]]
                add.append(dict(wrong=r[len(PREFIX):], source_term=g["source_term"], use=g["use"]))
        if add:
            p["term_guidance"] = add
    return out
