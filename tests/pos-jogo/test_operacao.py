import copy,json,sys,tempfile,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from custos_pos_jogo import BudgetCaller,usage_cost,reserve_bound,D
from operar_pos_jogo import run_once
from estado_operacao_pos_jogo import RemoteState,BRANCH,PATH

class MemoryState:
 def __init__(self):
  self.data={'version':1,'timing':{'version':1,'fixtures':{}},'jobs':{'espn-1':{'status':'running','api_calls':0}},'months':{}}
  self.saved=[]
 def save(self):self.saved.append(copy.deepcopy(self.data))

class BudgetTests(unittest.TestCase):
 def setUp(self):
  self.remote=MemoryState();self.config=json.loads((ROOT/'config/operacao-pos-jogo.json').read_text())
  self.now=datetime.fromisoformat('2026-10-26T13:00:00-03:00')
  self.payload={'model':'gpt-5.6-terra','max_output_tokens':6000,'input':'Teste'}
  self.response={'model':'gpt-5.6-terra','service_tier':'default','usage':{'input_tokens':1000,'output_tokens':100,'input_tokens_details':{'cached_tokens':200,'cache_write_tokens':300}},'output':[]}
  self.sent=[]
 def transport(self,p):
  self.assertEqual(self.remote.saved[-1]['months']['2026-10']['calls'][-1]['status'],'reserved')
  self.sent.append(p);return self.response
 def caller(self):return BudgetCaller(self.remote,'espn-1',config=self.config,clock=lambda:self.now,transport=self.transport)
 def test_reserve_before_call_and_settle(self):
  self.caller()(self.payload)
  row=self.remote.data['months']['2026-10']['calls'][0]
  self.assertEqual(row['status'],'settled');self.assertEqual(D(row['charged_usd']),D('0.00299'))
 def test_timeout_keeps_reservation_and_blocks_next(self):
  self.response=None
  with self.assertRaises(AttributeError):self.caller()(self.payload)
  self.assertTrue(self.remote.data['months']['2026-10']['blocked'])
  with self.assertRaises(ValueError):self.caller()(self.payload)
  self.assertEqual(len(self.sent),1)
 def test_unknown_usage_blocks(self):
  self.response.pop('usage')
  with self.assertRaises(ValueError):self.caller()(self.payload)
  self.assertTrue(self.remote.data['months']['2026-10']['blocked'])
 def test_insufficient_budget_no_api(self):
  self.remote.data['months']['2026-10']={'calls':[{'status':'settled','charged_usd':'5'}],'blocked':False}
  with self.assertRaises(ValueError):self.caller()(self.payload)
  self.assertEqual(self.sent,[])
 def test_persistence_failure_no_api(self):
  with patch.object(self.remote,'save',side_effect=OSError('conflict')):
   with self.assertRaises(OSError):self.caller()(self.payload)
  self.assertEqual(self.sent,[])
 def test_pending_previous_month_blocks(self):
  self.remote.data['months']['2026-09']={'calls':[{'status':'reserved','charged_usd':'5.3'}]}
  with self.assertRaises(ValueError):self.caller()(self.payload)
  self.assertEqual(self.sent,[])
 def test_price_expired_no_api(self):
  self.now=datetime.fromisoformat('2026-12-01T00:00:00-03:00')
  with self.assertRaises(ValueError):self.caller()(self.payload)
  self.assertEqual(self.sent,[])
 def test_month_uses_brasilia(self):
  self.now=datetime.fromisoformat('2026-11-01T02:00:00+00:00');self.caller()(self.payload)
  self.assertIn('2026-10',self.remote.data['months'])
 def test_long_context_and_search(self):
  self.response['usage']={'input_tokens':300000,'output_tokens':1000}
  self.response['output']=[{'type':'web_search_call'}]
  self.assertEqual(usage_cost(self.response,self.config),D('1.228'))
 def test_ten_call_limit(self):
  self.remote.data['jobs']['espn-1']['api_calls']=10
  with self.assertRaises(ValueError):self.caller()(self.payload)
  self.assertEqual(self.sent,[])
 def test_unknown_model_or_unbounded_tools_block(self):
  for payload in [dict(self.payload,model='other'),dict(self.payload,tools=[{'type':'web_search'}])]:
   with self.assertRaises(ValueError):self.caller()(payload)
  self.assertEqual(self.sent,[])
 def test_new_runner_keeps_settled_usage(self):
  self.caller()(self.payload)
  restored=MemoryState();restored.data=copy.deepcopy(self.remote.saved[-1])
  BudgetCaller(restored,'espn-1',config=self.config,clock=lambda:self.now,transport=lambda p:self.response)(self.payload)
  self.assertEqual(len(restored.data['months']['2026-10']['calls']),2)

class OperationalTests(unittest.TestCase):
 def test_remote_save_targets_only_state_branch_with_sha(self):
  r=object.__new__(RemoteState);r.sha='old';r.data={'example':True}
  calls=[]
  r.request=lambda method,path,body:(calls.append((method,path,body)) or {'content':{'sha':'new'}})
  r.save();self.assertEqual(calls[0][:2],('PUT','/contents/estado.json'))
  self.assertEqual(calls[0][2]['branch'],'estado-pos-jogo-piloto');self.assertEqual(calls[0][2]['sha'],'old');self.assertEqual(r.sha,'new')
 def test_restores_timing_and_skips_previous_attempts(self):
  (ROOT/'build/pos-jogo').mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=ROOT/'build/pos-jogo') as tmp:
   site=Path(tmp)/'site';site.mkdir();(site/'noticias.json').write_text('[]')
   remote=MemoryState();remote.data['jobs']['espn-1']['status']='blocked'
   seen=[]
   def runner(day,news,out,**kw):
    seen.append(kw['processed']);self.assertIn('espn-1',kw['processed'])
    self.assertEqual(json.loads(kw['timing_state'].read_text()),remote.data['timing'])
    return {'status':'no_eligible_matches','results':[]}
   run_once(remote,site,Path(tmp)/'out',clock=lambda:datetime.fromisoformat('2026-10-26T14:00:00-03:00'),runner=runner)
   self.assertEqual(len(seen),2);self.assertTrue(remote.saved)
