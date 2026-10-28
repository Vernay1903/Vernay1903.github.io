import copy,json,sys,tempfile,unittest
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from agendar_pos_jogo import scheduled_cycle,validate_configuration,budget_status
class Remote:
 def __init__(self):
  self.data={'version':1,'timing':{'version':1,'fixtures':{}},'jobs':{'old':{'status':'blocked','api_calls':3}},'months':{'2026-10':{'blocked':False,'calls':[{'status':'settled','charged_usd':'0.45'}]}}};self.saves=[]
 def save(self):self.saves.append(copy.deepcopy(self.data))
class ScheduleTests(unittest.TestCase):
 def setUp(self):
  self.cfg=json.loads((ROOT/'config/operacao-pos-jogo.json').read_text());self.scope=json.loads((ROOT/'config/pos-jogo-piloto.json').read_text());self.timing={'wait_minutes':50}
  self.now=datetime.fromisoformat('2026-10-27T23:58:00-03:00');self.remote=Remote();self.calls=[]
  (ROOT/'build/pos-jogo').mkdir(parents=True,exist_ok=True);self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'build/pos-jogo');self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def worker(self,remote,site,out,**kw):
  self.calls.append(kw);self.assertEqual(remote.data['jobs']['old'],{'status':'blocked','api_calls':3})
  return [{'status':'no_eligible_matches','results':[]}]
 def cycle(self):return scheduled_cycle(self.remote,self.root,self.root/'cycle',cfg=self.cfg,scope=self.scope,timing=self.timing,clock=lambda:self.now,worker=self.worker)
 def test_first_cycle_enables_only_drafts_and_preserves_history(self):
  report=self.cycle();self.assertEqual(report['status'],'idle');self.assertEqual(report['pilot_month_charged_usd'],'0.45')
  self.assertEqual(self.calls[0]['operation_mode'],'scheduled_drafts');self.assertTrue(self.remote.data['operation']['enabled']);self.assertFalse(self.remote.data['operation']['publication_enabled'])
  self.assertEqual(json.loads((self.root/'cycle/ciclo.json').read_text())['status'],'idle')
 def test_remote_pause_is_not_undone_by_cron(self):
  self.remote.data['operation']={'enabled':False,'mode':'scheduled_drafts','publication_enabled':False}
  self.assertEqual(self.cycle()['status'],'disabled');self.assertEqual(self.calls,[]);self.assertFalse(self.remote.data['operation']['enabled'])
 def test_uncertain_cost_blocks_worker_and_keeps_history(self):
  self.remote.data['months']['2026-10']['calls'].append({'status':'reserved','charged_usd':'0.1'})
  report=self.cycle();self.assertEqual(report['reason'],'uncertain_previous_spend');self.assertEqual(self.calls,[])
 def test_month_cap_blocks_worker(self):
  self.remote.data['months']['2026-10']['calls'][0]['charged_usd']='10'
  self.assertEqual(self.cycle()['reason'],'monthly_cap_reached');self.assertEqual(self.calls,[])
 def test_expired_prices_block_worker(self):
  self.now=datetime.fromisoformat('2026-11-26T00:00:00-03:00')
  self.assertEqual(self.cycle()['reason'],'pricing_expired');self.assertEqual(self.calls,[])
 def test_new_month_does_not_clear_old_costs(self):
  self.now=datetime.fromisoformat('2026-11-01T00:01:00-03:00')
  self.assertEqual(self.cycle()['pilot_month_charged_usd'],'0');self.assertEqual(self.remote.data['months']['2026-10']['calls'][0]['charged_usd'],'0.45')
 def test_scope_expansion_or_publication_blocked_before_state_change(self):
  for mutation in ('scope','publication','disabled','cap'):
   cfg=copy.deepcopy(self.cfg);scope=copy.deepcopy(self.scope)
   if mutation=='scope':scope['monitored_clubs'].append('Barcelona')
   if mutation=='publication':cfg['publication_enabled']=True
   if mutation=='disabled':cfg['schedule_enabled']=False
   if mutation=='cap':cfg['per_article_cap_usd']='0.11'
   with self.assertRaises(ValueError):validate_configuration(cfg,scope,self.timing)
 def test_waiting_is_not_a_failed_run(self):
  self.worker=lambda *a,**k:[{'status':'waiting','results':[{'fixture_id':'new','status':'waiting_after_final'}]}]
  self.assertEqual(self.cycle()['status'],'waiting')
 def test_draft_is_exported_without_publishing(self):
  self.worker=lambda *a,**k:[{'status':'completed','results':[{'fixture_id':'new','status':'package_ready'}]}]
  r=self.cycle();self.assertEqual(r['status'],'draft_ready');self.assertTrue(r['has_drafts']);self.assertFalse(r['publication_enabled'])
 def test_unexpected_failure_is_recorded_and_raised(self):
  def fail(*a,**k):raise OSError('indisponível')
  self.worker=fail
  with self.assertRaises(OSError):self.cycle()
  self.assertEqual(self.remote.data['operation']['last_status'],'error')
  self.assertEqual(json.loads((self.root/'cycle/ciclo.json').read_text())['status'],'error')
