"""Continuação única da avaliação, preservando gastos e fatos da tentativa anterior."""
import json,os,shutil
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
from pathlib import Path
from estado_operacao_pos_jogo import RemoteState
from custos_pos_jogo import BudgetCaller
from redigir_pos_jogo_openai import generate
from editorial_pos_jogo import prepare
from empacotar_redacao_pos_jogo import package_reviewed
ROOT=Path(__file__).resolve().parents[1]
KEY='validation-luna-20261026-real-leipzig'

def main():
 remote=RemoteState();job=remote.data['jobs'][KEY]
 if job.get('run_id')!='40410687634' or job.get('status')!='blocked' or job.get('continuation_started'):
  raise ValueError('Continuação não disponível; não repetir ou zerar custos')
 out=ROOT/'build/pos-jogo/custo-passo12-continuacao'
 if out.exists():raise ValueError('Saída já utilizada')
 out.mkdir(parents=True)
 previous=ROOT/'build/pos-jogo/custo-passo12-anterior/liberado/espn-401915313'
 for name in ('fatos.json','narrativa.json'):shutil.copyfile(previous/name,out/name)
 read=lambda p:json.loads(p.read_text())
 links=read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
 package=prepare(read(out/'fatos.json'),read(out/'narrativa.json'),links)
 cfg=read(ROOT/'config/operacao-pos-jogo.json')
 # Apenas esta avaliação pode fazer mais 7 chamadas; mantém US$0,10 TOTAL,
 # inclusive as dez chamadas já pagas. Não muda a política operacional.
 cfg['max_paid_calls_per_fixture']=17
 job.update(status='running',continuation_started=True,continuation_run_id=os.environ.get('GITHUB_RUN_ID'))
 remote.save();caller=BudgetCaller(remote,KEY,config=cfg);success=False
 try:
  generate(package,out/'redacao',execute=True,caller=caller)
  report=package_reviewed(out,ROOT/'current-main',links)
  (out/'pacote-validado.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
  success=True
 finally:
  job.update(status='completed' if success else 'blocked',finished_at=datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat())
  remote.save()
  calls=[c for m in remote.data['months'].values() for c in m.get('calls',[]) if c.get('fixture_id')==KEY]
  total=sum((Decimal(c['charged_usd']) for c in calls),Decimal(0))
  result={'total_including_previous_attempt_usd':str(total),'cap_usd':'0.10','calls':calls,
      'all_settled':all(c['status']=='settled' for c in calls),'package_ready':success,
      'historical_evaluation':True,'publication_enabled':False}
  (out/'custo.json').write_text(json.dumps(result,indent=2))
  print('Custo TOTAL da avaliação: US$ '+str(total),flush=True)

if __name__=='__main__':main()
