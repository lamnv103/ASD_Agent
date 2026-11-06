"""Three semantic retrieval smoke checks; no generated medical answers."""
import os,json,getpass
from types import SimpleNamespace
import whole_documents as w
from smoke_test_nim import atomic_json

key=getpass.getpass('COHERE_API_KEY (hidden, not saved): ').strip()
os.environ['COHERE_API_KEY']=key
questions=[
 ('SMOKE-01','Can thiệp phát triển hành vi tự nhiên NDBI là gì?',['ASD-SUP-PMC4513196']),
 ('SMOKE-02','Social Stories có cải thiện kết quả chính về đáp ứng xã hội trong ASSSIST-2 không?',['ASD-SUP-PMC11754701']),
 ('SMOKE-03','Nhận biết trầm cảm ở tuổi vị thành niên và tìm trợ giúp như thế nào?',['NIH-NIMH-TEEN-DEPRESSION'])]
docs,_,_=w.load_source();source_map={d['id']:d for d in docs};results=[]
for identifier,query,expected in questions:
 args=SimpleNamespace(db_env=w.DEFAULT_DB_ENV,query=query,top_k=5,prompt_key=False,cohere_env=None)
 result=w.search(args);ids=[r['source_id'] for r in result['results']]
 source=w.read_database_source(SimpleNamespace(db_env=w.DEFAULT_DB_ENV,source_id=expected[0]))
 assert source['content']==source_map[expected[0]]['noi_dung']
 row=dict(id=identifier,query=query,expected_sources=expected,top5_source_ids=ids,expected_in_top5=any(s in ids for s in expected),
  full_source_read_from_postgres_and_matches=True,results=result['results'])
 results.append(row);print(json.dumps({k:v for k,v in row.items() if k!='results'},ensure_ascii=False),flush=True)
report=dict(status='completed',purpose='Small semantic retrieval smoke check, not a validated clinical retrieval benchmark',
 model=w.MODEL,space_id=w.SPACE,queries=len(results),expected_in_top5=sum(r['expected_in_top5'] for r in results),
 generated_answers=False,clinical_answer_quality_evaluated=False,results=results)
atomic_json(w.REPORT/'retrieval_smoke.json',report)
for folder in [w.ROOT/'scripts/embedding',w.REPORT]:
 for file in folder.rglob('*'):
  if file.is_file():
   assert key.encode('utf-8') not in file.read_bytes(),'Credential found in generated artifact'
os.environ.pop('COHERE_API_KEY',None);key=None
print('Retrieval smoke finished; no API credential persisted.',flush=True)
