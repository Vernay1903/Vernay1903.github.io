import json
from pathlib import Path
from unittest.mock import patch
import test_integracao
import executar_pos_jogo as pipeline
from empacotar_redacao_pos_jogo import digest, package_reviewed

class PackageIntegrationTests(test_integracao.IntegrationTests):
 def setUp(self):
  super().setUp()
  self.site=self.out/'site';self.site.mkdir()
  (self.site/'noticias.json').write_text('[]')
  (self.site/'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><!-- MATÉRIAS --></urlset>')
  self.article=pipeline.read(pipeline.ROOT/'auditoria/pos-jogo/amostra-editorial-real-leipzig.json')
  self.stamp='2026-10-26T03:01:00+00:00'
 def writer(self,package,out,**kw):
  meta=super().writer(package,out,**kw)
  meta.update(format_passed=True,written_at=self.stamp,article_sha256=digest(self.article),package_sha256=digest(package))
  pipeline.save(out/'metadata.json',meta);pipeline.save(out/'artigo.json',self.article)
  return meta
 def test_writer_to_all_three_files(self):
  r=self.run_pipeline(execute=True,site_root=self.site)
  row=r['results'][0];self.assertEqual(row['status'],'package_ready')
  report=row['package'];directory=self.out/row['fixture_id'];out=directory/'publicacao-teste'
  news=pipeline.read(out/'noticias.json')[0]
  self.assertEqual(news['date'],'26/10/2026');self.assertEqual(news['title'],self.article['title'])
  self.assertIn('>26/10/2026</span>',(out/news['url']).read_text())
  self.assertIn('<lastmod>2026-10-26</lastmod>',(out/'sitemap.xml').read_text())
  self.assertEqual((self.site/'noticias.json').read_text(),'[]')
  links=pipeline.read(pipeline.ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
  self.assertEqual(package_reviewed(directory,self.site,links),report)
  self.assertEqual(len(self.calls),1)
 def test_midnight_uses_writer_date_not_collection(self):
  self.stamp='2026-10-26T02:59:59+00:00'
  r=self.run_pipeline(execute=True,site_root=self.site)
  self.assertEqual(r['results'][0]['package']['article_date'],'25/10/2026')
 def test_modified_article_blocked(self):
  r=self.run_pipeline(execute=True);directory=self.out/r['results'][0]['fixture_id']
  self.article['title']='Título alterado';pipeline.save(directory/'redacao/artigo.json',self.article)
  with self.assertRaises(ValueError):package_reviewed(directory,self.site,[])
  self.assertFalse((directory/'publicacao-teste').exists())
 def test_rejected_review_blocked(self):
  r=self.run_pipeline(execute=True);directory=self.out/r['results'][0]['fixture_id']
  meta=pipeline.read(directory/'redacao/metadata.json');meta['semantic_review_passed']=False
  pipeline.save(directory/'redacao/metadata.json',meta)
  with self.assertRaises(ValueError):package_reviewed(directory,self.site,[])
 def test_fresh_destination_collision_blocks(self):
  r=self.run_pipeline(execute=True,site_root=self.site);directory=self.out/r['results'][0]['fixture_id']
  (self.site/'noticias.json').write_bytes((directory/'publicacao-teste/noticias.json').read_bytes())
  links=pipeline.read(pipeline.ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
  with self.assertRaises(ValueError):package_reviewed(directory,self.site,links)
 def test_collect_cannot_package(self):
  with self.assertRaises(ValueError):self.run_pipeline(site_root=self.site)
