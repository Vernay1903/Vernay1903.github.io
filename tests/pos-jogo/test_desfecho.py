import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from preparar_fatos_pos_jogo import match_outcome,match_goals,build
from apurar_pos_jogo import candidate_proposal
import test_fatos

class OutcomeTest(unittest.TestCase):
 def setUp(self):
  self.comp={'status':{'type':{'completed':True,'name':'STATUS_FINAL_PEN'}},'competitors':[
   {'homeAway':'home','team':{'id':'1'},'score':'0','shootoutScore':5.0,'winner':True},
   {'homeAway':'away','team':{'id':'2'},'score':'0','shootoutScore':3.0,'winner':False}], 'details':[]}
 def test_separate_shootout(self):
  o=match_outcome(self.comp);self.assertEqual(o['match_score'],{'home':0,'away':0});self.assertEqual(o['shootout_score'],{'home':5,'away':3})
 def test_missing_shootout(self):
  del self.comp['competitors'][0]['shootoutScore']
  with self.assertRaises(ValueError):match_outcome(self.comp)
 def test_tied_shootout(self):
  self.comp['competitors'][1]['shootoutScore']=5
  with self.assertRaises(ValueError):match_outcome(self.comp)
 def test_conflicting_winner(self):
  self.comp['competitors'][1]['winner']=True
  with self.assertRaises(ValueError):match_outcome(self.comp)
 def test_unfinished(self):
  self.comp['status']['type']['completed']=False
  with self.assertRaises(ValueError):match_outcome(self.comp)
 def test_fractional_shootout(self):
  self.comp['competitors'][0]['shootoutScore']=5.2
  with self.assertRaises(ValueError):match_outcome(self.comp)
 def test_explicit_shootout_not_goal(self):
  self.comp['details']=[{'scoringPlay':True,'shootout':True}]
  self.assertEqual(match_goals(self.comp),[])
 def test_period_shootout_not_goal(self):
  self.comp['details']=[{'scoringPlay':True,'period':{'number':5}}]
  self.assertEqual(match_goals(self.comp),[])
 def test_ambiguous_scoring_blocked(self):
  self.comp['details']=[{'scoringPlay':True,'team':{'id':'1'},'participants':[{'athlete':{'displayName':'Jogador'}}]}]
  with self.assertRaises(ValueError):match_goals(self.comp)
 def test_in_game_penalty_counts(self):
  self.comp['competitors'][0]['score']='1'
  self.comp['details']=[{'scoringPlay':True,'penaltyKick':True,'team':{'id':'1'},'participants':[{'athlete':{'displayName':'Jogador'}}]}]
  self.assertEqual(len(match_goals(self.comp)),1)
 def test_extra_time_without_inferred_split(self):
  self.comp['status']['type']['name']='STATUS_FINAL_AET'
  for t in self.comp['competitors']:del t['shootoutScore']
  o=match_outcome(self.comp);self.assertEqual(o['decided_by'],'extra_time');self.assertNotIn('regulation_score',o)
 def test_inconsistent_status(self):
  self.comp['status']['type']['name']='STATUS_FULL_TIME'
  with self.assertRaises(ValueError):match_outcome(self.comp)
 def test_cup_without_campaign(self):
  f=test_fatos.FactsTest();f.setUp();f.s.pop('standings',None);f.r['campaign']={}
  self.assertEqual(f.run_build()['campaign'],{})
  proposal,core,_,_=candidate_proposal(f.c,f.s);self.assertEqual(core['campaign'],{})
 def test_extra_time_requires_external_review(self):
  f=test_fatos.FactsTest();f.setUp();c=f.s['header']['competitions'][0];c['status']['type']['name']='STATUS_FINAL_AET'
  with self.assertRaises(ValueError):f.run_build()
  f.r['outcome']=match_outcome(c)
  self.assertEqual(f.run_build()['outcome']['decided_by'],'extra_time')
 def test_actual_provider_snapshot(self):
  d=json.loads((ROOT/'tests/pos-jogo/fixtures/penalties-provider-header.json').read_text());c=d['competitions'][0]
  o=match_outcome(c);self.assertEqual(o['match_score'],{'home':1,'away':1});self.assertEqual(o['shootout_score'],{'home':5,'away':3})
  self.assertEqual(len(match_goals(c)),2)

if __name__=='__main__':unittest.main()
