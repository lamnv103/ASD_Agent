"""Offline regression checks. Synthetic fixtures are not real embedding results."""
import contextlib,copy,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import smoke_test_nim as s

class PilotTests(unittest.TestCase):
 def test_saved_real_vector_and_exact_source_locations(self):
  meta=s.load_sample();payload=json.loads((s.REPORT/'pilot_embedding.json').read_text(encoding='utf-8'))
  self.assertEqual(s.check_cached(payload,meta),payload)
  dataset=json.loads((s.LIBRARY/'documents.json').read_text(encoding='utf-8'))
  source=next(d for d in dataset['tai_lieu'] if d['id']==meta['source_id'])
  self.assertEqual(source['noi_dung'][meta['sample_start_char']:meta['sample_end_char_exclusive']],meta['sample_text'])
 def test_invalid_numeric_vectors_rejected(self):
  for vector in [[],[float('nan')],[float('inf')],[True],[0.0,0.0],['0.1']]:
   with self.subTest(vector=repr(vector)):
    with self.assertRaises(s.PilotError):s.validate_vector(vector)
 def test_wrong_model_extra_results_and_index_rejected(self):
  for payload in [
   {'model':'chat-model','data':[{'index':0,'embedding':[1.0]}]},
   {'data':[{'index':1,'embedding':[1.0]}]},
   {'data':[{'index':0,'embedding':[1.0]},{'index':1,'embedding':[1.0]}]}]:
   with self.assertRaises(s.PilotError):s.parse_response(payload)
 def test_cached_replay_never_reads_credential_or_calls_api(self):
  output=io.StringIO()
  with patch.object(s,'call_nim',side_effect=AssertionError('Unexpected API call')),patch.object(s,'read_key',side_effect=AssertionError('Unexpected credential read')),contextlib.redirect_stdout(output):
   self.assertEqual(s.main(['--print-full']),0)
  self.assertIn('cached result, no API call',output.getvalue())
  self.assertIn('VECTOR_FULL:',output.getvalue())
 def test_changed_source_or_model_cannot_reuse_cache(self):
  payload=json.loads((s.REPORT/'pilot_embedding.json').read_text(encoding='utf-8'))
  for key,value in [('sample_text','different'),('model_requested','chat-model'),('encoding_format','base64'),('dimensions',1)]:
   changed=copy.deepcopy(payload);changed[key]=value
   with self.assertRaises(s.PilotError):s.check_cached(changed,s.load_sample())
 def test_yaml_only_matching_nvidia_model_selected(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'fixture.env'
   path.write_text('models:\n  - provider: nvidia\n    model: '+s.MODEL+'\n    apiKey: fixture-key-not-a-real-credential\n',encoding='utf-8')
   self.assertEqual(s.read_key(path,'NVIDIA_API_KEY'),'fixture-key-not-a-real-credential')
   path.write_text('models:\n  - provider: nvidia\n    model: unrelated-model\n    apiKey: fixture-key-not-a-real-credential\n',encoding='utf-8')
   with self.assertRaises(s.PilotError):s.read_key(path,'NVIDIA_API_KEY')
 def test_dotenv_reads_only_named_key(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'fixture.env';path.write_text("OTHER_KEY=unrelated\nexport NVIDIA_API_KEY='fixture-only' # comment\n",encoding='utf-8')
   self.assertEqual(s.read_key(path,'NVIDIA_API_KEY'),'fixture-only')
 def test_payload_uses_embedding_endpoint_contract_without_truncation(self):
  payload=s.request_payload('exact source text')
  self.assertEqual(payload['input'],['exact source text']);self.assertEqual(payload['input_type'],'passage')
  self.assertEqual(payload['truncate'],'NONE');self.assertNotIn('dimensions',payload)

if __name__=='__main__':unittest.main()
