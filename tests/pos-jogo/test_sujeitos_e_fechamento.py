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
