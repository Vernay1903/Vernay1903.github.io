import copy,json,sys,unittest
from datetime import datetime,date,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from tempo_pos_jogo import observe,dates_to_check
class TimingTests(unittest.TestCase):
 def setUp(self):
  p=ROOT/'tests/pos-jogo/fixtures/real-leipzig-20261021'
  self.c=json.loads((p/'selection.json').read_text())['selected'][0]
  self.s=json.loads((p/'summary.json').read_text());self.state={'version':1,'fixtures':{}}
 def at(self,text):return datetime.fromisoformat(text)
 def move_kickoff(self,value):
  self.c['kickoff']=value
  self.s['header']['competitions'][0]['date']=value
 def test_1800_to_1850_exact_boundary(self):
  first=self.at('2026-10-21T18:00:00-03:00')
  r=observe(self.c,self.s,self.state,first)
  self.assertEqual(r['eligible_at'],'2026-10-21T18:50:00-03:00')
  self.assertFalse(observe(self.c,self.s,self.state,first+timedelta(minutes=49,seconds=59))['eligible'])
  self.assertTrue(observe(self.c,self.s,self.state,first+timedelta(minutes=50))['eligible'])
 def test_2130_game_crosses_midnight(self):
  self.move_kickoff('2026-10-21T21:30:00-03:00')
  r=observe(self.c,self.s,self.state,self.at('2026-10-21T23:30:00-03:00'))
  self.assertEqual(r['eligible_at'],'2026-10-22T00:20:00-03:00')
 def test_2200_game_ends_next_day(self):
  self.move_kickoff('2026-10-21T22:00:00-03:00')
  r=observe(self.c,self.s,self.state,self.at('2026-10-22T00:00:00-03:00'))
  self.assertEqual(r['eligible_at'],'2026-10-22T00:50:00-03:00')
 def test_late_finish_is_not_kickoff_plus_two_hours(self):
  r=observe(self.c,self.s,self.state,self.at('2026-10-21T18:14:00-03:00'))
  self.assertEqual(r['eligible_at'],'2026-10-21T19:04:00-03:00')
 def test_brasilia_date_differs_from_utc(self):
  self.assertEqual(dates_to_check(self.at('2026-10-22T01:00:00+00:00')),[date(2026,10,20),date(2026,10,21)])
 def test_year_rollover(self):
  self.assertEqual(dates_to_check(self.at('2027-01-01T00:20:00-03:00')),[date(2026,12,31),date(2027,1,1)])
 def test_changed_score_restarts_wait(self):
  first=self.at('2026-10-21T18:00:00-03:00');observe(self.c,self.s,self.state,first)
  self.c['score']['home']=5
  next(t for t in self.s['header']['competitions'][0]['competitors'] if t['homeAway']=='home')['score']='5'
  r=observe(self.c,self.s,self.state,first+timedelta(minutes=40))
  self.assertEqual(r['eligible_at'],'2026-10-21T19:30:00-03:00')
 def test_return_to_live_resets_clock(self):
  first=self.at('2026-10-21T18:00:00-03:00');observe(self.c,self.s,self.state,first)
  self.s['header']['competitions'][0]['status']['type']={'name':'STATUS_IN_PROGRESS','completed':False}
  self.assertFalse(observe(self.c,self.s,self.state,first+timedelta(minutes=5))['eligible'])
  self.assertEqual(self.state['fixtures'],{})

class RecordedTimingTests(TimingTests):
 def end(self,value,kind='end-regular-time',period=2):
  self.s['keyEvents']=[{'type':{'type':kind},'period':{'number':period},'text':'Second Half ends, A 1, B 0.','wallclock':value}]
 def test_delayed_poll_uses_source_finish(self):
  self.end('2026-10-21T21:00:00Z')
  r=observe(self.c,self.s,self.state,self.at('2026-10-21T19:10:00-03:00'))
  self.assertTrue(r['eligible']);self.assertEqual(r['eligible_at'],'2026-10-21T18:50:00-03:00')
  self.assertEqual(r['basis'],'source_recorded_final')
 def test_migrates_existing_observation_without_extra_wait(self):
  observe(self.c,self.s,self.state,self.at('2026-10-21T19:10:00-03:00'))
  self.end('2026-10-21T21:00:00Z')
  self.assertTrue(observe(self.c,self.s,self.state,self.at('2026-10-21T19:11:00-03:00'))['eligible'])
 def test_source_finish_after_midnight(self):
  self.move_kickoff('2026-10-21T22:00:00-03:00');self.end('2026-10-22T03:07:00Z')
  r=observe(self.c,self.s,self.state,self.at('2026-10-22T01:00:00-03:00'))
  self.assertEqual(r['eligible_at'],'2026-10-22T00:57:00-03:00')
 def test_arbitrary_last_update_is_not_finish(self):
  self.s['meta']={'lastUpdatedAt':'2026-10-21T21:00:00Z'}
  r=observe(self.c,self.s,self.state,self.at('2026-10-21T19:10:00-03:00'))
  self.assertFalse(r['eligible'])
 def test_nonterminal_or_future_timestamp_not_used(self):
  for kind,period,time in [('goal',2,'2026-10-21T21:00:00Z'),('end-regular-time',1,'2026-10-21T21:00:00Z'),('end-regular-time',2,'2026-10-22T21:00:00Z')]:
   self.state={'version':1,'fixtures':{}};self.end(time,kind,period)
   self.assertFalse(observe(self.c,self.s,self.state,self.at('2026-10-21T19:10:00-03:00'))['eligible'])
 def test_regular_time_not_final_for_penalties(self):
  from tempo_pos_jogo import recorded_finish
  self.end('2026-10-21T21:00:00Z')
  self.assertIsNone(recorded_finish(self.s,'STATUS_FINAL_PEN',self.at(self.c['kickoff']),self.at('2026-10-21T19:10:00-03:00')))
 def test_later_event_invalidates_early_finish(self):
  self.end('2026-10-21T21:00:00Z');self.s['keyEvents'].append({'type':{'type':'goal'},'wallclock':'2026-10-21T21:05:00Z'})
  self.assertFalse(observe(self.c,self.s,self.state,self.at('2026-10-21T19:10:00-03:00'))['eligible'])

class VenueResolutionTests(unittest.TestCase):
 def test_correction_is_exact_and_fixture_scoped(self):
  from preparar_fatos_pos_jogo import venue_name
  s={'header':{'id':'401882819'},'gameInfo':{'venue':{'fullName':'El Sardineros'}}}
  self.assertEqual(venue_name(s),'El Sardinero')
  s['header']['id']='another';self.assertEqual(venue_name(s),'El Sardineros')
  s['header']['id']='401882819';s['gameInfo']['venue']['fullName']='Other Stadium'
  self.assertEqual(venue_name(s),'Other Stadium')
