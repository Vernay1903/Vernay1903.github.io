"""Publicação automática autorizada: commit atômico, sem sobrescrever matérias."""
import base64,hashlib,io,json,os,subprocess,tempfile,zipfile
from datetime import datetime,date
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from zoneinfo import ZoneInfo
from estado_operacao_pos_jogo import RemoteState,REPO
from editorial_pos_jogo import prepare as editorial_prepare
from empacotar_redacao_pos_jogo import digest
from preparar_publicacao_pos_jogo import prepare
from operar_pos_jogo import validate_generated_package
from selecionar_pos_jogos import duplicate_reason,PILOT,FINAL
from executar_pos_jogo import fetch
from preparar_fatos_pos_jogo import match_outcome,match_goals
from confirmar_pages_pre_jogo import confirm
ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo('America/Sao_Paulo')

def validate_candidate(data,fid,job,config,now,months):
    facts,narr,article,meta=(data[k] for k in ('fatos.json','narrativa.json','redacao/artigo.json','redacao/metadata.json'))
    if job.get('status') not in ('package_ready','publication_pending'):raise ValueError('Rascunho não aprovado')
    if facts['fixture_id']!=fid or meta['fixture_id']!=fid or not facts['ready_for_drafting'] or not narr['reviewed']:raise ValueError('Apuração não validada')
    if not meta.get('semantic_review_passed') or not meta.get('format_passed'):raise ValueError('Revisão não aprovada')
    if not {facts['match']['home'],facts['match']['away']} & PILOT:raise ValueError('Fora dos quatro clubes')
    if set(config['clubs'])!=PILOT or not config['enabled']:raise ValueError('Publicação não autorizada')
    if not config['from_match_date']<=facts['match']['match_date']<=now.date().isoformat():raise ValueError('Partida fora da vigência autorizada')
    written=datetime.fromisoformat(meta['written_at']).astimezone(TZ)
    if written>now or (now-written).total_seconds()>172800:raise ValueError('Rascunho antigo; não publicar automaticamente')
    if any(g and g.get('date_brasilia','')<now.date().isoformat() for side in facts.get('upcoming',{}).values() for g in side.values()):raise ValueError('Agenda do rascunho já passou')
    calls=[c for m in months.values() for c in m.get('calls',[]) if c.get('fixture_id')==fid]
    if any(c.get('status')!='settled' for c in calls) or sum((Decimal(c['charged_usd']) for c in calls),Decimal(0))>Decimal('0.10'):raise ValueError('Orçamento não validado')
    urls=json.loads((ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json').read_text())
    package=editorial_prepare(facts,narr,urls)
    if digest(package)!=meta['package_sha256'] or digest(article)!=meta['article_sha256'] or job['package']['article_sha256']!=digest(article):raise ValueError('Conteúdo alterado após revisão')
    return facts,article,meta,urls

def load_data(remote,fid,job):
    required=('fatos.json','narrativa.json','redacao/artigo.json','redacao/metadata.json')
    root=ROOT/'build/pos-jogo/agendado'
    def matching_meta(meta):
        return meta.get('semantic_review_passed') is True and meta.get('article_sha256')==job['package']['article_sha256']
    candidates=[]
    for p in root.rglob('fatos.json'):
        meta=p.parent/'redacao/metadata.json'
        if p.parent.name==fid and meta.exists() and matching_meta(json.loads(meta.read_text())):candidates.append(p.parent)
    if len(candidates)==1:return {n:json.loads((candidates[0]/n).read_text()) for n in required}
    artifacts=remote.request('GET',f'/actions/runs/{job["run_id"]}/artifacts')['artifacts']
    selected=[a for a in artifacts if a['name']==job['artifact_name'] and not a['expired']]
    if len(selected)!=1 or selected[0]['size_in_bytes']>10000000:raise ValueError('Artefato ausente ou ambíguo')
    a=selected[0];raw=subprocess.check_output(['gh','api',f'repos/{REPO}/actions/artifacts/{a["id"]}/zip'],timeout=60)
    if 'sha256:'+hashlib.sha256(raw).hexdigest()!=a['digest']:raise ValueError('Artefato corrompido')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        prefix=[n[:-len('fatos.json')] for n in z.namelist() if n.endswith('/'+fid+'/fatos.json')]
        prefix=[p for p in prefix if p+'redacao/metadata.json' in z.namelist() and matching_meta(json.loads(z.read(p+'redacao/metadata.json')))]
        if len(prefix)!=1:raise ValueError('Candidato ambíguo no artefato')
        if any(z.getinfo(prefix[0]+n).file_size>4000000 for n in required):raise ValueError('Entrada excede limite')
        return {n:json.loads(z.read(prefix[0]+n)) for n in required}

def read_file(remote,path,ref):
    r=remote.request('GET',f'/contents/{path}?ref={ref}')
    return base64.b64decode(r['content']).decode('utf-8')

def publish_atomic(remote,fid,facts,article,meta,urls):
    receipt_path=f'auditoria/pos-jogo/publicados/{fid}.json'
    for attempt in range(3):
        head=remote.request('GET','/git/ref/heads/main')['object']['sha']
        commit=remote.request('GET',f'/git/commits/{head}')
        # Um recibo no mesmo commit dos arquivos permite recuperar falha de persistência.
        try:
            receipt=json.loads(read_file(remote,receipt_path,head))
        except HTTPError as e:
            if e.code!=404:raise
        else:
            if receipt['article_sha256']!=digest(article):raise ValueError('Recibo existente diverge; preservar edição')
            return dict(receipt,commit=head,recovered=True)
        tree=remote.request('GET',f'/git/trees/{commit["tree"]["sha"]}')['tree']
        files=[x['path'] for x in tree if x['type']=='blob']
        news=read_file(remote,'noticias.json',head);site_map=read_file(remote,'sitemap.xml',head)
        reason=duplicate_reason(dict(facts['match'],fixture_id=fid),json.loads(news))
        if reason:return {'status':'skipped','reason':reason}
        outputs=prepare(article,facts['match'],meta['written_at'],news,site_map,urls,files)
        report=json.loads(outputs['validacao.json'])
        # O construtor mantém suas travas locais; somente esta etapa faz o commit.
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'publicacao-teste';folder.mkdir()
            for name,content in outputs.items():(folder/name).write_text(content)
            validate_generated_package(temp,report)
        slug=report['filename']
        receipt={'fixture_id':fid,'article_sha256':digest(article),'url':slug,'written_at':meta['written_at'],'status':'publication_pending'}
        contents={k:v for k,v in outputs.items() if k!='validacao.json'}
        contents['noticias-home.json']=json.dumps(json.loads(contents['noticias.json'])[:10],ensure_ascii=False,indent=2)+'\n'
        contents[receipt_path]=json.dumps(receipt,ensure_ascii=False,indent=2)+'\n'
        new_tree=remote.request('POST','/git/trees',{'base_tree':commit['tree']['sha'],'tree':[{'path':p,'mode':'100644','type':'blob','content':v} for p,v in contents.items()]})
        new_commit=remote.request('POST','/git/commits',{'message':'Publicar resultado: '+article['title'],'tree':new_tree['sha'],'parents':[head]})
        try:
            remote.request('PATCH','/git/refs/heads/main',{'sha':new_commit['sha'],'force':False})
        except HTTPError as e:
            if e.code not in (409,422) or attempt==2:raise
            # Nova main exige reconstruir os índices; nunca forçar nem sobrescrever.
            continue
        return dict(receipt,commit=new_commit['sha'],recovered=False)
    raise ValueError('Main mudou repetidamente')

def main():
    cfg=json.loads((ROOT/'config/publicacao-pos-jogo.json').read_text());remote=RemoteState();now=datetime.now(TZ)
    if not cfg['enabled']:return
    remote.data['automatic_publication']={'enabled':True,'from_match_date':cfg['from_match_date'],'last_checked_at':now.isoformat()};remote.save()
    results=[];errors=[]
    for fid,job in list(remote.data['jobs'].items()):
        if job.get('status') not in ('package_ready','publication_pending'):continue
        match_date=remote.data['timing']['fixtures'].get(fid,{}).get('match_date','')
        # Um commit pendente já passou pelas regras de vigência.
        # A seleção pode remover o jogo após encontrá-lo em noticias.json.
        if job.get('status')!='publication_pending' and match_date<cfg['from_match_date']:continue
        try:
            if job.get('status')=='publication_pending':
                receipt=job['publication']
            else:
                data=load_data(remote,fid,job)
                facts,article,meta,urls=validate_candidate(data,fid,job,cfg,now,remote.data['months'])
                source=next(s['url'] for s in facts['sources'] if '/summary?' in s['url'])
                live=fetch(source);comp=live['header']['competitions'][0]
                if 'espn-'+str(live['header']['id'])!=fid or not comp['status']['type']['completed'] or comp['status']['type']['name'] not in FINAL or match_outcome(comp)['match_score']!=facts['score']:raise ValueError('Resultado final mudou')
                if [(g['side'],g['scorer'],bool(g.get('own_goal'))) for g in match_goals(comp)]!=[(g['side'],g['scorer'],bool(g.get('own_goal'))) for g in facts['goals']]:raise ValueError('Autores dos gols mudaram')
                receipt=publish_atomic(remote,fid,facts,article,meta,urls)
                if receipt['status']=='skipped':
                    job['publication_skip']=receipt;remote.save();results.append(dict(fixture_id=fid,**receipt));continue
                job.update(status='publication_pending',publication=receipt);remote.save()
            confirm(REPO,receipt['commit'],'https://cortedosesportes.com.br',[receipt['url']],timeout=300)
            job.update(status='published',published_at=datetime.now(TZ).isoformat());job.pop('publication_error',None);remote.save()
            results.append({'fixture_id':fid,'status':'published','url':receipt['url'],'commit':receipt['commit']})
        except Exception as exc:
            job['publication_error']=str(exc);remote.save();errors.append({'fixture_id':fid,'error':str(exc)})
    report={'enabled':True,'results':results,'errors':errors,'checked_at':now.isoformat(),'from_match_date':cfg['from_match_date']}
    out=ROOT/'build/pos-jogo/agendado/publicacao.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('\nPublicação automática ATIVA. Resultados: '+json.dumps(results,ensure_ascii=False)+'\nErros: '+json.dumps(errors,ensure_ascii=False)+'\n')
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
