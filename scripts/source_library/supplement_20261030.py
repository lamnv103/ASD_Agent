"""Publish reviewed source additions in ASD_AGENT only. No embeddings, LLM or DB.

plan inspects cached permitted originals; publish creates a versioned data release.
"""
from __future__ import annotations
import argparse,copy,csv,io,json,re
from pathlib import Path
from urllib.parse import urlparse,unquote,parse_qs
from library import base_record,convert_jats,licensed_oa,make_document,clean,text,digest
from direct_sources import jats_bibliography
from storage import atomic_write
ROOT=Path(__file__).resolve().parents[2];LIB=ROOT/'knowledge/rag/source_library'
REPORT=ROOT/'reports/source_supplement_20261030';CACHE=REPORT/'cache';DATE='2026-10-30'
PARENT='840ce10a6b688e4de4ab90d9c03f9fb2bb3e2354d1d5114c0ccc298912e5e0a9'
REVISION='asd-agent-fulltext-supplement-20261030-v1'
SCOPES={
 'PMC4513196':('Young autistic children, especially toddlers and preschoolers; conceptual narrative review, not one recruited cohort.',['early_intervention','language_therapy','family_support'],[
  'Foundational 2015 description of NDBIs, not a current professional practice guideline or a head-to-head trial.',
  'Intervention choices and goals must be individualized; no guaranteed language gain, cure or fixed intensity for all children.',
  'Reviews/program descriptions can overlap underlying studies; not independent replication.']),
 'PMC6590432':('Review conclusion concerns autistic children aged 4–12; study-selection and cognitive criteria retained in full text.',['occupational_therapy','sensory_interventions'],[
  'Ayres Sensory Integration (ASI) with fidelity and trained therapists is not equivalent to generic sensory-based activities or all occupational therapy.',
  'Search covered 2006–2017; three studies met final criteria. CEC evidence classification is not a universal current clinical recommendation.',
  'Predates SenITA 2022 (https://doi.org/10.3310/TQGE0020), which found no significant main benefit over usual care on its primary outcome; do not present the older positive conclusion as current consensus.',
  'Do not infer effectiveness for infants, all cognitive profiles or every ASD outcome; no home pressure/weighted-device prescription.']),
 'PMC12658592':('Review inclusion range 0–21 years with sensory-processing challenges, mixed diagnoses; not an ASD-only sample or evidence for every age.',['occupational_therapy','sensory_interventions','family_support'],[
  'Sensory-based interventions (SBIs) are distinct from fidelity-based Ayres Sensory Integration (ASI).',
  'Do not transfer mixed-diagnosis findings wholesale to autistic children or infer infant safety from the inclusion age range.',
  'Evidence varies by intervention/outcome; no unsupervised deep-pressure, restraint or weighted-device advice.']),
 'PMC11754701':('UK primary-school autistic children aged 4–11; 87 schools, 249 children, cluster randomized trial.',['social_skills','school_support'],[
  'Primary intention-to-treat social responsiveness outcome was not statistically significant; individual socio-emotional goals improved.',
  'Do not claim global social-skill, anxiety, depression or caregiver-stress improvement from individual-goal findings.',
  'Social Stories are not PEERS and this trial does not reproduce a licensed PEERS treatment manual.']),
 'PMC9399988':('Polish adolescents; eligibility age 11–18; recruited ages 11.8–16.1, IQ >70, caregiver participation and motivation criteria; exact recruited ages retained.',['social_skills','peers'],[
  'PEERS cultural adaptation RCT; parent/self-report and unblinded outcomes, wait-list comparison, attrition and small sample limit generalization.',
  'Not a licensed full PEERS manual and not evidence for every autistic adolescent or toddlers.',
  'Plots contain graphical information not yet transcribed without estimating values; keep out of accepted text-only set.']),
 'PMC12208088':('Minimally speaking autistic children; actual study ages and intervention variation retained; not all language profiles.',['language_therapy','aac','early_intervention'],[
  'Systematic review/meta-analysis of NDBIs with/without AAC; evidence may overlap other reviews.',
  'Not a stand-alone speech-language therapy clinical guideline or a guarantee of speech development.',
  'Funnel plot information is not yet safely converted into machine-readable text; retain pending status.']),
 'PMC7726187':('Methodological/narrative analysis of sensory integration/processing treatment; pediatric examples, not an effectiveness trial.',['occupational_therapy','sensory_interventions'],['Critical methodological discussion, not a professional guideline; source images still need full transcription.']),
 'PMC10981608':('Review of social-skills group programs in autistic adolescents; individual program eligibility and actual ages retained.',['social_skills','peers'],['Systematic review/meta-analysis with methodological/fidelity limitations; multiple programs are not interchangeable.','Forest/other plots remain untranscribed; no promotion solely because a paper is a review.']),
 'PMC13414371':('Review of communication interventions in minimally verbal autistic children; exact ages/designs retained.',['language_therapy','aac'],['Do not treat all communication interventions as speech therapy alone; evidence quality differs by study.','Figures and supplementary ZIP have not all been converted; pending.']),
 'PMC10783429':('Project AIM early-childhood intervention review; sample mean-age criteria and all exclusions retained.',['early_intervention','language_therapy'],['Bibliographic/version relationship with PMC10644209 and DOI 10.1136/bmj-2023-076733 must be resolved before acceptance.','Not an additional independent body of evidence beside other Project AIM versions; do not count duplicates.'])}
