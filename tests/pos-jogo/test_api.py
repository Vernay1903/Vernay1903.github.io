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
