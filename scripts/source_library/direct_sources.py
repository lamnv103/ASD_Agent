"""Admit selected original PMC articles using independent Cloud/JATS identity checks."""
from __future__ import annotations
import difflib
import json
import re
from library import base_record, convert_jats, licensed_oa, text, comparable

def jats_bibliography(article, pmc):
    meta=article.find('front/article-meta')
    ids={n.get('pub-id-type'):text(n) for n in meta.findall('article-id')}
    authors=[]
    for n in meta.findall('contrib-group/contrib'):
        if n.get('contrib-type','author')!='author':continue
        name=n.find('name')
        value=' '.join(filter(None,[text(name.find('given-names')),text(name.find('surname'))])) if name is not None else text(n.find('collab'))
        if value:authors.append(value)
    dates=meta.findall('pub-date')
    preferred=next((n for n in dates if n.get('pub-type') in {'epub','epub-ppub'} or n.get('publication-format')=='electronic'),None)
    if preferred is None:preferred=next(iter(dates),None)
    parts={n.tag:text(n) for n in preferred} if preferred is not None else {}
    date='-'.join(parts.get(k,'') for k in ['year','month','day']).strip('-') or None
    return {'ids':dict(ids,pmc=pmc),'authors':authors,'date':date,'date_parts':parts,
            'publication_types':['Review'] if article.get('article-type')=='review-article' else [],
            'metadata_provider':'PMC JATS original; not a PubMed linked-notice search'}

def direct_records(existing,root,cache,report,save_document,json_write):
    manifest=json.loads((root/'scripts/source_library/oai_sources.json').read_text(encoding='utf-8'))
    records=[]
    for item in manifest:
        pmc=item['pmc'];sid=item['source_id']
        r=base_record(sid,item['title'],'https://pmc.ncbi.nlm.nih.gov/articles/'+pmc+'/','research')
        r.update(language='en',topics=item['topics'],limits=item.get('limits',[]))
        original=cache/(pmc+'_oai.xml');cloud=cache/(pmc+'.1_cloud.json')
        if item.get('metadata_only_hold'):
            r['status']=item['metadata_only_hold']['status'];r['correction_check']=item['metadata_only_hold']
            r['rights']['status']='permission_not_established';records.append(r);continue
        if not original.exists() or not cloud.exists():
            r['status']='pending_source_metadata_verification' if original.exists() else 'pending_official_full_text_fetch'
            records.append(r);continue
        raw=original.read_bytes();article,body,check=convert_jats(raw)
        metadata=json.loads(cloud.read_text(encoding='utf-8'));bib=jats_bibliography(article,pmc)
        doi=bib['ids'].get('doi','').lower()
        if (metadata.get('pmcid')!=pmc or metadata.get('doi','').lower()!=doi
            or difflib.SequenceMatcher(None,comparable(metadata.get('title','')),comparable(check['title'])).ratio()<.97
            or difflib.SequenceMatcher(None,comparable(item['title']),comparable(check['title'])).ratio()<.97):
            r['status']='pending_identity_mismatch';records.append(r);continue
        duplicate=next((p for p in existing if p.get('verified_bibliography',{}).get('ids',{}).get('pmc')==pmc
                        or doi and ((p.get('verified_bibliography',{}).get('ids',{}).get('doi') or '').lower()==doi
                                    or (p.get('source_url') or '').lower()=='https://doi.org/'+doi)),None)
        if duplicate:
            duplicate['aliases']=list(dict.fromkeys(duplicate['aliases']+[sid]))
            continue
        r.update(title=check['title'],bibliography_status='matched_PMC_Cloud_and_JATS',
                 verified_bibliography=bib,authors=bib['authors'],publication_date=bib['date'],
                 source_design=article.get('article-type'),version='PMC distributed version '+str(metadata['version']),
                 original_age_scope='Pending full-text population review',full_text_url=r['source_url'])
        notices=[{'type':n.get('related-article-type'),'doi':n.get('{http://www.w3.org/1999/xlink}href'),'text':text(n)}
                 for n in article.findall('.//related-article')]
        r['correction_check']={'method':'PMC Cloud is_retracted flag and JATS related-article notices at acquisition snapshot; not exhaustive',
                               'retracted':metadata.get('is_retracted'),'notices':notices,
                               'metadata_path':cloud.relative_to(root).as_posix(),
                               'limitations':'PubMed linked notices and publisher Crossmark require separate refresh; absence of a flag is not proof no future correction exists.'}
        if metadata.get('is_retracted') is None:
            r['status']='pending_retraction_status';records.append(r);continue
        if metadata.get('is_retracted') or any('retract' in (n['type'] or '') for n in notices):
            r['status']='excluded_retracted';records.append(r);continue
        if notices:
            r['status']='pending_correction_review';records.append(r);continue
        rights=licensed_oa(raw,article)
        if not rights:
            r['status']='pending_reuse_permission';records.append(r);continue
        r['rights']=rights
        if item.get('quality_hold'):
            r['status']='pending_clinical_content_review';records.append(r);continue
        r['limits']+=['Source/provenance review only; no independent clinical appraisal.',
                      'Retain actual ages, geography and study limitations; no individualized diagnosis, treatment or dosing inference.']
        r['conversion']=dict(status='complete_text_with_gaps' if check['gaps'] else 'complete_text',
                             **{k:v for k,v in check.items() if k not in {'native_units','title'}})
        evidence=report/'conversion_checks'/(sid+'.json')
        json_write(evidence,dict(source_id=sid,cached_original=original.relative_to(root).as_posix(),**check))
        save_document(r,body,raw,evidence);records.append(r)
    return records
