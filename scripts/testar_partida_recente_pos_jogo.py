"""Passo 13: partida recente, relógio real, saldo persistente e nenhum publish."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from estado_operacao_pos_jogo import RemoteState,observe_live
from operar_pos_jogo import run_once,wait_until_eligible
ROOT=Path(__file__).resolve().parents[1]
FIXTURE='espn-401841286'

def main():
 out=ROOT/'build/pos-jogo/passo13'
 if out.exists():raise ValueError('Teste já iniciado; não repetir')
 site=ROOT/'current-main';remote=RemoteState()
 if FIXTURE in remote.data['jobs']:raise ValueError('Partida já tentada; histórico e saldo preservados')
 reports=observe_live(remote,out/'observacao',site)
 candidates=[row for report in reports for row in report['observations'] if row['candidate']['fixture_id']==FIXTURE]
 if len(candidates)!=1:raise ValueError('Partida esperada indisponível, duplicada ou já publicada; sem chamadas pagas')
 selected=candidates[0]
 (out/'partida-selecionada.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2))
 print('Partida selecionada: '+json.dumps(selected,ensure_ascii=False),flush=True)
 wait_until_eligible(remote)
 results=run_once(remote,site,out/'execucao')
 rows=[row for report in results for row in report['results'] if row.get('fixture_id')==FIXTURE]
 passed=len(rows)==1 and rows[0]['status']=='package_ready'
 from decimal import Decimal
 calls=[c for month in remote.data['months'].values() for c in month.get('calls',[]) if c.get('fixture_id')==FIXTURE]
 total=sum((Decimal(c['charged_usd']) for c in calls),Decimal(0))
 report={'step':13,'fixture_id':FIXTURE,'actual_clock':True,'historical_replay':False,
  'completed_at':datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
  'package_ready':passed,'charged_usd':str(total),'cap_usd':'0.10','calls':calls,
  'results':results,'publication_enabled':False,'schedule_enabled':False}
 (out/'resultado.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps(report,ensure_ascii=False),flush=True)
 if not passed:raise ValueError('Teste recente não produziu pacote aprovado; consultar relatório')

if __name__=='__main__':main()
