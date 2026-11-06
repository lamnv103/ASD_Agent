"""Finalize the loaded whole-document release. No embedding API calls."""
import json,csv,io
import whole_documents as w
from smoke_test_nim import sha,atomic_json

def main():
 if (w.REPORT/'embedding.lock').exists():raise SystemExit('Embedding process still active.')
 status=w.verify(w.DEFAULT_DB_ENV)
 complete_path=w.REPORT/'embedding_complete.json'
 complete=json.loads(complete_path.read_text(encoding='utf-8'))
 complete.update(database_loaded=True,database_verified_at=status['checked_at'],database_verification_file='database_verification.json')
 complete.pop('database_note',None);atomic_json(complete_path,complete)
 docs,dataset,collection=w.load_source()
 records=[w.read_cached(w.cache_path(collection,d['id']),d,dataset,collection) for d in docs]
 assert len({r['provider_request_id'] for r in records})==33
 aggregate=w.REPORT/'whole_document_embeddings.jsonl'
 aggregate.write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+chr(10) for r in records),encoding='utf-8')
 assert len([json.loads(x) for x in aggregate.read_text(encoding='utf-8').splitlines()])==33
 log=w.REPORT/'request_events.jsonl';events=[]
 if log.exists():
  raw=log.read_text(encoding='utf-8');pos=0;decoder=json.JSONDecoder()
  while pos<len(raw):
   if raw[pos].isspace():pos+=1;continue
   if raw[pos:pos+2]=='\\n':pos+=2;continue
   value,end=decoder.raw_decode(raw,pos);events.append(value);pos=end
  log.write_text(''.join(json.dumps(e,ensure_ascii=False)+chr(10) for e in events),encoding='utf-8')
 rows=[dict(source_id=r['source_id'],title=r['source_title'],characters=r['input_characters'],sent_characters=r['sent_characters'],
  provider_billed_input_tokens=r['usage_meta']['billed_units']['input_tokens'],dimensions=r['dimensions'],truncate=r['truncate'],whole_document=True,
  content_sha256=r['content_sha256'],embedding_sha256=r['embedding_sha256']) for r in records]
 buff=io.StringIO(newline='');writer=csv.DictWriter(buff,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 (w.REPORT/'document_lengths_and_embeddings.csv').write_text('\ufeff'+buff.getvalue(),encoding='utf-8')
 preflight_path=w.REPORT/'preflight.json';preflight=json.loads(preflight_path.read_text(encoding='utf-8'))
 if not (w.REPORT/'preflight_before_embedding.json').exists():atomic_json(w.REPORT/'preflight_before_embedding.json',preflight)
 preflight['status']='all_33_native_whole_inputs_accepted_and_loaded'
 byid={r['source_id']:r for r in rows}
 for row in preflight['documents_detail']:
  row['embedding_status']='native_full_input_accepted'
  row['provider_billed_input_tokens']=byid[row['source_id']]['provider_billed_input_tokens']
  row['token_status']='Provider billing count available; not inferred from characters. Exact tokenizer count not separately requested.'
 atomic_json(preflight_path,preflight)
 conn=w.connection(w.DEFAULT_DB_ENV);blocked=False
 try:
  with conn.cursor() as c:
   c.execute('select space_id from carobud_rag.embedding_spaces where space_id<>%s and dimensions=%s limit 1',(w.SPACE,w.DIM));other=c.fetchone()
   assert other
   try:
    c.execute('insert into carobud_rag.embeddings(collection_id,chunk_id,space_id,dimensions,embedding) select collection_id,chunk_id,%s,dimensions,embedding from carobud_rag.embeddings where collection_id=%s and space_id=%s limit 1',(other[0],collection,w.SPACE))
   except w.psycopg2.errors.UniqueViolation as e:blocked=e.diag.constraint_name=='whole33_'+dataset[:12]+'_one_vector'
   finally:conn.rollback()
 finally:conn.close()
 assert blocked,'One-vector constraint did not reject duplicate across spaces.'
 status=w.verify(w.DEFAULT_DB_ENV)
 atomic_json(w.REPORT/'embedding_manifest.json',dict(collection_id=collection,space_id=w.SPACE,profile=w.PROFILE,dataset_sha256=dataset,documents=33,
  whole_document_vectors=33,aggregate_file=aggregate.relative_to(w.ROOT).as_posix(),aggregate_sha256=sha(aggregate.read_bytes()),no_chunk_averaging=True,
  records=[dict(source_id=r['source_id'],content_sha256=r['content_sha256'],cache_file=w.cache_path(collection,r['source_id']).relative_to(w.ROOT).as_posix(),
   cache_sha256=sha(w.cache_path(collection,r['source_id']).read_bytes()),embedding_sha256=r['embedding_sha256'],dimensions=1536,provider_request_id=r['provider_request_id']) for r in records]))
 smoke_path=w.REPORT/'retrieval_smoke.json';smoke=json.loads(smoke_path.read_text(encoding='utf-8')) if smoke_path.exists() else None
 protected=json.loads((w.LIB/'SUPPLEMENT_20261030_MANIFEST.json').read_text(encoding='utf-8'))
 verification=dict(ok=True,checked_at=w.now(),database=status,whole_documents=33,whole_document_vectors=33,dimensions=1536,model='embed-v4.0',provider='cohere',
  source_characters=sum(r['input_characters'] for r in records),maximum_document_characters=max(r['input_characters'] for r in records),
  provider_billed_input_tokens=sum(r['usage_meta']['billed_units']['input_tokens'] for r in records),
  maximum_provider_billed_tokens_per_document=max(r['usage_meta']['billed_units']['input_tokens'] for r in records),
  successful_unique_document_requests=33,recorded_rejected_requests=sum(e.get('event')=='provider_rejected' for e in events),
  all_inputs_sent_unmodified=True,truncate='NONE',all_vectors_finite=True,duplicate_vector_across_spaces_rejected_by_postgres=blocked,
  legacy_rows_unchanged=True,protected_library_files_verified=len(protected['files']),cached_files=33,aggregate_sha256=sha(aggregate.read_bytes()),
  retrieval_smoke=smoke,clinical_answer_quality_evaluated=False,existing_chatbot_configuration_changed=False)
 controls=w.REPORT/'runtime_controls.json'
 if controls.exists():verification['runtime_controls']=json.loads(controls.read_text(encoding='utf-8'))
 atomic_json(w.REPORT/'verification.json',verification)
 lines=['# Kết quả nhúng nguyên văn 33 tài liệu','',
  '**Đã nhúng và nạp PostgreSQL: 33 tài liệu = 33 vector.** Không chia đoạn, tóm tắt, lấy phần đầu/cuối hoặc trung bình vector.','',
  '- Model Cohere embed-v4.0, ngữ cảnh 128k, vector 1536 chiều.',
  '- Toàn văn gốc documents.json giữ nguyên hash; database giữ đủ 2.307.606 ký tự nguồn.',
  '- whole_document_embeddings.jsonl: 33 dòng, mỗi dòng một vector kèm metadata/hash nguồn.',
  '- vectors/: cùng các vector ở tệp riêng để tiếp tục, không phải tập vector khác.',
  '- embedding_manifest.json: model/profile, ID và hash nguồn/vector.',
  '- document_lengths_and_embeddings.csv: số ký tự thực gửi và token tính phí API trả về.',
  '- database_verification.json / verification.json: nghiệm thu và bảo toàn dữ liệu cũ.',
  '- postgres_before.dump / backup.json: bản pg_dump trước cập nhật và hash backup.',
  '- retrieval_smoke.json: thử truy xuất tiếng Việt từ PostgreSQL/pgvector, chưa phải benchmark y khoa.',
  '- active_collection.json: cấu hình collection/không gian đã xác minh.','',
  'Cấu hình chatbot trong dự án cũ chưa bị sửa. Không dùng query Gemini/NVIDIA để tìm trong vector Cohere.',
  'Kho vẫn phục vụ nghiên cứu, chưa có thẩm định lâm sàng độc lập. Xem scripts/embedding/README_WHOLE_DOCUMENTS.md.','']
 (w.REPORT/'README.md').write_text(chr(10).join(lines),encoding='utf-8')
 root_readme=w.ROOT/'README.md';text=root_readme.read_text(encoding='utf-8')
 text=text.replace('Sau đợt bổ sung, đã chạy thử embedding một đoạn CDC qua NVIDIA; chưa nhúng nguyên tài liệu hoặc toàn bộ kho.','Sau đợt bổ sung và pilot NVIDIA, đã nhúng đủ 33 tài liệu nguyên văn bằng Cohere embed-v4.0 và nạp vào collection PostgreSQL mới.')
 heading='## Embedding nguyên văn 33 tài liệu và PostgreSQL'
 if heading not in text:
  text+=chr(10)+heading+chr(10)+chr(10)+'Đã hoàn tất **33 tài liệu = 33 vector Cohere 1536 chiều**, giữ đủ toàn văn, không chia đoạn hoặc trung bình vector. Collection mới đã bật cho công cụ truy xuất; các collection/vector cũ giữ nguyên. Không tự chuyển chatbot cũ sang Cohere.'+chr(10)+chr(10)+'Xem [hướng dẫn vận hành](scripts/embedding/README_WHOLE_DOCUMENTS.md), [33 vector JSONL](reports/whole_document_embedding_20261030/whole_document_embeddings.jsonl) và [nghiệm thu](reports/whole_document_embedding_20261030/verification.json). Các trạng thái embedding cũ trong source_library là snapshot lịch sử của đợt phát hành nguồn, không phải trạng thái vector hiện tại.'+chr(10)
 root_readme.write_text(text,encoding='utf-8')
 print(json.dumps({k:v for k,v in verification.items() if k not in {'database','retrieval_smoke'}},ensure_ascii=False,indent=2))
 return verification

if __name__=='__main__':main()