PMCS=list(SCOPES)

def json_text(value):return json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n'
def jsonl(rows):return ''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows)
def canonical_doi(value):
 value=(value or '').strip().lower();return re.sub(r'^https?://(?:dx\.)?doi\.org/','',value).rstrip('.')
def record_doi(row):
 return canonical_doi(row.get('verified_bibliography',{}).get('ids',{}).get('doi') or row.get('imported_metadata',{}).get('doi_imported') or (row.get('source_url') if 'doi.org/' in (row.get('source_url') or '') else None))
def choose_id(existing,doi,url,fallback):
 matches=[r for r in existing if (doi and record_doi(r)==canonical_doi(doi)) or r.get('source_url')==url]
 if len(matches)>1:raise ValueError('Duplicate source identity already in catalog')
 return matches[0]['source_id'] if matches else fallback

def source_record(sid,title,url,kind):
 row=base_record(sid,title,url,kind);row.update(checked_at=DATE,language='en',clinical_reviewed=False,
  quality_status='not_independently_clinically_appraised',review_agent='AI source/conversion review, not independent clinical approval',
  prototype_ingest=False,production_ingest=False,index_preview=dict(requested=False,status='not_generated_for_this_addition',final_chunk_strategy=False),
  embedding=dict(requested=False,status='not_requested_data_only',token_count=None,truncate=False,split=False),
  source_assets=[],evidence_independence='not_established; reviews and reports may reuse underlying studies')
 return row

