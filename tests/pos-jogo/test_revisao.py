import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from revisar_pos_jogo import validate_review
class ReviewTests(unittest.TestCase):
 def setUp(self):
  self.p={'facts':{'score':{'home':4,'away':1}},'narrative_facts':[]}
  self.a={'title':'A','excerpt':'B','blocks':[{'text':'C'}]}
  self.checks=[{'unit':u,'supported':True,'evidence_ids':['score'],'issues':[]} for u in ['title','excerpt','block_0']]
 def test_complete_review_passes(self):self.assertEqual(validate_review({'checks':self.checks},self.p,self.a),[])
 def test_missing_unit_blocks(self):
  with self.assertRaises(ValueError):validate_review({'checks':self.checks[:-1]},self.p,self.a)
 def test_invented_evidence_blocks(self):
  self.checks[0]['evidence_ids']=['not_found']
  with self.assertRaises(ValueError):validate_review({'checks':self.checks},self.p,self.a)
 def test_contradictory_approval_blocks(self):
  self.checks[0]['issues']=['Erro']
  with self.assertRaises(ValueError):validate_review({'checks':self.checks},self.p,self.a)
 def test_rejection_reaches_writer(self):
  self.checks[2].update(supported=False,issues=['Mando invertido'])
  self.assertEqual(validate_review({'checks':self.checks},self.p,self.a),['block_0: Mando invertido'])

class PatchTests(unittest.TestCase):
 def test_preserves_approved_units(self):
  from revisar_pos_jogo import apply_patch
  a={'title':'Título','excerpt':'Chamada','blocks':[{'type':'paragraph','text':'Correto'},{'type':'paragraph','text':'Erro'}]}
  b=apply_patch(a,{'replacements':[{'unit':'block_1','text':'Corrigido'}]},['block_1: erro factual'])
  self.assertEqual(b['blocks'][0],a['blocks'][0]);self.assertEqual(b['title'],a['title'])
  self.assertEqual(a['blocks'][1]['text'],'Erro')
 def test_unrequested_edit_blocks(self):
  from revisar_pos_jogo import apply_patch
  a={'title':'Título','excerpt':'Chamada','blocks':[]}
  with self.assertRaises(ValueError):apply_patch(a,{'replacements':[{'unit':'title','text':'Outro'}]},['excerpt: erro'])
