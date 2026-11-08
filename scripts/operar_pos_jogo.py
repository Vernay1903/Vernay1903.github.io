"""Execução persistente do piloto; prepara artefatos, nunca publica."""
import argparse,json,os,time
from decimal import Decimal
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

RECOVERABLE_SOURCE_ERRORS=(
 'Nenhum relato oficial efetivamente aberto',
 'Menos de dois domínios com páginas efetivamente abertas',
 'Fato não confirmado: identity',
 'Fato não confirmado: score',
 'Gol contra/equipe desconhecida',
)
# Reserva conservadora atual de uma busca única na API. Não pode gastar acima do teto.
SEARCH_MIN_RESERVE=Decimal('0.07535')

def needs_new_evidence(job):
 return (job.get('length_retry') is True and job.get('reason')=='Expansão sem fatos suficientes'
         and not job.get('official_index_retry') and job.get('api_calls',0)<=12)

def needs_venue_omission(j):
 return (j.get('official_index_retry') and not j.get('venue_retry') and
         str(j.get('reason','')).startswith('Fato não confirmado: venue') and j.get('api_calls',0)<=14)

def has_located_report(job):
 path=pipeline.ROOT/'config/relatos-localizados-pos-jogo.json'
 records=json.loads(path.read_text()) if path.exists() else {}
 return bool(job.get('fixture_id') in records and not job.get('located_report_retry') and job.get('api_calls',0)<=5 and str(job.get('reason','')).startswith('Fato não confirmado: score'))

def needs_incomplete_retry(job):
 return (job.get('reason')=='Apuração incompleta na API' and not job.get('incomplete_retry')
         and job.get('api_calls',0)<=5 and bool(job.get('run_id')))

def previous_discovery(remote,fid,job):
 """Reutiliza só os localizadores; a apuração reabre todas as fontes ao vivo."""
 import hashlib,io,subprocess,zipfile
 from estado_operacao_pos_jogo import REPO
 rows=remote.request('GET',f'/actions/runs/{job["run_id"]}/artifacts')['artifacts']
 selected=[a for a in rows if a['name'].startswith('pos-jogo-rascunhos-'+str(job['run_id'])+'-') and not a['expired']]
 if len(selected)!=1 or selected[0]['size_in_bytes']>10000000:raise ValueError('Artefato da apuração ausente ou ambíguo')
 a=selected[0]
 raw=subprocess.check_output(['gh','api',f'repos/{REPO}/actions/artifacts/{a["id"]}/zip'],timeout=60)
 if 'sha256:'+hashlib.sha256(raw).hexdigest()!=a['digest']:raise ValueError('Artefato da apuração corrompido')
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  names=[n for n in z.namelist() if n.endswith('/'+fid+'/apuracao/descoberta.json')]
  if len(names)!=1 or z.getinfo(names[0]).file_size>2000000:raise ValueError('Descoberta anterior ausente ou ambígua')
  discovery=json.loads(z.read(names[0]))
 if not isinstance(discovery.get('output'),list):raise ValueError('Descoberta anterior inválida')
 return discovery

def eligible_source_retry(job,months,now,config):
 """Apenas uma nova apuração após falha de fontes, sem apagar gastos nem falsificar provas."""
 if job.get('status')!='blocked' or job.get('operation_mode')!='scheduled_drafts':
  return False
 exact_retry=(job.get('source_retry_count',0)==1 and not job.get('official_index_retry') and
              any(x in (job.get('reason') or '') for x in ('Fato não confirmado: goals','Fato não confirmado: score')) and
              job.get('api_calls',0)<=5)
 exact_retry=exact_retry or needs_new_evidence(job) or needs_venue_omission(job) or has_located_report(job) or needs_incomplete_retry(job)
 if job.get('source_retry_count',0)>=1 and not exact_retry:return False
 reason=job.get('reason','')
 if not exact_retry and (not isinstance(reason,str) or not any(term in reason for term in RECOVERABLE_SOURCE_ERRORS)):
  return False
 if not (needs_new_evidence(job) or needs_venue_omission(job)) and job.get('api_calls',0)>=config['max_paid_calls_per_fixture']:
  return False
 try:
  finished=datetime.fromisoformat(job['finished_at'])
  if finished.tzinfo is None or (not (needs_venue_omission(job) or has_located_report(job)) and now-finished<timedelta(hours=2)):return False
 except (KeyError,TypeError,ValueError):
  return False
 if any(m.get('blocked') or any(c.get('status')!='settled' for c in m.get('calls',[])) for m in months.values()):
  return False
 fid=job.get('fixture_id')
 if not fid:return False
 used=sum((Decimal(c['charged_usd']) for m in months.values() for c in m.get('calls',[]) if c.get('fixture_id')==fid),Decimal(0))
 monthly=sum((Decimal(c['charged_usd']) for c in months.get(now.strftime('%Y-%m'),{}).get('calls',[])),Decimal(0))
 required=Decimal('0.025') if exact_retry else SEARCH_MIN_RESERVE
 return (Decimal(config['per_article_cap_usd'])-used>=required
         and Decimal(config['monthly_pilot_cap_usd'])-monthly>=required)

