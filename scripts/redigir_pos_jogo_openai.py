"""Redação, revisão factual e correção limitada; publicação permanece bloqueada."""
import argparse
from datetime import datetime, timezone
from empacotar_redacao_pos_jogo import digest
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from editorial_pos_jogo import ROOT, prepare, validate, render
from revisar_pos_jogo import review_request, validate_review, patch_request, apply_patch, units


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


def generate(package, out, *, execute=False, calibrate=False, caller=None):
    read=lambda p:json.loads((ROOT/p).read_text())
    provider=read('config/redacao-pos-jogo.json')['provider']
    request=build_request(package,provider)
    if len(json.dumps(package,ensure_ascii=False))>20000: raise ValueError('Pacote acima do limite')
    if not execute: print('Preparo validado; nenhuma chamada realizada');return
    if caller is None:raise ValueError('Redação paga exige controlador persistente de orçamento')
    key=os.environ.get('OPENAI_API_KEY','').strip()
    if not key: raise ValueError('OPENAI_API_KEY ausente no ambiente')
    out=Path(out).resolve()
    if not out.is_relative_to((ROOT/'build/pos-jogo').resolve()):raise ValueError('Saída fora do diretório do piloto')
    out.mkdir(parents=True,exist_ok=True)
    marker=out/'tentativa.json'
    if marker.exists(): raise ValueError('Teste já iniciado neste diretório; repetição bloqueada')
    marker.write_text(json.dumps({'max_calls':7,'publication_enabled':False}))
    calls=[]
    def save(name,obj): (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    def call(payload, stage):
        if len(calls)>=7: raise ValueError('Limite total de chamadas atingido')
        req=urllib.request.Request('https://api.openai.com/v1/responses',
            data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
        calls.append({'stage':stage,'status':'started'})
        save('chamadas.json',calls)
        try:
            if caller:result=caller(payload)
            else:
                with urllib.request.urlopen(req,timeout=180) as response: result=json.load(response)
        except urllib.error.HTTPError as exc:
            calls[-1]['status']=f'http_{exc.code}';save('chamadas.json',calls)
            raise ValueError(f'API retornou HTTP {exc.code}; sem repetição automática') from None
        calls[-1].update({'response_id':result.get('id'),'status':result.get('status'),'usage':result.get('usage')})
        save('chamadas.json',calls)
        return result
    if calibrate:
        calibration={'title':'Real Madrid 4 x 1 Leipzig', 'excerpt':'Bernardo Silva abriu o placar antes do intervalo.', 'blocks':[
            {'type':'paragraph','text':'Mbappé descontou para o Leipzig aos 83 minutos.'},
            {'type':'paragraph','text':'O Leipzig recebe o Elversberg em casa e, nessa partida, poderá encerrar sua sequência de derrotas fora de casa.'},
            {'type':'paragraph','text':'O Barcelona recebe o Real Madrid em 25 de outubro, no Spotify Camp Nou, pela décima rodada de LaLiga.'}]}
        calibration_review=response_object(call(review_request(package,calibration,provider),'calibration'))
        validate_review(calibration_review,package,calibration)
        mapped={c['unit']:c['supported'] for c in calibration_review['checks']}
        calibration_passed=(mapped=={'title':True,'excerpt':True,'block_0':False,'block_1':False,'block_2':True})
        save('calibracao.json',{'passed':calibration_passed,'review':calibration_review})
        print('Calibração factual: '+str(calibration_passed),flush=True)
        if not calibration_passed:raise ValueError('Revisor não distinguiu erros conhecidos de fatos sustentados')
    article=None; issues=[]; passed=False
    for attempt in range(1,4):
        if article is not None and all(s.split(':',1)[0] in units(article) for s in issues):
            patch=response_object(call(patch_request(package,article,issues,provider),f'patch_{attempt}'))
            save(f'correcao-{attempt}.json',patch)
            article=apply_patch(article,patch,issues)
        else:
            request=build_request(package,provider)
            if article is not None:
                request['input'].append({'role':'user','content':json.dumps({'draft':article,'issues':issues,
                    'instruction':'Corrija as falhas de formato mantendo fatos e narrativa corretos. Retorne texto completo.'},ensure_ascii=False)})
            article=parse_response(call(request,f'write_{attempt}'))
        written_at=datetime.now(timezone.utc).isoformat()
        save(f'artigo-{attempt}.json',article)
        checks=validate(article,package['allowed_internal_urls'])
        review=response_object(call(review_request(package,article,provider),f'review_{attempt}'))
        save(f'revisao-{attempt}.json',review)
        issues=checks['errors']+validate_review(review,package,article)
        if attempt==1 and not calibrate:
            second=response_object(call(review_request(package,article,provider),'review_1_second_pass'))
            save('revisao-1-segunda-leitura.json',second)
            issues=list(dict.fromkeys(issues+validate_review(second,package,article)))
        print(json.dumps({'attempt':attempt,'issues':issues},ensure_ascii=False),flush=True)
        if not issues:
            passed=True;break
    metadata={'model':provider['model'],'automatic_model_run':True,'publication_enabled':False,
        'human_review_required':True,'fixture_id':package['facts']['fixture_id'],
        'semantic_review_passed':passed,'calls':calls,
        'format_passed':checks['format_passed'],'written_at':written_at,
        'article_sha256':digest(article),'package_sha256':digest(package)}
    save('metadata.json',metadata);save('artigo.json',article);save('validacao.json',checks)
    print(json.dumps({'metadata':metadata,'validation':checks},ensure_ascii=False))
    print('INICIO DO RASCUNHO\n'+render(article)+'FIM DO RASCUNHO',flush=True)
    if not passed:raise ValueError('Revisão factual/editorial reprovada após limite de correções')
    return metadata

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['facts','narrative','links']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'build/pos-jogo/api')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--calibrate',action='store_true',help='Somente com o pacote de calibração Real x Leipzig')
    args=parser.parse_args()
    read=lambda p:json.loads(p.read_text())
    package=prepare(read(args.facts),read(args.narrative),read(args.links))
    if args.calibrate and package['facts']['fixture_id']!='espn-401915313':raise ValueError('Calibração com partida incompatível')
    generate(package,args.output_dir,execute=args.execute,calibrate=args.calibrate)

if __name__=='__main__':main()
