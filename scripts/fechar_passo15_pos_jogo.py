"""Fecha uma correção localizada preservando aprovação, evidências e custo total."""
import base64,hashlib,json,os,shutil
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from pathlib import Path
from estado_operacao_pos_jogo import RemoteState
from custos_pos_jogo import BudgetCaller
from redigir_pos_jogo_openai import response_object
from editorial_pos_jogo import prepare,validate
from revisar_pos_jogo import patch_request,apply_patch,validate_review,review_changed
from empacotar_redacao_pos_jogo import digest,package_reviewed
from preparar_fatos_pos_jogo import when
from selecionar_pos_jogos import TZ
ROOT=Path(__file__).resolve().parents[1];KEY='espn-401921835'
def read(p):return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 remote=RemoteState();job=remote.data['jobs'][KEY]
 if job.get('incremental_completion_run_id')!='40688512866' or job.get('status')!='blocked' or job.get('step15_final_completion'):
  raise ValueError('Fechamento indisponível; histórico preservado')
 previous=ROOT/'build/pos-jogo/passo15-fechamento-anterior'
 manifest=read(ROOT/'auditoria/pos-jogo/manifesto-passo15-fechamento.json')
 for name,sha in manifest.items():
  if hashlib.sha256((previous/name).read_bytes()).hexdigest()!=sha:raise ValueError('Artefato anterior divergente')
 out=ROOT/'build/pos-jogo/passo15-validado'
 if out.exists():raise ValueError('Saída já utilizada')
 out.mkdir(parents=True);red=out/'redacao';red.mkdir()
 for name in ('fatos.json','narrativa.json'):shutil.copyfile(previous/name,out/name)
 facts=read(out/'fatos.json');now=datetime.now(TZ)
 if not timedelta(0)<=now-when(facts['generated_at'])<=timedelta(hours=24):raise ValueError('Apuração vencida')
 links=read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json')
 package=prepare(facts,read(out/'narrativa.json'),links);save(out/'pacote.json',package)
 before=read(previous/'redacao/artigo-2.json');previous_review=read(previous/'redacao/revisao-2.json')
 issues=validate_review(previous_review,package,before)
 if not issues or not validate(before,links)['format_passed']:raise ValueError('Estado editorial inesperado')
 save(red/'artigo-anterior.json',before);save(red/'revisao-anterior.json',previous_review)
 cfg=read(ROOT/'config/operacao-pos-jogo.json');cfg['max_paid_calls_per_fixture']=14
 providers=read(ROOT/'config/redacao-pos-jogo.json')
 patch_provider=dict(providers['writer_provider'],patch_max_output_tokens=1000)
 job.update(status='running',incremental_completion_started=True,incremental_completion_run_id=os.environ.get('GITHUB_RUN_ID'),validation_call_limit=14,step15_final_completion=True)
 remote.save();caller=BudgetCaller(remote,KEY,config=cfg);success=False
 try:
  article=json.loads(json.dumps(before))
  old_text='O Fleetwood se protegia com muitos jogadores e bloqueios, reduzindo os caminhos para o Arsenal finalizar. Foi nesse contexto que o Fleetwood abriu o placar.'
  if article['blocks'][4]['text']!=old_text:raise ValueError('Trecho diverge da correção autorizada')
  article['blocks'][4]['text']='O Fleetwood se protegia com muitos jogadores e bloqueios, reduzindo os caminhos para o Arsenal finalizar.'
  save(red/'artigo.json',article)
  written=datetime.now(timezone.utc).isoformat();checks=validate(article,links);save(red/'validacao.json',checks)
  if not checks['format_passed']:raise ValueError('Correção falhou no formato: '+str(checks['errors']))
  review=review_changed(package,before,previous_review,article,providers['provider'],caller,package)
  save(red/'revisao.json',review);issues=validate_review(review,package,article)
  if issues:raise ValueError('Revisão pendente: '+str(issues))
  save(red/'metadata.json',{'model':patch_provider['model'],'review_model':providers['provider']['model'],
   'semantic_review_passed':True,'format_passed':True,'fixture_id':KEY,'written_at':written,
   'article_sha256':digest(article),'package_sha256':digest(package),'review_sha256':digest(review),
   'review_method':'full_review_plus_changed_unit_review_with_global_context',
   'human_review_required':True,'publication_enabled':False,'continued_from_run':'40687696901','correction_method':'deterministic_removal_of_unsupported_causal_link'})
  report=package_reviewed(out,ROOT/'current-main',links);save(out/'pacote-validado.json',report);success=True
  print(json.dumps({'package':report,'validation':checks},ensure_ascii=False),flush=True)
 finally:
  job.update(status='completed' if success else 'blocked',finished_at=datetime.now(TZ).isoformat())
  if success: job.pop('reason',None)
  remote.save()
  calls=[c for m in remote.data['months'].values() for c in m.get('calls',[]) if c.get('fixture_id')==KEY]
  total=sum((Decimal(c['charged_usd']) for c in calls),Decimal(0))
  save(out/'resultado.json',{'step':15,'fixture_id':KEY,'actual_clock':True,'historical_replay':False,
   'total_including_all_previous_attempts_usd':str(total),'cap_usd':'0.10','calls':calls,
   'all_settled':all(c['status']=='settled' for c in calls),'package_ready':success,'publication_enabled':False,'schedule_enabled':True})
  if success:
   archive={'step':15,'status':'validated','run_id':os.environ.get('GITHUB_RUN_ID'),'tests_passed':181,
    'article':article,'facts':facts,'narrative':read(out/'narrativa.json'),'metadata':read(red/'metadata.json'),
    'validation':checks,'review':review,'cost':read(out/'resultado.json'),'package':report,
    'code_pinned_in_main':'cbb4300b9a9e29489def916d75c5b83e61eaa95f',
    'activation_commit':'3516984481b7dcd6d78ffa168abff401ed135818',
    'automation_check_run':40687749206,'publication_enabled':False}
   remote.request('PUT','/contents/auditoria/pos-jogo/validacao-final-passo15.json',{
    'branch':'piloto-pos-jogo-quatro-clubes','message':'Registrar validacao final do passo 15',
    'content':base64.b64encode((json.dumps(archive,ensure_ascii=False,indent=2)+'\\n').encode()).decode()})
  print('Custo TOTAL: US$ '+str(total),flush=True)
if __name__=='__main__':main()