def pmc_material(pmc,existing):
 raw=(CACHE/(pmc+'_oai.xml')).read_bytes();article,body,check=convert_jats(raw)
 bib=jats_bibliography(article,pmc);doi=bib['ids'].get('doi');url='https://pmc.ncbi.nlm.nih.gov/articles/'+pmc+'/'
 sid=choose_id(existing,doi,url,'ASD-SUP-'+pmc);row=source_record(sid,check['title'],url,'research')
 rights=licensed_oa(raw,article)
 if not rights:raise ValueError('No recognized reusable full-text license: '+pmc)
 ver=bib['ids'].get('pmcid-ver',pmc+'.1').rsplit('.',1)[-1]
 cloud_path=CACHE/(pmc+'_v'+ver+'_cloud.json')
 if not cloud_path.exists():cloud_path=CACHE/(pmc+'_cloud.json')
 cloud=json.loads(cloud_path.read_text(encoding='utf-8'))
 if cloud.get('is_retracted') is not False:raise ValueError('Unknown/retracted cloud status: '+pmc)
 if cloud.get('pmcid')!=pmc or canonical_doi(cloud.get('doi'))!=canonical_doi(doi):raise ValueError('Cloud/JATS identity mismatch')
 old=next((r for r in existing if r['source_id']==sid),None)
 if old and old.get('coverage_eligible'):raise ValueError('Existing core source must not be rewritten by supplement')
 if old:
  for key in ['original_profile_path','original_profile_sha256','imported_metadata','previous_source_snapshots','previous_conversion_snapshots']:
   if key in old:row[key]=copy.deepcopy(old[key])
 row.update(authors=bib['authors'],publication_date=bib['date'],verified_bibliography=bib,rights=rights,
  version=bib['ids'].get('pmcid-ver')+'; acquired '+DATE,source_family=canonical_doi(doi),
  full_text_url=url,bibliography_status='matched_PMC_OAI_and_cloud_version',source_identity_status='PMC_DOI_title_matched',
  original_age_scope=SCOPES[pmc][0],topics=SCOPES[pmc][1],limits=SCOPES[pmc][2]+['No independent clinical review; research/internal noncommercial use, no individual diagnosis or prescription.'],
  applicability_0_18_years='retain_original_population_scope',source_design=article.get('article-type'),
  correction_check=dict(method='PMC latest-version Cloud flag and JATS related-article scan; core four also checked on PubMed web pages for Erratum/Retraction labels',
   retracted=False,notices=[dict(n.attrib,text=text(n)) for n in article.findall('.//related-article')],
   checked_on=DATE,limitations='Snapshot check, not exhaustive publisher/Crossmark monitoring. NCBI EFetch was unavailable.',metadata_path=cloud_path.relative_to(ROOT).as_posix()))
 assets=[];copies={}
 reviews={e['original_href']:e for e in check.get('source_assets',[])}
 # Native checks use reviewed_assets; keep all supplied original media too, with explicit review state.
 reviewed=json.loads((ROOT/'scripts/source_library/asset_reviews.json').read_text(encoding='utf-8'))
 reviewed={e['original_href']:e for e in reviewed if e['source_xml_sha256']==digest(raw)}
 for cloud_url in cloud.get('media_urls',[]):
  u=urlparse(cloud_url);name=Path(unquote(u.path)).name;file=CACHE/'assets'/pmc/name
  if not file.is_file():continue
  archived='knowledge/rag/source_library/originals/assets/'+pmc+'/'+name
  entry=copy.deepcopy(reviewed.get(name,{}))
  if not entry:entry=dict(pmc=pmc,original_href=name,kind='untranscribed_original_asset',source_cloud_url=cloud_url,
   asset_sha256=digest(file.read_bytes()),cached_path=file.relative_to(ROOT).as_posix(),transcription_status='pending')
  entry['archived_path']=archived;assets.append(entry);copies[archived]=file.read_bytes()
  marker='[Original asset: '+name+'; see source article]'
  if marker in body:body=body.replace(marker,marker+'\n\n[Original asset file](../originals/assets/'+pmc+'/'+name+')')
 row['source_assets']=assets
 row['conversion']=dict(status='complete_text' if not check['gaps'] else 'complete_text_with_gaps',
  **{k:v for k,v in check.items() if k not in {'native_units','title','source_assets','conversion_revision'}},conversion_revision=REVISION)
 if pmc=='PMC10783429':row['conversion']['gaps'].append(dict(type='bibliographic_version',status='needs_relationship_review',related_pmc='PMC10644209'))
 blocking=[n for n in row['correction_check']['notices'] if n.get('related-article-type')!='commentary']
 row['correction_check']['blocking_notices']=blocking
 if pmc=='PMC4513196':
  row['limits'].append('Linked 2022 commentary (PMC9561015) revisits simplification of adult language input; this foundational 2015 review is not a settled language-input prescription. The commentary link is not a retraction or correction notice.')
 accepted=not row['conversion']['gaps'] and not blocking
 row.update(status='accepted_complete_text' if accepted else 'full_text_with_conversion_gaps',coverage_eligible=accepted,
  original_path='knowledge/rag/source_library/originals/'+sid+'/snapshot-'+DATE+'-'+digest(raw)[:12]+'.xml',
  original_sha256=digest(raw),raw_sha256=digest(raw),original_format='xml',
  snapshot_id='snapshot-'+DATE+'-'+digest(raw)[:12])
 copies[row['original_path']]=raw
 return finalize(row,body,copies)

