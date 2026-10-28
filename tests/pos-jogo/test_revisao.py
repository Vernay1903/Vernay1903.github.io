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
 def test_patch_budget_excludes_title_and_unchanged_blocks(self):
  import json
  from revisar_pos_jogo import patch_request
  p={'facts':{},'narrative_facts':[],'instructions':''}
  a={'title':'Titulo longo aqui','excerpt':'Chamada aqui','blocks':[{'type':'paragraph','text':'palavra '*500},{'type':'paragraph','text':'erro '*90}]}
  request=patch_request(p,a,['block_1: corrigir'],{'model':'test','reasoning_effort':'medium'})
  data=json.loads(request['input'][1]['content'])
  self.assertEqual(data['word_budget']['unchanged_body_words'],500)
  self.assertEqual(data['word_budget']['minimum_words_in_replaced_body_units'],100)
  self.assertEqual(data['word_budget']['preferred_words_in_replaced_body_units'],180)

class ReviewSchemaTests(unittest.TestCase):
 def test_references_are_restricted_to_supplied_evidence(self):
  from revisar_pos_jogo import review_request
  p={'facts':{'score':{}},'narrative_facts':['Fato']}
  a={'title':'T','excerpt':'C','blocks':[]}
  r=review_request(p,a,{'model':'test','reasoning_effort':'medium'})
  refs=r['text']['format']['schema']['properties']['checks']['items']['properties']['evidence_ids']['items']['enum']
  self.assertEqual(refs,['score','narrative_0'])

class DeletionTests(unittest.TestCase):
 def test_deletes_only_rejected_blocks_without_index_shift(self):
  from revisar_pos_jogo import apply_patch
  a={'title':'T','excerpt':'E','blocks':[{'type':'paragraph','text':str(i)} for i in range(4)]}
  b=apply_patch(a,{'replacements':[{'unit':'block_1','text':'','delete':True},{'unit':'block_3','text':'Novo','delete':False}]},['block_1: repetição','block_3: erro'])
  self.assertEqual([x['text'] for x in b['blocks']],['0','2','Novo'])
  self.assertEqual(len(a['blocks']),4)
 def test_empty_replacement_is_not_silent_deletion(self):
  from revisar_pos_jogo import apply_patch
  a={'title':'T','excerpt':'E','blocks':[{'text':'Texto'}]}
  for change in [{'unit':'block_0','text':'','delete':False},{'unit':'title','text':'','delete':True}]:
   with self.assertRaises(ValueError):apply_patch(a,{'replacements':[change]},[change['unit']+': erro'])

class IncrementalReviewTests(unittest.TestCase):
 def setup_case(self):
  self.package={'facts':{'fixture_id':'x','match':{}},'narrative_facts':[]}
  self.before={'title':'Título','excerpt':'Chamada','blocks':[{'type':'paragraph','text':'Fato certo. Interpretação.'},{'type':'paragraph','text':'Outro fato certo.'}]}
  self.after=__import__('copy').deepcopy(self.before);self.after['blocks'][0]['text']='Fato certo.'
  from revisar_pos_jogo import units
  self.previous={'checks':[{'unit':u,'supported':u!='block_0','evidence_ids':['match'],'issues':['Retirar interpretação'] if u=='block_0' else []} for u in units(self.before)]}
  self.provider={'model':'gpt-6-luna','reasoning_effort':'medium'}
 def test_context_is_complete_and_unchanged_approvals_are_preserved(self):
  import json
  from revisar_pos_jogo import review_changed,validate_review
  self.setup_case();seen=[]
  def caller(payload):
   data=json.loads(payload['input'][-1]['content']);seen.append(data)
   result={'checks':[{'unit':'block_0','supported':True,'evidence_ids':['match'],'issues':[]}]}
   return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(result)}]}]}
  result=review_changed(self.package,self.before,self.previous,self.after,self.provider,caller,self.package)
  self.assertEqual(set(seen[0]['units']),{'block_0'})
  self.assertEqual(seen[0]['whole_article_context']['block_1'],'Outro fato certo.')
  self.assertEqual(validate_review(result,self.package,self.after),[])
  self.assertIn('block_1',result['provenance']['unchanged_approved_units'])
 def test_changed_evidence_blocks_reuse_without_api(self):
  import copy
  from revisar_pos_jogo import review_changed
  self.setup_case();new=copy.deepcopy(self.package);new['facts']['match']={'score':'alterado'}
  with self.assertRaisesRegex(ValueError,'revisão integral'):
   review_changed(new,self.before,self.previous,self.after,self.provider,lambda p:self.fail('API não deveria ser chamada'),self.package)
 def test_unfixed_rejection_blocks_without_api(self):
  from revisar_pos_jogo import review_changed
  self.setup_case()
  with self.assertRaisesRegex(ValueError,'não foi corrigido'):
   review_changed(self.package,self.before,self.previous,self.before,self.provider,lambda p:self.fail('API indevida'),self.package)
 def test_missing_partial_checks_cannot_release_article(self):
  import json
  from revisar_pos_jogo import review_changed
  self.setup_case()
  def caller(p):return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'checks':[]})}]}]}
  with self.assertRaisesRegex(ValueError,'incompleta'):
   review_changed(self.package,self.before,self.previous,self.after,self.provider,caller,self.package)
