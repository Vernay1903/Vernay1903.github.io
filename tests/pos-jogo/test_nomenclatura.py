import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from editorial_pos_jogo import competition_names,validate
class NamingTests(unittest.TestCase):
 def test_all_fields_and_grammar_preserve_links(self):
  url='https://cortedosesportes.com.br/campeonato-ingles.html'
  a={'title':'Arsenal vence no Campeonato Inglês','excerpt':'Pelo Campeonato Inglês, o Arsenal venceu.','blocks':[{'type':'paragraph','text':'Líder do campeonato inglês. <a href="'+url+'">O Campeonato Inglês</a>'}]}
  b=competition_names(a)
  self.assertEqual(b['title'],'Arsenal vence na Premier League')
  self.assertEqual(b['excerpt'],'Pela Premier League, o Arsenal venceu.')
  self.assertEqual(b['blocks'][0]['text'],'Líder da Premier League. <a href="'+url+'">A Premier League</a>')
  self.assertEqual(a['title'],'Arsenal vence no Campeonato Inglês')
  self.assertEqual(competition_names(b),b)
 def test_validator_blocks_old_name(self):
  a={'title':'Campeonato Inglês','excerpt':'Resumo','blocks':[{'type':'subtitle','text':'Jogo'},{'type':'paragraph','text':'palavra '*600}]}
  self.assertIn('Nomenclatura obrigatória: Premier League',validate(a,[])['errors'])
  self.assertNotIn('Nomenclatura obrigatória: Premier League',validate(competition_names(a),[])['errors'])
