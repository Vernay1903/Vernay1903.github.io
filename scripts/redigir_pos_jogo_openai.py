"""Redação, revisão factual e correção limitada; publicação permanece bloqueada."""
import argparse
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from editorial_pos_jogo import ROOT, prepare, validate, render
from revisar_pos_jogo import review_request, validate_review


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


def response_object(response):
    if response.get('status') != 'completed' or response.get('error'):
        raise ValueError('Resposta incompleta ou com erro; não liberada')
    chunks=[]
    for item in response.get('output',[]):
        if item.get('type') != 'message': continue
        for part in item.get('content',[]):
            if part.get('type') == 'refusal': raise ValueError('Recusa do modelo')
            if part.get('type') == 'output_text': chunks.append(part['text'])
    article=json.loads(''.join(chunks))
    return article


def parse_response(response):
    article=response_object(response)
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
    marker.write_text(json.dumps({'max_calls':6,'publication_enabled':False}))
    calls=[]
    def save(name,obj): (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    def call(payload, stage):
        if len(calls)>=6: raise ValueError('Limite total de chamadas atingido')
        req=urllib.request.Request('https://api.openai.com/v1/responses',
            data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
        calls.append({'stage':stage,'status':'started'})
        save('chamadas.json',calls)
        try:
            with urllib.request.urlopen(req,timeout=180) as response: result=json.load(response)
        except urllib.error.HTTPError as exc:
            calls[-1]['status']=f'http_{exc.code}';save('chamadas.json',calls)
            raise ValueError(f'API retornou HTTP {exc.code}; sem repetição automática') from None
        calls[-1].update({'response_id':result.get('id'),'status':result.get('status'),'usage':result.get('usage')})
        save('chamadas.json',calls)
        return result
    article=None; issues=[]; passed=False
    for attempt in range(1,4):
        request=build_request(package,provider)
        if article is not None:
            request['input'].append({'role':'user','content':json.dumps({
                'revision_instruction':'Corrija somente os problemas apontados. Preserve informações corretas e o estilo. Não acrescente fatos; mantenha pelo menos 600 palavras com desenvolvimento dos fatos disponíveis. Retorne a matéria completa.',
                'draft':article,'issues':issues},ensure_ascii=False)})
        article=parse_response(call(request,f'write_{attempt}'))
        save(f'artigo-{attempt}.json',article)
        checks=validate(article,package['allowed_internal_urls'])
        review=response_object(call(review_request(package,article,provider),f'review_{attempt}'))
        save(f'revisao-{attempt}.json',review)
        issues=checks['errors']+validate_review(review,package,article)
        print(json.dumps({'attempt':attempt,'issues':issues},ensure_ascii=False),flush=True)
        if not issues:
            passed=True;break
    metadata={'model':provider['model'],'automatic_model_run':True,'publication_enabled':False,
        'human_review_required':True,'fixture_id':package['facts']['fixture_id'],
        'semantic_review_passed':passed,'calls':calls}
    save('metadata.json',metadata);save('artigo.json',article);save('validacao.json',checks)
    print(json.dumps({'metadata':metadata,'validation':checks},ensure_ascii=False))
    print('INICIO DO RASCUNHO\n'+render(article)+'FIM DO RASCUNHO')
    if not passed:raise ValueError('Revisão factual/editorial reprovada após limite de correções')

if __name__=='__main__':main()
