import copy
import sys
import unittest
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from testar_editorial_passo17 import reserve_test,total,FID,KEY
class FakeRemote:
 def __init__(self):
  self.data={'jobs':{FID:{'status':'package_ready','run_id':'40784987236','api_calls':8,'package':{'original':True}}},
   'months':{'2026-10':{'calls':[{'fixture_id':FID,'charged_usd':'0.027376955'}]},
    '2026-11':{'calls':[{'fixture_id':'other','charged_usd':'0.05'}]}}}
  self.saves=0
 def save(self):self.saves+=1
class TestValidationReservation(unittest.TestCase):
 def test_preserves_prior_spending_and_original_job(self):
  r=FakeRemote();original=copy.deepcopy(r.data['jobs'][FID]);months=copy.deepcopy(r.data['months'])
  saved=reserve_test(r)
  self.assertEqual(saved,original);self.assertEqual(r.data['months'],months)
  self.assertEqual(total(r.data),Decimal('0.027376955'))
  self.assertEqual(r.data[KEY]['per_fixture_total_cap_usd'],'0.10')
  self.assertFalse(r.data[KEY]['publication_enabled'])
  self.assertEqual(r.saves,1)
 def test_cannot_repeat_even_after_success(self):
  r=FakeRemote();reserve_test(r)
  r.data['jobs'][FID]['status']='package_ready';r.data[KEY]['status']='completed'
  with self.assertRaises(ValueError):reserve_test(r)
 def test_rejects_concurrent_or_changed_job(self):
  for change in [{'api_calls':9},{'status':'running'},{'run_id':'other'}]:
   r=FakeRemote();r.data['jobs'][FID].update(change)
   with self.assertRaises(ValueError):reserve_test(r)
   self.assertEqual(r.saves,0)
if __name__=='__main__':unittest.main()
