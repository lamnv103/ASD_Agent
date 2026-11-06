"""Exact source spans and explicit reviewed judgments. No keyword-to-truth inference."""
from __future__ import annotations
import copy,re
from .retriever import RetrievalError,canonical,sha

STATUSES={"sufficient","partially_sufficient","insufficient","conflicting"}
RELATIONS={"direct","indirect","topical"}
STANCES={"supports","opposes","context_only"}
INTENTS={"general_information","individual_diagnosis","personalized_medication","current_services","scope_legal","unclassified"}

class EvidenceError(RetrievalError): pass

def require(condition,code,message):
    if not condition: raise EvidenceError(code,message)

def sections(text):
    """Complete heading subtrees; tables and fenced blocks cannot create headings."""
    nodes=[dict(start=0,end=len(text),level=0,path=[])]
    ignored=[(m.start(),m.end()) for m in re.finditer(r'<table\b[\s\S]*?</table>|```[\s\S]*?```|~~~[\s\S]*?~~~',text,re.I)]
    headings=[m for m in re.finditer(r'(?m)^(#{1,6})[ \t]+(.+?)\r?$',text) if not any(a<=m.start()<b for a,b in ignored)]
    stack=[]
    if headings and headings[0].start()>0:nodes.append(dict(start=0,end=headings[0].start(),level=0,path=["Opening material"]))
    for i,m in enumerate(headings):
        level=len(m[1])
        while stack and stack[-1][0]>=level:stack.pop()
        path=[x[1] for x in stack]+[m[2]];stack.append((level,m[2]))
        end=next((n.start() for n in headings[i+1:] if len(n[1])<=level),len(text))
        nodes.append(dict(start=m.start(),end=end,level=level,path=path))
    return nodes

def containing_section(text,start,end):
    all_sections=sections(text)
    node=min((s for s in all_sections if s['start']<=start and end<=s['end']),key=lambda s:s['end']-s['start'])
    ancestors=[]
    for parent in all_sections:
        if parent['start']<=node['start'] and node['end']<=parent['end'] and parent['end']-parent['start']>node['end']-node['start']:
            children=[c for c in all_sections if c['level']>parent['level'] and parent['start']<c['start']<parent['end']]
            end=min((c['start'] for c in children),default=parent['end'])
            if end<=node['start'] and text[parent['start']:end].strip():
                piece=dict(start=parent['start'],end=end,text=text[parent['start']:end])
                if piece not in ancestors:ancestors.append(piece)
    return dict(node,text=text[node['start']:node['end']],ancestor_introductions=ancestors,
        boundary_method='complete_heading_subtree_plus_ancestor_introductions',semantic_boundary_independently_verified=False)

def instruction_flags(text):
    patterns=[r'ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions',r'<\|(?:im_start|system|start_header_id)\|>',r'(?m)^\s*(?:SYSTEM|DEVELOPER)\s*:',r'bỏ\s+qua\s+(?:mọi|tất cả)\s+(?:chỉ dẫn|hướng dẫn)']
    return [dict(kind="instruction_like_text",start=m.start(),end=m.end()) for pattern in patterns for m in re.finditer(pattern,text,re.I)]

def validate_documents(retrieval):
    require(retrieval.get('status')=='ok','retrieval_failed','Evidence reading requires a successful retrieval result.')
    documents={}
    for doc in retrieval.get('results',[]):
        sid=doc.get('source_id');content=doc.get('content')
        require(isinstance(sid,str) and sid and sid not in documents,'source_invalid','Missing or duplicate source ID.')
        require(isinstance(content,str) and content.strip() and sha(content)==doc.get('content_sha256'),'source_invalid','Full source content/hash mismatch: '+sid)
        documents[sid]=copy.deepcopy(doc)
    return documents

def source_limits(doc,annotation=None):
    scope=doc.get('scope') or {}
    # These curator metadata are explicitly distinguished from direct source quotations.
    return dict(population=None,age=scope.get('pham_vi_tuoi_goc'),conditions=None,country=None,
        time=doc.get('dates'),limitations=copy.deepcopy(scope.get('gioi_han',[])),
        annotation=annotation,metadata_origin='existing_source_metadata_not_independently_clinically_validated',
        unknown_fields=['population','conditions','country'])