def convert_web_snapshot(block,start,end,links):
 match=re.search(r'Total lines: (\d+)',block)
 lines={int(n):value for n,value in re.findall(r'^L(\d+): ?(.*)$',block,re.M)}
 if not match or set(lines)!=set(range(int(match[1]))):raise ValueError('Incomplete web-reader line set')
 selected=[lines[i] for i in range(start,end)]
 if not selected[0].startswith('# '):raise ValueError('Article must start with its original h1')
 photos=[]
 def substitute(m):
  idx=int(m[1]);label=m[2].split('†')[0]
  if label.startswith('Image:'):
   photos.append(label[6:].strip());return '[Illustrative photograph in source; image not copied: '+label[6:].strip()+']'
  if idx in links:return '['+label+']('+links[idx]+')'
  # Only same-page category anchors, page controls and attribution labels are removed as link markup.
  if idx not in {11,14,15,16,17,18,19,20,26,27,28}:raise ValueError('Unresolved source hyperlink: '+str(idx))
  return label
 body=clean(re.sub(r'【(\d+)†([^】]+)】',substitute,'\n\n'.join(selected)))
 if '【' in body:raise ValueError('Unconverted web citation marker')
 return body,dict(status='complete_text',gaps=[],method='complete numbered public web-reader snapshot; all article lines retained; source hrefs checked',
  source_total_lines=int(match[1]),article_line_range=[start,end],checked_article_lines=end-start,
  original_html_available=False,format_note='Reader snapshot is not an original HTML file; page layout and scripts are not certified.',
  excluded_media=[dict(type='illustrative_photograph',alt=p,clinical_information=False,license_not_assumed=True) for p in photos],
  removals=['site menus and navigation outside article boundaries','same-page anchor/control link markup; visible labels retained'],conversion_revision=REVISION)

def cdc_materials(existing):
 raw=(CACHE/'CDC_COMPLETE_WEB_READER.txt').read_text(encoding='utf-8');blocks=raw.split('--------------------------------------------------------------------------------')
 if len(blocks)!=2:raise ValueError('Expected two complete CDC reader pages')
 configs=[('CDC-EARLY-INTERVENTION','https://www.cdc.gov/act-early/early-intervention/',21,71,
  {13:'https://www.cdc.gov/act-early/early-intervention/contact-information-by-state.html',14:'https://www.parentcenterhub.org/preschoolers/',17:'https://www.cdc.gov/ncbddd/index.html'},
  'Babies/young children with developmental delays/disabilities and families; US under-3 EI and age-3+ preschool referral pathways, not ASD-only.',
  ['early_intervention','family_support'],'2025-09-04','2026-02-16'),
 ('CDC-ASD-TREATMENT','https://www.cdc.gov/autism/treatment/index.html',24,109,
  {22:'https://pediatrics.aappublications.org/content/145/1/e20193447',23:'https://autismsociety.org/resources/intervention-and-therapies/',24:'https://iacc.hhs.gov/publications/publications-analysis/2012/treatments.shtml',25:'https://www.nichd.nih.gov/health/topics/autism/conditioninfo/treatments',29:'https://pubmed.ncbi.nlm.nih.gov/31843864/'},
  'All ages overview; ESDM subsection explicitly 12–48 months. US context; not a child-specific clinical prescription.',
  ['early_intervention','language_therapy','occupational_therapy','sensory_interventions','social_skills'],None,None)]
 result=[]
 for i,(sid,url,start,end,links,scope,topics,published,updated) in enumerate(configs):
  body,conversion=convert_web_snapshot(blocks[i],start,end,links);title=body.splitlines()[0][2:]
  sid=choose_id(existing,None,url,sid);row=source_record(sid,title,url,'official_health_education')
  original=blocks[i].strip()+'\n';path='knowledge/rag/source_library/originals/'+sid+'/snapshot-'+DATE+'-'+digest(original)[:12]+'.web.txt'
  row.update(organization='Centers for Disease Control and Prevention (CDC), National Center on Birth Defects and Developmental Disabilities',
   authors=[],publication_date=published,updated_date=updated,version='CDC public article reader captured '+DATE,
   original_age_scope=scope,topics=topics,full_text_url=url,source_family=url,
   rights=dict(status='verified',license='CDC public-domain agency text; no logos or third-party photographs copied',
    evidence_url='https://www.cdc.gov/other/agencymaterials.html',
    attribution='Source: CDC. Available free on the CDC website. Use does not imply endorsement by CDC, ATSDR, HHS or the US Government.',
    review_basis='Official CDC reuse policy read; selected article text attributed to CDC; no third-party copyright notice in the selected article text. Photographs excluded.'),
   conversion=conversion,status='accepted_complete_text',coverage_eligible=True,source_identity_status='official_CDC_article_and_full_reader_line_coverage',
   original_path=path,original_format='web.txt',original_sha256=digest(original),raw_sha256=digest(original),
   source_assets=[],snapshot_id='snapshot-'+DATE+'-'+digest(original)[:12],
   limits=['Official health education, not an AAP/ASHA/AOTA practice guideline or a treatment-effect trial.',
    'US access/eligibility and service rights must not be applied as Vietnamese legal entitlements.',
    'Overview mentions different approaches without establishing equal evidence or universal benefit; no individualized treatment or medication instructions.',
    'Original HTML download returned 403; this source is a complete numbered reader snapshot, not an original HTML archive.',
    'No independent clinical review.'])
  if i==0:row['source_reviewed_date']='2026-02-17'
  else:row['displayed_source_date']='2024-05-16'
  result.append(finalize(row,body,{path:original.encode('utf-8')}))
 return result

