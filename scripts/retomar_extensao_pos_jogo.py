"""Retoma uma única vez o texto curto verificável, sem redescobrir fatos nem publicar."""
import hashlib,io,json,os,subprocess,zipfile
from datetime import datetime,date,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from custos_pos_jogo import BudgetCaller
from estado_operacao_pos_jogo import RemoteState,REPO
from preparar_fatos_pos_jogo import match_outcome,match_goals,pair
from selecionar_pos_jogos import duplicate_reason,FINAL
from operar_pos_jogo import validate_generated_package
from executar_pos_jogo import ROOT,read,save,fetch
from editorial_pos_jogo import prepare,validate,coverage_errors
from redigir_pos_jogo_openai import generate,remove_collective_recap
from empacotar_redacao_pos_jogo import digest,package_reviewed
from agendar_pos_jogo import budget_status
TZ=ZoneInfo('America/Sao_Paulo')
def load_previous(remote,run,fid,day,approved=False):
    if not str(run).isdigit():raise ValueError('Execução anterior inválida')
    artifacts=remote.request('GET',f'/actions/runs/{run}/artifacts')['artifacts']
    records=[a for a in artifacts if a['name'].startswith(f'pos-jogo-rascunhos-{run}-') and not a['expired']]
    if len(records)!=1 or records[0]['size_in_bytes']>5000000:raise ValueError('Artefato de origem indisponível ou ambíguo')
    a=records[0]
    raw=subprocess.check_output(['gh','api',f'repos/{REPO}/actions/artifacts/{a["id"]}/zip'],timeout=45)
    if 'sha256:'+hashlib.sha256(raw).hexdigest()!=a['digest']:raise ValueError('Integridade do artefato divergente')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        def get(path):
            n='execucao/'+day+'/'+path
            if z.getinfo(n).file_size>4000000:raise ValueError('Entrada muito grande')
            return json.loads(z.read(n))
        candidate=next(c for c in get('selecao.json')['selected'] if c['fixture_id']==fid)
        facts,narrative,package,article,meta=[get(fid+'/'+f) for f in ('fatos.json','narrativa.json','pacote.json','redacao/artigo.json','redacao/metadata.json')]
    if not (meta['fixture_id']==fid==facts['fixture_id']==narrative['fixture_id'] and meta['article_sha256']==digest(article)
            and meta['package_sha256']==digest(package) and meta['semantic_review_passed'] is approved
            and facts['ready_for_drafting'] and narrative['reviewed']):raise ValueError('Arquivo não corresponde à apuração revisada')
    reconstructed=prepare(facts,narrative,package['allowed_internal_urls'])
    if any(reconstructed[k]!=package[k] for k in ('facts','narrative_facts','allowed_internal_urls')):raise ValueError('Fatos não correspondem ao pacote original')
    return candidate,facts,narrative,article
def main():
    remote=RemoteState();now=datetime.now(TZ);site=Path('current-main')
    out=ROOT/'build/pos-jogo/agendado/retomada';cfg=read(ROOT/'config/operacao-pos-jogo.json')
    if cfg['publication_enabled'] or budget_status(remote.data,cfg,now):raise ValueError('Operação ou orçamento bloqueado')
    for fid,j in list(remote.data['jobs'].items()):
        approved=(j.get('status')=='package_ready' and not j.get('collective_recap_checked') and j.get('operation_mode')=='scheduled_drafts')
        if not approved and (j.get('status')!='blocked' or j.get('length_retry') or j.get('reason')!='Revisão factual/editorial reprovada após limite de correções'):continue
        timing=remote.data['timing']['fixtures'].get(fid,{})
        day=timing.get('match_date','')
        if day not in {(now.date()-timedelta(days=v)).isoformat() for v in (0,1)}:continue
        c,facts,narr,a=load_previous(remote,j['run_id'],fid,day,approved=approved)
        if approved:
            cleaned=remove_collective_recap(a)
            if cleaned==a:
                j['collective_recap_checked']=True;remote.save();continue
            a=cleaned
        if duplicate_reason(c,read(site/'noticias.json')):continue
        live=fetch(c['source_url']);h=live['header'];comp=h['competitions'][0]
        if ('espn-'+str(h['id'])!=fid or comp['status']['type']['name'] not in FINAL or not comp['status']['type']['completed']
            or match_outcome(comp)['match_score']!=facts['score']):raise ValueError('Placar ou encerramento mudou')
        if [(g['side'],g['scorer'],bool(g.get('own_goal'))) for g in match_goals(comp)]!=[(g['side'],g['scorer'],bool(g.get('own_goal'))) for g in facts['goals']]:
            raise ValueError('Autores dos gols mudaram; requer nova apuração')
        if any(game and game.get('date_brasilia','')<=now.date().isoformat() for side in facts['upcoming'].values() for game in side.values()):continue
        urls=read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
        package=prepare(facts,narr,urls);checks=validate(a,urls)
        if (checks['errors']!=['Corpo com menos de 600 palavras'] and not (approved and not checks['errors'])) or checks['body_words']<400 or coverage_errors(a,package):continue
        if approved:j['collective_recap_checked']=True
        previous=j['run_id'];j.update(status='running',length_retry=True,previous_editorial_run=previous,run_id=os.environ['GITHUB_RUN_ID']);remote.save()
        try:
            directory=out/fid;save(directory/'fatos.json',facts);save(directory/'narrativa.json',narr)
            save(directory/'pacote.json',package)
            caller=BudgetCaller(remote,fid,config=dict(cfg,max_paid_calls_per_fixture=min(18,j['api_calls']+5)))
            generate(package,directory/'redacao',execute=True,caller=caller,seed_article=a,review_seed=approved)
            report=package_reviewed(directory,site,urls);validate_generated_package(directory,report)
            j.update(status='package_ready',package=report,artifact_name=os.environ['POS_JOGO_ARTIFACT_NAME'],review_run_url=f'https://github.com/{REPO}/actions/runs/'+j['run_id'])
            j.pop('reason',None)
        except Exception as e:
            j.update(status='blocked',reason=str(e));raise
        finally:
            j['finished_at']=datetime.now(TZ).isoformat();remote.save();save(out/'resultado.json',j)
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as fp:fp.write('has_drafts=true\n')
        break
if __name__=='__main__':main()
