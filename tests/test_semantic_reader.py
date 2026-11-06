import copy,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from rag.semantic_reader import NimEvidenceReader,NimClient,MODEL,ENDPOINT,messages,read_key,passage_units
from rag.evidence import EvidenceError
from rag.evidence_pipeline import EvidencePipeline
from rag.retriever import ROOT,sha
from test_evidence_context import document,retrieved,review_for,QUESTION,FixtureCounter,config

class ReaderCounter(FixtureCounter):
    profile=dict(kind='test_only',model_id=MODEL)
    config={'tokenizer':{'request_profile':{'template_kwargs':{'enable_thinking':False}}}}
def settings():
    return dict(model=MODEL,endpoint=ENDPOINT,answer_generation_enabled=False,chat_template_kwargs={'enable_thinking':False},
      context_window_tokens=100000,max_output_tokens=2048,safety_margin_tokens=512,temperature=0,timeout_seconds=1,per_source_input_tokens=10000,max_evidence_items=6)
def selected(doc=None):
    d=doc or document()
    return [dict(excerpt_id='x-test',source_id=d['source_id'],content_sha256=d['content_sha256'],start=0,end=len(d['content']),text=d['content'])]
def model_output():
    return dict(intent='general_information',claims=[dict(claim_id='c1',text='Test information need',required=True)],
      items=[dict(item_id='i1',excerpt_id='x-test',quote='Only in population A, the fictional intervention helped.',relation='direct',stance='supports',claim_ids=['c1'],scope_quotes=[])],
      conflicts=[],required_personal_information=[])

class SemanticReaderTests(unittest.TestCase):
    def setUp(self):self.reader=NimEvidenceReader(settings(),counter=ReaderCounter(),client=object())
    def validate(self,out,excerpts=None,docs=None):
        return self.reader.validate_output(QUESTION,{'content':json.dumps(out)},excerpts or selected(),retrieved(docs))
    def test_exact_quote_becomes_source_offsets(self):
        rv=self.validate(model_output());self.assertEqual(rv['reviewer']['kind'],'model_semantic_review')
        item=rv['items'][0];self.assertEqual(document()['content'][item['start']:item['end']],item['quote'])
    def test_fabricated_or_rewritten_quote_rejected(self):
        for quote in ['Completely fabricated proof of a treatment working.','Only in population B, the fictional intervention helped.']:
            out=model_output();out['items'][0]['quote']=quote
            with self.assertRaises(EvidenceError):self.validate(out)
    def test_ambiguous_quote_rejected(self):
        d=document();d['content']+=d['content'];d['content_sha256']=sha(d['content'])
        with self.assertRaises(EvidenceError):self.validate(model_output(),selected(d),[d])
    def test_unknown_excerpt_or_source_rejected(self):
        out=model_output();out['items'][0]['excerpt_id']='invented'
        with self.assertRaises(EvidenceError):self.validate(out)
    def test_quote_outside_material_read_not_accepted(self):
        x=selected();x[0]['text']='This excerpt does not contain the requested quotation.'
        with self.assertRaises(EvidenceError):self.validate(model_output(),x)
    def test_scope_must_be_an_exact_same_source_quote(self):
        out=model_output();out['items'][0]['scope_quotes']=[dict(field='age',excerpt_id='x-test',quote='All ages worldwide')]
        with self.assertRaises(EvidenceError):self.validate(out)
    def test_no_patient_answer_field_allowed(self):
        out=model_output();out['answer']='Take a drug.'
        with self.assertRaises(EvidenceError):self.validate(out)
    def test_malformed_shapes_and_optional_flags_rejected(self):
        for field,val in [('items',[3]),('claims',[True]),('required_personal_information','age'),('conflicts','none')]:
            out=model_output();out[field]=val
            with self.subTest(field=field),self.assertRaises(EvidenceError):self.validate(out)
        out=model_output();out['claims'][0]['required']=False
        with self.assertRaises(EvidenceError):self.validate(out)
    def test_personal_decision_gets_unsatisfied_server_requirement(self):
        for intent in ['individual_diagnosis','personalized_medication','scope_legal','current_services']:
            out=model_output();out['intent']=intent;rv=self.validate(out)
            self.assertTrue(any(c['claim_id'].startswith('server_required') for c in rv['claims']))
            self.assertFalse(any('server_required_individual_or_local_decision' in i['claim_ids'] for i in rv['items']))
    def test_bad_json_not_repaired_or_inferred(self):
        with self.assertRaises(EvidenceError):self.reader.validate_output(QUESTION,{'content':'not JSON'},selected(),retrieved())
    def test_reading_pack_stays_in_budget_and_logs_coverage(self):
        excerpts,coverage=self.reader.pack_sources(QUESTION,retrieved())
        self.assertTrue(coverage[0]['full_document_read'])
        for x in excerpts:self.assertEqual(document()['content'][x['start']:x['end']],x['text'])
    def test_pipeline_uses_reader_without_reference_labels(self):
        rv=self.validate(model_output())
        class Fake:
            def review(self,q,r):return rv,dict(provider='mock_test_only',reading_coverage=[])
        pipeline=EvidencePipeline(retriever=object(),config=config(),counter=FixtureCounter(),semantic_reader=Fake())
        trace=pipeline.prepare_retrieved(QUESTION,retrieved())
        self.assertEqual(trace['assessment_before_selection']['assessment_state'],'model_semantic_review_not_independent_clinical_validation')
        self.assertFalse(trace['evaluation_reference_mode']);self.assertFalse(trace['generation_enabled'])
    def test_explicit_review_does_not_trigger_reader_call(self):
        class Forbidden:
            def review(self,*args):raise AssertionError('Must not call provider')
        pipeline=EvidencePipeline(retriever=object(),config=config(),counter=FixtureCounter(),semantic_reader=Forbidden())
        pipeline.prepare_retrieved(QUESTION,retrieved(),review=review_for())

