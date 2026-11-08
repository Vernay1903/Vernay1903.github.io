import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from revisar_pos_jogo import targeted_issues, validate_review, units
from redigir_pos_jogo_openai import generate, ROOT


class EditorialQualityTests(unittest.TestCase):
    def test_global_failure_requires_rewrite_but_local_fact_allows_patch(self):
        a = {'title':'T', 'excerpt':'E', 'blocks':[{'type':'paragraph','text':'Texto'}]}
        self.assertIsNone(targeted_issues(a, ['block_0: [EDITORIAL_GLOBAL] Catálogo de lances']))
        self.assertEqual(targeted_issues(a, ['block_0: Mando errado']), ['block_0: Mando errado'])

    def test_factual_support_does_not_override_editorial_rejection(self):
        p = {'facts':{'score':{}}, 'narrative_facts':[]}
        a = {'title':'T', 'excerpt':'E', 'blocks':[]}
        checks = [{'unit':u,'supported':u!='excerpt','evidence_ids':['score'],
                   'issues':['[EDITORIAL_GLOBAL] Abertura burocrática e relato de eventos'] if u=='excerpt' else []}
                  for u in units(a)]
        self.assertIn('[EDITORIAL_GLOBAL]', validate_review({'checks':checks}, p, a)[0])

    def test_global_rejection_rewrites_whole_article_and_reviews_all_units(self):
        p = {'instructions':'Teste sintético','facts':{'fixture_id':'editorial-regression','match':{}},
             'narrative_facts':[], 'allowed_internal_urls':[]}
        articles = [{'title':'Teste','excerpt':'Chamada','blocks':[
            {'type':'subtitle','text':'Desenvolvimento'},
            {'type':'paragraph','text':word * 650}]} for word in ['original ', 'reescrito ']]
        calls = []; writes = []
        def response(x):
            return {'status':'completed','output':[{'type':'message','content':[
                {'type':'output_text','text':json.dumps(x)}]}]}
        def caller(payload):
            name = payload['text']['format']['name']; calls.append(name)
            if name == 'pos_jogo':
                article = articles[len(writes)]; writes.append(article); return response(article)
            self.assertEqual(name, 'review_pos_jogo')  # nunca patch/expansão
            received = json.loads(payload['input'][-1]['content'])['units']
            self.assertEqual(set(received), set(units(writes[-1])))
            reject = len(writes) == 1
            return response({'checks':[{'unit':u,'supported':not(reject and u=='block_1'),
                'evidence_ids':['match'],'issues':['[EDITORIAL_GLOBAL] Reorganizar relato de lances']
                if reject and u=='block_1' else []} for u in received]})
        (ROOT/'build/pos-jogo').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'build/pos-jogo') as out, \
             patch.dict(os.environ, {'OPENAI_API_KEY':'test-only'}), contextlib.redirect_stdout(io.StringIO()):
            result = generate(p, out, execute=True, caller=caller)
            final = json.loads((Path(out)/'artigo.json').read_text())
        self.assertEqual(final, articles[1])
        self.assertTrue(result['semantic_review_passed'])
        self.assertEqual(calls, ['pos_jogo','review_pos_jogo','review_pos_jogo','pos_jogo','review_pos_jogo'])
