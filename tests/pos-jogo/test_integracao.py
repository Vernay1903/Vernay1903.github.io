import copy
import json
import sys
import tempfile
import unittest
from datetime import date,datetime
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import executar_pos_jogo as pipeline
class IntegrationTests(unittest.TestCase):
 def setUp(self):
  p=ROOT/'tests/pos-jogo/fixtures/real-leipzig-20261021'
  read=lambda f:json.loads(f.read_text())
  self.selection=read(p/'selection.json');self.selection['blocked']=[]
  self.summary=read(p/'summary.json');self.schedules={i:read(p/f'schedule-{i}.json') for i in ['86','11420']}
  self.now=datetime.fromisoformat('2026-10-22T12:00:00-03:00')
  self.calls=[]
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'build/pos-jogo')
  self.out=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def query(self,url):
  if '/summary?' in url:return self.summary
  return self.schedules[url.split('/teams/')[1].split('/')[0]]
 def writer(self,package,out,**kw):
  self.calls.append(package['facts']['fixture_id'])
  pipeline.save(out/'tentativa.json',{})
  return {'semantic_review_passed':True,'fixture_id':package['facts']['fixture_id']}
 def run_pipeline(self,**kw):
  with patch.object(pipeline,'select',return_value=self.selection):
   return pipeline.run(date(2026,10,21),[],self.out,query=self.query,writer=self.writer,now=self.now,**kw)
 def test_live_packet_to_writer_and_repeat(self):
  r=self.run_pipeline(execute=True)
  self.assertEqual(r['results'][0]['status'],'draft_reviewed');self.assertEqual(self.calls,['espn-401915313'])
  self.assertEqual(self.run_pipeline(execute=True)['results'][0]['status'],'already_attempted');self.assertEqual(len(self.calls),1)
 def test_missing_review_blocks_api(self):
  r=self.run_pipeline(execute=True,registry={})
  self.assertEqual(r['results'][0]['status'],'needs_source_review');self.assertEqual(self.calls,[])
 def test_collection_error_never_generates(self):
  self.selection['collection_complete']=False
  self.assertEqual(self.run_pipeline(execute=True)['status'],'collection_failed');self.assertEqual(self.calls,[])
 def test_no_matches_is_not_error(self):
  self.selection['selected']=[]
  self.assertEqual(self.run_pipeline(execute=True)['status'],'no_eligible_matches');self.assertEqual(self.calls,[])
 def test_changed_score_blocks(self):
  self.summary['header']['competitions'][0]['competitors'][0]['score']='9'
  self.assertEqual(self.run_pipeline(execute=True)['results'][0]['status'],'blocked');self.assertEqual(self.calls,[])
 def test_expired_review_blocks(self):
  self.now=datetime.fromisoformat('2026-10-24T12:00:00-03:00')
  self.assertEqual(self.run_pipeline(execute=True)['results'][0]['status'],'blocked');self.assertEqual(self.calls,[])
 def test_collect_only_no_api(self):
  self.assertEqual(self.run_pipeline()['results'][0]['status'],'ready_for_drafting');self.assertEqual(self.calls,[])
