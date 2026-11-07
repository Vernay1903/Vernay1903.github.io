"""Retoma uma única vez o texto curto verificável, sem redescobrir fatos nem publicar."""
import hashlib,io,json,os,re,subprocess,zipfile
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
from corrigir_assistencia_pos_jogo import correct_candidate
TZ=ZoneInfo('America/Sao_Paulo')
def load_previous(remote,run,fid,day,approved=False,checkpoint=False):
    if not str(run).isdigit():raise ValueError('Execução anterior inválida')
    artifacts=remote.request('GET',f'/actions/runs/{run}/artifacts')['artifacts']
    records=[a for a in artifacts if a['name'].startswith(f'pos-jogo-rascunhos-{run}-') and not a['expired']]
    if len(records)!=1 or records[0]['size_in_bytes']>5000000:raise ValueError('Artefato de origem indisponível ou ambíguo')
    a=records[0]
    raw=subprocess.check_output(['gh','api',f'repos/{REPO}/actions/artifacts/{a["id"]}/zip'],timeout=45)
    if 'sha256:'+hashlib.sha256(raw).hexdigest()!=a['digest']:raise ValueError('Integridade do artefato divergente')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        resumed=f'retomada/{fid}/fatos.json' in z.namelist()
        def get(path):
            n=('retomada/'+path) if resumed else ('execucao/'+day+'/'+path)
            if z.getinfo(n).file_size>4000000:raise ValueError('Entrada muito grande')
            return json.loads(z.read(n))
        candidate=None if resumed else next(c for c in get('selecao.json')['selected'] if c['fixture_id']==fid)
        facts,narrative,package=[get(fid+'/'+f) for f in ('fatos.json','narrativa.json','pacote.json')]
        if checkpoint:
            prefix=f'execucao/{day}/{fid}/redacao/artigo-'
            versions=[int(n[len(prefix):-5]) for n in z.namelist() if n.startswith(prefix) and re.fullmatch(r'[0-9]+\.json',n[len(prefix):])]
            if not versions:raise ValueError('Nenhum rascunho recuperável')
            v=max(versions);article=get(fid+f'/redacao/artigo-{v}.json')
            if not get(fid+f'/redacao/formato-{v}.json')['format_passed']:raise ValueError('Última versão não passou no formato')
        else:
            article=get(fid+'/redacao/artigo.json');meta=get(fid+'/redacao/metadata.json')
            if not (meta['fixture_id']==fid and meta['article_sha256']==digest(article) and meta['package_sha256']==digest(package)
                    and meta['semantic_review_passed'] is approved):raise ValueError('Metadados divergentes')
    if not (facts['fixture_id']==fid==narrative['fixture_id'] and facts['ready_for_drafting'] and narrative['reviewed']):
        raise ValueError('Arquivo não corresponde à apuração revisada')
    reconstructed=prepare(facts,narrative,package['allowed_internal_urls'])
    if any(reconstructed[k]!=package[k] for k in ('facts','narrative_facts','allowed_internal_urls')):raise ValueError('Fatos não correspondem ao pacote original')
    if candidate is None:
        candidate=dict(facts['match'],fixture_id=fid,source_url=next(s['url'] for s in facts['sources'] if '/summary?' in s['url']))
    return candidate,facts,narrative,article
def main():
    remote=RemoteState();now=datetime.now(TZ);site=Path('current-main')
    out=ROOT/'build/pos-jogo/agendado/retomada';cfg=read(ROOT/'config/operacao-pos-jogo.json')
    if cfg['publication_enabled'] or budget_status(remote.data,cfg,now):raise ValueError('Operação ou orçamento bloqueado')
    for fid,j in list(remote.data['jobs'].items()):
        assist_check=(j.get('status')=='package_ready' and not j.get('assist_attribution_checked') and j.get('operation_mode')=='scheduled_drafts')
        schema_retry=(j.get('status')=='blocked' and j.get('reason')=='Revisão incompleta ou unidades duplicadas' and j.get('previous_editorial_run') and not j.get('schema_retry'))
        approved=(j.get('status')=='package_ready' and not j.get('collective_recap_checked') and j.get('operation_mode')=='scheduled_drafts')
        checkpoint=(j.get('status')=='blocked' and j.get('reason') in ('Limite de chamadas da partida','Trecho reprovado não foi corrigido') and not j.get('last_review_retry'))
        if not assist_check and not schema_retry and not approved and not checkpoint and (j.get('status')!='blocked' or j.get('length_retry') or j.get('reason')!='Revisão factual/editorial reprovada após limite de correções'):continue
        timing=remote.data['timing']['fixtures'].get(fid,{})
        day=timing.get('match_date','')
        if day not in {(now.date()-timedelta(days=v)).isoformat() for v in ((0,1,2) if schema_retry or assist_check else (0,1))}:continue
        c,facts,narr,a=load_previous(remote,j['previous_editorial_run'] if schema_retry else j['run_id'],fid,day,approved=approved or bool(schema_retry) or assist_check,checkpoint=checkpoint)
        if schema_retry:a=remove_collective_recap(a)
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
        if assist_check:
            revised_narr,revised_article=correct_candidate(narr,a,live.get('commentary',[]))
            if revised_narr==narr and revised_article==a:
                j['assist_attribution_checked']=True;remote.save()
                if not approved and not schema_retry and not checkpoint:continue
            else:narr,a=revised_narr,revised_article
        if any(game and game.get('date_brasilia','')<=now.date().isoformat() for side in facts['upcoming'].values() for game in side.values()):continue
        urls=read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
        package=prepare(facts,narr,urls);checks=validate(a,urls)
        if (checks['errors']!=['Corpo com menos de 600 palavras'] and not ((approved or checkpoint or schema_retry or assist_check) and not checks['errors'])) or checks['body_words']<400 or coverage_errors(a,package):continue
        if assist_check:j['assist_attribution_checked']=True
        if schema_retry:j['schema_retry']=True
        if checkpoint:j['last_review_retry']=True
        if approved:j['collective_recap_checked']=True
        previous=j['run_id'];j.update(status='running',length_retry=True,previous_editorial_run=previous,run_id=os.environ['GITHUB_RUN_ID']);remote.save()
        try:
            directory=out/fid;save(directory/'fatos.json',facts);save(directory/'narrativa.json',narr)
            save(directory/'pacote.json',package)
            caller=BudgetCaller(remote,fid,config=dict(cfg,max_paid_calls_per_fixture=min(28,j['api_calls']+6)))
            generate(package,directory/'redacao',execute=True,caller=caller,seed_article=a,review_seed=approved or checkpoint or bool(schema_retry) or assist_check)
            report=package_reviewed(directory,site,urls);validate_generated_package(directory,report)
            j.update(status='package_ready',package=report,artifact_name=os.environ['POS_JOGO_ARTIFACT_NAME'],review_run_url=f'https://github.com/{REPO}/actions/runs/'+j['run_id'])
            j.pop('reason',None);j['collective_recap_checked']=True
        except Exception as e:
            j.update(status='blocked',reason=str(e));raise
        finally:
            j['finished_at']=datetime.now(TZ).isoformat();remote.save();save(out/'resultado.json',j)
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as fp:fp.write('has_drafts=true\n')
        # Cada partida possui sua própria reserva, trava e saída.
if __name__=='__main__':main()
