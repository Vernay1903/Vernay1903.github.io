import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from fontes_oficiais_pos_jogo import trusted_report_matches
class LocatedReportTests(unittest.TestCase):
 def setUp(self):
  self.c={'home':'Arsenal','away':'Hull City','score':{'home':1,'away':0},'match_date':'2026-11-07','competition_code':'eng.1'}
  self.p={'url':'https://www.skysports.com/football/arsenal-vs-hull-city/report/559534','text':'Arsenal 1-0 Hull City Premier League Saturday 7th November 2026'}
 def test_exact_match(self):self.assertTrue(trusted_report_matches(self.c,self.p))
 def test_old_match_wrong_score_and_wrong_domain_rejected(self):
  for old,new in [('2026','2017'),('1-0','2-0'),('Hull City','Chelsea'),('Premier League','Championship')]:
   self.assertFalse(trusted_report_matches(self.c,dict(self.p,text=self.p['text'].replace(old,new))))
  self.assertFalse(trusted_report_matches(self.c,dict(self.p,url='https://example.com/report/1')))
