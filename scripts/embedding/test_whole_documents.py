"""Meaningful offline integrity/contract tests; no billable API calls or DB writes."""
import copy,json,os,tempfile,unittest,io
from pathlib import Path
from unittest.mock import patch,MagicMock
from types import SimpleNamespace
from urllib.error import HTTPError
import whole_documents as w
from smoke_test_nim import PilotError

class WholeDocumentTests(unittest.TestCase):
 def test_full_unicode_input_preserved_through_json_serialization(self):
  body='Điều kiện: tuổi 0–18; không suy rộng.\\nMethods\\n'+('clinical data < 5 mg; −1.5; ' * 8000)+'END OF SOURCE'
  payload=w.api_payload(body,'search_document')
  self.assertEqual(json.loads(json.dumps(payload,ensure_ascii=False))['texts'],[body])
  self.assertEqual(payload['truncate'],'NONE');self.assertEqual(payload['output_dimension'],1536)
 def test_source_release_has_33_unique_whole_documents_and_hashes(self):
  docs,sha,collection=w.load_source()
  self.assertEqual(len(docs),33);self.assertEqual(sum(len(d['noi_dung']) for d in docs),2307606)
  self.assertEqual(max(len(d['noi_dung']) for d in docs),159095)
 def test_saved_native_cohere_vector_is_not_nvidia_excerpt(self):
  docs,dataset,collection=w.load_source();doc=next(d for d in docs if d['id']=='CDC-EARLY-INTERVENTION')
  p=w.read_cached(w.cache_path(collection,doc['id']),doc,dataset,collection)
  self.assertTrue(p['whole_document']);self.assertEqual(p['input_characters'],3478);self.assertEqual(len(p['embedding']),1536)
  self.assertNotEqual(p['profile']['provider'],'nvidia')
 def test_corrupted_or_truncated_cache_is_refused(self):
  docs,dataset,collection=w.load_source();doc=next(d for d in docs if d['id']=='CDC-EARLY-INTERVENTION')
  saved=json.loads(w.cache_path(collection,doc['id']).read_text(encoding='utf-8'))
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'bad.json'
   for field,value in [('sent_characters',107),('content_sha256','wrong'),('embedding_sha256','wrong'),('dimensions',4096)]:
    bad=copy.deepcopy(saved);bad[field]=value;path.write_text(json.dumps(bad),encoding='utf-8')
    with self.assertRaises(PilotError):w.read_cached(path,doc,dataset,collection)
 def test_partial_cache_never_opens_database_for_vector_load(self):
  with patch.object(w,'read_cached',side_effect=PilotError('missing vector')),patch.object(w,'connection',side_effect=AssertionError('Unexpected DB write')):
   with self.assertRaises(PilotError):w.load_vectors(w.DEFAULT_DB_ENV)
 def test_nvidia_credentials_never_sent_to_cohere(self):
  args=SimpleNamespace(prompt_key=False,cohere_env=None)
  with patch.dict(os.environ,{'COHERE_API_KEY':'nvapi-fake-nvidia-key'},clear=False):
   with self.assertRaises(PilotError):w.key_from_args(args)
 def test_rate_rejection_is_distinct_from_uncertain_network_failure(self):
  client=MagicMock();client.open.side_effect=HTTPError(w.ENDPOINT,429,'rate limit',{'Retry-After':'60'},io.BytesIO(b''))
  with patch.object(w.request,'build_opener',return_value=client):
   with self.assertRaises(w.ProviderRejected) as caught:w.api_embed('original body','fixture-key','search_document')
  self.assertEqual(caught.exception.code,429);self.assertEqual(caught.exception.retry_after,60)
  self.assertNotIn('fixture-key',str(caught.exception))
 def test_document_and_query_types_share_exact_model_space(self):
  d=w.api_payload('text','search_document');q=w.api_payload('text','search_query')
  self.assertEqual(d['model'],q['model']);self.assertEqual(d['output_dimension'],q['output_dimension'])
  self.assertNotEqual(d['input_type'],q['input_type'])
 def test_nonfinite_vectors_refused_before_postgres(self):
  for vector in [[float('inf')],[float('nan')],[0.0]*1536,[True]]:
   with self.assertRaises(PilotError):w.validate_vector(vector)

if __name__=='__main__':unittest.main()
