"""Correção editorial do passo 13 com saldo e apuração preservados."""
import hashlib,json,os,shutil
from datetime import datetime,timezone
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
 if job.get('targeted_run_id')!='40557096943' or job.get('status')!='blocked' or job.get('final_patch_started'):
  raise ValueError('Correção já tentada ou origem incompatível')
 previous=ROOT/'build/pos-jogo/passo13-correcao-anterior'
 manifest=read(ROOT/'auditoria/pos-jogo/manifesto-passo13-correcao.json')
 for name,sha in manifest.items():
  if hashlib.sha256((previous/name).read_bytes()).hexdigest()!=sha:raise ValueError('Artefato divergente')
 out=ROOT/'build/pos-jogo/passo13-patch'
 if out.exists():raise ValueError('Saída já utilizada')
 out.mkdir(parents=True);red=out/'redacao';red.mkdir()
 save=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2))
 for name in ('fatos.json','narrativa.json'):shutil.copyfile(previous/name,out/name)
 links=read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
 facts=read(out/'fatos.json')
 from preparar_fatos_pos_jogo import when
 from selecionar_pos_jogos import TZ
 if when(facts['generated_at']).date()!=datetime.now(TZ).date():raise ValueError('Dados precisam de nova conferência')
 package=prepare(facts,read(out/'narrativa.json'),links)
 article=read(previous/'redacao/artigo-1.json')
 issues=validate(article,links)['errors']
 for name in ('revisao-1.json',):
  issues+=validate_review(read(previous/'redacao'/name),package,article)
 issues=targeted_issues(article,list(dict.fromkeys(issues)))
 if issues is None:raise ValueError('Falha de formato não corrigível por trecho')
 cfg=read(ROOT/'config/operacao-pos-jogo.json')
 providers=read(ROOT/'config/redacao-pos-jogo.json')
 job.update(status='running',final_patch_started=True,final_patch_run_id=os.environ.get('GITHUB_RUN_ID'))
 remote.save();caller=BudgetCaller(remote,KEY,config=cfg);success=False
 try:
  for attempt in range(1,2):
   patch=response_object(caller(patch_request(package,article,issues,providers['patch_provider'])))
   save(red/f'correcao-{attempt}.json',patch)
   article=apply_patch(article,patch,issues)
   written=datetime.now(timezone.utc).isoformat()
   save(red/f'artigo-{attempt}.json',article)
   review=response_object(caller(review_request(package,article,providers['provider'])))
   save(red/f'revisao-{attempt}.json',review)
   checks=validate(article,links);issues=checks['errors']+validate_review(review,package,article)
   print(json.dumps({'attempt':attempt,'issues':issues},ensure_ascii=False),flush=True)
  if issues:raise ValueError('Revisão não aprovada após correções limitadas')
  save(red/'artigo.json',article);save(red/'validacao.json',checks)
  save(red/'metadata.json',{'model':providers['writer_provider']['model'],'review_model':providers['provider']['model'],'patch_model':providers['patch_provider']['model'],
    'semantic_review_passed':True,'format_passed':True,'fixture_id':package['facts']['fixture_id'],
    'written_at':written,'article_sha256':digest(article),'package_sha256':digest(package),
    'human_review_required':True,'publication_enabled':False,'continued_from_run':'40557096943'})
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
