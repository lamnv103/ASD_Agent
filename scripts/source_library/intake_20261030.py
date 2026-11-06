"""ASD source supplementation. Public source retrieval only; no models or database."""
from pathlib import Path
import argparse,json,ssl,time,urllib.request,urllib.parse,urllib.error
from storage import atomic_write,sha256,validate_payload
import certifi
ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'reports/source_supplement_20261030';CACHE=REPORT/'cache'
CANDIDATES=['PMC6590432','PMC7726187','PMC12658592','PMC9399988','PMC11754701','PMC10981608','PMC12208088','PMC13414371','PMC8862714','PMC10783429']
CDC={'CDC-EARLY-INTERVENTION':'https://www.cdc.gov/act-early/early-intervention/',
     'CDC-ASD-TREATMENT':'https://www.cdc.gov/autism/treatment/index.html',
     'CDC-REUSE-POLICY':'https://www.cdc.gov/other/agencymaterials.html'}
ALLOWED={'pmc.ncbi.nlm.nih.gov','pmc-oa-opendata.s3.amazonaws.com','www.cdc.gov','eutils.ncbi.nlm.nih.gov','www.ncbi.nlm.nih.gov'}

def fetch(key,url):
    if urllib.parse.urlparse(url).hostname not in ALLOWED:raise ValueError('Host outside allowed original sources')
    target=CACHE/key
    if target.exists():validate_payload(key,target.read_bytes());return target.read_bytes()
    time.sleep(.5)
    request=urllib.request.Request(url,headers={'User-Agent':'ASDSourceLibrary/20261030 (internal noncommercial research)','Accept-Encoding':'identity'})
    row=dict(key=key,requested_url=url,checked_on='2026-10-30')
    try:
        with urllib.request.urlopen(request,context=ssl.create_default_context(cafile=certifi.where()),timeout=35) as response:
            if urllib.parse.urlparse(response.url).hostname not in ALLOWED:raise ValueError('Redirect outside allowed sources')
            raw=response.read();row.update(final_url=response.url,status=response.status,content_type=response.headers.get('Content-Type'))
        validate_payload(key,raw);row.update(sha256=sha256(raw),bytes=len(raw));atomic_write(target,raw)
    except Exception as error:row.update(status='error',error_type=type(error).__name__,message=str(error)[:200]);raw=None
    logfile=REPORT/'fetch_log.jsonl';prior=logfile.read_text(encoding='utf-8') if logfile.exists() else ''
    atomic_write(logfile,prior+json.dumps(row,ensure_ascii=False)+'\n')
    return raw

def online():
    from library import convert_jats,licensed_oa,xml_without_tag_namespaces,text
    from direct_sources import jats_bibliography
    report=[]
    for pmc in CANDIDATES:
        cloud=fetch(pmc+'_cloud.json','https://pmc-oa-opendata.s3.amazonaws.com/metadata/'+pmc+'.1.json')
        url='https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/?'+urllib.parse.urlencode(dict(verb='GetRecord',identifier='oai:pubmedcentral.nih.gov:'+pmc[3:],metadataPrefix='pmc'))
        raw=fetch(pmc+'_oai.xml',url)
        if raw is None:print(pmc,'FETCH_FAILED',flush=True);continue
        try:
            article,body,check=convert_jats(raw);bib=jats_bibliography(article,pmc);rights=licensed_oa(raw,article)
            item=dict(pmc=pmc,title=check['title'],bibliography=bib,cloud=json.loads(cloud) if cloud else None,
                rights=rights,characters=len(body),gaps=check['gaps'],tables=len(article.findall('.//table-wrap')),figures=len(article.findall('.//fig')),
                headings=[text(n) for n in article.findall('.//body/sec/title')],
                related_articles=[dict(n.attrib,text=text(n)) for n in article.findall('.//related-article')])
            report.append(item);print(pmc,'characters',len(body),'gaps',len(check['gaps']),'tables',item['tables'],'figures',item['figures'],'rights',bool(rights),flush=True)
        except Exception as error:print(pmc,type(error).__name__,str(error)[:100],flush=True)
    for key,url in CDC.items():
        raw=fetch(key+'.html',url);print(key,'fetched' if raw else 'FETCH_FAILED',flush=True)
    atomic_write(REPORT/'candidate_inspection.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--online',action='store_true');args=parser.parse_args()
    if not args.online:raise SystemExit('Use --online to fetch permitted originals; no provider/API key needed')
    online()
