"""Ciclo agendado do piloto: monitora e prepara rascunhos, nunca publica."""
import argparse,json,os
from datetime import datetime,date
from decimal import Decimal
from pathlib import Path
from selecionar_pos_jogos import TZ,PILOT
from estado_operacao_pos_jogo import RemoteState
from operar_pos_jogo import run_once
ROOT=Path(__file__).resolve().parents[1]

def read(p):return json.loads(p.read_text())
def save(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def validate_configuration(cfg,scope,timing):
 if cfg.get('schedule_enabled') is not True or cfg.get('publication_enabled') is not False:
  raise ValueError('Agendamento não autorizado ou publicação habilitada')
 if scope.get('publication_enabled') is not False or len(scope.get('monitored_clubs',[]))!=4 or set(scope['monitored_clubs'])!=PILOT:
  raise ValueError('Escopo deve conter somente os quatro clubes do piloto')
 if timing.get('wait_minutes')!=50 or cfg.get('timezone')!='America/Sao_Paulo':raise ValueError('Espera/fuso divergentes')
 if not Decimal(0)<Decimal(cfg['per_article_cap_usd'])<=Decimal('0.10'):raise ValueError('Teto por matéria inválido')
 if not Decimal(0)<Decimal(cfg['monthly_pilot_cap_usd'])<=Decimal('10'):raise ValueError('Teto mensal inválido')
 if cfg.get('budget_review',{}).get('status')!='reviewed_separate_controls':raise ValueError('Conferência de orçamento ausente')
 if cfg['budget_review'].get('global_account_cap_verified') is not False:raise ValueError('Limite global da conta não foi comprovado')

def budget_status(data,cfg,now):
 for month in data['months'].values():
  if month.get('blocked') or any(c.get('status')!='settled' for c in month.get('calls',[])):
   return 'uncertain_previous_spend'
 if not date.fromisoformat(cfg['price_checked_on'])<=now.date()<=date.fromisoformat(cfg['price_valid_until']):return 'pricing_expired'
 spent=sum((Decimal(c['charged_usd']) for c in data['months'].get(now.strftime('%Y-%m'),{}).get('calls',[])),Decimal(0))
 if spent>=Decimal(cfg['monthly_pilot_cap_usd']):return 'monthly_cap_reached'
 return None

def scheduled_cycle(remote,site,out,*,cfg=None,scope=None,timing=None,clock=None,worker=run_once):
 cfg=cfg or read(ROOT/'config/operacao-pos-jogo.json');scope=scope or read(ROOT/'config/pos-jogo-piloto.json');timing=timing or read(ROOT/'config/tempo-pos-jogo.json')
 validate_configuration(cfg,scope,timing)
 clock=clock or (lambda:datetime.now(TZ));now=clock().astimezone(TZ);out=Path(out).resolve()
 if not out.is_relative_to((ROOT/'build/pos-jogo').resolve()) or out.exists():raise ValueError('Saída inválida ou já utilizada')
 out.mkdir(parents=True)
 operation=remote.data.setdefault('operation',{'enabled':True,'activated_at':now.isoformat(),'mode':'scheduled_drafts','publication_enabled':False})
 if operation.get('publication_enabled') is not False or operation.get('mode')!='scheduled_drafts':raise ValueError('Estado operacional inválido')
 report={'mode':'scheduled_drafts','started_at':now.isoformat(),'run_id':os.environ.get('GITHUB_RUN_ID'),
  'clubs':scope['monitored_clubs'],'wait_minutes':50,'publication_enabled':False,'status':'starting','results':[],
  'budget_scope':'post_match_only','global_account_cap_verified':False,'has_drafts':False}
 error=None
 try:
  if operation.get('enabled') is not True:report['status']='disabled';return report
  blocked=budget_status(remote.data,cfg,now)
  if blocked:report.update(status='budget_blocked',reason=blocked);return report
  operation.update(last_started_at=now.isoformat(),last_run_id=report['run_id']);remote.save()
  reports=worker(remote,Path(site),out/'execucao',clock=clock,operation_mode='scheduled_drafts')
  report['results']=reports
  rows=[r for day in reports for r in day['results']]
  report['has_drafts']=any(r['status']=='package_ready' for r in rows)
  if any(day['status'] in {'pending','collection_failed'} for day in reports):report['status']='needs_review'
  elif report['has_drafts']:report['status']='draft_ready'
  elif any(day['status']=='waiting' for day in reports):report['status']='waiting'
  else:report['status']='idle'
  return report
 except Exception as exc:
  report.update(status='error',reason=str(exc));error=exc;raise
 finally:
  report['finished_at']=clock().astimezone(TZ).isoformat()
  month=now.strftime('%Y-%m')
  report['pilot_month_charged_usd']=str(sum((Decimal(c['charged_usd']) for c in remote.data['months'].get(month,{}).get('calls',[])),Decimal(0)))
  operation.update(last_finished_at=report['finished_at'],last_run_id=report['run_id'],last_status=report['status'],
   last_report={'run_id':report['run_id'],'status':report['status'],'has_drafts':report['has_drafts'],'pilot_month_charged_usd':report['pilot_month_charged_usd']})
  remote.save();save(out/'ciclo.json',report)

def main():
 p=argparse.ArgumentParser();p.add_argument('--site-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 report=scheduled_cycle(RemoteState(),a.site_root,a.output)
 if os.environ.get('GITHUB_OUTPUT'):
  with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('has_drafts='+str(report['has_drafts']).lower()+'\n')
 if os.environ.get('GITHUB_STEP_SUMMARY'):
  with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
   f.write('### Piloto de pós-jogo — rascunhos\n\nEstado: **'+report['status']+'**.\n\nClubes: '+', '.join(report['clubs'])+'.\n\nEspera mínima: 50 minutos desde a confirmação do encerramento; fuso do Brasil.\n\nCusto acumulado do piloto neste mês: US$ '+report['pilot_month_charged_usd']+'. Teto: US$ 0,10/matéria e US$ 10/mês, exclusivo do pós-jogo.\n\nPublicação automática: **desativada**. Rascunhos aprovados ficam no artefato desta execução.\n')
 print(json.dumps(report,ensure_ascii=False),flush=True)
 if report['status'] in {'needs_review','budget_blocked','error'}:raise SystemExit(1)
if __name__=='__main__':main()
