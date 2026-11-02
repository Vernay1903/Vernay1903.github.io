import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from operar_pos_jogo import eligible_source_retry,validate_generated_package,run_once
from montar_html_pos_jogo import render_html


class FakeRemote:
 def __init__(self):
  self.data={'timing':{'version':1,'fixtures':{}},'jobs':{},'months':{}}
  self.snapshots=[]
 def save(self):
  self.snapshots.append(copy.deepcopy(self.data))


class Step21Tests(unittest.TestCase):
 def setUp(self):
  self.config=json.loads((ROOT/'config/operacao-pos-jogo.json').read_text())
  self.now=datetime.fromisoformat('2026-11-02T16:00:00-03:00')
  self.job={'status':'blocked','operation_mode':'scheduled_drafts',
            'reason':'Nenhum relato oficial efetivamente aberto',
            'finished_at':'2026-11-02T12:00:00-03:00','api_calls':2,
            'fixture_id':'espn-123'}
  self.months={'2026-11':{'blocked':False,'calls':[{'fixture_id':'espn-123',
                  'status':'settled','charged_usd':'0.015'}]}}
 def test_only_bounded_fresh_source_retry(self):
  self.assertTrue(eligible_source_retry(self.job,self.months,self.now,self.config))
  for update in [
   {'source_retry_count':1},
   {'status':'package_ready'},
   {'reason':'Revisão factual/editorial reprovada após limite de correções'},
   {'operation_mode':'authorized_step15_validation'},
   {'api_calls':12},
   {'finished_at':'2026-11-02T15:00:00-03:00'}
  ]:
   job=dict(self.job,**update)
   self.assertFalse(eligible_source_retry(job,self.months,self.now,self.config),update)
 def test_uncertain_or_costly_retry_never_allowed(self):
  for charge in ('0.025','0.099'):
   months={'2026-11':{'blocked':False,'calls':[{'fixture_id':'espn-123','status':'settled','charged_usd':charge}]}}
   self.assertFalse(eligible_source_retry(self.job,months,self.now,self.config))
  m=copy.deepcopy(self.months);m['2026-11']['calls'][0]['status']='reserved'
  self.assertFalse(eligible_source_retry(self.job,m,self.now,self.config))
 def test_no_retry_if_job_has_no_reason(self):
  job=dict(self.job);job.pop('reason')
  self.assertFalse(eligible_source_retry(job,self.months,self.now,self.config))
 def test_recovery_preserves_spend_and_marks_single_retry(self):
  remote=FakeRemote();remote.data['jobs']={'espn-123':copy.deepcopy(self.job)}
  remote.data['months']=copy.deepcopy(self.months)
  (ROOT/'build/pos-jogo').mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=ROOT/'build/pos-jogo') as tmp:
   site=Path(tmp)/'site';site.mkdir()
   (site/'noticias.json').write_text('[]')
   seen=[]
   def runner(day,news,out,**opts):
    seen.append(set(opts['processed']))
    if len(seen)==1:
     self.assertNotIn('espn-123',opts['processed'])
     opts['researcher']({'fixture_id':'espn-123'},None,None,Path(out)/'ap',self.now)
     return {'status':'pending','results':[{'fixture_id':'espn-123',
                             'status':'blocked','reason':'Menos de dois domínios com páginas efetivamente abertas'}]}
    self.assertIn('espn-123',opts['processed'])
    return {'status':'no_eligible_matches','results':[]}
   def research(*args,**kw):return None
   result=run_once(remote,site,Path(tmp)/'cycle',clock=lambda:self.now,runner=runner,
                   researcher=research,caller_factory=lambda *a:object(),
                   operation_mode='scheduled_drafts')
   self.assertEqual(len(result),2)
   self.assertEqual(remote.data['jobs']['espn-123']['source_retry_count'],1)
   self.assertEqual(remote.data['jobs']['espn-123']['api_calls'],2)
   self.assertEqual(remote.data['jobs']['espn-123']['status'],'blocked')
   self.assertIn('Menos de dois domínios',remote.data['jobs']['espn-123']['reason'])
   self.assertEqual(self.months,remote.data['months'])
   self.assertTrue(remote.snapshots)
 def test_three_ads_and_desktop_sidebar_are_mandatory(self):
  blocks=[{'type':'subtitle','text':'Etapas do jogo'}]+[
     {'type':'paragraph','text':'palavra '*60} for _ in range(11)]
  html,meta=render_html({'title':'Resultado na competição','excerpt':'Partida encerrada',
             'blocks':blocks},'02/11/2026',[])
  meta.update(fixed_shell_unchanged=True,old_news_preserved=True,
              old_sitemap_preserved=True,publication_enabled=False,
              filename='teste.html')
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d)/'publicacao-teste';folder.mkdir()
   (folder/'teste.html').write_text(html)
   for name in ('noticias.json','sitemap.xml'):(folder/name).write_text('[]')
   (folder/'validacao.json').write_text(json.dumps(meta))
   self.assertTrue(validate_generated_package(d,meta))
   changed=html.replace('data-ad-slot="5521804159"','data-ad-slot="000"',1)
   (folder/'teste.html').write_text(changed)
   with self.assertRaisesRegex(ValueError,'anúncio|sidebar'):
    validate_generated_package(d,meta)


if __name__=='__main__':
 unittest.main()
