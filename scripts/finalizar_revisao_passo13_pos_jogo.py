"""Correção editorial do passo 13 com saldo e apuração preservados."""
import hashlib,json,os,shutil
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from pathlib import Path
from estado_operacao_pos_jogo import RemoteState
from custos_pos_jogo import BudgetCaller
from redigir_pos_jogo_openai import response_object,rewrite_request,parse_response
from editorial_pos_jogo import prepare,validate
from revisar_pos_jogo import patch_request,apply_patch,review_request,validate_review,targeted_issues
from empacotar_redacao_pos_jogo import digest,package_reviewed
ROOT=Path(__file__).resolve().parents[1];KEY='espn-401841286'

def main():
 read=lambda p:json.loads(p.read_text())
 remote=RemoteState();job=remote.data['jobs'][KEY]
 if job.get('expanded_run_id')!='40577346518' or job.get('status')!='blocked' or job.get('completion_patch_started'):
  raise ValueError('Correção já tentada ou origem incompatível')
 previous=ROOT/'build/pos-jogo/passo13-completo-anterior'
 manifest=read(ROOT/'auditoria/pos-jogo/manifesto-passo13-completo.json')
 for name,sha in manifest.items():
  if hashlib.sha256((previous/name).read_bytes()).hexdigest()!=sha:raise ValueError('Artefato divergente')
 out=ROOT/'build/pos-jogo/passo13-aprovacao'
 if out.exists():raise ValueError('Saída já utilizada')
 out.mkdir(parents=True);red=out/'redacao';red.mkdir()
 save=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2))
 for name in ('fatos.json','narrativa.json'):shutil.copyfile(previous/name,out/name)
 links=read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
 facts=read(out/'fatos.json')
 from preparar_fatos_pos_jogo import when
 from selecionar_pos_jogos import TZ
 now=datetime.now(TZ)
 if not timedelta(0)<=now-when(facts['generated_at'])<=timedelta(hours=24):raise ValueError('Apuração precisa ser renovada')
 from coletar_competicoes_pre_jogo import fetch,BASE
 from preparar_fatos_pos_jogo import build,pair
 from tempo_pos_jogo import observe
 original=read(previous/'resumo-atual.json')
 candidate=dict(facts['match'],fixture_id=KEY,score=facts['score'],competition_code=original['header']['league']['slug'],source_url=facts['sources'][0]['url'])
 summary=fetch(candidate['source_url']);save(out/'resumo-atual.json',summary)
 timing=observe(candidate,summary,remote.data['timing'],now);remote.save();save(out/'tempo.json',timing)
 if not timing['eligible']:raise ValueError('Espera ainda não cumprida')
 ids=[str(t['team']['id']) for t in pair(summary['header']['competitions'][0]).values()]
 if not all(i.isdigit() for i in ids):raise ValueError('ID inválido')
 schedules={i:fetch(f'{BASE}/all/teams/{i}/schedule?fixture=true&season={now.year}') for i in ids}
 save(out/'agendas-atuais.json',schedules)
 refreshed=build(candidate,summary,schedules,read(previous/'apuracao/conferencia.json'),now)
 if refreshed['upcoming']!=facts['upcoming']:raise ValueError('Agenda mudou; não reutilizar revisão anterior')
 facts=refreshed;save(out/'fatos.json',facts)
 package=prepare(facts,read(out/'narrativa.json'),links)
 if digest(package)!=digest(read(previous/'pacote.json')):raise ValueError('Pacote factual mudou')
 article=read(previous/'redacao/artigo.json')
 if digest(article)!=read(previous/'redacao/metadata.json')['article_sha256']:raise ValueError('Artigo diverge da revisão')
 issues=validate(article,links)['errors']
 for name in ('revisao-3.json',):
  issues+=validate_review(read(previous/'redacao'/name),package,article)
 issues=targeted_issues(article,list(dict.fromkeys(issues)))
 if issues is None:raise ValueError('Falha de formato não corrigível por trecho')
 cfg=read(ROOT/'config/operacao-pos-jogo.json');cfg['max_paid_calls_per_fixture']=23
 providers=read(ROOT/'config/redacao-pos-jogo.json')
 job.update(status='running',completion_patch_started=True,completion_patch_run_id=os.environ.get('GITHUB_RUN_ID'))
 remote.save();caller=BudgetCaller(remote,KEY,config=cfg);success=False
 try:
  for attempt in range(1,3):
   patch=response_object(caller(patch_request(package,article,issues,providers['writer_provider'])))
   save(red/f'correcao-{attempt}.json',patch)
   article=apply_patch(article,patch,issues)
   written=datetime.now(timezone.utc).isoformat()
   save(red/f'artigo-{attempt}.json',article)
   review=response_object(caller(review_request(package,article,providers['provider'])))
   save(red/f'revisao-{attempt}.json',review)
   checks=validate(article,links);issues=checks['errors']+validate_review(review,package,article)
   print(json.dumps({'attempt':attempt,'issues':issues},ensure_ascii=False),flush=True)
   if not issues:break
  if issues:raise ValueError('Revisão não aprovada após correções limitadas')
  save(red/'artigo.json',article);save(red/'validacao.json',checks)
  save(red/'metadata.json',{'model':providers['writer_provider']['model'],'review_model':providers['provider']['model'],'patch_model':providers['writer_provider']['model'],
    'semantic_review_passed':True,'format_passed':True,'fixture_id':package['facts']['fixture_id'],
    'written_at':written,'article_sha256':digest(article),'package_sha256':digest(package),
    'human_review_required':True,'publication_enabled':False,'continued_from_run':'40577346518'})
  save(out/'pacote-validado.json',package_reviewed(out,ROOT/'current-main',links));success=True
 finally:
  job.update(status='completed' if success else 'blocked',finished_at=datetime.now(timezone.utc).isoformat());remote.save()
  calls=[c for m in remote.data['months'].values() for c in m.get('calls',[]) if c.get('fixture_id')==KEY]
  total=sum((Decimal(c['charged_usd']) for c in calls),Decimal(0))
  save(out/'custo.json',{'total_including_previous_attempts_usd':str(total),'cap_usd':'0.10','calls':calls,
    'all_settled':all(c['status']=='settled' for c in calls),'package_ready':success,
    'historical_evaluation':False,'actual_clock':True,'step':13,'schedule_enabled':False,'publication_enabled':False})
  print('Custo TOTAL da avaliação: US$ '+str(total),flush=True)

if __name__=='__main__':main()
