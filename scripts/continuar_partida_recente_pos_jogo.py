"""Retoma uma única apuração do passo 13 sem apagar tentativas ou custos."""
import hashlib,json,os
from datetime import datetime,timedelta
from decimal import Decimal
from pathlib import Path
from apurar_pos_jogo import candidate_proposal,finalize_review
from estado_operacao_pos_jogo import RemoteState
from custos_pos_jogo import BudgetCaller
from coletar_competicoes_pre_jogo import fetch,BASE
from preparar_fatos_pos_jogo import pair,when
from selecionar_pos_jogos import TZ
from tempo_pos_jogo import observe
from editorial_pos_jogo import prepare
from redigir_pos_jogo_openai import generate
from empacotar_redacao_pos_jogo import package_reviewed
ROOT=Path(__file__).resolve().parents[1]
KEY='espn-401841286'
PREVIOUS_RUN='40518351945'

def read(p):return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')

def main():
 remote=RemoteState();job=remote.data['jobs'][KEY]
 if job.get('run_id')!=PREVIOUS_RUN or job.get('status')!='blocked' or job.get('continuation_started'):
  raise ValueError('Continuação indisponível; histórico preservado')
 previous=ROOT/'build/pos-jogo/passo13-anterior'
 manifest=read(ROOT/'auditoria/pos-jogo/manifesto-passo13-anterior.json')
 for name,digest in manifest.items():
  if hashlib.sha256((previous/name).read_bytes()).hexdigest()!=digest:raise ValueError('Artefato anterior divergente: '+name)
 out=ROOT/'build/pos-jogo/passo13-continuacao'
 if out.exists():raise ValueError('Saída já utilizada')
 out.mkdir(parents=True)
 candidate=read(previous/'partida-selecionada.json')['candidate']
 old=previous/'execucao/2026-10-26'/KEY/'apuracao'
 pages=read(old/'paginas.json');now=datetime.now(TZ)
 if any(not timedelta(0)<=now-when(p['checked_at'])<=timedelta(hours=24) for p in pages.values()):
  raise ValueError('Apuração anterior vencida; requer nova consulta')
 # Reconsultar os campos obrigatórios e a agenda sem repetir chamadas de IA.
 summary=fetch(candidate['source_url']);save(out/'resumo-atual.json',summary)
 collections=[read(p) for p in (previous/'execucao/2026-10-26/coleta').glob('*.json')]
 original=next(x['data'] for x in collections if x['url']==candidate['source_url'])
 _,old_core,_,_=candidate_proposal(candidate,original)
 proposal,core,_,teams=candidate_proposal(candidate,summary)
 if core!=old_core:raise ValueError('Dados obrigatórios mudaram desde a revisão; não reutilizar aprovação')
 timing=observe(candidate,summary,remote.data['timing'],now)
 remote.save();save(out/'tempo.json',timing)
 if not timing['eligible']:raise ValueError('Espera ainda não cumprida')
 ids=[str(t['team']['id']) for t in teams.values()]
 if not all(i.isdigit() for i in ids):raise ValueError('ID de equipe inválido')
 schedules={i:fetch(f'{BASE}/all/teams/{i}/schedule?fixture=true&season={now.year}') for i in ids}
 save(out/'agendas-atuais.json',schedules)
 facts,narrative=finalize_review(candidate,summary,schedules,proposal,core,read(old/'extracao.json'),pages,read(old/'revisao.json'),out/'apuracao',now)
 save(out/'fatos.json',facts);save(out/'narrativa.json',narrative)
 links=read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
 package=prepare(facts,narrative,links);save(out/'pacote.json',package)
 save(out/'proveniencia.json',{'previous_run':PREVIOUS_RUN,'artifact_id':12744900386,'manifest':manifest,
  'research_reused':True,'fresh_summary_and_schedules':True,'research_timestamps_preserved':True})
 # Reserva o mesmo trabalho e conserva api_calls e todos os débitos anteriores.
 job.update(status='running',continuation_started=True,continuation_run_id=os.environ.get('GITHUB_RUN_ID'))
 remote.save();caller=BudgetCaller(remote,KEY);success=False
 try:
  generate(package,out/'redacao',execute=True,caller=caller)
  report=package_reviewed(out,ROOT/'current-main',links)
  save(out/'pacote-validado.json',report);success=True
 finally:
  job.update(status='completed' if success else 'blocked',finished_at=datetime.now(TZ).isoformat())
  remote.save()
  calls=[c for m in remote.data['months'].values() for c in m.get('calls',[]) if c.get('fixture_id')==KEY]
  total=sum((Decimal(c['charged_usd']) for c in calls),Decimal(0))
  result={'step':13,'fixture_id':KEY,'actual_clock':True,'historical_replay':False,
   'total_including_previous_attempt_usd':str(total),'cap_usd':'0.10','calls':calls,
   'all_settled':all(c['status']=='settled' for c in calls),'package_ready':success,
   'publication_enabled':False,'schedule_enabled':False}
  save(out/'resultado.json',result)
  print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