def senita_material(existing):
 from pypdf import PdfReader
 import io
 raw=(CACHE/'SENITA_full.pdf').read_bytes();reader=PdfReader(io.BytesIO(raw))
 if reader.metadata.get('/doi','').lower()!='10.3310/tqge0020' or len(reader.pages)!=172:raise ValueError('SenITA PDF identity/page count mismatch')
 pages=[p.extract_text() or '' for p in reader.pages];license_text=pages[6]
 if 'Creative Commons Attribution CC BY 4.0' not in license_text:raise ValueError('SenITA reuse license not found in PDF')
 url='https://www.ncbi.nlm.nih.gov/books/NBK581603/'
 sid=choose_id(existing,'10.3310/TQGE0020',url,'NIHR-SENITA-2022')
 row=source_record(sid,reader.metadata['/Title'],url,'research_report')
 row.update(organization='NIHR Journals Library',
  authors=['Elizabeth Randell','Melissa Wright','Sarah Milosevic','David Gillespie','Lucy Brookes-Howell','Monica Busse-Morris','Richard Hastings','Wakunyambo Maboshe','Rhys Williams-Thomas','Laura Mills','Renee Romeo','Nahel Yaziji','Anne Marie McKigney','Alka Ahuja','Gemma Warren','Eleni Glarou','Sue Delport','Rachel McNamara'],
  publication_date='2022-06',version='Health Technology Assessment 26(29), June 2022; PDF acquired '+DATE,
  full_text_url='https://njl-admin.nihr.ac.uk/document/download/2039906',source_family='10.3310/tqge0020',
  verified_bibliography=dict(ids={'doi':'10.3310/TQGE0020','pmid':'35766242'},pdf_title=reader.metadata['/Title']),
  source_identity_status='Official NIHR PDF DOI and title matched; 172 physical PDF pages',
  original_age_scope='UK autistic primary-school children aged 4–11 with sensory-processing difficulties; 138 randomized.',
  topics=['occupational_therapy','sensory_interventions'],
  rights=dict(status='verified',license='CC BY 4.0',license_url='https://creativecommons.org/licenses/by/4.0/',evidence_url='https://njl-admin.nihr.ac.uk/document/download/2039906',evidence_pdf_page=7,
   attribution='Randell et al. Sensory integration therapy for children with autism and sensory processing difficulties: the SenITA RCT. NIHR Journals Library, Health Technol Assess 2022;26(29). DOI: 10.3310/TQGE0020.'),
  limits=['Primary main effect did not show significant benefit over usual care; exploratory subgroups do not establish efficacy.',
   'Raw page-level PDF text is provisional: tables/figures, line order, hyphenation and symbols need visual verification; use original PDF for source review.',
   'Complete PDF acquired, but not a verified complete Markdown conversion; no independent clinical appraisal.'],
  conversion=dict(status='complete_text_with_gaps',conversion_revision=REVISION,method='pypdf page-level extraction; no page omitted or clinically rewritten',pdf_pages=len(pages),
   empty_text_pdf_pages=[i+1 for i,t in enumerate(pages) if not t.strip()],
   gaps=[dict(type='pdf_layout',status='needs_table_order_and_symbol_review'),dict(type='figures',status='needs_complete_visual_transcription')]),
  status='full_text_with_conversion_gaps',coverage_eligible=False,
  original_path='knowledge/rag/source_library/originals/'+sid+'/snapshot-'+DATE+'-'+digest(raw)[:12]+'.pdf',
  original_sha256=digest(raw),raw_sha256=digest(raw),original_format='pdf',snapshot_id='snapshot-'+DATE+'-'+digest(raw)[:12])
 body=clean('\n\n'.join('<!-- SOURCE_PDF_PAGE '+str(i+1)+' -->\n\n'+t for i,t in enumerate(pages)))
 return finalize(row,body,{row['original_path']:raw})

