import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from fontes_oficiais_pos_jogo import uefa_record
from redigir_pos_jogo_openai import apply_expansion

class IdentityTests(unittest.TestCase):
 def test_reject_prior_meeting_or_reversed_teams(self):
  c=dict(kickoff='2026-11-04T17:00:00-03:00',home='Slavia Prague',away='Arsenal',score={'home':1,'away':2})
  d=dict(competition={'id':'1','code':'UCL'},status='FINISHED',kickOffTime={'dateTime':'2026-11-04T20:00:00Z'},homeTeam={'internationalName':'Slavia Praha'},awayTeam={'internationalName':'Arsenal'},score={'regular':dict(c['score'])},stadium={},matchday={'longName':'Matchday 4'})
  self.assertIsNotNone(uefa_record(c,d))
  for patch in [{'competition':{'id':'2'}},{'kickOffTime':{'dateTime':'2021-11-04T20:00:00Z'}},{'score':{'regular':{'home':2,'away':1}}},{'homeTeam':d['awayTeam']}]:
   self.assertIsNone(uefa_record(c,dict(d,**patch)))
 def test_short_article_preserves_order_and_original_text(self):
  a={'blocks':[dict(type='paragraph',text='Primeiro.'),dict(type='paragraph',text='Fechamento.')]}
  b=apply_expansion(a,{'additions':[{'after':0,'text':'Outro fato verificado.'}]})
  self.assertEqual([x['text'] for x in b['blocks']],['Primeiro.','Outro fato verificado.','Fechamento.'])
  self.assertEqual(len(a['blocks']),2)
