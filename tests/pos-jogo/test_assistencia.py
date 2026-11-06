import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from corrigir_assistencia_pos_jogo import correct_text,correct_candidate
class AssistanceTests(unittest.TestCase):
 def test_only_explicit_assist_removes_false_blocker(self):
  wrong='Depois, Razvan Marin teve uma finalização bloqueada por Zine; outro lance.'
  source='Attempt blocked. Razvan Marin (AEK Athens) left footed shot from the centre of the box is blocked. Assisted by Zine.'
  self.assertEqual(correct_text(wrong,[{'text':source}]),'Depois, Razvan Marin teve uma finalização bloqueada; outro lance.')
  self.assertEqual(correct_text(wrong,[{'text':source.replace('Assisted by','Blocked by')}]),wrong)
  self.assertEqual(correct_text(wrong,[{'text':source.replace('Razvan Marin','Outro jogador')}]),wrong)
 def test_does_not_modify_inputs(self):
  n={'claims':[{'text':'Fato certo'}]};a={'blocks':[{'text':'Texto certo'}]}
  nn,aa=correct_candidate(n,a,[])
  self.assertEqual((nn,aa),(n,a));self.assertIsNot(nn,n);self.assertIsNot(aa,a)
