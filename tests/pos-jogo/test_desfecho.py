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

class OutcomeEditorialTest(unittest.TestCase):
 def test_penalty_outcome_reaches_writer(self):
  from editorial_pos_jogo import prepare
  f=test_fatos.FactsTest();f.setUp();c=f.s['header']['competitions'][0]
  c['status']['type']['name']='STATUS_FINAL_PEN'
  for t in c['competitors']:
   t['shootoutScore']=5 if t['homeAway']=='home' else 3
   t['winner']=t['homeAway']=='home'
  f.r['outcome']=match_outcome(c)
  facts=f.run_build()
  narrative={'fixture_id':f.c['fixture_id'],'reviewed':True,'sources':[{'id':'test','opened':True}],
             'claims':[{'text':'Synthetic test only','source_ids':['test']}]}
  package=prepare(facts,narrative,[])
  self.assertEqual(package['facts']['outcome']['shootout_score'],{'home':5,'away':3})
  self.assertEqual(package['facts']['score'],f.c['score'])
  self.assertFalse(package['publication_enabled'])

class CupFutureTest(unittest.TestCase):
 def test_missing_next_in_competition_is_optional(self):
  f=test_fatos.FactsTest();f.setUp()
  for data in f.cal.values():
   for e in data['events']:e['league']['slug']='other.league'
  out=f.run_build();self.assertTrue(out['ready_for_drafting'])
  self.assertIsNone(out['upcoming']['home']['next_in_competition'])
  self.assertIn('home.next_in_competition',out['gaps'])

class RetryTest(unittest.TestCase):
 def state(self):
  from types import SimpleNamespace
  return SimpleNamespace(data={'jobs':{'espn-401921835':{'status':'blocked','run_id':'40643743077','api_calls':0}},'months':{'2026-10':{'calls':[]}}},save=lambda:None)
 def test_once_and_history(self):
  from testar_passo15_pos_jogo import authorize_retry
  r=self.state();authorize_retry(r)
  self.assertEqual(r.data['step15_retry']['original_job']['run_id'],'40643743077')
  with self.assertRaises(ValueError):authorize_retry(r)
 def test_paid_call_prevents_retry(self):
  from testar_passo15_pos_jogo import authorize_retry
  r=self.state();r.data['months']['2026-10']['calls']=[{'fixture_id':'espn-401921835','charged_usd':'0.01'}]
  with self.assertRaises(ValueError):authorize_retry(r)
 def test_different_job_prevents_retry(self):
  from testar_passo15_pos_jogo import authorize_retry
  r=self.state();r.data['jobs']['espn-401921835']['run_id']='other'
  with self.assertRaises(ValueError):authorize_retry(r)

class PenaltyTimingTest(unittest.TestCase):
 def test_changed_shootout_restarts_wait(self):
  from tempo_pos_jogo import observe
  from datetime import datetime,timedelta
  h=json.loads((ROOT/'tests/pos-jogo/fixtures/penalties-provider-header.json').read_text())
  c={'fixture_id':'espn-'+h['id'],'kickoff':h['competitions'][0]['date'],'score':{'home':1,'away':1}}
  state={'fixtures':{}};now=datetime.fromisoformat('2026-10-27T23:40:00-03:00')
  first=observe(c,{'header':h},state,now)
  self.assertEqual(first['eligible_at'],'2026-10-28T00:30:00-03:00')
  h['competitions'][0]['competitors'][0]['shootoutScore']=4
  changed=observe(c,{'header':h},state,now+timedelta(minutes=40))
  self.assertFalse(changed['eligible']);self.assertEqual(changed['eligible_at'],'2026-10-28T01:10:00-03:00')

if __name__=='__main__':unittest.main()
