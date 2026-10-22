import copy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.editorial_pos_jogo import validate,prepare
class EditorialTest(unittest.TestCase):
 def setUp(self):
  p=ROOT/'auditoria/pos-jogo'
  self.a=json.loads((p/'amostra-editorial-real-leipzig.json').read_text())
  self.links=json.loads((p/'links-autorizados-piloto.json').read_text())
 def test_sample(self):self.assertTrue(validate(self.a,self.links)['format_passed'])
 def test_title_boundary(self):
  self.a['title']='A'*70; self.assertTrue(validate(self.a,self.links)['format_passed'])
  self.a['title']='A'*71; self.assertFalse(validate(self.a,self.links)['format_passed'])
 def test_spaces_count(self):
  self.a['title']='A '*35+'B';self.assertEqual(validate(self.a,self.links)['title_chars'],71)
 def test_unicode(self):
  self.a['title']='e\u0301'*70;self.assertEqual(validate(self.a,self.links)['title_chars'],70)
 def test_short_body(self):
  self.a['blocks']=self.a['blocks'][:2];self.assertFalse(validate(self.a,self.links)['format_passed'])
 def test_unapproved_url(self):self.assertFalse(validate(self.a,[])['format_passed'])
 def test_html_and_markdown(self):
  for text in ['<p>texto</p>','## título','**negrito**','<!-- nota -->']:
   a=copy.deepcopy(self.a);a['blocks'][0]['text']=text;self.assertFalse(validate(a,self.links)['format_passed'])
 def test_source_gate(self):
  f={'ready_for_drafting':True,'fixture_id':'a'}
  n={'fixture_id':'a','reviewed':True,'sources':[{'id':'x','opened':False}],'claims':[{'text':'x','source_ids':['x']}]}
  with self.assertRaises(ValueError):prepare(f,n,[])
if __name__=='__main__':unittest.main()
