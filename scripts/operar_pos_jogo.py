"""Execução persistente do piloto; prepara artefatos, nunca publica."""
import argparse,json,os,time
from datetime import datetime,timedelta,date
from pathlib import Path
from zoneinfo import ZoneInfo
import executar_pos_jogo as pipeline
from apurar_pos_jogo import apurar
from redigir_pos_jogo_openai import generate
from estado_operacao_pos_jogo import RemoteState
from custos_pos_jogo import BudgetCaller
from tempo_pos_jogo import dates_to_check,load_state,save_state
TZ=ZoneInfo('America/Sao_Paulo')


def run_once(remote,site,out,*,clock=None,runner=pipeline.run,researcher=apurar,writer=generate,caller_factory=BudgetCaller,operation_mode="test"):
 clock=clock or (lambda:datetime.now(TZ));now=clock();out=Path(out).resolve();site=Path(site).resolve()
 if not out.is_relative_to((pipeline.ROOT/'build/pos-jogo').resolve()):raise ValueError('Saída fora do piloto')
 if out.exists():raise ValueError('Diretório de execução já utilizado')
 out.mkdir(parents=True)
 state=out/'tempo.json';save_state(state,remote.data['timing'])
 budget={'research':0,'articles':0};reports=[];active={}
 def research(candidate,summary,schedules,directory,observed_at):
  fid=candidate['fixture_id']
  if fid in remote.data['jobs']:raise ValueError('Tentativa já registrada; não repetir API')
  remote.data['jobs'][fid]={'status':'running','started_at':clock().isoformat(),
    'run_id':os.environ.get('GITHUB_RUN_ID'),'api_calls':0,'operation_mode':operation_mode}
  remote.data['timing']=load_state(state);remote.save()
  active[fid]=caller_factory(remote,fid)
  return researcher(candidate,summary,schedules,directory,observed_at,caller=active[fid])
 def draft(package,directory,**kwargs):
  return writer(package,directory,**kwargs,caller=active[package['facts']['fixture_id']])
 try:
  for day in dates_to_check(now):
   # Destinos atuais lidos novamente por data e pelo empacotador.
   report=runner(day,pipeline.read(site/'noticias.json'),out/day.isoformat(),
    execute=True,auto_research=True,query=pipeline.fetch,writer=draft,researcher=research,
    now=now,timing_state=state,work_budget=budget,site_root=site,processed=set(remote.data['jobs']))
   reports.append(report)
   for row in report['results']:
    fid=row['fixture_id']
    if fid in active:
     remote.data['jobs'][fid].update(status=row['status'],finished_at=clock().isoformat())
     if 'package' in row:
      remote.data['jobs'][fid]['package']=row['package']
      remote.data['jobs'][fid]['artifact_name']=os.environ.get('POS_JOGO_ARTIFACT_NAME')
      remote.data['jobs'][fid]['review_run_url']='https://github.com/Vernay1903/Vernay1903.github.io/actions/runs/'+os.environ.get('GITHUB_RUN_ID','')
   remote.data['timing']=load_state(state);remote.save()
 finally:
  for fid in active:
   if remote.data['jobs'][fid].get('status')=='running':
    remote.data['jobs'][fid].update(status='interrupted',finished_at=clock().isoformat(),reason='Execução interrompida; repetição automática bloqueada')
  remote.data['timing']=load_state(state);remote.save()
  pipeline.save(out/'operacao.json',{'reports':reports,'publication_enabled':False,
    'shared_pre_match_budget_reconciled':False,'state_branch':'estado-pos-jogo-piloto'})
 return reports


def wait_until_eligible(remote):
 cfg=pipeline.read(pipeline.ROOT/'config/tempo-pos-jogo.json')
 now=datetime.now(TZ)
 pending=[datetime.fromisoformat(v['first_final_seen_at'])+timedelta(minutes=cfg['wait_minutes'])
   for fid,v in remote.data['timing']['fixtures'].items() if fid not in remote.data['jobs']]
 if not pending:return
 target=min(pending)
 if (target-now).total_seconds()>3600:raise ValueError('Espera acima do limite do teste')
 print('Teste único aguardando até '+target.isoformat(),flush=True)
 while (remaining:=(target-datetime.now(TZ)).total_seconds())>0:
  time.sleep(min(30,remaining))


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--site-root',required=True,type=Path)
 p.add_argument('--output',required=True,type=Path);p.add_argument('--test-once',action='store_true');p.add_argument('--wait-once',action='store_true')
 a=p.parse_args();cfg=pipeline.read(pipeline.ROOT/'config/operacao-pos-jogo.json')
 if cfg['publication_enabled']:raise ValueError('Publicação não autorizada nesta etapa')
 if not a.test_once:raise ValueError('Operação contínua ainda bloqueada: conciliar orçamento compartilhado')
 remote=RemoteState()
 if a.wait_once:wait_until_eligible(remote)
 result=run_once(remote,a.site_root,a.output)
 print(json.dumps(result,ensure_ascii=False))
 if any(r['status'] in {'pending','collection_failed'} for r in result):raise SystemExit(1)

if __name__=='__main__':main()
