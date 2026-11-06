import base64,copy,json,sys,unittest
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from publicar_pos_jogo import publish_atomic
class FakeRemote:
 def __init__(self,race=False):
  self.files={'noticias.json':'[]','sitemap.xml':'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><!-- MATÉRIAS --></urlset>'}
  self.head='h1';self.new={};self.race=race;self.patches=[]
 def request(self,method,path,body=None):
  if path=='/git/ref/heads/main':return {'object':{'sha':self.head}}
  if path.startswith('/git/commits/') and method=='GET':return {'tree':{'sha':self.head}}
  if path.startswith('/git/trees/') and method=='GET':return {'tree':[{'path':p,'type':'blob'} for p in self.files]}
  if path.startswith('/contents/'):
   p=path[10:].split('?')[0]
   if p not in self.files:raise HTTPError(path,404,'not found',{},None)
   return {'content':base64.b64encode(self.files[p].encode()).decode()}
  if method=='POST' and path=='/git/trees':self.new={e['path']:e['content'] for e in body['tree']};return {'sha':'tree-new'}
  if method=='POST' and path=='/git/commits':return {'sha':'commit-'+self.head}
  if method=='PATCH':
   self.patches.append(body)
   if self.race:
    self.race=False;self.head='h2';self.files['noticias.json']='[{"title":"Notícia manual","url":"manual.html","date":"06/11/2026","category":"Tênis"}]'
    raise HTTPError(path,422,'race',{},None)
   self.files.update(self.new);self.head=body['sha'];return {'object':{'sha':self.head}}
  raise AssertionError((method,path))
class AutomaticPublicationTests(unittest.TestCase):
 def setUp(self):
  self.a={'title':'Real Madrid vence pela Champions League','excerpt':'Resumo confirmado do confronto pela Champions League.','blocks':[{'type':'subtitle','text':'Como foi o jogo'}]+[{'type':'paragraph','text':'palavra '*50} for _ in range(13)]}
  self.f={'match':{'home':'Real Madrid','away':'Visitante','competition':'Champions League','match_date':'2026-11-06'}}
  self.m={'written_at':'2026-11-06T18:00:00-03:00'}
 def run_publish(self,r):return publish_atomic(r,'espn-test',self.f,self.a,self.m,[])
 def test_atomic_files_ads_home_and_receipt(self):
  r=FakeRemote();receipt=self.run_publish(r)
  self.assertEqual(len(r.new),5)
  self.assertEqual(json.loads(r.files['noticias-home.json']),json.loads(r.files['noticias.json'])[:10])
  self.assertEqual(r.files[receipt['url']].count('data-ad-slot="8702501261"'),3)
  self.assertEqual(len(r.patches),1);self.assertIs(r.patches[0]['force'],False)
 def test_concurrent_manual_news_preserved_on_retry(self):
  r=FakeRemote(race=True);self.run_publish(r)
  self.assertEqual(json.loads(r.files['noticias.json'])[1]['url'],'manual.html')
  self.assertEqual(len(r.patches),2)
 def test_retry_after_commit_does_not_republish_or_overwrite_manual_edit(self):
  r=FakeRemote();receipt=self.run_publish(r);r.files[receipt['url']]='Edição manual do usuário'
  again=self.run_publish(r)
  self.assertTrue(again['recovered']);self.assertEqual(len(r.patches),1)
  self.assertEqual(r.files[receipt['url']],'Edição manual do usuário')
 def test_existing_slug_without_receipt_is_not_overwritten(self):
  r=FakeRemote();r.files['real-madrid-visitante-champions-league-2026-resultado.html']='Manual'
  with self.assertRaisesRegex(ValueError,'URL já existente'):self.run_publish(r)
  self.assertFalse(r.patches)
 def test_duplicate_match_is_skipped(self):
  r=FakeRemote();r.files['noticias.json']=json.dumps([{'title':'Real Madrid vence Visitante','url':'outro.html','date':'06/11/2026','category':'Futebol'}])
  self.assertEqual(self.run_publish(r)['status'],'skipped');self.assertFalse(r.patches)

class CandidateRecoveryTests(unittest.TestCase):
 def test_selects_approved_version_among_failed_and_recovered_outputs(self):
  import tempfile
  from unittest.mock import patch
  import publicar_pos_jogo as module
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);fid='espn-1'
   for folder,passed,sha in [('execucao',False,'old'),('retomada',True,'final')]:
    p=root/'build/pos-jogo/agendado'/folder/fid;(p/'redacao').mkdir(parents=True)
    for n in ['fatos.json','narrativa.json','redacao/artigo.json']:(p/n).write_text('{"version":"'+sha+'"}')
    (p/'redacao/metadata.json').write_text(json.dumps({'semantic_review_passed':passed,'article_sha256':sha}))
   with patch.object(module,'ROOT',root):data=module.load_data(None,fid,{'package':{'article_sha256':'final'}})
   self.assertEqual(data['redacao/artigo.json']['version'],'final')
