import copy,json,re,unittest
from pathlib import Path
from unittest.mock import patch
import supplement_20261030 as s
from library import convert_jats,licensed_oa,xml_without_tag_namespaces,digest
from source_assets import load_assets

class SupplementTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.old,cls.materials,cls.held=s.plan();cls.byid={r['source_id']:(r,c) for r,c in cls.materials}
 def test_six_complete_additions_and_seven_pending(self):
  self.assertEqual(sum(r['coverage_eligible'] for r,c in self.materials),6)
  self.assertEqual(sum(not r['coverage_eligible'] for r,c in self.materials),7)
 def test_complete_sources_have_no_conversion_gaps_or_clinical_approval(self):
  for r,c in self.materials:
   self.assertFalse(r['clinical_reviewed']);self.assertFalse(r['production_ingest']);self.assertFalse(r['embedding']['requested'])
   if r['coverage_eligible']:self.assertEqual(r['conversion']['gaps'],[])
 def test_incomplete_plots_cannot_enter_core(self):
  for pmc in ['PMC9399988','PMC12208088','PMC10981608']:
   row=next(r for r,c in self.materials if pmc in r['source_url']);self.assertFalse(row['coverage_eligible']);self.assertTrue(row['conversion']['gaps'])
 def test_existing_source_identity_reused(self):
  row=next(r for r,c in self.materials if 'PMC12208088' in r['source_url'])
  self.assertEqual(row['source_id'],'ASD-CSV-017')
 def test_unknown_rights_and_metadata_only_not_admitted(self):
  for r in self.held:self.assertFalse(r['coverage_eligible']);self.assertIsNone(r['document_path'])
 def test_no_abstract_only_article(self):
  raw=b'<article><front><article-meta><abstract><p>Abstract only.</p></abstract></article-meta></front></article>'
  with self.assertRaises(ValueError):convert_jats(raw)
 def test_incomplete_reader_snapshot_rejected(self):
  raw='Total lines: 3\nL0: # Article\nL2: Last line'
  with self.assertRaises(ValueError):s.convert_web_snapshot(raw,0,3,{})
 def test_reader_does_not_invent_original_html(self):
  rows=[r for r,c in self.materials if r['source_type']=='official_health_education']
  self.assertEqual(len(rows),2)
  for r in rows:self.assertEqual(r['original_format'],'web.txt');self.assertIs(r['conversion']['original_html_available'],False)
 def test_clinical_numeric_signs_and_null_primary_outcome_preserved(self):
  r,c=next((r,c) for r,c in self.materials if 'PMC11754701' in r['source_url']);body=c[r['document_path']].decode('utf-8')
  self.assertIn('−4.18',body);self.assertIn('0.96',body);self.assertIn('.220',body)
  self.assertIn('not statistically significant',' '.join(r['limits']))
 def test_mixed_age_and_diagnosis_scope_not_relabeled(self):
  r=next(r for r,c in self.materials if 'PMC12658592' in r['source_url'])
  self.assertIn('0–21',r['original_age_scope']);self.assertIn('mixed diagnoses',r['original_age_scope'])
 def test_reviewed_asset_hash_change_rejected(self):
  raw=(s.CACHE/'PMC6590432_oai.xml').read_bytes()
  with patch('library.digest',return_value='wrong-hash'):
   with self.assertRaises(ValueError):load_assets(digest(raw))
 def test_whole_document_not_split_or_truncated(self):
  r,c=next((r,c) for r,c in self.materials if 'PMC4513196' in r['source_url']);body=c[r['document_path']].decode('utf-8')
  self.assertGreater(len(body),90000);self.assertIn('## End matter (original)',body)
  self.assertFalse(r['embedding']['truncate']);self.assertFalse(r['embedding']['split'])
 def test_senita_original_is_full_but_conversion_is_pending(self):
  r,c=self.byid['NIHR-SENITA-2022'];self.assertFalse(r['coverage_eligible'])
  self.assertEqual(r['conversion']['pdf_pages'],172);self.assertEqual(r['rights']['license'],'CC BY 4.0')
  self.assertTrue(c[r['original_path']].startswith(b'%PDF-'));self.assertIn(b'SOURCE_PDF_PAGE 172',c[r['document_path']])
 def test_peers_actual_and_eligible_ages_differ(self):
  r,c=self.byid['ASD-SUP-PMC9399988'];self.assertIn('11–18',r['original_age_scope']);self.assertIn('11.8–16.1',r['original_age_scope'])
 def test_linked_commentary_is_not_misrepresented_as_correction(self):
  r,c=self.byid['ASD-SUP-PMC4513196'];self.assertTrue(r['coverage_eligible'])
  self.assertEqual(r['correction_check']['blocking_notices'],[]);self.assertEqual(r['correction_check']['notices'][0]['related-article-type'],'commentary')
 def test_request_rejected_html_not_a_source(self):
  from storage import validate_payload
  with self.assertRaises(ValueError):validate_payload('x.html',b'<html><title>Request Rejected</title></html>')
 def test_duplicate_doi_rejected(self):
  rows=[{'source_id':'A','source_url':'https://doi.org/10.test/paper'},{'source_id':'B','source_url':'https://doi.org/10.test/paper'}]
  with self.assertRaises(ValueError):s.choose_id(rows,'10.test/paper','https://elsewhere.example/','C')

if __name__=='__main__':unittest.main()
