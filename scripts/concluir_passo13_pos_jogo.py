"""Validação recente com apuração completa, mantendo todas as despesas anteriores."""
import hashlib,json,os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from apurar_pos_jogo import apurar,candidate_proposal
from estado_operacao_pos_jogo import RemoteState
from custos_pos_jogo import BudgetCaller
from coletar_competicoes_pre_jogo import fetch,BASE
from selecionar_pos_jogos import TZ
from tempo_pos_jogo import observe
from editorial_pos_jogo import prepare
from redigir_pos_jogo_openai import generate
from empacotar_redacao_pos_jogo import package_reviewed
from preparar_publicacao_pos_jogo import slug_part
ROOT=Path(__file__).resolve().parents[1];KEY='espn-401841286'
def read(p):return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')

def main():
 remote=RemoteState();job=remote.data['jobs'][KEY]
 if job.get('final_patch_run_id')!='40557767577' or job.get('status')!='blocked' or job.get('expanded_research_started'):
  raise ValueError('Retomada indisponível; histórico preservado')
 previous=ROOT/'build/pos-jogo/passo13-anterior'
 manifest=read(ROOT/'auditoria/pos-jogo/manifesto-passo13-anterior.json')
 for name,sha in manifest.items():
  if hashlib.sha256((previous/name).read_bytes()).hexdigest()!=sha:raise ValueError('Artefato de origem divergente')
 out=ROOT/'build/pos-jogo/passo13-conclusao'
 if out.exists():raise ValueError('Saída já utilizada')
 out.mkdir(parents=True);site=ROOT/'current-main'
 candidate=read(previous/'partida-selecionada.json')['candidate'];now=datetime.now(TZ)
 filename='-'.join(slug_part(candidate[k]) for k in ('home','away','competition'))+f"-{candidate['match_date'][:4]}-resultado.html"
 if (site/filename).exists() or any(n.get('url','').split('/')[-1]==filename for n in read(site/'noticias.json')):
  raise ValueError('Matéria já publicada; sem consumo pago')
 summary=fetch(candidate['source_url']);save(out/'resumo-atual.json',summary)
 _,_,_,teams=candidate_proposal(candidate,summary)
 timing=observe(candidate,summary,remote.data['timing'],now)
 remote.save();save(out/'tempo.json',timing)
 if not timing['eligible']:raise ValueError('Espera de 50 minutos não cumprida')
 ids=[str(t['team']['id']) for t in teams.values()]
 if not all(i.isdigit() for i in ids):raise ValueError('ID inválido')
 schedules={i:fetch(f'{BASE}/all/teams/{i}/schedule?fixture=true&season={now.year}') for i in ids}
 save(out/'agendas-atuais.json',schedules)
 discovery=read(previous/'execucao/2026-10-26'/KEY/'apuracao/descoberta.json')
 cfg=read(ROOT/'config/operacao-pos-jogo.json')
 # Exceção somente para terminar esta avaliação autorizada. Não aumenta o teto
 # de US$0,10 e não redefine nenhum débito; máximo 9 chamadas adicionais.
 cfg['max_paid_calls_per_fixture']=19
 job.update(status='running',expanded_research_started=True,expanded_run_id=os.environ.get('GITHUB_RUN_ID'),
   validation_call_limit=19,validation_article_cap_usd='0.10')
 remote.save();caller=BudgetCaller(remote,KEY,config=cfg);success=False
 try:
  facts,narrative=apurar(candidate,summary,schedules,out/'apuracao',now,caller=caller,discovery=discovery)
  save(out/'fatos.json',facts);save(out/'narrativa.json',narrative)
  links=read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
  package=prepare(facts,narrative,links);save(out/'pacote.json',package)
  generate(package,out/'redacao',execute=True,caller=caller)
  report=package_reviewed(out,site,links);save(out/'pacote-validado.json',report)
  success=True
 finally:
  job.update(status='completed' if success else 'blocked',finished_at=datetime.now(TZ).isoformat());remote.save()
  calls=[c for m in remote.data['months'].values() for c in m.get('calls',[]) if c.get('fixture_id')==KEY]
  total=sum((Decimal(c['charged_usd']) for c in calls),Decimal(0))
  result={'step':13,'fixture_id':KEY,'actual_clock':True,'historical_replay':False,
   'total_including_all_previous_attempts_usd':str(total),'cap_usd':'0.10','calls':calls,
   'all_settled':all(c['status']=='settled' for c in calls),'package_ready':success,
   'research_pages_reopened':True,'discovery_reused_from_run':'40518351945',
   'publication_enabled':False,'schedule_enabled':False}
  save(out/'resultado.json',result)
  print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
