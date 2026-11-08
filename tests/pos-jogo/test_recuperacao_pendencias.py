import contextlib,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import publicar_pos_jogo as publication
from operar_pos_jogo import eligible_source_retry,TZ
from conferir_sujeitos_pos_jogo import audit_request,actor_passages

class PendingRecoveryTests(unittest.TestCase):
 def test_pending_commit_is_confirmed_even_without_timing_fixture(self):
  class Remote:
   def __init__(self):
    self.data={'jobs':{'espn-1':{'status':'publication_pending','publication':{'commit':'already-written','url':'article.html'}}},'timing':{'fixtures':{}}}
   def save(self):pass
  remote=Remote()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'config').mkdir()
   (root/'config/publicacao-pos-jogo.json').write_text(json.dumps({'enabled':True,'from_match_date':'2026-11-06'}))
   with patch.object(publication,'ROOT',root),patch.object(publication,'RemoteState',return_value=remote),patch.object(publication,'confirm') as confirm,patch.object(publication,'publish_atomic') as publish,contextlib.redirect_stdout(io.StringIO()):
    publication.main()
   confirm.assert_called_once();publish.assert_not_called()
   self.assertEqual(remote.data['jobs']['espn-1']['status'],'published')

 def test_incomplete_retry_is_single_and_keeps_cost_guard(self):
  now=datetime(2026,11,8,14,tzinfo=TZ)
  j={'fixture_id':'espn-1','status':'blocked','operation_mode':'scheduled_drafts','reason':'Apuração incompleta na API','run_id':'123','api_calls':3,'finished_at':(now-timedelta(hours=3)).isoformat()}
  cfg={'max_paid_calls_per_fixture':12,'per_article_cap_usd':'0.10','monthly_pilot_cap_usd':'10'}
  m={'2026-11':{'calls':[{'fixture_id':'espn-1','status':'settled','charged_usd':'0.0315'}]}}
  self.assertTrue(eligible_source_retry(j,m,now,cfg))
  self.assertFalse(eligible_source_retry(dict(j,incomplete_retry=True),m,now,cfg))
  m['2026-11']['calls'][0]['charged_usd']='0.09'
  self.assertFalse(eligible_source_retry(j,m,now,cfg))

 def test_compact_audit_preserves_every_original_passage(self):
  pages={'p':{'url':'https://example.org','text':'Fonte original. '*1000,'opened':True}}
  request=audit_request({'model':'test','reasoning_effort':'medium'},{'claim_0':'Fato'},{'claims':[]},pages)
  data=json.loads(request['input'][1]['content'])
  self.assertEqual(data['passages'],actor_passages(pages))
  self.assertNotIn('text',data['pages']['p'])
  self.assertNotIn('extraction',data)
  self.assertEqual(request['max_output_tokens'],10000)