def exact_evidence(doc,start,end,quote,*,relation='topical',stance='context_only',claim_ids=None,review_id=None,annotation=None):
    text=doc['content'];sid=doc['source_id']
    require(type(start) is int and type(end) is int and 0<=start<end<=len(text),'span_invalid','Invalid Unicode offsets: '+sid)
    require(isinstance(quote,str) and text[start:end]==quote,'span_invalid','Quotation does not match exact source position: '+sid)
    require(relation in RELATIONS and stance in STANCES,'review_invalid','Invalid evidence relation/stance.')
    context=containing_section(text,start,end)
    identity=dict(source_id=sid,content_sha256=doc['content_sha256'],start=start,end=end)
    return dict(evidence_id='ev-'+sha(canonical(identity))[:24],document_id='whole-document:'+sid,source_id=sid,
        collection_id=doc.get('collection_id'),content_sha256=doc['content_sha256'],quote=quote,start=start,end=end,
        offset_unit='unicode_codepoints_zero_based_half_open',section_path=context['path'],
        source_context=context,
        metadata=dict(title=doc.get('title'),source=copy.deepcopy(doc.get('source')),dates=copy.deepcopy(doc.get('dates')),
            source_version=(doc.get('scope') or {}).get('phien_ban')),
        applicability=source_limits(doc,annotation),relation=relation,stance=stance,claim_ids=claim_ids or [],
        review_id=review_id,semantic_reviewed=review_id is not None,source_is_untrusted_data=True,
        instruction_flags=instruction_flags(context['text']))

class EvidenceReader:
    def __init__(self,max_candidates_per_source=2,max_candidates_total=10):
        self.max_per_source=max_candidates_per_source;self.max_total=max_candidates_total

    def read(self,question,retrieval,review=None):
        require(isinstance(question,str) and question.strip(),'invalid_input','Question must not be empty.')
        documents=validate_documents(retrieval);evidence=[];missing=[];selection_log=[]
        for doc in documents.values():doc['collection_id']=retrieval.get('collection_id')
        if review is not None:
            validate_review(review,question)
            for item in review['items']:
                sid=item['source_id']
                if sid not in documents:
                    missing.append(dict(source_id=sid,reason='reviewed_source_not_retrieved'));continue
                doc=documents[sid]
                require(item['content_sha256']==doc['content_sha256'],'review_stale','Reviewed source hash differs: '+sid)
                ev=exact_evidence(doc,item['start'],item['end'],item['quote'],relation=item['relation'],stance=item['stance'],
                    claim_ids=item['claim_ids'],review_id=review['review_id'],annotation=item.get('scope_limits'))
                if review.get('review_protocol')=='atomic_needs_v3':
                    require(len(item['claim_ids'])==1 and isinstance(item.get('need_judgment'),dict),'review_invalid','Atomic evidence requires one need and its explicit judgment.')
                    # Distinguish per-need annotations while preserving source/span/context.
                    ev['evidence_id']='ev-'+sha(canonical([ev['evidence_id'],review['review_id'],item['claim_ids'][0]]))[:24]
                    ev['need_judgment']=copy.deepcopy(item['need_judgment'])
                    extras=item.get('additional_source_passages',[])
                    for part in extras:
                        require(part.get('source_id')==sid and part.get('content_sha256')==doc['content_sha256'] and type(part.get('start')) is int and type(part.get('end')) is int and 0<=part['start']<part['end']<=len(doc['content']) and doc['content'][part['start']:part['end']]==part.get('text'),'span_invalid','Additional proof context differs from original source.')
                    if extras:
                        ev['additional_source_passages']=copy.deepcopy(extras)
                        ev['instruction_flags'] += [flag for part in extras for flag in instruction_flags(part['text'])]

                ev['review_item_id']=item['item_id'];evidence.append(ev)
        # Candidate discovery is lexical only. It never assigns support or sufficiency.
        stop={'what','with','from','this','that','children','trẻ','những','không','các','được','trong','như','cho','của','với','thế','nào','là','và','có'}
        terms={t.casefold() for t in re.findall(r'[\w-]+',question) if len(t)>2 and t.casefold() not in stop}
        candidates=[]
        for rank,(sid,doc) in enumerate(documents.items(),1):
            options=[]
            for section in sections(doc['content']):
                if section['level']==0:continue
                text=doc['content'][section['start']:section['end']]
                words={w.casefold() for w in re.findall(r'[\w-]+',text)};score=len(terms & words)
                if score:options.append((score,-len(text),section))
            chosen=[]
            for score,_,section in sorted(options,key=lambda x:(-x[0],-x[1],x[2]['start'])):
                if any(section['start']<b and a<section['end'] for a,b in chosen):continue
                chosen.append((section['start'],section['end']))
                if any(e['source_id']==sid and e['source_context']['start']<=section['start'] and section['end']<=e['source_context']['end'] for e in evidence):continue
                ev=exact_evidence(doc,section['start'],section['end'],doc['content'][section['start']:section['end']])
                ev['candidate_selection']=dict(method='lexical_overlap_only',score=score,retrieval_rank=rank)
                candidates.append(ev)
                if len(chosen)>=self.max_per_source:break
            selection_log.append(dict(source_id=sid,heading_units_examined=len(options),candidate_ranges=chosen,
                method='lexical_only_not_semantic_reading',source_completely_semantically_reviewed=False))
        candidates=candidates[:self.max_total]
        unique={e['evidence_id']:e for e in candidates}
        unique.update({e['evidence_id']:e for e in evidence})
        return dict(evidence=list(unique.values()),missing_review_sources=missing,candidate_log=selection_log,
            semantic_backend='explicit_review_annotation' if review else 'unconfigured',
            note='Exact spans and lexical candidates do not establish semantic support. Review annotations are assertions, not clinical certification.')

