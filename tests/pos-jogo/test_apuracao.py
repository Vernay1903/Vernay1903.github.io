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

 def test_source_diversity_before_translations(self):
  sources=[{'url':f'https://www.realmadrid.com/{i}'} for i in range(10)]+[{'url':'https://rbleipzig.com/report'}]
  r={'output':[{'type':'web_search_call','action':{'sources':sources}}]}
  self.assertEqual(discovered_urls(r)[1],'https://rbleipzig.com/report')

class ResearchFlowTests(unittest.TestCase):
 def test_semantic_rejection_never_releases_facts(self):
  import json,tempfile
  from datetime import datetime
  from apurar_pos_jogo import apurar
  root=Path(__file__).resolve().parents[2]
  base=root/'tests/pos-jogo/fixtures/real-leipzig-20261021'
  read=lambda p:json.loads(p.read_text())
  candidate=read(base/'selection.json')['selected'][0]
  summary=read(base/'summary.json')
  schedules={i:read(base/f'schedule-{i}.json') for i in ['86','11420']}
  quote='Trecho fictício exclusivo do teste automatizado.'
  refs=[{'passage_id':'page_0:0'},{'passage_id':'page_1:0'}]
  extraction={'checks':[{'id':i,'supported':True,'evidence':refs} for i in ['identity','score','venue','goals','campaign']],
    'claims':[{'text':f'Afirmação de teste {i}','evidence':refs} for i in range(6)]}
  stages=[]
  def response(value):return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
  def caller(payload):
   stages.append(payload)
   if len(stages)==1:return {'status':'completed','output':[{'type':'web_search_call','action':{'sources':[{'url':'https://realmadrid.com/test'},{'url':'https://dfb.de/test'}]}}]}
   if len(stages)==2:return response(extraction)
   return response({'checks':[{'id':i,'supported':False,'reason':'Trecho não sustenta o fato'} for i in ['identity','score','venue','goals','campaign']+[f'claim_{n}' for n in range(6)]]})
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaisesRegex(ValueError,'revisão independente'):
    apurar(candidate,summary,schedules,Path(tmp),datetime.fromisoformat('2026-10-22T12:00:00-03:00'),caller=caller,opener=lambda u:{'url':u,'text':quote,'opened':True})
   self.assertFalse((Path(tmp)/'fatos.json').exists())
   self.assertEqual(len(stages),3)

class PassageTests(unittest.TestCase):
 def test_only_original_passages_can_be_attached(self):
  from apurar_pos_jogo import source_passages,attach_passages
  p=source_passages({'s':{'text':'Trecho original da página aberta.'}})
  r={'checks':[],'claims':[{'evidence':[{'passage_id':'s:0'}]}]}
  self.assertEqual(attach_passages(r,p)['claims'][0]['evidence'][0]['quote'],'Trecho original da página aberta.')
  with self.assertRaises(ValueError):attach_passages({'checks':[],'claims':[{'evidence':[{'passage_id':'inventado'}]}]},p)
