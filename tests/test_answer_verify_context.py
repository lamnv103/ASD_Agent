"""Change C (rag/answer_verify_context.py): uncited passages may only ADD a reason, never rescue a claim. No provider calls."""
import json
import unittest

from rag import answer_layer as al
from rag import answer_verify_context as ctx
from rag.answer_policy import load_config
from rag.retriever import sha

CFG = load_config()
E1 = "It is well researched that sleep problems exacerbate pre-existing behavioral problems in children with ASD."
E2 = "Although poor sleep exacerbates problematic daytime behavior, these conclusions are still premature and require further investigation."
E3 = "Parent report measures such as the CSHQ help gage the overall quality of sleep."
CAT = {"E1": dict(quote=E1), "E2": dict(quote=E2), "E3": dict(quote=E3)}
NEEDS = [dict(claim_id="n1", text="need")]
CLAIM = dict(claim_id="c1", role="chi_tiet", text="Rối loạn giấc ngủ làm hành vi nặng thêm.", evidence_ids=["E1"], need_ids=["n1"])


def out(issue="absent", support="supported", flags=(), span=E1):
    v = dict(claim_id="c1", support=support, flags=list(flags), evidence_span=span, explanation="")
    if issue != "absent":
        v["other_passage_issue"] = issue
    return json.dumps(dict(claims=[v], gaps=[], needs=[dict(need_id="n1", fully_addressed=True, by_claims=["c1"], missing="")],
                           question_parts_uncovered=[]))


def parse(content):
    return ctx.parse_verification(content, [CLAIM], [], NEEDS, CAT, CFG)["claims"]["c1"]["reasons"]


def v05(content):
    data = json.loads(content)
    for v in data["claims"]:
        v.pop("other_passage_issue", None)
    return al.parse_verification(json.dumps(data), [CLAIM], [], NEEDS, CAT, CFG)["claims"]["c1"]["reasons"]


class DisabledIsV05Tests(unittest.TestCase):
    def test_v05_prompt_untouched_and_c_prompt_only_adds(self):
        self.assertTrue(sha(al.VERIFY_SYSTEM).startswith("fd7c1477"))  # the accepted v0.5 verifier prompt
        self.assertTrue(ctx.VERIFY_SYSTEM.startswith("You check Vietnamese answer claims"))  # routes to the verifier model
        self.assertEqual(ctx.VERIFY_SYSTEM.replace(ctx._RULE, "").replace(',"other_passage_issue":null', ""), al.VERIFY_SYSTEM)

    def test_payload_is_v05_plus_context_passages(self):
        base = al.build_verify_payload("q", NEEDS, [CLAIM], [], CAT)
        got = ctx.build_verify_payload("q", NEEDS, [CLAIM], [], CAT)
        self.assertEqual(got.pop("context_passages"), [dict(id=e, quote=CAT[e]["quote"]) for e in CAT])
        self.assertEqual(got, base)
        self.assertEqual(got["claims"][0]["cited"], [dict(id="E1", quote=E1)])  # support still comes from cited only


class ContextIssueTests(unittest.TestCase):
    def test_null_issue_gives_exactly_the_v05_result(self):
        for kw in (dict(), dict(support="partially_supported", flags=["condition_dropped"]), dict(span=E2)):
            content = out(None, **kw)
            self.assertEqual(parse(content), v05(content), kw)

    def test_valid_issue_on_an_uncited_passage_adds_a_content_reason(self):
        span = "these conclusions are still premature and require further investigation."
        self.assertEqual(parse(out(dict(id="E2", span=span))), ["context_limit:E2"])

    def test_bad_issue_is_a_separate_mechanical_reason(self):
        self.assertEqual(parse(out(dict(id="E1", span=E1))), ["context_id_invalid"])        # cited passage named
        self.assertEqual(parse(out(dict(id="E9", span=E2))), ["context_id_invalid"])        # unknown passage
        self.assertEqual(parse(out(dict(id="E2", span="conclusions are premature"))), ["context_span_not_verbatim"])
        self.assertEqual(parse(out(dict(id="E2", span="premature."))), ["context_span_not_verbatim"])  # too short

    def test_an_uncited_passage_never_rescues_a_claim(self):
        # unsupported on the cited quote: still rejected, whatever the context says
        self.assertEqual(parse(out(None, support="not_supported", span="")),
                         ["support_not_supported", "span_not_in_cited_evidence"])
        # an evidence_span copied from an UNCITED passage still fails the v0.5 verbatim-in-cited check
        self.assertIn("span_not_in_cited_evidence", parse(out(None, span=E3)))
        # a context issue only adds: the v0.5 reasons stay
        span = "these conclusions are still premature and require further investigation."
        self.assertEqual(parse(out(dict(id="E2", span=span), support="partially_supported")),
                         ["support_partially_supported", "context_limit:E2"])

    def test_schema(self):
        for bad in (out(), out("E2"), out(dict(id="E2")), out(dict(id="E2", span=E2, note="x")), out(dict(id=2, span=E2)), "nope"):
            with self.assertRaises(al.AnswerError) as cm:
                parse(bad)
            self.assertEqual(cm.exception.code, "verifier_output_invalid")


if __name__ == "__main__":
    unittest.main()