class NimClientTests(unittest.TestCase):
    def test_endpoint_and_template_pinned(self):
        for field,value in [('endpoint','https://example.invalid'),('model','other'),('answer_generation_enabled',True),('chat_template_kwargs',{'enable_thinking':True})]:
            cfg=settings();cfg[field]=value
            with self.subTest(field=field),self.assertRaises(EvidenceError):NimClient(cfg,ReaderCounter())
    def test_invalid_provider_key_rejected_before_network(self):
        c=NimClient(settings(),ReaderCounter(),key_supplier=lambda:'cohere-test-key')
        with tempfile.TemporaryDirectory() as tmp:
            c.cache_dir=Path(tmp)
            with self.assertRaises(EvidenceError):c.complete(messages('q',[]))
    def test_budget_rejection_before_key_or_network(self):
        cfg=settings();cfg['context_window_tokens']=10
        client=NimClient(cfg,ReaderCounter(),key_supplier=lambda:(_ for _ in ()).throw(AssertionError()))
        with self.assertRaises(EvidenceError):client.complete(messages('q',[]))
    def test_http_errors_not_retried_or_exposed(self):
        for code,expected in [(401,'nim_auth'),(429,'nim_rate_limit'),(500,'nim_http')]:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as tmp:
                c=NimClient(settings(),ReaderCounter(),key_supplier=lambda:'nvapi-test-key',cache_dir=tmp)
                with patch('rag.semantic_reader.request.build_opener') as build:
                    build.return_value.open.side_effect=HTTPError(ENDPOINT,code,'bad',{},io.BytesIO(b'sensitive'))
                    with self.assertRaises(EvidenceError) as e:c.complete(messages('q',[]))
                    self.assertEqual(e.exception.code,expected);self.assertNotIn('sensitive',str(e.exception));self.assertEqual(build.return_value.open.call_count,1)
    def test_success_cache_usage_and_no_secret_saved(self):
        msgs=messages('q',[]);n=ReaderCounter().count_messages(msgs)
        body=dict(model=MODEL,id='test-request',usage={'prompt_tokens':n,'completion_tokens':5},choices=[dict(finish_reason='stop',message={'content':'{"ok":true}','reasoning_content':'never persist hidden reasoning'})])
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,*a):return json.dumps(body).encode()
        with tempfile.TemporaryDirectory() as tmp:
            c=NimClient(settings(),ReaderCounter(),key_supplier=lambda:'nvapi-test-key',cache_dir=tmp)
            with patch('rag.semantic_reader.request.build_opener') as build:
                build.return_value.open.return_value=Reply();first=c.complete(msgs)
            with patch.object(c,'key_supplier',side_effect=AssertionError('no credential on cache hit')):second=c.complete(msgs)
            self.assertEqual(first['prompt_token_delta'],0);self.assertTrue(second['cache_hit'])
            raw=next(Path(tmp).glob('*.json')).read_text();self.assertNotIn('nvapi-test-key',raw);self.assertNotIn('never persist',raw)
    def test_embedding_model_entry_not_used_as_chat_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'config.yaml';p.write_text('models:\n- provider: nvidia\n  model: nvidia/nemotron-3.5-embed-8b\n  apiKey: nvapi-test\n')
            with patch.dict('os.environ',{},clear=True),self.assertRaises(EvidenceError):read_key(p)


