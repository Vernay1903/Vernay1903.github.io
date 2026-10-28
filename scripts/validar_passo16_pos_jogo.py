"""Certifica um rascunho do cron, sem redação, correção ou publicação."""
import argparse,json,os,re
from datetime import datetime,timedelta
from decimal import Decimal
from pathlib import Path
from estado_operacao_pos_jogo import RemoteState
from empacotar_redacao_pos_jogo import package_reviewed
from editorial_pos_jogo import prepare
from revisar_pos_jogo import validate_review
from preparar_fatos_pos_jogo import when
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())

def inspect_package(root,site,day,row):
 fid=row['fixture_id']
 if not re.fullmatch(r'espn-\d+',fid) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day['target_date']):raise ValueError('Identidade inválida')
 directory=root/'execucao'/day['target_date']/fid
 links=read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
 meta=read(directory/'redacao/metadata.json')
 if meta.get('automatic_model_run') is not True or meta.get('publication_enabled') is not False or meta.get('continued_from_run') or meta.get('correction_method'):
  raise ValueError('Redação assistida ou metadados inválidos')
 provenance=read(directory/'apuracao/proveniencia-descoberta.json')
 if provenance.get('reused') is not False or provenance.get('fresh_pages_required') is not True:
  raise ValueError('Descoberta de fontes não foi autônoma')
 article=read(directory/'redacao/artigo.json')
 package=prepare(read(directory/'fatos.json'),read(directory/'narrativa.json'),links)
 reviews=list((directory/'redacao').glob('revisao-[0-9].json'))
 if not reviews:raise ValueError('Revisão ausente')
 last=max(reviews,key=lambda p:int(p.stem.split('-')[-1]))
 if last.name=='revisao-1.json':last=directory/'redacao/revisao-inicial-consolidada.json'
 if validate_review(read(last),package,article):raise ValueError('Revisão final pendente')
 # Reconstrói e compara todos os arquivos do pacote, inclusive o HTML fixo.
 result=package_reviewed(directory,site,links)
 if result!=row['package']:raise ValueError('Pacote diverge do ciclo')
 return result

def evaluate(report,state,event,run_id,inspector):
 result={'step':16,'status':'waiting_for_scheduled_draft','run_id':run_id,'publication_enabled':False}
 if report.get('run_id')!=run_id:raise ValueError('Relatório de outra execução')
 if event!='schedule':return dict(result,status='waiting_for_schedule')
 if report.get('publication_enabled') is not False or report.get('mode')!='scheduled_drafts':raise ValueError('Modo inválido')
 if report.get('status') in {'error','needs_review','budget_blocked','disabled'}:
  return dict(result,status='blocked',reason=report.get('reason',report['status']))
 ready=[(d,r) for d in report['results'] for r in d['results'] if r.get('status')=='package_ready']
 if not ready:return result
 if len(ready)!=1:raise ValueError('Quantidade de matérias inesperada')
 day,row=ready[0];fid=row['fixture_id'];job=state['jobs'][fid]
 expected={'status','started_at','run_id','api_calls','operation_mode','finished_at','package','artifact_name','review_run_url'}
 if set(job)-expected or job.get('operation_mode')!='scheduled_drafts' or job.get('run_id')!=run_id or job.get('status')!='package_ready':
  raise ValueError('Tentativa assistida ou fora deste cron')
 timing=row['timing'];start=when(job['started_at']);finish=when(job['finished_at'])
 if timing.get('eligible') is not True or timing.get('wait_minutes')!=50 or timing.get('basis')!='first_observed_final':raise ValueError('Espera inválida')
 if when(timing['eligible_at'])!=when(timing['first_final_seen_at'])+timedelta(minutes=50) or start<when(timing['eligible_at']):raise ValueError('Espera antecipada')
 if not when(report['started_at'])<=start<=finish<=when(report['finished_at']):raise ValueError('Cronologia divergente')
 calls=[c for m in state['months'].values() for c in m.get('calls',[]) if c.get('fixture_id')==fid]
 if not 1<=len(calls)<=12 or len(calls)!=job.get('api_calls'):raise ValueError('Histórico de chamadas divergente')
 if any(c.get('status')!='settled' or not start<=when(c['started_at'])<=finish for c in calls):raise ValueError('Cobrança incerta ou tentativa anterior')
 values=[Decimal(c['charged_usd']) for c in calls]
 if any(not x.is_finite() or x<0 for x in values) or sum(values)>Decimal('0.10'):raise ValueError('Teto financeiro inválido')
 package=inspector(day,row)
 return dict(result,status='approved',fixture_id=fid,cost_usd=str(sum(values)),calls=len(calls),package=package,
             artifact_name=job.get('artifact_name'),run_url=job.get('review_run_url'),event='schedule',manual_adjustments=False)

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--site-root',type=Path,required=True);a=p.parse_args()
 root=a.output.resolve()
 if not root.is_relative_to((ROOT/'build/pos-jogo').resolve()):raise ValueError('Saída inválida')
 remote=RemoteState();prior=remote.data.get('validation_step16',{})
 if prior.get('status')=='approved':result=prior
 else:
  try:result=evaluate(read(root/'ciclo.json'),remote.data,os.environ.get('GITHUB_EVENT_NAME'),os.environ.get('GITHUB_RUN_ID'),lambda d,r:inspect_package(root,a.site_root,d,r))
  except Exception as exc:result={'step':16,'status':'blocked','reason':str(exc),'run_id':os.environ.get('GITHUB_RUN_ID'),'publication_enabled':False}
  remote.data['validation_step16']=result;remote.save()
 (root/'passo16.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 if os.environ.get('GITHUB_STEP_SUMMARY'):
  with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('\n\nPasso 16: **'+result['status']+'**. Sem publicação.\n')
 print(json.dumps(result,ensure_ascii=False))
 if result['status']=='blocked':raise SystemExit(1)
if __name__=='__main__':main()
