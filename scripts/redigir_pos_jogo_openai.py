"""Teste isolado: uma chamada, sem publicação ou alteração de arquivos do site."""
import argparse
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from editorial_pos_jogo import ROOT, prepare, validate, render


def build_request(package, provider):
    schema = {'type':'object','additionalProperties':False,
        'properties':{'title':{'type':'string'},'excerpt':{'type':'string'},
        'blocks':{'type':'array','items':{'type':'object','additionalProperties':False,
        'properties':{'type':{'type':'string','enum':['paragraph','subtitle','list']},'text':{'type':'string'}},
        'required':['type','text']}}},'required':['title','excerpt','blocks']}
    facts = {k:v for k,v in package.items() if k != 'instructions'}
    return {'model':provider['model'],'store':False,'max_output_tokens':6000,
        'reasoning':{'effort':provider['reasoning_effort']},
        'input':[{'role':'system','content':package['instructions'] + '\nProtocolo interno: devolva title, excerpt e blocks no JSON exigido. O renderizador entregará texto comum ao leitor. Não acrescente fatos fora do pacote.'},
                 {'role':'user','content':json.dumps(facts,ensure_ascii=False)}],
        'text':{'format':{'type':'json_schema','name':'pos_jogo','strict':True,'schema':schema}}}


def parse_response(response):
    if response.get('status') != 'completed' or response.get('error'):
        raise ValueError('Resposta incompleta ou com erro; não liberada')
    chunks=[]
    for item in response.get('output',[]):
        if item.get('type') != 'message': continue
        for part in item.get('content',[]):
            if part.get('type') == 'refusal': raise ValueError('Recusa do modelo')
            if part.get('type') == 'output_text': chunks.append(part['text'])
    article=json.loads(''.join(chunks))
    if not isinstance(article,dict) or set(article) != {'title','excerpt','blocks'}:
        raise ValueError('Objeto editorial inválido')
    return article


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    read=lambda p:json.loads((ROOT/p).read_text())
    package=prepare(read('auditoria/pos-jogo/fatos-real-leipzig-20261021.json'),
        read('auditoria/pos-jogo/narrativa-real-leipzig-20261021.json'),
        read('auditoria/pos-jogo/links-autorizados-piloto.json'))
    provider=read('config/redacao-pre-jogo.json')['provider']
    request=build_request(package,provider)
    if len(json.dumps(package,ensure_ascii=False))>20000: raise ValueError('Pacote acima do limite')
    if not args.execute: print('Preparo validado; nenhuma chamada realizada');return
    key=os.environ.get('OPENAI_API_KEY','').strip()
    if not key: raise ValueError('OPENAI_API_KEY ausente no ambiente')
    out=ROOT/'build/pos-jogo/api';out.mkdir(parents=True,exist_ok=True)
    marker=out/'tentativa.json'
    if marker.exists(): raise ValueError('Teste já iniciado neste diretório; repetição bloqueada')
    marker.write_text(json.dumps({'attempts':1,'publication_enabled':False}))
    req=urllib.request.Request('https://api.openai.com/v1/responses',
        data=json.dumps(request).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=180) as response: result=json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'API retornou HTTP {exc.code}; sem repetição automática') from None
    metadata={'model':provider['model'],'response_id':result.get('id'),'status':result.get('status'),
        'usage':result.get('usage'),'automatic_model_run':True,'publication_enabled':False,
        'human_review_required':True,'fixture_id':package['facts']['fixture_id']}
    (out/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    article=parse_response(result)
    checks=validate(article,package['allowed_internal_urls'])
    (out/'artigo.json').write_text(json.dumps(article,ensure_ascii=False,indent=2))
    (out/'validacao.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
    print(json.dumps({'metadata':metadata,'validation':checks},ensure_ascii=False))
    print('INICIO DO RASCUNHO\n'+render(article)+'FIM DO RASCUNHO')
    if not checks['format_passed']: raise ValueError('Rascunho reprovado no formato; preservado para diagnóstico')

if __name__=='__main__':main()
