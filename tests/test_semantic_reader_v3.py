import copy,json,unittest
from unittest.mock import patch
from rag.semantic_reader_v3 import AtomicNeedsReader,own_sections,selection_score
from rag.semantic_reader import passage_units
from rag.evidence import EvidenceError,EvidenceReader,assess
from rag.context import blocks_for
from test_semantic_reader import ReaderCounter,settings
from test_evidence_context import document,retrieved,QUESTION

def cfg():
    c=settings();c.update(output_protocol='atomic_needs_v3',max_needs=8,max_evidence_items=10);return c
def plan(task='verify'):
    return dict(intent='general_information',needs=[dict(need_id='n1',request='Check a specific statement',task=task,anchor=QUESTION,
        proposition='The fictional intervention helps everyone.' if task=='verify' else None,search_terms=['intervention','population'])],required_personal_information=[])
def record(d):return dict(content=json.dumps(d),cache_hit=True,prompt_token_delta=0)
def check(**kw):
    pid=next(p['passage_id'] for p in passage_units(document()['content'],1,0,len(document()['content'])) if 'Only in population A' in p['text'])
    c=dict(item_id='i1',need_id='n1',level='direct',finding='refutes',coverage='complete',support_passage_ids=[pid],reason='The source restricts applicability.')
    c.update(kw);return c
def verified(checks,**kw):
    d=dict(plan_faithful=True,question_coverage_complete=True,missing_needs=[],checks=checks,conflicts=[]);d.update(kw);return record(d)

