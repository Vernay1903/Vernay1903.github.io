"""Continuação única com fonte oficial EFL; preserva chamadas e saldo anteriores."""
import json,os
from datetime import datetime
from pathlib import Path
from estado_operacao_pos_jogo import RemoteState
from custos_pos_jogo import BudgetCaller
from executar_pos_jogo import ROOT,read,save,fetch
from preparar_fatos_pos_jogo import pair,when,match_outcome,BASE,TZ
from apurar_pos_jogo import apurar
from editorial_pos_jogo import prepare
from redigir_pos_jogo_openai import generate
from empacotar_redacao_pos_jogo import package_reviewed

def main():
 fid='espn-401921835';remote=RemoteState();job=remote.data['jobs'][fid]
 if job.get('run_id')!='40685735443' or job.get('status')!='blocked' or remote.data.get('step15_sources_retry'):
  raise ValueError('Continuação não autorizada ou já usada')
 remote.data['step15_sources_retry']={'run_id':os.environ['GITHUB_RUN_ID'],'previous_job':dict(job)}
 remote.save()
 old=ROOT/'build/pos-jogo/passo15-anterior/2026-10-27'
 c=next(c for c in read(old/'selecao.json')['selected'] if c['fixture_id']==fid)
 summary=fetch(c['source_url']);now=datetime.now(TZ)
 archived=next(read(p)['data'] for p in (old/'coleta').glob('*.json') if read(p)['url']==c['source_url'])
 if match_outcome(summary['header']['competitions'][0])!=match_outcome(archived['header']['competitions'][0]):
  raise ValueError('Desfecho mudou: nova espera necessária')
 prior=next(r for r in read(old/'relatorio.json')['results'] if r['fixture_id']==fid)
 if prior['timing']['eligible'] is not True or now<when(prior['timing']['eligible_at']):raise ValueError('Espera incompleta')
 schedules={str(t['team']['id']):fetch(f"{BASE}/all/teams/{t['team']['id']}/schedule?fixture=true&season={now.year}") for t in pair(summary['header']['competitions'][0]).values()}
 out=ROOT/'build/pos-jogo/passo15-completo';out.mkdir(parents=True,exist_ok=False)
 discovery={'output':[{'type':'web_search_call','action':{'sources':[{'url':u} for u in [
  'https://www.efl.com/news/2026/october/28/carabao-cup--fleetwood-town-shock-arsenal-in-shootout-win/',
  'https://www.espn.com/soccer/report/_/gameId/401921835']]}}]}
 save(out/'fontes-adicionadas.json',{'method':'explicit_sources_opened_again','discovery':discovery})
 job.update(status='running',continuation_run_id=os.environ['GITHUB_RUN_ID']);remote.save()
 try:
  caller=BudgetCaller(remote,fid)
  facts,narrative=apurar(c,summary,schedules,out/'apuracao',now,caller=caller,discovery=discovery)
  save(out/'fatos.json',facts);save(out/'narrativa.json',narrative)
  links=read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
  package=prepare(facts,narrative,links);save(out/'pacote.json',package)
  generate(package,out/'redacao',execute=True,caller=caller)
  result=package_reviewed(out,ROOT/'current-main',links)
  job.update(status='package_ready',package=result,review_run_url='https://github.com/Vernay1903/Vernay1903.github.io/actions/runs/'+os.environ['GITHUB_RUN_ID'])
  save(out/'resultado.json',{'package':result,'publication_enabled':False})
  print(json.dumps(result,ensure_ascii=False))
 except Exception as exc:
  job.update(status='blocked',reason=str(exc));save(out/'erro.json',{'reason':str(exc)});raise
 finally:
  job['finished_at']=datetime.now(TZ).isoformat();remote.save()
if __name__=='__main__':main()