def validate_review(review,question):
    require(isinstance(review,dict) and review.get('schema_version')==1,'review_invalid','Unsupported review schema.')
    require(review.get('question')==question and review.get('question_sha256')==sha(question),'review_mismatch','Review belongs to another exact question.')
    require(isinstance(review.get('review_id'),str) and bool(review['review_id']),'review_invalid','Missing review ID.')
    reviewer=review.get('reviewer',{})
    require(reviewer.get('kind') in {'human_review','ai_reference_review','model_semantic_review','test_fixture'} and bool(reviewer.get('name')) and bool(reviewer.get('date')),'review_invalid','Reviewer identity/type/date required.')
    require(review.get('intent') in INTENTS,'review_invalid','Explicit review intent is required.')
    claims=review.get('claims',[])
    require(bool(claims) and all(isinstance(c,dict) and isinstance(c.get('claim_id'),str) and c.get('text') and type(c.get('required')) is bool for c in claims),'review_invalid','Claims and explicit required flags are required.')
    require(any(c['required'] for c in claims),'review_invalid','At least one claim must be required.')
    claim_ids={c['claim_id'] for c in claims};require(len(claim_ids)==len(claims),'review_invalid','Duplicate claim IDs.')
    items=review.get('items')
    require(isinstance(items,list),'review_invalid','Review items must be a list.')
    item_ids=set()
    for item in items:
        require(isinstance(item,dict) and isinstance(item.get('item_id'),str) and item['item_id'] not in item_ids,'review_invalid','Missing or duplicate review item ID.')
        item_ids.add(item['item_id'])
        require(item.get('relation') in RELATIONS and item.get('stance') in STANCES,'review_invalid','Unknown semantic relation.')
        require(isinstance(item.get('claim_ids'),list) and set(item['claim_ids'])<=claim_ids,'review_invalid','Evidence refers to an unknown claim.')
        require(item.get('relation')!='topical' or item.get('stance')=='context_only','review_invalid','Topical evidence cannot prove or disprove a claim.')
        require(all(k in item for k in ['source_id','content_sha256','start','end','quote']),'review_invalid','Source identity and exact span are required.')
    for conflict in review.get('conflicts',[]):
        require(conflict.get('claim_id') in claim_ids and len(set(conflict.get('item_ids',[])))>=2 and set(conflict['item_ids'])<=item_ids and bool(conflict.get('rationale')),
            'review_invalid','A conflict requires a claim, at least two known review items and a rationale.')
        require(conflict.get('comparability_reviewed') is True,'review_invalid','Population/outcome comparability must be reviewed explicitly.')