def finalize(row,body,copies):
 body=clean(body);folder='documents' if row['coverage_eligible'] else 'pending_documents'
 row['document_path']='knowledge/rag/source_library/'+folder+'/'+row['source_id']+'.md'
 row.update(content_sha256=digest(body),body_characters=len(body),body_words_whitespace=len(body.split()))
 markdown=make_document(row,body)
 if (row.get('organization') or '').startswith('Centers for Disease'):
  markdown=markdown.replace('\n---\n','\nNguồn: CDC; nội dung có miễn phí tại trang nguồn. Việc sử dụng không hàm ý CDC, ATSDR, HHS hoặc Chính phủ Hoa Kỳ bảo trợ dự án.\n\n---\n',1)
 row['document_sha256']=digest(markdown);copies[row['document_path']]=markdown.encode('utf-8')
 return row,copies

def held_records(existing):
 items=[('AAP-ASD-CLINICAL-2020','Identification, Evaluation, and Management of Children With Autism Spectrum Disorder',
  'https://publications.aap.org/pediatrics/article/145/1/e20193447/36917/Identification-Evaluation-and-Management-of','American Academy of Pediatrics','10.1542/peds.2019-3447','2020-01-01',
  'Free to read is not verified permission to reproduce full content for this AI corpus. Publisher PDF says copyrighted AAP property; reaffirmed October 2025.'),
 ('ASHA-AUTISM-PORTAL','Autism and Autism Spectrum Disorder',
  'https://www.asha.org/practice-portal/clinical-topics/autism/','American Speech-Language-Hearing Association',None,None,
  'Practice Portal consulted; no explicit corpus/AI reuse permission established. Metadata/link only, no copied full-text substitute.'),
 ('AOTA-ASD-SERVICES-2022','Autism Spectrum Disorders Across the Life Course and Occupational Therapy Services',
  'https://doi.org/10.5014/ajot.2022.76S3002','American Occupational Therapy Association','10.5014/ajot.2022.76S3002','2022',
  'Official AOTA document; copyright reserved. General AOTA terms restrict reproduction; no separate AI reuse permission established.'),
 ('NIHR-SENITA-2022','Sensory integration therapy for children with autism and sensory processing difficulties: the SenITA RCT',
  'https://www.ncbi.nlm.nih.gov/books/NBK581603/','NIHR Journals Library','10.3310/TQGE0020','2022-06',
  'Full 140-page report not acquired (PDF fetch failed); PubMed/Bookshelf results checked for countervailing evidence. Abstract is not a full report.'),
 ('ASD-SUP-PMC8862714','Understanding the Effects of Naturalistic Developmental Behavioral Interventions: A Project AIM Meta-analysis',
  'https://pmc.ncbi.nlm.nih.gov/articles/PMC8862714/',None,'10.1002/aur.2471','2021',
  'No recognized permitted OA reuse license established by the OAI/license gate; do not add full article to accepted corpus.')]
 out=[]
 for sid,title,url,org,doi,date,reason in items:
  if sid=='NIHR-SENITA-2022':continue  # full original now acquired separately, still conversion-pending
  sid=choose_id(existing,doi,url,sid);row=source_record(sid,title,url,'professional_reference' if org else 'research')
  row.update(organization=org,publication_date=date,status='pending_full_text_acquisition' if sid=='NIHR-SENITA-2022' else 'pending_reuse_permission',
   coverage_eligible=False,source_family=canonical_doi(doi) or url,verified_bibliography=dict(ids={'doi':doi}) if doi else {},
   original_age_scope='See original source; not normalized to the full 0–18 age range',
   rights=dict(status='permission_not_established' if sid!='NIHR-SENITA-2022' else 'needs_original_license_capture',evidence_url='https://www.aota.org/terms-of-use/' if org=='American Occupational Therapy Association' else url),
   limits=[reason,'Metadata only; not included as full-text evidence or in documents.json.'],document_path=None)
  if sid=='NIHR-SENITA-2022':row['evidence_context_note']='138 randomized; no significant primary main effect over usual care. Subgroups hypothesis-generating; this note is editorial metadata, not full source text.'
  out.append(row)
 return out

