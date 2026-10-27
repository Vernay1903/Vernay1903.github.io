import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from redigir_pos_jogo_openai import build_request, parse_response

class ApiTests(unittest.TestCase):
    def test_no_tools_no_storage_bounded_output(self):
        p=build_request({'instructions':'editorial','facts':{}},{'model':'configured','reasoning_effort':'none'})
        self.assertFalse(p['store'])
        self.assertNotIn('tools',p)
        self.assertEqual(p['max_output_tokens'],6000)
        self.assertTrue(p['text']['format']['strict'])
    def test_incomplete_rejected(self):
        with self.assertRaises(ValueError): parse_response({'status':'incomplete','output':[]})
    def test_refusal_rejected(self):
        with self.assertRaises(ValueError): parse_response({'status':'completed','output':[{'type':'message','content':[{'type':'refusal'}]}]})
    def test_structured_text_extraction(self):
        r={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{"title":"Teste", "excerpt":"Chamada", "blocks":[]}'}]}]}
        self.assertEqual(parse_response(r)['title'],'Teste')

class FormatBeforePaidReviewTests(unittest.TestCase):
    def test_short_draft_is_rewritten_without_paying_for_semantic_review(self):
        import json,os,tempfile,contextlib,io
        from unittest.mock import patch
        from redigir_pos_jogo_openai import generate,ROOT
        from revisar_pos_jogo import units
        package={'instructions':'Instrução exclusiva do teste','facts':{'fixture_id':'test-1','match':{}},'narrative_facts':[],'allowed_internal_urls':[]}
        articles=[{'title':'Teste','excerpt':'Chamada','blocks':[{'type':'subtitle','text':'Teste'},{'type':'paragraph','text':'palavra '*n}]} for n in [100,650]]
        stages=[];written=[]
        def response(x):return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(x)}]}]}
        def caller(payload):
            stage=payload['text']['format']['name'];stages.append(stage)
            if stage=='pos_jogo':
                article=articles[len(written)];written.append(article);return response(article)
            self.assertEqual(len(written),2)
            return response({'checks':[{'unit':u,'supported':True,'evidence_ids':['match'],'issues':[]} for u in units(articles[1])]})
        (ROOT/'build/pos-jogo').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'build/pos-jogo') as out,patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'}),contextlib.redirect_stdout(io.StringIO()):
            result=generate(package,out,execute=True,caller=caller)
        self.assertTrue(result['semantic_review_passed'])
        self.assertEqual(stages,['pos_jogo','pos_jogo','review_pos_jogo','review_pos_jogo'])