def validate_generated_package(directory,report):
 """Bloqueia aprovação com anúncios ou sidebar ausentes; não altera site."""
 if (report.get('body_ad_count')!=3 or report.get('body_words',0)<600
     or report.get('publication_enabled') is not False
     or report.get('fixed_shell_unchanged') is not True
     or report.get('old_news_preserved') is not True
     or report.get('old_sitemap_preserved') is not True):
  raise ValueError('Pacote não validado: anúncios, extensão, shell ou índices')
 name=report.get('filename','')
 if not name or '/' in name or '\\\\' in name or not name.endswith('.html'):
  raise ValueError('Nome de HTML inválido')
 folder=Path(directory)/'publicacao-teste'
 article=(folder/name).read_text(encoding='utf-8')
 if (article.count('data-ad-slot="8702501261"')!=3
     or article.count('data-ad-slot="5521804159"')!=1
     or '.desktop-only-ad { display: none !important; }' not in article
     or 'window.matchMedia("('+'min-width: 1025px'+')").matches' not in article):
  raise ValueError('Blocos de anúncio ou sidebar desktop ausentes no HTML')
 for required in ('noticias.json','sitemap.xml','validacao.json'):
  if not (folder/required).is_file():raise ValueError('Pacote incompleto: '+required)
 if json.loads((folder/'validacao.json').read_text(encoding='utf-8')).get('body_ad_count')!=3:
  raise ValueError('Validação de anúncios divergente')
 return True



def run_once(remote,site,out,*,clock=None,runner=pipeline.run,researcher=apurar,writer=generate,caller_factory=BudgetCaller,operation_mode="test"):
 clock=clock or (lambda:datetime.now(TZ));now=clock();out=Path(out).resolve();site=Path(site).resolve()
 if not out.is_relative_to((pipeline.ROOT/'build/pos-jogo').resolve()):raise ValueError('Saída fora do piloto')
 if out.exists():raise ValueError('Diretório de execução já utilizado')
 out.mkdir(parents=True)
 state=out/'tempo.json';save_state(state,remote.data['timing'])
 budget={'research':0,'articles':0};reports=[];active={}
 config=pipeline.read(pipeline.ROOT/'config/operacao-pos-jogo.json')
 def allowed(now):
  return {fid for fid,j in remote.data['jobs'].items()
          if eligible_source_retry(dict(j,fixture_id=fid),remote.data['months'],now,config)}
 def research(candidate,summary,schedules,directory,observed_at):
  fid=candidate['fixture_id'];previous=remote.data['jobs'].get(fid)
  recovery_discovery=None
  if previous is not None:
   if fid not in allowed(now):raise ValueError('Repetição não autorizada')
   incomplete=needs_incomplete_retry(previous)
   if incomplete:
    recovery_discovery=previous_discovery(remote,fid,previous)
    previous['incomplete_retry']=True
   venue_retry=needs_venue_omission(previous)
   if venue_retry:previous['venue_retry']=True
   located=has_located_report(dict(previous,fixture_id=fid))
   if located:previous['located_report_retry']=True
   fresh_evidence=needs_new_evidence(previous) or venue_retry or located or incomplete
   exact=previous.get('source_retry_count',0)==1 or fresh_evidence
   if fresh_evidence:previous['evidence_retry_call_limit']=previous['api_calls']+9
   if exact and not incomplete:previous['official_index_retry']=True
   previous.update(status='running',started_at=clock().isoformat(),
     run_id=os.environ.get('GITHUB_RUN_ID'),
     source_retry_count=previous.get('source_retry_count',0)+1,
     source_retry_started_at=clock().isoformat())
  else:
   remote.data['jobs'][fid]={'status':'running','started_at':clock().isoformat(),
     'run_id':os.environ.get('GITHUB_RUN_ID'),'api_calls':0,'operation_mode':operation_mode}
  remote.data['timing']=load_state(state);remote.save()
  if previous and previous.get('evidence_retry_call_limit'):
   active[fid]=caller_factory(remote,fid,config=dict(config,max_paid_calls_per_fixture=previous['evidence_retry_call_limit']))
  else:active[fid]=caller_factory(remote,fid)
  kw={'direct_only':True} if previous and previous.get('official_index_retry') else {}
  if recovery_discovery is not None:kw={'discovery':recovery_discovery}
  return researcher(candidate,summary,schedules,directory,observed_at,caller=active[fid],**kw)
 def draft(package,directory,**kwargs):
  return writer(package,directory,**kwargs,caller=active[package['facts']['fixture_id']])
 try:
  for day in dates_to_check(now):
   # Destinos atuais lidos novamente por data e pelo empacotador.
   report=runner(day,pipeline.read(site/'noticias.json'),out/day.isoformat(),
    execute=True,max_articles=4 if operation_mode=='scheduled_drafts' else 1,auto_research=True,query=pipeline.fetch,writer=draft,researcher=research,
    now=now,timing_state=state,work_budget=budget,site_root=site,processed=set(remote.data['jobs'])-allowed(now))
   reports.append(report)
   for row in report['results']:
    fid=row['fixture_id']
    if row['status']=='already_attempted':
     previous=remote.data['jobs'].get(fid,{})
     row['previous_status']=previous.get('status')
     if previous.get('status')=='blocked':
      row['recovery']='waiting_for_safe_sources_or_human_review'
    if fid in active:
     if row['status']=='package_ready':
      try:validate_generated_package(out/day.isoformat()/fid,row['package'])
      except (ValueError,OSError,KeyError,TypeError) as exc:
       row.update(status='blocked',reason=str(exc))
       report['status']='pending'
     values={'status':row['status'],'finished_at':clock().isoformat()}
     if row.get('reason'):values['reason']=row['reason']
     remote.data['jobs'][fid].update(values)
     if row['status']=='package_ready':
      remote.data['jobs'][fid].pop('reason',None)
      remote.data['jobs'][fid]['package']=row['package']
      remote.data['jobs'][fid]['artifact_name']=os.environ.get('POS_JOGO_ARTIFACT_NAME')
      remote.data['jobs'][fid]['review_run_url']='https://github.com/Vernay1903/Vernay1903.github.io/actions/runs/'+os.environ.get('GITHUB_RUN_ID','')
   pipeline.save(out/day.isoformat()/'relatorio.json',report)
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
