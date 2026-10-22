import copy
import json
import sys
import unittest
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.preparar_fatos_pos_jogo import build
P=ROOT/'tests/pos-jogo/fixtures'
class FactsTest(unittest.TestCase):
 def setUp(self):
  f=P/'real-leipzig-20261021'
  self.c=json.loads((f/'selection.json').read_text())['selected'][0]
  self.s=json.loads((f/'summary.json').read_text())
  self.cal={i:json.loads((f/f'schedule-{i}.json').read_text()) for i in ['86','11420']}
  self.r=json.loads((P/'revisao-real-leipzig-20261021.json').read_text())
  self.now=datetime.fromisoformat(self.r['sources'][0]['checked_at'])
 def run_build(self): return build(self.c,self.s,self.cal,self.r,self.now)
 def test_real_packet(self):
  r=self.run_build(); self.assertTrue(r['ready_for_drafting']); self.assertFalse(r['ready_for_publication'])
  self.assertEqual(len(r['goals']),5); self.assertIsNone(r['goals'][0]['minute'])
  self.assertEqual(r['upcoming']['home']['next_match']['time_brasilia'],'17:00')
  self.assertEqual(r['upcoming']['away']['next_match']['time_brasilia'],'10:30')
 def test_wrong_match(self):
  self.s['header']['id']='9'
  with self.assertRaises(ValueError):self.run_build()
 def test_changed_score(self):
  self.s['header']['competitions'][0]['competitors'][0]['score']='5'
  with self.assertRaises(ValueError):self.run_build()
 def test_missing_goal(self):
  self.s['header']['competitions'][0]['details'].pop()
  with self.assertRaises(ValueError):self.run_build()
 def test_wrong_scorer(self):
  self.r['goals'][0]['scorer']='Outro'
  with self.assertRaises(ValueError):self.run_build()
 def test_campaign(self):
  self.r['campaign']['home']['points']=6
  with self.assertRaises(ValueError):self.run_build()
 def test_schedule_identity(self):
  self.cal['86']['team']['id']='359'
  with self.assertRaises(ValueError):self.run_build()
 def test_missing_future_is_gap(self):
  self.cal['86']['events']=[]
  self.assertFalse(self.run_build()['ready_for_drafting'])
 def test_unknown_time_omitted(self):
  self.cal['86']['events'][0]['timeValid']=False
  self.assertIsNone(self.run_build()['upcoming']['home']['next_match']['time_brasilia'])
 def test_final_and_penalties(self):
  for status in ['STATUS_IN_PROGRESS','STATUS_FINAL_PEN']:
   self.s['header']['competitions'][0]['status']['type']['name']=status
   with self.assertRaises(ValueError): self.run_build()
 def test_missing_review(self):
  self.r['sources']=[]
  with self.assertRaises(ValueError):self.run_build()
if __name__=='__main__':unittest.main()
