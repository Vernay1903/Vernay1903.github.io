"""Recuperação única com URL oficial localizada; conserva orçamento e revisões."""
import json,os,copy
from datetime import datetime,date
from pathlib import Path
from zoneinfo import ZoneInfo
import executar_pos_jogo as pipeline
from estado_operacao_pos_jogo import RemoteState
from custos_pos_jogo import BudgetCaller
from apurar_pos_jogo import apurar
from redigir_pos_jogo_openai import generate
from tempo_pos_jogo import save_state,load_state
FID='espn-401882819'
URLS=['https://www.realmadrid.com/es-ES/noticias/futbol/primer-equipo/cronicas/cronica-racing-rm-j11-liga-01-11-2026','https://www.realmadrid.com/es-ES/noticias/futbol/primer-equipo/actualidad/once-inicial-del-real-madrid-frente-al-racing-01-11-2026']
def main():
 remote=RemoteState();job=remote.data['jobs'][FID]
 if job.get('status')!='blocked' or job.get('run_id')!='41344445496' or job.get('api_calls')!=1 or job.get('source_recovery_started'):raise ValueError('Recuperação repetida ou estado divergente')
 out=pipeline.ROOT/'build/pos-jogo/real-recuperacao20';out.mkdir(parents=True,exist_ok=False)
 state=out/'tempo.json';save_state(state,remote.data['timing'])
 original=copy.deepcopy(job);job.update(source_recovery_started=True,source_recovery_run_id=os.environ['GITHUB_RUN_ID'])
 remote.save();caller=BudgetCaller(remote,FID)
 def research(candidate,summary,schedules,directory,now):
  if candidate['fixture_id']!=FID:raise ValueError('Jogo fora da recuperação')
  job['status']='running';remote.save()
  discovery={'output':[{'type':'web_search_call','action':{'sources':[{'url':u} for u in URLS]}}]}
  directory.mkdir(parents=True,exist_ok=True)
  pipeline.save(directory/'origem-links.json',{'method':'operator_located_official_urls','urls':URLS,'fresh_open_required':True,'automatic_source_discovery_passed':False})
  return apurar(candidate,summary,schedules,directory,now,caller=caller,discovery=discovery)
 def writer(package,directory,**kwargs):return generate(package,directory,caller=caller,**kwargs)
 try:
  report=pipeline.run(date(2026,11,1),pipeline.read(Path('current-main/noticias.json')),out/'execucao',execute=True,auto_research=True,now=datetime.now(ZoneInfo('America/Sao_Paulo')),researcher=research,writer=writer,timing_state=state,site_root=Path('current-main'),processed=set(remote.data['jobs'])-{FID})
  rows=[r for r in report['results'] if r['fixture_id']==FID]
  if len(rows)!=1:raise ValueError('Jogo não selecionado; não forçar duplicata')
  row=rows[0];job.update(status=row['status'],source_recovery_result=row)
  if row['status']=='package_ready':job.update(package=row['package'],artifact_name='pos-jogo-real-recuperacao20-'+os.environ['GITHUB_RUN_ID'],review_run_url='https://github.com/Vernay1903/Vernay1903.github.io/actions/runs/'+os.environ['GITHUB_RUN_ID'])
  if row['status']!='package_ready':raise ValueError(row.get('reason',row['status']))
 finally:
  if job['status']=='running':job['status']='blocked'
  job['finished_at']=datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
  remote.data['timing']=load_state(state);remote.save();pipeline.save(out/'resultado.json',{'original_job':original,'job':job,'publication_enabled':False})
if __name__=='__main__':main()
