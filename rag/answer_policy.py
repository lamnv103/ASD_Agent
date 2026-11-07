"""Answer-layer configuration, fixed policy templates and the emergency placeholder check.

Everything here is an engineering draft (review_status "chua_duyet"): templates, the emergency
phrase list and the source-note tables have NOT been clinically reviewed and are not a basis for
opening a pilot. See docs/answer_layer/DAC_TA_DAU_RA.md.
"""
from __future__ import annotations

import copy
import json
import re
import unicodedata
from functools import lru_cache

from .retriever import ROOT

CONFIG_PATH = ROOT / "deployments/answer_layer.json"
POLICY_INTENTS = ("individual_diagnosis", "personalized_medication", "current_services", "scope_legal", "unclassified")


@lru_cache(maxsize=1)
def _load_default():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


UNREVIEWED = "chua_duyet"


def _review_statuses(node, path="$"):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "review_status":
                yield path, v
            else:
                yield from _review_statuses(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _review_statuses(v, f"{path}[{i}]")


def load_config(config=None):
    """Reject the config unless EVERY component is still marked unreviewed.

    Required markers: top level, disclaimer, each policy template, emergency, source_notes.
    Any other review_status anywhere must also be "chua_duyet". Changing one template to
    "da_duyet" is a review decision that needs its own release, not a config edit.
    """
    cfg = copy.deepcopy(config if config is not None else _load_default())
    problems = []
    if cfg.get("purpose") != "internal_prototype_only":
        problems.append("$.purpose")
    required = ["$", "$.disclaimer", "$.disclaimer_no_content", "$.emergency", "$.source_notes"] + [f"$.policy_templates.{k}" for k in cfg.get("policy_templates", {})]
    found = dict(_review_statuses(cfg))
    for path in required:
        if found.get(path) != UNREVIEWED:
            problems.append(path + ".review_status")
    problems += [p + ".review_status" for p, v in found.items() if v != UNREVIEWED]
    if set(cfg.get("policy_templates", {})) != set(POLICY_INTENTS):
        problems.append("$.policy_templates (expected exactly %s)" % ", ".join(POLICY_INTENTS))
    if problems:
        raise ValueError("answer_layer config must stay internal_prototype_only and chua_duyet everywhere: "
                         + ", ".join(sorted(set(problems))))
    return cfg


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).casefold()
    return re.sub(r"\s+", " ", text)


def detect_emergency(question: str, config=None) -> list[str]:
    """Return matched emergency phrases (empty list = none). Local only, no provider.

    Phrases match on word boundaries against the NFC/casefolded question, so "đánh giá" or
    "tự kỷ" never match. Unaccented phrases match only text typed without accents.
    """
    cfg = load_config(config)
    q = _norm(question)
    hits = []
    for phrase in cfg["emergency"]["phrases"]:
        p = _norm(phrase)
        if re.search(r"(?<![\w])" + re.escape(p) + r"(?![\w])", q):
            hits.append(phrase)
    return hits


def policy_template(intent: str, config=None) -> dict:
    cfg = load_config(config)
    tpl = cfg["policy_templates"].get(intent)
    if tpl is None:
        raise KeyError(intent)
    return dict(intent=intent, text=tpl["text"], review_status=tpl["review_status"])
