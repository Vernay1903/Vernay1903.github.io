import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from preparar_publicacao_pos_jogo import prepare, BASE

class PublicationTests(unittest.TestCase):
 def setUp(self):
  self.article=json.loads((ROOT/'auditoria/pos-jogo/amostra-editorial-real-leipzig.json').read_text())
  self.links=json.loads((ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json').read_text())
  self.match=dict(home='Real Madrid',away='RB Leipzig',competition='Champions League',match_date='2026-10-21')
  self.news='[\n {"title":"Anterior", "url":"anterior.html"}\n]'
  self.xml='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n<!-- MATÉRIAS -->\n<url><loc>'+BASE+'anterior.html</loc></url>\n</urlset>'
 def run_case(self, stamp='2026-10-26T03:20:00+00:00', files=()):
  return prepare(self.article,self.match,stamp,self.news,self.xml,self.links,files)
 def test_integrated_preserves_entries_and_exact_editorial(self):
  r=self.run_case();n=json.loads(r['noticias.json']);report=json.loads(r['validacao.json'])
  self.assertEqual(n[1:],json.loads(self.news));self.assertTrue(r['noticias.json'].endswith(self.news[1:]))
  self.assertEqual(list(n[0]),['title','excerpt','url','date','category'])
  self.assertEqual(n[0]['title'],self.article['title']);self.assertEqual(n[0]['excerpt'],self.article['excerpt'])
  self.assertEqual(n[0]['url'],'real-madrid-rb-leipzig-champions-league-2026-resultado.html')
  self.assertEqual(n[0]['date'],'26/10/2026');self.assertEqual(n[0]['category'],'Futebol')
  self.assertIn('>26/10/2026</span>',r[n[0]['url']]);self.assertIn('<lastmod>2026-10-26</lastmod>',r['sitemap.xml'])
  self.assertIn('<priority>0.9</priority>',r['sitemap.xml']);self.assertTrue(report['fixed_shell_unchanged'])
 def test_before_brasilia_midnight(self):
  r=self.run_case('2026-10-26T02:59:59+00:00');self.assertEqual(json.loads(r['noticias.json'])[0]['date'],'25/10/2026')
 def test_new_year_and_match_year(self):
  r=self.run_case('2027-01-01T03:00:00+00:00');n=json.loads(r['noticias.json'])[0]
  self.assertEqual(n['date'],'01/01/2027');self.assertIn('-2026-resultado.html',n['url'])
 def test_naive_timestamp_blocked(self):
  with self.assertRaises(ValueError):self.run_case('2026-10-26T00:20:00')
 def test_duplicate_news_blocked(self):
  self.news=self.run_case()['noticias.json']
  with self.assertRaises(ValueError):self.run_case()
 def test_duplicate_sitemap_blocked(self):
  self.xml=self.run_case()['sitemap.xml']
  with self.assertRaises(ValueError):self.run_case()
 def test_existing_html_blocked(self):
  with self.assertRaises(ValueError):self.run_case(files=['real-madrid-rb-leipzig-champions-league-2026-resultado.html'])
 def test_accents_and_empty_news(self):
  self.news='[\n]';self.match.update(home='Grêmio',away='São Paulo',competition='Brasileirão Série A')
  self.assertIn('gremio-sao-paulo-brasileirao-serie-a-2026-resultado.html',self.run_case())
 def test_bad_input_blocked(self):
  self.news='invalid'
  with self.assertRaises(ValueError):self.run_case()
 def test_missing_marker_blocked(self):
  self.xml=self.xml.replace('<!-- MATÉRIAS -->','')
  with self.assertRaises(ValueError):self.run_case()