class AtomicNeedsTests(unittest.TestCase):
    def setUp(self):
        self.reader=AtomicNeedsReader(cfg(),counter=ReaderCounter(),client=object())
        d=document();self.excerpts=[dict(source_id=d['source_id'],content_sha256=d['content_sha256'],start=0,end=len(d['content']),passages=passage_units(d['content'],1,0,len(d['content'])))]
        p=next(p for p in self.excerpts[0]['passages'] if 'Only in population A' in p['text'])
        self.item=dict(item_id='i1',passage_id=p['passage_id'],need_ids=['n1'],scope_passages=[])
    def selection(self,items=None,p=None):
        return self.reader.parse_selection(record(dict(items=items if items is not None else [self.item])),self.excerpts,p or plan())
    def review(self,checks=None,p=None,**kw):
        selected,mapping=self.selection(p=p)
        return self.reader.make_review(QUESTION,p or plan(),selected,mapping,verified(checks if checks is not None else [check()],**kw))[0]
    def test_negative_answer_directly_refutes_fixed_proposition(self):
        rv=self.review();a=assess(QUESTION,EvidenceReader().read(QUESTION,retrieved(),rv),rv)
        self.assertEqual(a['status'],'sufficient');self.assertTrue(a['claims'][0]['direct_refutation'])
        self.assertEqual(rv['items'][0]['need_judgment']['need']['proposition'],plan()['needs'][0]['proposition'])
    def test_explanation_has_no_positive_or_negative_truth(self):
        with self.assertRaises(EvidenceError):self.review(p=plan(task='explain'))
        rv=self.review([check(finding='explains')],p=plan(task='explain'));self.assertEqual(rv['items'][0]['stance'],'supports')
    def test_partial_detail_stays_partial(self):
        rv=self.review([check(coverage='partial')])
        self.assertEqual(assess(QUESTION,EvidenceReader().read(QUESTION,retrieved(),rv),rv)['status'],'partially_sufficient')
    def test_omitted_user_need_remains_required(self):
        rv=self.review(question_coverage_complete=False,missing_needs=[dict(anchor=QUESTION,request='Another requested outcome')])
        a=assess(QUESTION,EvidenceReader().read(QUESTION,retrieved(),rv),rv)
        self.assertEqual(a['status'],'partially_sufficient');self.assertIn('server_missing_1',a['missing_claims'])
    def test_unfaithful_plan_is_rejected(self):
        with self.assertRaises(EvidenceError):self.review(plan_faithful=False)
    def test_selector_cannot_assign_truth_or_generate_quotes(self):
        for field,value in [('stance','supports'),('quote','Invented source text')]:
            i=copy.deepcopy(self.item);i[field]=value
            with self.assertRaises(EvidenceError):self.selection([i])
    def test_unknown_and_duplicate_passages_rejected(self):
        i=copy.deepcopy(self.item);i['passage_id']='fake'
        with self.assertRaises(EvidenceError):self.selection([i])
        with self.assertRaises(EvidenceError):self.selection([self.item,self.item])
    def test_scope_cannot_use_metadata_or_unknown_passage(self):
        i=copy.deepcopy(self.item);i['scope_passages']=[dict(field='age',passage_id='metadata')]
        with self.assertRaises(EvidenceError):self.selection([i])
    def test_missing_and_duplicate_verifier_links_fail_closed(self):
        for cs in [[],[check(),check()]]:
            with self.assertRaises(EvidenceError):self.review(cs)
    def test_inconsistent_zero_support_flags_only_downgrade(self):
        for c in [check(coverage='none'),check(finding='context_only'),check(level='topical')]:
            rv=self.review([c]);self.assertEqual(rv['items'][0]['relation'],'topical');self.assertEqual(rv['items'][0]['stance'],'context_only')
            self.assertEqual(assess(QUESTION,EvidenceReader().read(QUESTION,retrieved(),rv),rv)['status'],'insufficient')
    def test_rewritten_proposition_field_is_rejected(self):
        with self.assertRaises(EvidenceError):self.review([dict(check(),proposition='Changed proposition')])
    def test_plan_requires_exact_anchor_and_declarative_proposition(self):
        for field,value in [('anchor','invented user words'),('proposition','Whether this works?'),('task',[])]:
            p=plan();p['needs'][0][field]=value
            with self.assertRaises(EvidenceError):self.reader.parse_plan(QUESTION,record(p))
    def test_multiword_planner_concepts_match_constituent_source_words(self):
        text='# Medication safety\n\nDo not stop a prescribed medicine without speaking to your provider.'
        units=own_sections(text);n=plan()['needs'][0];n['search_terms']=['discontinue prescribed medication after symptom improvement','stop medication safety']
        self.assertGreater(selection_score(units[0],text,[n]),0)
    def test_real_pack_selects_complete_units_when_exact_phrase_is_absent(self):
        text='# Medication safety\n\nDo not stop a prescribed medicine without speaking to your provider.\n\n# Other section\n\n'+'Unrelated material. '*300
        d=document(text=text);c=cfg();c['per_source_input_tokens']=2200
        reader=AtomicNeedsReader(c,counter=ReaderCounter(),client=object());p=plan()
        p['needs'][0]['search_terms']=['discontinue prescribed medication after symptom improvement','stop medication safety']
        xs,coverage=reader.pack_sources(QUESTION,retrieved([d]),p)
        self.assertTrue(any('Do not stop' in p['text'] for x in xs for p in x['passages']))
        self.assertFalse(coverage[0]['full_document_read'])
        for x in xs:
            for part in x['passages']:self.assertEqual(text[part['start']:part['end']],part['text'])
    def test_parent_intro_and_child_sections_both_available(self):
        text='# Parent\n\nThe limitation applies to every subgroup.\n\n## Child\n\nSubgroup finding.\n\n## Second\n\nAnother finding.'
        units=own_sections(text);cut=text.index('## Child')
        self.assertTrue(any('limitation' in text[u['start']:u['end']] for u in units))
        self.assertTrue(any(text[u['start']:u['end']].startswith('## Child') for u in units))
        self.assertFalse(any(u['start']<cut<u['end'] for u in units))
    def test_same_source_span_keeps_separate_need_polarity_without_double_source(self):
        p=plan();n=copy.deepcopy(p['needs'][0]);n['need_id']='n2';n['proposition']='The fictional intervention never helps anyone.';p['needs'].append(n)
        i=copy.deepcopy(self.item);i['need_ids']=['n1','n2']
        selected,mapping=self.selection([i],p)
        rv,_=self.reader.make_review(QUESTION,p,selected,mapping,verified([check(),check(need_id='n2',finding='affirms')]))
        reading=EvidenceReader().read(QUESTION,retrieved(),rv);es=[e for e in reading['evidence'] if e['semantic_reviewed']]
        self.assertEqual(len(es),2);self.assertEqual(len({e['evidence_id'] for e in es}),2)
        self.assertEqual(len({e['source_id'] for e in es}),1)
        self.assertEqual(assess(QUESTION,reading,rv)['status'],'sufficient')
        bs=blocks_for(es);self.assertEqual(len(bs),1);self.assertTrue(all('need_judgment' in e for e in bs[0]['evidence']))
    def test_conflict_uses_same_fixed_proposition_and_both_sources(self):
        docs=[document('A'),document('B')]
        ex=[dict(source_id=d['source_id'],content_sha256=d['content_sha256'],start=0,end=len(d['content']),passages=passage_units(d['content'],idx,0,len(d['content']))) for idx,d in enumerate(docs,1)]
        ps=[next(p for p in x['passages'] if 'Only in population A' in p['text']) for x in ex]
        selected=[dict(item_id='i'+str(idx),passage_id=p['passage_id'],need_ids=['n1'],scope_passages=[]) for idx,p in enumerate(ps,1)]
        items,mapping=self.reader.parse_selection(record(dict(items=selected)),ex,plan())
        groups=[dict(need_id='n1',item_ids=['i1','i2'],comparability_reviewed=True,rationale='Explicit synthetic comparable-outcome annotation for wiring tests only.')]
        rv,_=self.reader.make_review(QUESTION,plan(),items,mapping,verified([check(finding='affirms'),check(item_id='i2',support_passage_ids=[ps[1]['passage_id']])],conflicts=groups))
        reading=EvidenceReader().read(QUESTION,retrieved(docs),rv)
        self.assertEqual(assess(QUESTION,reading,rv)['status'],'conflicting')
        groups[0]['comparability_reviewed']=False
        with self.assertRaises(EvidenceError):self.reader.make_review(QUESTION,plan(),items,mapping,verified([check(finding='affirms'),check(item_id='i2',support_passage_ids=[ps[1]['passage_id']])],conflicts=groups))
    def test_cross_source_scope_is_rejected(self):
        second=document('B');x=dict(source_id=second['source_id'],content_sha256=second['content_sha256'],passages=passage_units(second['content'],2,0,len(second['content'])))
        i=copy.deepcopy(self.item);i['scope_passages']=[dict(field='population',passage_id=x['passages'][0]['passage_id'])]
        with self.assertRaises(EvidenceError):self.reader.parse_selection(record(dict(items=[i])),self.excerpts+[x],plan())
    def test_child_cannot_bypass_oversized_ancestor_condition(self):
        text='# Conditions\n\n'+('This condition limits applicability. '*100)+'\n\n## Child result\n\nOnly in population A the intervention helped; do not generalize.'
        d=document(text=text);c=cfg();c['per_source_input_tokens']=1800
        reader=AtomicNeedsReader(c,counter=ReaderCounter(),client=object())
        with self.assertRaises(EvidenceError) as err:reader.pack_sources(QUESTION,retrieved([d]),plan())
        self.assertEqual(err.exception.code,'reader_no_context')
    def test_coordinated_question_anchor_retains_all_intervening_user_words(self):
        q='Children under 3 and children age 3 or older go where?'
        p=plan(task='explain');p['needs'][0]['anchor']='Children under 3 go where'
        out=self.reader.parse_plan(q,record(p),allow_coordinated_anchor=True)
        n=out['needs'][0];self.assertEqual(n['anchor'],'Children under 3 and children age 3 or older go where')
        self.assertTrue(n['anchor_alignment']['intervening_user_words_preserved'])
        p['needs'][0]['anchor']='Children under 2 go where'
        with self.assertRaises(EvidenceError):self.reader.parse_plan(q,record(p),allow_coordinated_anchor=True)
    def test_plan_schema_correction_is_bounded_and_never_fixes_anchors_in_code(self):
        bad=plan();bad['needs'][0]['anchor']='Words not present in the question'
        responses=[record(bad),record(bad)];c=cfg();c['max_plan_schema_repairs']=1
        class Client:
            def complete(self,*args):return responses.pop(0)
        reader=AtomicNeedsReader(c,counter=ReaderCounter(),client=Client())
        with self.assertRaises(EvidenceError) as err:reader.review(QUESTION,retrieved())
        self.assertEqual(err.exception.code,'v3_plan_schema');self.assertEqual(err.exception.stage,'question_plan_repair');self.assertFalse(responses)
    def test_selection_schema_repair_is_bounded_and_never_accepts_bad_ids(self):
        p=plan();c=cfg();c['max_selection_repairs']=1
        bad=copy.deepcopy(self.item);bad['passage_id']='fabricated'
        responses=[record(p),record(dict(items=[bad])),record(dict(items=[bad]))]
        class Client:
            def complete(self,*args):return responses.pop(0)
        reader=AtomicNeedsReader(c,counter=ReaderCounter(),client=Client())
        with patch.object(reader,'pack_sources',return_value=(self.excerpts,[])):
            with self.assertRaises(EvidenceError) as err:reader.review(QUESTION,retrieved())
        self.assertEqual(err.exception.code,'v3_selection_schema');self.assertEqual(err.exception.stage,'source_selection_repair');self.assertFalse(responses)
    def test_selection_repair_can_only_choose_existing_source_passages(self):
        p=plan();c=cfg();c['max_selection_repairs']=1
        bad=copy.deepcopy(self.item);bad['passage_id']='fabricated'
        responses=[record(p),record(dict(items=[bad])),record(dict(items=[self.item])),verified([check()])]
        class Client:
            def complete(self,*args):return responses.pop(0)
        reader=AtomicNeedsReader(c,counter=ReaderCounter(),client=Client())
        with patch.object(reader,'pack_sources',return_value=(self.excerpts,[])):rv,tr=reader.review(QUESTION,retrieved())
        self.assertEqual(rv['items'][0]['quote'],self.passage_text())
        self.assertEqual([x['stage'] for x in tr['calls']],['question_plan','source_selection','source_selection_repair','source_verification'])
        self.assertFalse(responses)
    def passage_text(self):
        return next(p['text'] for p in self.excerpts[0]['passages'] if p['passage_id']==self.item['passage_id'])
    def test_no_curator_metadata_reaches_source_reader(self):
        d=document();d['scope']={'gioi_han':['CURATOR_SENTINEL_NOT_ORIGINAL_PROOF']}
        xs,_=self.reader.pack_sources(QUESTION,retrieved([d]),plan())
        self.assertNotIn('CURATOR_SENTINEL',json.dumps(xs));self.assertNotIn('metadata',xs[0])
    def test_verifier_cannot_cite_another_packet_or_invent_proof(self):
        with self.assertRaises(EvidenceError):self.review([check(support_passage_ids=['another-packet'])])
        self.assertEqual(self.review([check(support_passage_ids=[])])['items'][0]['relation'],'topical')
    def test_known_but_unrequested_link_cannot_upgrade_missing_need(self):
        p=plan();n=copy.deepcopy(p['needs'][0]);n['need_id']='n2';p['needs'].append(n)
        rv=self.review([check(),check(need_id='n2')],p=p)
        self.assertEqual([i['claim_ids'] for i in rv['items']],[['n1']])
        self.assertEqual(assess(QUESTION,EvidenceReader().read(QUESTION,retrieved(),rv),rv)['status'],'partially_sufficient')
    def test_same_need_can_compare_two_sections_with_literal_source_context(self):
        d=document(text='# First\n\nThe first stage is a screening activity, not a diagnosis.\n\n# Second\n\nThe second stage evaluates multiple domains to establish a diagnosis.')
        parts=passage_units(d['content'],1,0,len(d['content']))
        ps=[p for p in parts if len(p['text'])>40]
        ex=[dict(source_id=d['source_id'],content_sha256=d['content_sha256'],start=0,end=len(d['content']),passages=parts)]
        items=[dict(item_id='i'+str(j),passage_id=p['passage_id'],need_ids=['n1'],scope_passages=[]) for j,p in enumerate(ps,1)]
        selected,mapping=self.reader.parse_selection(record(dict(items=items)),ex,plan())
        packets,_=self.reader.verification_packets(selected,mapping,retrieved([d]))
        self.assertTrue(all({p['passage_id'] for p in ps}<=set(packet['allowed_passage_ids']) for packet in packets))
        checks=[check(item_id=i['item_id'],support_passage_ids=[p['passage_id'] for p in ps]) for i in selected]
        rv,_=self.reader.make_review(QUESTION,plan(),selected,mapping,verified(checks),packets=packets)
        rd=EvidenceReader().read(QUESTION,retrieved([d]),rv)
        self.assertEqual(assess(QUESTION,rd,rv)['status'],'sufficient')
        for item in rv['items']:
            starts=[p['start'] for p in item.get('additional_source_passages',[])]
            self.assertEqual(starts,sorted(starts))
        bs=blocks_for([e for e in rd['evidence'] if e['semantic_reviewed']])
        for b in bs:
            rendered=b['text']+' '.join(a['text'] for a in b['ancestor_introductions'])+' '.join(a['text'] for a in b.get('additional_source_passages',[]))
            self.assertIn('first stage',rendered);self.assertIn('second stage',rendered)
    def test_unknown_extra_need_link_stays_rejected(self):
        with self.assertRaises(EvidenceError):self.review([check(),check(need_id='n2')])
    def test_support_passages_are_in_final_evidence_context(self):
        rv=self.review();es=[e for e in EvidenceReader().read(QUESTION,retrieved(),rv)['evidence'] if e['semantic_reviewed']]
        b=blocks_for(es)[0]['evidence'][0];proof=b['need_judgment']['supporting_passages'][0]
        self.assertEqual(document()['content'][proof['start']:proof['end']],proof['quote'])
    def test_personal_dose_stops_before_source_selection(self):
        p=plan();p['intent']='personalized_medication'
        class Client:
            def __init__(self):self.n=0
            def complete(self,*args):
                self.n+=1
                if self.n>1:raise AssertionError('No dose/source selection allowed')
                return record(p)
        client=Client();reader=AtomicNeedsReader(cfg(),counter=ReaderCounter(),client=client)
        rv,tr=reader.review(QUESTION,retrieved())
        self.assertEqual(rv['items'],[]);self.assertEqual(client.n,1);self.assertFalse(tr['answer_generation_performed'])
    def test_empty_selection_still_audits_question_coverage(self):
        responses=[record(plan()),record(dict(items=[])),verified([],question_coverage_complete=False,missing_needs=[dict(anchor=QUESTION,request='Missing detail')])]
        class Client:
            def complete(self,*args):return responses.pop(0)
        reader=AtomicNeedsReader(cfg(),counter=ReaderCounter(),client=Client())
        with patch.object(reader,'pack_sources',return_value=(self.excerpts,[])):rv,tr=reader.review(QUESTION,retrieved())
        self.assertFalse(responses);self.assertEqual(rv['items'],[]);self.assertTrue(tr['verification']['missing_needs'])

if __name__=='__main__':unittest.main()
