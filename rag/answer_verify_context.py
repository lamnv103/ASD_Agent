"""Change C (trial; used only when deployments/answer_layer.json has "verifier_context": {"enabled": true}).

The verifier ALSO sees the catalog passages a claim does not cite, ONLY to report a limitation, condition or
contradiction the claim leaves out.

What the CODE guarantees:
* the v0.5 parser (rag.answer_layer.parse_verification) runs unchanged; evidence_span must lie verbatim in a CITED quote;
* the extra field can only ADD a rejection reason; it can never remove a reason the v0.5 parser produced;
* a reported issue must name a passage the claim does NOT cite and quote one or more WHOLE consecutive sentences of it
  verbatim (sentence boundaries checked, so a fragment that cuts off a condition is refused); otherwise the claim fails
  with a separate mechanical reason (context_id_invalid / context_span_not_verbatim / context_span_not_whole_sentence),
  never counted as a content catch;
* the generator, repair prompt, gates, terms and repair budget are untouched (reasons reach repair as before).

What the code does NOT guarantee: the model sees the whole catalog, so it may still judge a claim "supported" because
of an UNCITED passage and then pick a real but insufficient sentence from a cited quote as evidence_span. The parser
cannot detect that semantic misuse; it is measured with the no-rescue cases (CR1, CR2), not prevented.
Not wired into rag.answer_layer's pipeline yet: measured through scripts/evaluation/measure_verifier.py first.
"""
import json
import re

from rag import answer_layer as al

VERSION = "verifier_context_v0.1"
ISSUE_KEY = "other_passage_issue"
CONTENT_REASON = "context_limit:"          # + passage id; a content reason
MECHANICAL_REASONS = ("context_id_invalid", "context_span_not_verbatim", "context_span_not_whole_sentence")

_ANCHOR_RULE = "- explanation: short English\n"
_ANCHOR_SHAPE = '"evidence_span":"...","explanation":"..."}]'
_RULE = """- other_passage_issue: context_passages are all catalog passages. For a claim, look ONLY at the context passages
  it does NOT cite, and ONLY for a limitation, condition or contradiction that the claim leaves out and that changes its
  meaning: a passage about the SAME population and the SAME conclusion that calls this conclusion premature, limited or
  uncertain, restricts it, or states the opposite. A passage about a different population, outcome or topic is NOT an
  issue; a passage that merely adds other information is NOT an issue. Never use context passages as support: support,
  flags and evidence_span still use only the cited quotes. Value: null, or
  {"id":"<id of an uncited passage>","span":"<copy VERBATIM the WHOLE sentence of that passage that states the limitation>"}
"""

assert al.VERIFY_SYSTEM.count(_ANCHOR_RULE) == 1 and al.VERIFY_SYSTEM.count(_ANCHOR_SHAPE) == 1
VERIFY_SYSTEM = (al.VERIFY_SYSTEM.replace(_ANCHOR_RULE, _ANCHOR_RULE + _RULE)
                 .replace(_ANCHOR_SHAPE, '"evidence_span":"...","explanation":"...","other_passage_issue":null}]'))


_END = r"[.!?][\"')\]]*"  # sentence-final punctuation, optionally followed by closing quotes/brackets (normalized text)


def whole_sentences(span, passage):
    """True if span (normalized) occurs in passage (normalized) starting at a sentence start and ending at a sentence end.
    A missing final full stop is tolerated when the passage has it right after the span."""
    i = passage.find(span)
    while i != -1:
        end = i + len(span)
        starts = i == 0 or re.search(_END + r" $", passage[:i]) is not None
        ends = (end == len(passage) and re.search(_END + "$", span) is not None)             or (re.search(_END + "$", span) is not None and passage[end] == " ")             or re.match(_END + r"( |$)", passage[end:]) is not None
        if starts and ends:
            return True
        i = passage.find(span, i + 1)
    return False


def build_verify_payload(question, needs, claims, gaps, catalog):
    """The v0.5 payload unchanged, plus every catalog passage under context_passages."""
    payload = al.build_verify_payload(question, needs, claims, gaps, catalog)
    payload["context_passages"] = [dict(id=e, quote=catalog[e]["quote"]) for e in catalog]
    return payload


def parse_verification(content, sent_claims, sent_gaps, needs, catalog, cfg):
    """Validate the extra field, strip it, run the unchanged v0.5 parser, then ADD context reasons."""
    def need(cond, msg):
        if not cond:
            raise al.AnswerError("verifier_output_invalid", msg)
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        raise al.AnswerError("verifier_output_invalid", "not JSON") from None
    need(isinstance(data, dict) and isinstance(data.get("claims"), list), "claims")
    issues = {}
    for v in data["claims"]:
        need(isinstance(v, dict) and ISSUE_KEY in v, "other_passage_issue missing")
        issue = v.pop(ISSUE_KEY)
        need(issue is None or (isinstance(issue, dict) and set(issue) == {"id", "span"}
                               and all(isinstance(issue[k], str) for k in ("id", "span"))), "other_passage_issue")
        issues[v.get("claim_id")] = issue
    res = al.parse_verification(json.dumps(data, ensure_ascii=False), sent_claims, sent_gaps, needs, catalog, cfg)
    claim_map = {c["claim_id"]: c for c in sent_claims}
    for cid, r in res["claims"].items():
        if r["verdict"] is None:
            continue
        issue = issues.get(cid)
        r["verdict"] = dict(r["verdict"], **{ISSUE_KEY: issue})
        if issue is None:
            continue
        pid = issue["id"]
        if pid not in catalog or pid in claim_map[cid]["evidence_ids"]:
            r["reasons"].append("context_id_invalid")
            continue
        span, passage = al._span_norm(issue["span"]), al._span_norm(catalog[pid]["quote"])
        if len(span) < cfg["limits"]["min_evidence_span_chars"] or span not in passage:
            r["reasons"].append("context_span_not_verbatim")
            continue
        if not whole_sentences(span, passage):
            r["reasons"].append("context_span_not_whole_sentence")
            continue
        r["reasons"].append(CONTENT_REASON + pid)
    return res