class PassageProtocolTests(unittest.TestCase):
    def setUp(self):
        cfg=settings();cfg['output_protocol']='passage_ids_v2'
        self.reader=NimEvidenceReader(cfg,counter=ReaderCounter(),client=object())
        d=document();self.excerpts=selected();self.excerpts[0].pop('text');self.excerpts[0]['passages']=passage_units(d['content'],1,0,len(d['content']))
        self.passage=next(p for p in self.excerpts[0]['passages'] if 'Only in population A' in p['text'])
    def output(self):
        o=model_output();i=o['items'][0];i.pop('excerpt_id');i.pop('quote');i.pop('scope_quotes');i['passage_id']=self.passage['passage_id'];i['scope_passages']=[];return o
    def check(self,o):
        return self.reader.validate_output(QUESTION,{'content':json.dumps(o)},self.excerpts,retrieved())
    def test_code_constructs_exact_quote_and_position(self):
        rv=self.check(self.output());i=rv['items'][0];self.assertEqual(i['quote'],self.passage['text']);self.assertEqual(document()['content'][i['start']:i['end']],i['quote'])
    def test_generated_quote_not_allowed_even_if_plausible(self):
        o=self.output();o['items'][0]['quote']='rewritten content'
        with self.assertRaises(EvidenceError):self.check(o)
    def test_metadata_cannot_be_cited_as_source(self):
        o=self.output();o['items'][0]['passage_id']='metadata-not-source'
        with self.assertRaises(EvidenceError):self.check(o)
    def test_duplicate_passage_cannot_create_two_independent_sources(self):
        o=self.output();second=copy.deepcopy(o['items'][0]);second['item_id']='i2';o['items'].append(second)
        with self.assertRaises(EvidenceError):self.check(o)
    def test_tampered_passage_text_rejected(self):
        self.passage['text']='tampered'
        with self.assertRaises(EvidenceError):self.check(self.output())
    def test_unknown_scope_passage_rejected(self):
        o=self.output();o['items'][0]['scope_passages']=[{'field':'age','passage_id':'fake'}]
        with self.assertRaises(EvidenceError):self.check(o)
    def test_unicode_offset_tables_and_final_tail_preserved(self):
        text='Prefix tiếng Việt ≤2.\n\n<table><tr><td>A\n\nB ≥5</td></tr></table>\n\nFinal limitation, not a clinical claim.'
        units=passage_units(text,2,0,len(text));self.assertEqual(len(units),3)
        self.assertIn('A\n\nB',units[1]['text']);self.assertTrue(units[-1]['text'].endswith('claim.'))
        for p in units:self.assertEqual(text[p['start']:p['end']],p['text'])
    def test_nested_invalid_json_types_fail_as_reader_errors(self):
        for field,value in [('intent',[]),('claims',[{'claim_id':[],'text':'x','required':True}]),('conflicts',[None])]:
            out=self.output();out[field]=value
            with self.subTest(field=field),self.assertRaises(EvidenceError):self.check(out)
        for field in ['item_id','passage_id','relation','stance','claim_ids']:
            out=self.output();out['items'][0][field]=[[]]
            with self.subTest(item_field=field),self.assertRaises(EvidenceError):self.check(out)
        out=self.output();out['items'][0]['scope_passages']=[{'field':[],'passage_id':[]}]
        with self.assertRaises(EvidenceError):self.check(out)
    def test_proof_without_a_claim_is_rejected(self):
        out=self.output();out['items'][0]['claim_ids']=[]
        with self.assertRaises(EvidenceError):self.check(out)
    def test_v2_pack_does_not_send_two_copies_of_source(self):
        ex,cov=self.reader.pack_sources(QUESTION,retrieved())
        self.assertTrue(ex);self.assertNotIn('text',ex[0]);self.assertIn('passages',ex[0])



