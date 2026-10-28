import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from validar_passo16_pos_jogo import evaluate
class AcceptanceTests(unittest.TestCase):
 def setUp(self):
  self.row={'fixture_id':'espn-1','status':'package_ready','package':{},'timing':{'eligible':True,'wait_minutes':50,'basis':'first_observed_final','first_final_seen_at':'2026-10-27T23:30:00-03:00','eligible_at':'2026-10-28T00:20:00-03:00'}}
  self.report={'run_id':'7','publication_enabled':False,'mode':'scheduled_drafts','status':'draft_ready','started_at':'2026-10-28T00:20:00-03:00','finished_at':'2026-10-28T00:23:00-03:00','results':[{'target_date':'2026-10-27','results':[self.row]}]}
  self.job={'run_id':'7','status':'package_ready','operation_mode':'scheduled_drafts','api_calls':1,'started_at':'2026-10-28T00:21:00-03:00','finished_at':'2026-10-28T00:22:00-03:00'}
  self.call={'fixture_id':'espn-1','started_at':'2026-10-28T00:21:20-03:00','status':'settled','charged_usd':'0.03'}
  self.state={'jobs':{'espn-1':self.job},'months':{'2026-10':{'calls':[self.call]}}};self.inspections=0
 def inspect(self,*args):self.inspections+=1;return {'checked':True}
 def evaluate(self,event='schedule'):return evaluate(self.report,self.state,event,'7',self.inspect)
 def test_autonomous_cross_midnight_accepted(self):
  self.assertEqual(self.evaluate()['status'],'approved');self.assertEqual(self.inspections,1)
 def test_manual_trigger_not_accepted(self):
  self.assertEqual(self.evaluate('workflow_dispatch')['status'],'waiting_for_schedule');self.assertEqual(self.inspections,0)
 def test_no_new_draft_waits(self):
  self.row['status']='already_attempted';self.assertEqual(self.evaluate()['status'],'waiting_for_scheduled_draft')
 def test_assisted_job_rejected(self):
  self.job['continuation_run_id']='8'
  with self.assertRaises(ValueError):self.evaluate()
 def test_budget_over_cap_rejected(self):
  self.call['charged_usd']='0.10001'
  with self.assertRaises(ValueError):self.evaluate()
 def test_uncertain_call_rejected(self):
  self.call['status']='reserved'
  with self.assertRaises(ValueError):self.evaluate()
 def test_previous_call_rejected(self):
  self.call['started_at']='2026-10-27T23:00:00-03:00'
  with self.assertRaises(ValueError):self.evaluate()
 def test_early_start_rejected(self):
  self.job['started_at']='2026-10-28T00:19:59-03:00'
  with self.assertRaises(ValueError):self.evaluate()
 def test_different_run_rejected(self):
  self.job['run_id']='6'
  with self.assertRaises(ValueError):self.evaluate()
 def test_failed_cycle_not_accepted(self):
  self.report['status']='needs_review';self.assertEqual(self.evaluate()['status'],'blocked')
 def test_package_reconstruction_failure_rejected(self):
  def bad(*args):raise ValueError('Pacote alterado')
  self.inspect=bad
  with self.assertRaises(ValueError):self.evaluate()
