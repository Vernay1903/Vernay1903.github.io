import json,re,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from montar_html_pos_jogo import render_html,fixed_shell,ad_positions,words
class HtmlTests(unittest.TestCase):
 def setUp(self):
  self.policy=json.loads((ROOT/'config/html-pos-jogo.json').read_text())['ads']
 def article(self,n):
  return {'title':'Resultado do jogo: análise e gols','excerpt':'Resumo da partida e dos principais lances.',
   'blocks':[{'type':'subtitle','text':'Como foi a partida'}]+[{'type':'paragraph','text':'palavra '*50} for _ in range(n//50)]}
 def test_preserves_fixed_template_exactly(self):
  template=(ROOT/'templates/materia-validada.html').read_bytes().decode('utf-8')
  rendered,report=render_html(self.article(600),'24/10/2026',[])
  self.assertEqual(fixed_shell(template),fixed_shell(rendered))
  self.assertTrue(report['fixed_shell_unchanged'])
  self.assertIn('const CATEGORY_SLUG = "futebol";',rendered)
  self.assertNotIn('Gabriel Medina',rendered)
  self.assertNotIn('youtube.com/embed/',rendered)
  self.assertEqual(rendered.count('pagead/js/adsbygoogle.js'),1)
  self.assertEqual(rendered.count('data-ad-slot="5521804159"'),1)
 def test_ad_counts_and_spacing(self):
  for total,count in [(600,1),(900,2),(1500,3)]:
   a=self.article(total);positions=ad_positions(a['blocks'],self.policy)
   self.assertEqual(len(positions),count)
   previous=0
   for i in positions:
    cumulative=sum(words(b['text']) for b in a['blocks'][:i+1])
    self.assertGreaterEqual(cumulative-previous,250);previous=cumulative
    self.assertEqual(a['blocks'][i]['type'],'paragraph')
   self.assertGreaterEqual(sum(words(b['text']) for b in a['blocks'])-previous,150)
 def test_does_not_force_ads_inside_long_paragraph(self):
  a=self.article(600);a['blocks']=[a['blocks'][0],{'type':'paragraph','text':'palavra '*600}]
  self.assertEqual(ad_positions(a['blocks'],self.policy),[])
 def test_does_not_separate_list_intro(self):
  blocks=[{'type':'paragraph','text':'palavra '*300},{'type':'list','text':'item '*100},{'type':'paragraph','text':'palavra '*300}]
  self.assertEqual(ad_positions(blocks,self.policy),[])
 def test_title_and_attributes_escaped(self):
  a=self.article(600);a['title']='Time A & Time B';a['excerpt']='O técnico disse "vitória" & comemorou.'
  rendered,_=render_html(a,'24/10/2026',[])
  self.assertIn('content="O técnico disse &quot;vitória&quot; &amp; comemorou."',rendered)
  self.assertIn('Time A &amp; Time B</h1>',rendered)
 def test_only_authorized_link_survives(self):
  a=self.article(600);url='https://cortedosesportes.com.br/exemplo-fornecido.html'
  a['blocks'][1]['text']+='<a href="'+url+'">resultado anterior</a>'
  rendered,_=render_html(a,'24/10/2026',[url])
  self.assertIn('<a href="'+url+'">resultado anterior</a>',rendered)
  with self.assertRaises(ValueError):render_html(a,'24/10/2026',[])
 def test_script_in_body_blocked(self):
  a=self.article(600);a['blocks'][1]['text']+='<script>alert(1)</script>'
  with self.assertRaises(ValueError):render_html(a,'24/10/2026',[])
 def test_invalid_date_blocked(self):
  with self.assertRaises(ValueError):render_html(self.article(600),'31/02/2026',[])
 def test_changed_template_blocked(self):
  with patch('montar_html_pos_jogo.hashlib.sha256') as digest:
   digest.return_value.hexdigest.return_value='changed'
   with self.assertRaises(ValueError):render_html(self.article(600),'24/10/2026',[])