class EntailmentGuardTests(unittest.TestCase):
    def review(self):
        rv=review_for();rv['reviewer']['kind']='model_semantic_review';return rv
    def reader(self,checks):
        class Client:
            def complete(self,m):return {'content':json.dumps({'checks':checks}),'cache_hit':False,'prompt_token_delta':0}
        return NimEvidenceReader(settings(),counter=ReaderCounter(),client=Client())
    def test_verifier_can_downgrade_not_upgrade(self):
        rv=self.review()
        reader=self.reader([{'item_id':'i0','claim_id':'c1','relation':'indirect','stance':'supports','reason':'qualifier absent'}])
        out,trace=reader.verify_links(QUESTION,rv)
        self.assertEqual(out['items'][0]['relation'],'indirect');self.assertTrue(trace['downgrades'])
        rv['items'][0]['relation']='indirect'
        reader=self.reader([{'item_id':'i0','claim_id':'c1','relation':'direct','stance':'supports'}])
        self.assertEqual(reader.verify_links(QUESTION,rv)[0]['items'][0]['relation'],'indirect')
    def test_invalid_verifier_nested_types_fail_as_evidence_errors(self):
        for field in ['item_id','claim_id','relation','stance']:
            check=dict(item_id='i0',claim_id='c1',relation='direct',stance='supports');check[field]=[]
            with self.subTest(field=field),self.assertRaises(EvidenceError):self.reader([check]).verify_links(QUESTION,self.review())
    def test_verifier_missing_link_fails_closed(self):
        with self.assertRaises(EvidenceError):self.reader([]).verify_links(QUESTION,self.review())
    def test_medication_legal_and_diagnosis_cannot_provide_final_evidence(self):
        for intent in ['personalized_medication','individual_diagnosis','scope_legal','current_services']:
            rv=self.review();rv['intent']=intent
            out,overrides=self.reader([]).apply_safety_guards(rv)
            self.assertTrue(overrides);self.assertEqual(out['items'][0]['relation'],'topical');self.assertEqual(out['items'][0]['stance'],'context_only')
    def test_general_education_is_preserved(self):
        rv=self.review();out,overrides=self.reader([]).apply_safety_guards(rv)
        self.assertEqual(out,rv);self.assertFalse(overrides)


    def test_context_only_links_do_not_call_verifier(self):
        rv=self.review();rv['items'][0].update(relation='topical',stance='context_only')
        class Forbidden:
            def complete(self,*args):raise AssertionError('No proof link to verify')
        reader=NimEvidenceReader(settings(),counter=ReaderCounter(),client=Forbidden())
        out,trace=reader.verify_links(QUESTION,rv)
        self.assertEqual(out,rv);self.assertIsNone(trace)
    def test_only_proof_links_required_but_not_context_only_links(self):
        rv=self.review();other=copy.deepcopy(rv['items'][0]);other.update(item_id='context',relation='topical',stance='context_only')
        rv['items'].append(other)
        checks=[dict(item_id='i0',claim_id='c1',relation='direct',stance='supports')]
        out,trace=self.reader(checks).verify_links(QUESTION,rv)
        self.assertEqual(out['items'][0]['relation'],'direct')
        self.assertEqual(out['items'][1],other)
    def test_guard_runs_before_verifier_and_keeps_raw_review_for_audit(self):
        rv=self.review();rv['intent']='personalized_medication'
        cfg=settings();cfg['verify_claim_links']=True
        class Client:
            def complete(self,*args):return {'content':'{}','cache_hit':True}
        reader=NimEvidenceReader(cfg,counter=ReaderCounter(),client=Client())
        with patch.object(reader,'pack_sources',return_value=(selected(),[])),patch.object(reader,'validate_output',return_value=rv),patch.object(reader,'verify_links',wraps=reader.verify_links) as verify:
            out,trace=reader.review(QUESTION,retrieved())
        self.assertEqual(verify.call_args.args[1]['items'][0]['relation'],'topical')
        self.assertIsNone(trace['verification'])
        self.assertEqual(trace['model_review_before_guards']['items'][0]['relation'],'direct')
        self.assertTrue(trace['safety_overrides'])
        self.assertFalse(trace['answer_generation_performed'])

if __name__=='__main__':unittest.main(verbosity=2)