def plan():
 parent_catalog=REPORT/'before_release/catalog.jsonl'
 catalog_input=parent_catalog if parent_catalog.exists() else LIB/'catalog.jsonl'
 old=[json.loads(x) for x in catalog_input.read_text(encoding='utf-8').splitlines() if x]
 materials=[pmc_material(pmc,old) for pmc in PMCS]+cdc_materials(old)+[senita_material(old)]
 held=held_records(old);ids=[r['source_id'] for r,c in materials]+[r['source_id'] for r in held]
 if len(ids)!=len(set(ids)):raise ValueError('Duplicate intake source IDs')
 return old,materials,held

def publish():
 if str(ROOT).casefold()!=r'E:\AI4LIFE\ASD_AGENT'.casefold():raise ValueError('Only the new ASD_AGENT workspace may be published')
 before_status=json.loads((LIB/'BUILD_STATUS.json').read_text(encoding='utf-8'))
 if before_status['documents_json_sha256']!=PARENT or digest((LIB/'documents.json').read_bytes())!=PARENT:raise ValueError('Dataset changed; create a new intake version rather than overwrite')
 old,materials,held=plan();backup=REPORT/'before_release'
 if backup.exists():raise ValueError('Backup exists; review previous publication before resuming')
 for name in ['catalog.jsonl','core_catalog.jsonl','documents.json','BUILD_STATUS.json','CORE_DOCUMENTS.md','CLINICAL_REVIEW_QUEUE.csv']:
  atomic_write(backup/name,(LIB/name).read_bytes())
 atomic_write(backup/'README.md',(ROOT/'README.md').read_bytes())
 old_core=[r for r in old if r.get('coverage_eligible')];baseline={}
 for r in old_core:
  for path in [r['document_path'],r['original_path']]+[a['archived_path'] for a in r.get('source_assets',[])]:baseline[path]=digest((ROOT/path).read_bytes())
 atomic_write(backup/'original_27_file_hashes.json',json_text(baseline))
 updated={r['source_id']:r for r in old}
 for row,copies in materials:
  for relative,raw in copies.items():
   target=(ROOT/relative).resolve()
   if not target.is_relative_to(LIB.resolve()):raise ValueError('Material path outside library')
   if target.exists() and target.read_bytes()!=raw:raise ValueError('Refuse to overwrite materialized source file: '+relative)
   if not target.exists():atomic_write(target,raw)
  updated[row['source_id']]=row
 for row in held:updated[row['source_id']]=row
 allrows=sorted(updated.values(),key=lambda r:r['source_id']);core=[r for r in allrows if r.get('coverage_eligible')]
 if len({record_doi(r) for r in core if record_doi(r)})!=sum(bool(record_doi(r)) for r in core):raise ValueError('Duplicate DOI in core')
 for r in core:
  if r['status']!='accepted_complete_text' or r['conversion']['gaps'] or r['clinical_reviewed']:raise ValueError('Invalid core admission state')
 # Publish the usability marker last. Existing readers reject the building state.
 atomic_write(LIB/'BUILD_STATUS.json',json_text(dict(status='building',usable=False,parent_release_sha256=PARENT,clinical_reviewed=False)))
 atomic_write(LIB/'catalog.jsonl',jsonl(allrows));atomic_write(LIB/'core_catalog.jsonl',jsonl(core))
 from export_json import build_export,verify_roundtrip
 catalog_sha=digest((LIB/'catalog.jsonl').read_bytes())
 atomic_write(LIB/'BUILD_STATUS.json',json_text(dict(status='building',usable=False,checked_at=DATE,parent_release_sha256=PARENT,clinical_reviewed=False)))
 payload=build_export(expected_catalog_sha256=catalog_sha);verify_roundtrip(json.loads(json_text(payload)),payload)
 previous=json.loads((backup/'documents.json').read_text(encoding='utf-8'))
 new_by_id={d['id']:d for d in payload['tai_lieu']}
 if any(new_by_id.get(d['id'])!=d for d in previous['tai_lieu']):raise ValueError('Original 27 document/metadata entries changed')
 atomic_write(LIB/'documents.json',json_text(payload))
 with (LIB/'CLINICAL_REVIEW_QUEUE.csv').open(encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f);fields=reader.fieldnames;reviews={r['source_id']:r for r in reader}
 buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=fields);writer.writeheader()
 for row in core:
  value=reviews.get(row['source_id']) or {f:'' for f in fields}
  if not value.get('source_id'):value.update(source_id=row['source_id'],title=row['title'],source_url=row['source_url'],document_path=row['document_path'],population_scope=row['original_age_scope'],source_limits='; '.join(row.get('limits',[])))
  writer.writerow(value)
 atomic_write(LIB/'CLINICAL_REVIEW_QUEUE.csv','\ufeff'+buffer.getvalue())
 pending=[r for r,c in materials if not r['coverage_eligible']]
 atomic_write(LIB/'documents_pending_review.json',json_text(dict(status='NOT_ACCEPTED_FOR_INDEXING',reason='Full source body acquired but conversion/identity gaps remain',
  documents=[dict(source_id=r['source_id'],title=r['title'],source_url=r['source_url'],status=r['status'],conversion_gaps=r['conversion']['gaps'],metadata=r,
   content=(ROOT/r['document_path']).read_text(encoding='utf-8').split('<!-- ORIGINAL_DOCUMENT_BODY -->\n',1)[1]) for r in pending])))
 guide=['# Tài liệu toàn văn trong tập chính','', '**Kho nguồn phục vụ nghiên cứu; chưa thẩm định lâm sàng độc lập.**','',
  str(len(core))+' tài liệu; '+format(payload['thong_tin_bo_du_lieu']['tong_ky_tu_noi_dung'],',')+' ký tự nội dung. Chỉ tính tài liệu được nhận; không cộng bản chờ, hình hoặc phụ lục.','',
  '| ID và tài liệu | Phạm vi gốc |','|---|---|']
 for r in core:guide.append('| ['+r['source_id']+': '+r['title']+'](documents/'+r['source_id']+'.md) | '+r['original_age_scope'].replace('|',' / ')+' |')
 atomic_write(LIB/'CORE_DOCUMENTS.md','\n'.join(guide)+'\n')
 for path,sha in baseline.items():
  if digest((ROOT/path).read_bytes())!=sha:raise ValueError('Original source file changed')
 status=dict(status='verified',usable=True,release_id=REVISION,parent_release_sha256=PARENT,checked_at=DATE,
  catalog_sha256=catalog_sha,documents_json_sha256=digest((LIB/'documents.json').read_bytes()),
  core_documents=len(core),body_characters=payload['thong_tin_bo_du_lieu']['tong_ky_tu_noi_dung'],
  clinical_reviewed=False,usable_for='source_review_only',production_ingest=False,embedding_ready=False,
  index_preview_scope='Original 183 units cover the original 27 documents only; additions not indexed in this phase',
  original_project_and_database_unchanged=True,embedding_called=False,llm_called=False)
 atomic_write(LIB/'BUILD_STATUS.json',json_text(status))
 report=dict(ok=True,local_date=DATE,source_library=str(LIB),new_release=status,original_core_documents=27,
  additions_accepted=[r['source_id'] for r,c in materials if r['coverage_eligible']],
  acquired_pending_sources=[dict(source_id=r['source_id'],title=r['title'],gaps=r['conversion']['gaps']) for r in pending],
  metadata_only_held=[dict(source_id=r['source_id'],title=r['title'],status=r['status'],reason=r['limits'][0]) for r in held],
  original_27_entries_and_source_assets_unchanged=True,clinical_reviewed=False,embedding_called=False,database_changed=False)
 atomic_write(REPORT/'publication.json',json_text(report));return report

def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['plan','publish']);a=p.parse_args()
 if a.command=='plan':
  old,materials,held=plan();out=dict(accepted=[r['source_id'] for r,c in materials if r['coverage_eligible']],pending=[r['source_id'] for r,c in materials if not r['coverage_eligible']],held=[r['source_id'] for r in held])
 else:out=publish()
 print(json_text(out),end='')
if __name__=='__main__':main()
