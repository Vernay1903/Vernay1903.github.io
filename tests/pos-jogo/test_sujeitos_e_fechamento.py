import sys,unittest,copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from conferir_sujeitos_pos_jogo import validate_actor_audit
from editorial_pos_jogo import validate
class ActorTests(unittest.TestCase):
 def fixture(self):
  items={'claim_0':'A cruzou para B.'}
  pages={'p':{'opened':True,'text':'A passed to B, whose cross found nobody.'}}
  row={'id':'claim_0','supported':True,'reason':'','actor_checks':[{'action':'cruzar','claimed_actor':'A','source_actor':'B','passage_id':'p:0','matches':True}]}
  return items,pages,{'checks':[row]}
 def test_subject_mismatch_overrides_approval(self):
  i,p,a=self.fixture();out=validate_actor_audit(a,i,p)
  self.assertFalse(out['checks'][0]['supported']);self.assertTrue(a['checks'][0]['supported'])
 def test_correct_actor_and_exact_quote_accepted(self):
  i,p,a=self.fixture();i['claim_0']='B cruzou.';a['checks'][0]['actor_checks'][0]['claimed_actor']='B'
  self.assertTrue(validate_actor_audit(a,i,p)['checks'][0]['supported'])
 def test_invented_quote_rejected(self):
  i,p,a=self.fixture();a['checks'][0]['actor_checks'][0].update(claimed_actor='B',passage_id='invented:0')
  self.assertFalse(validate_actor_audit(a,i,p)['checks'][0]['supported'])
 def test_short_name_matches_full_name(self):
  i,p,a=self.fixture();a['checks'][0]['actor_checks'][0].update(claimed_actor='Cherki',source_actor='Rayan Cherki')
  self.assertTrue(validate_actor_audit(a,i,p)['checks'][0]['supported'])
 def test_missing_action_checks_rejected(self):
  i,p,a=self.fixture();a['checks'][0]['actor_checks']=[]
  self.assertFalse(validate_actor_audit(a,i,p)['checks'][0]['supported'])
class ClosingTests(unittest.TestCase):
 def article(self):
  return {'title':'Resultado','excerpt':'Resumo', 'blocks':[{'type':'subtitle','text':'Primeiro tempo'}, {'type':'paragraph','text':'palavra '*600}, {'type':'subtitle','text':'Próximos jogos'}, {'type':'paragraph','text':'O clube enfrenta o adversário no sábado.'}]}
 def test_next_game_is_valid_closure(self):self.assertTrue(validate(self.article(),[])['format_passed'])
 def test_substitutions_after_upcoming_blocked(self):
  a=self.article();a['blocks'].append({'type':'paragraph','text':'O jogador entrou no lugar do atacante.'})
  self.assertTrue(any(e.startswith('Organização:') for e in validate(a,[])['errors']))
 def test_substitution_before_upcoming_allowed(self):
  a=self.article();a['blocks'].insert(2,{'type':'paragraph','text':'O jogador entrou no lugar do atacante.'})
  self.assertTrue(validate(a,[])['format_passed'])
if __name__=='__main__':unittest.main()

class CoverageTests(unittest.TestCase):
 def test_missing_goal_blocked_and_accent_variants_allowed(self):
  from editorial_pos_jogo import coverage_errors
  package={'facts':{'goals':[{'scorer':'Mateo Kovačić'}]}}
  article={'blocks':[{'type':'paragraph','text':'Vitor Reis empatou.'}]}
  self.assertTrue(coverage_errors(article,package))
  article['blocks'][0]['text']='Kovacic empatou.'
  self.assertEqual(coverage_errors(article,package),[])
 def test_title_only_does_not_cover_goal(self):
  from editorial_pos_jogo import coverage_errors
  self.assertTrue(coverage_errors({'title':'Kovacic marca','blocks':[]},{'facts':{'goals':[{'scorer':'Kovacic'}]}}))
 def test_hosting_team_does_not_require_personal_actor(self):
  from conferir_sujeitos_pos_jogo import validate_actor_audit
  audit={'checks':[{'id':'claim_0','supported':True,'reason':'','actor_checks':[]}]}
  self.assertTrue(validate_actor_audit(audit,{'claim_0':'O clube recebeu o adversário na semifinal.'},{})['checks'][0]['supported'])

class RecoveryTests(unittest.TestCase):
 def test_repaired_claim_is_not_promoted_when_second_review_rejects(self):
  from apurar_pos_jogo import recover_rejected_claims,approved_claims
  core={'score':{'home':1,'away':0}}
  claims=[{'text':str(i),'evidence':[{'source_id':'p','quote':'Fonte literal.'}]} for i in range(7)]
  result={'checks':[],'claims':claims}
  audit={'checks':[{'id':'score','supported':True}]+[{'id':f'claim_{i}','supported':i!=6,'reason':'incerto'} for i in range(7)]}
  pages={'p':{'text':'Fonte literal.','opened':True}}
  calls=[]
  def call(payload,stage):
   calls.append(stage)
   value={'claims':[{'text':'Detalhe recuperado','evidence':[{'passage_id':'p:0'}]}]} if stage=='recover' else {'checks':[{'id':'claim_7','supported':False,'reason':'Sem suporte','actor_checks':[]}]}
   return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
  out,review=recover_rejected_claims({'model':'test','reasoning_effort':'medium'},core,result,pages,audit,call,lambda *args:None)
  kept,omitted=approved_claims(core,out['claims'],review)
  self.assertEqual(len(kept),6);self.assertEqual(len(omitted),2)
  self.assertEqual(calls,['recover','recover_verify']);self.assertEqual(len(result['claims']),7)
 def test_core_rejection_cannot_trigger_paid_recovery(self):
  from apurar_pos_jogo import recover_rejected_claims
  with self.assertRaises(ValueError):
   recover_rejected_claims({}, {'score':{}},{'claims':[]},{},{'checks':[{'id':'score','supported':False}]},lambda *args:self.fail('Called API'),lambda *args:None)
