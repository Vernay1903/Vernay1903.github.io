import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from apurar_pos_jogo import safe_url,validate_evidence,discovered_urls,VisibleText
class SourceTests(unittest.TestCase):
 def test_unknown_domain_blocked(self):
  for u in ['http://realmadrid.com/a','https://realmadrid.com.evil.test/a','https://localhost/a','https://cortedosesportes.com.br/a','https://user@realmadrid.com/a']:
   with self.assertRaises(ValueError):safe_url(u)
 def test_known_subdomain(self):self.assertEqual(safe_url('https://www.realmadrid.com/a'),'https://www.realmadrid.com/a')
 def test_body_excludes_scripts(self):
  p=VisibleText();p.feed('<p>Fato</p><script>falso</script><style>css</style><p>Outro</p>')
  self.assertEqual(p.parts,['Fato','Outro'])
 def test_exact_quote_required(self):
  pages={'p':{'text':'Um fato confirmado no relato oficial.','opened':True}}
  row={'id':'score','supported':True,'evidence':[{'source_id':'p','quote':'Um fato confirmado no relato oficial.'}]}
  validate_evidence([row],['score'],pages)
  row['evidence'][0]['quote']='Outro fato inventado pelo extrator.'
  with self.assertRaises(ValueError):validate_evidence([row],['score'],pages)
 def test_no_partial_coverage(self):
  with self.assertRaises(ValueError):validate_evidence([],['score'],{})
 def test_search_text_is_not_source(self):
  self.assertEqual(discovered_urls({'output':[{'type':'message','content':[{'text':'https://www.realmadrid.com/a'}]}]}),[])
 def test_search_sources_allowlist(self):
  r={'output':[{'type':'web_search_call','action':{'sources':[{'url':'https://www.realmadrid.com/a'},{'url':'https://cortedosesportes.com.br/a'}]}}]}
  self.assertEqual(discovered_urls(r),['https://www.realmadrid.com/a'])
