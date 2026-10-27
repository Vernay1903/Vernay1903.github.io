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

class OptionalNarrativeTests(unittest.TestCase):
 def fixture(self,count=7):
  core={'identity':{},'score':{},'venue':{},'goals':{},'campaign':{}}
  claims=[{'text':str(i),'evidence':[{'source_id':'s','quote':'literal'}]} for i in range(count)]
  audit={'checks':[{'id':k,'supported':True,'reason':''} for k in list(core)+[f'claim_{i}' for i in range(count)]]}
  return core,claims,audit
 def test_optional_rejection_omits_whole_claim_without_rewriting(self):
  from apurar_pos_jogo import approved_claims
  core,claims,audit=self.fixture();audit['checks'][6].update(supported=False,reason='Local não sustentado')
  kept,omitted=approved_claims(core,claims,audit)
  self.assertEqual(kept,[claims[i] for i in [0,2,3,4,5,6]])
  self.assertEqual(omitted[0]['claim'],claims[1]);self.assertEqual(omitted[0]['reason'],'Local não sustentado')
 def test_mandatory_rejection_blocks(self):
  from apurar_pos_jogo import approved_claims
  for index in range(5):
   core,claims,audit=self.fixture();audit['checks'][index]['supported']=False
   with self.assertRaises(ValueError):approved_claims(core,claims,audit)
 def test_insufficient_approved_claims_blocks(self):
  from apurar_pos_jogo import approved_claims
  core,claims,audit=self.fixture(6);audit['checks'][-1]['supported']=False
  with self.assertRaises(ValueError):approved_claims(core,claims,audit)
 def test_missing_duplicate_or_unknown_review_id_blocks(self):
  from apurar_pos_jogo import approved_claims
  for mode in ['missing','duplicate','unknown']:
   core,claims,audit=self.fixture()
   if mode=='missing':audit['checks'].pop()
   else:audit['checks'][-1]['id']='score' if mode=='duplicate' else 'unexpected'
   with self.assertRaises(ValueError):approved_claims(core,claims,audit)

class RewriteBudgetTests(unittest.TestCase):
 def test_rewrite_uses_separate_limit_and_preserves_diagnostics(self):
  import json
  from redigir_pos_jogo_openai import rewrite_request
  provider={'model':'gpt-5.6-terra','reasoning_effort':'medium','max_output_tokens':4000,'rewrite_max_output_tokens':2500}
  article={'title':'Teste','excerpt':'Chamada','blocks':[]}
  issues=['Corpo com menos de 600 palavras','block_0: Informação sem apoio']
  request=rewrite_request({'instructions':'Não invente','facts':{}},article,issues,provider)
  self.assertEqual(request['max_output_tokens'],2500)
  data=json.loads(request['input'][-1]['content'])
  self.assertEqual(data['draft'],article);self.assertEqual(data['issues'],issues)
  self.assertEqual(provider['max_output_tokens'],4000)
