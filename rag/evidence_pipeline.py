"""Question -> unchanged retrieval -> exact evidence -> assessment -> bounded context."""
from __future__ import annotations
import copy,json
from datetime import datetime,timezone
from .retriever import ROOT,PostgresRetriever,atomic_json,sha,canonical
from .evidence import EvidenceReader,assess,medical_policy,require
from .context import ContextManager
from .tokenization import load_counter

class EvidencePipeline:
    def __init__(self,retriever=None,*,config=None,counter=None,semantic_reader=None):
        self.retriever=retriever or PostgresRetriever()
        self.config=copy.deepcopy(config) if config is not None else json.loads((ROOT/'deployments/evidence_context.json').read_text(encoding='utf-8'))
        self.counter=counter if counter is not None else load_counter(self.config)
        self.semantic_reader=semantic_reader
        self.reader=EvidenceReader();self.manager=ContextManager(self.config,self.counter)

    def prepare(self,question,*,top_k=5,review=None,trace_path=None):
        retrieved=self.retriever.retrieve(question,top_k,include_content=True)
        trace=self.prepare_retrieved(question,retrieved,review=review)
        if trace_path:atomic_json(trace_path,trace)
        return trace

    def prepare_retrieved(self,question,retrieved,*,review=None):
        require(retrieved.get('query')==question and retrieved.get('actual_query')==question,'question_mismatch','Question differs from the actual retrieval query.')
        fixture_mode=self.config.get('mode')=='test_fixture'
        if not fixture_mode:
            require(isinstance(self.retriever,PostgresRetriever),'source_provenance','Research mode requires the approved PostgreSQL retriever.')
            pins=self.retriever.config
            require(retrieved.get('collection_id')==pins['collection_id'] and retrieved.get('space_id')==pins['space_id'],
                'source_provenance','Supplied retrieval belongs to a different collection or embedding space.')
            for doc in retrieved.get('results',[]):
                pin=pins['sources'].get(doc.get('source_id'))
                require(pin is not None and pin['content_sha256']==doc.get('content_sha256'),'source_provenance','Supplied source is outside the approved release.')
                expected=self.retriever.read_source(doc['source_id'])['document']
                require(all(doc.get(k)==expected.get(k) for k in ['title','source','dates','scope']),
                    'source_provenance','Supplied source attribution/scope differs from PostgreSQL.')

        semantic_trace=None
        if review is None and self.semantic_reader is not None:
            review,semantic_trace=self.semantic_reader.review(question,retrieved)
        reading=self.reader.read(question,copy.deepcopy(retrieved),review)
        before=assess(question,reading,review);policy=medical_policy(review,before)
        policy_history=[]
        for attempt in range(4):
            context=self.manager.select(question,reading,before,policy)
            after=assess(question,reading,review,set(context['selected_evidence_ids']))
            selected_policy=medical_policy(review,after)
            policy_history.append(dict(attempt=attempt+1,policy_action=policy['action'],context_status=context['status'],selected_status=after['status']))
            if selected_policy==policy:break
            policy=selected_policy
        else:
            context.update(status='blocked_policy_budget_instability',messages=None,selected_blocks=[],selected_evidence_ids=[])
            after=assess(question,reading,review,set());selected_policy=medical_policy(review,after)
        context['policy_selection_history']=policy_history
        # Explicit reference and model reviews remain provisional; patient-answer generation stays disabled.
        return dict(schema_version=1,recorded_at=datetime.now(timezone.utc).isoformat(),question=question,question_sha256=sha(question),
            retrieval=dict(collection_id=retrieved.get('collection_id'),space_id=retrieved.get('space_id'),actual_query=retrieved.get('actual_query'),
                strategy=retrieved.get('strategy'),query_embedding=retrieved.get('query_embedding'),
                sources=[{k:v for k,v in d.items() if k!='content'} for d in retrieved['results']]),
            semantic_reader=semantic_trace,evidence_reading=reading,assessment_before_selection=before,medical_policy=policy,context_selection=context,
            assessment_after_selection=after,medical_policy_after_selection=selected_policy,
            review_input_sha256=sha(canonical(review)) if review else None,configuration_sha256=sha(canonical(self.config)),
            input_provenance='synthetic_fixture_explicitly_enabled' if fixture_mode else 'postgresql_release_and_attribution_revalidated',
            evaluation_reference_mode=bool(review and review['reviewer']['kind']=='ai_reference_review'),
            generation_enabled=False,clinical_reviewed=False,
            limitations=['Exact-source validation does not establish semantic or clinical correctness.',
                'Explicit review annotations are trusted inputs; reviewer identity/credentials are not authenticated.',
                'Model semantic review is provisional; no patient-answer generator or complete prompt-injection defense is implemented.',
                'Hosted payload token parity is reported per reader request; observations do not establish universal endpoint parity.'])