def assess(question,reading,review=None,selected_evidence_ids=None):
    evidence=reading['evidence'];by_id={e['evidence_id']:e for e in evidence}
    available=[e for e in evidence if e['semantic_reviewed'] and not e['instruction_flags'] and (selected_evidence_ids is None or e['evidence_id'] in selected_evidence_ids)]
    if review is None:
        return dict(status='insufficient',assessment_state='pending_semantic_review',reason='No question-specific semantic assessment is configured. This is not a finding that the corpus lacks evidence.',
            claims=[],reviewer=None,review_id=None,conflicts=[],missing_claims=[],used_evidence_ids=[],independent_clinical_reviewed=False)
    validate_review(review,question)
    claims=[];direct_complete=True;any_support=False
    for claim in review['claims']:
        matches=[e for e in available if claim['claim_id'] in e['claim_ids']]
        direct=[e['evidence_id'] for e in matches if e['relation']=='direct' and e['stance']=='supports']
        indirect=[e['evidence_id'] for e in matches if e['relation']=='indirect' and e['stance']=='supports']
        direct_refutation=[e['evidence_id'] for e in matches if e['relation']=='direct' and e['stance']=='opposes']
        indirect_refutation=[e['evidence_id'] for e in matches if e['relation']=='indirect' and e['stance']=='opposes']
        if claim['required'] and not (direct or direct_refutation):direct_complete=False
        any_support=any_support or bool(direct or indirect or direct_refutation or indirect_refutation)
        claims.append(dict(claim_id=claim['claim_id'],text=claim['text'],required=claim['required'],direct=direct,indirect=indirect,direct_refutation=direct_refutation,indirect_refutation=indirect_refutation,
            opposing=[e['evidence_id'] for e in matches if e['stance']=='opposes']))
    by_item={e['review_item_id']:e for e in available if 'review_item_id' in e};conflicts=[];unresolved=[]
    for group in review.get('conflicts',[]):
        present=[by_item[x] for x in group['item_ids'] if x in by_item]
        if len(present)==len(group['item_ids']):
            require({'supports','opposes'}<={e['stance'] for e in present} and all(group['claim_id'] in e['claim_ids'] and e['relation'] in {'direct','indirect'} for e in present),
                'review_invalid','Conflict annotations must link opposing evidence for the same claim.')
            conflicts.append(dict(claim_id=group['claim_id'],evidence_ids=[e['evidence_id'] for e in present],rationale=group['rationale'],comparability_reviewed=True))
        else:unresolved.append(group)
    # Opposing annotations without a reviewed comparison must not be silently ignored.
    pending_comparison=any(c['opposing'] and (c['direct'] or c['indirect']) and not any(g['claim_id']==c['claim_id'] for g in conflicts) for c in claims)
    status='conflicting' if conflicts else 'sufficient' if direct_complete and not unresolved and not pending_comparison else 'partially_sufficient' if any_support else 'insufficient'
    return dict(status=status,assessment_state='model_semantic_review_not_independent_clinical_validation' if review['reviewer']['kind']=='model_semantic_review' else 'reviewed_annotation_not_independent_clinical_validation',
        reason='Computed from review assertions and source spans actually available; model assertions remain provisional.',
        claims=claims,reviewer=copy.deepcopy(review['reviewer']),review_id=review['review_id'],conflicts=conflicts,
        unresolved_conflict_comparisons=bool(unresolved or pending_comparison),
        missing_claims=[c['claim_id'] for c in claims if c['required'] and not (c['direct'] or c['direct_refutation'])],
        missing_review_sources=reading['missing_review_sources'],used_evidence_ids=[e['evidence_id'] for e in available if e['stance']!='context_only'],
        independent_clinical_reviewed=False)

def medical_policy(review,assessment):
    intent=review['intent'] if review else 'unclassified'
    missing=review.get('required_personal_information',[]) if review else []
    if intent=='individual_diagnosis':action='do_not_confirm_personal_diagnosis'
    elif intent=='personalized_medication':action='do_not_prescribe_or_calculate_personal_dose'
    elif missing:action='request_clarification'
    elif assessment['status']=='conflicting' or assessment.get('unresolved_conflict_comparisons'):action='explain_conflict_and_limits'
    elif assessment['assessment_state']=='pending_semantic_review':action='await_semantic_and_intent_review'
    elif assessment['status']=='insufficient':action='explain_insufficient_evidence'
    elif intent=='current_services':action='requires_verified_current_local_information'
    elif intent=='scope_legal':action='explain_scope_only_no_local_legal_conclusion'
    else:action='general_education_with_source_limits'
    return dict(intent=intent,action=action,clarification_fields=missing,individual_diagnosis_allowed=False,individual_prescribing_allowed=False,
        retrieved_content_is_untrusted_data=True,instruction_detection_complete=False,clinical_reviewed=False)
