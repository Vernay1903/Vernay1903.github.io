"""Retomada única autorizada, somente do bloqueio sem custo do passo 14."""
import copy,json,os
from pathlib import Path
from estado_operacao_pos_jogo import RemoteState
from operar_pos_jogo import run_once
from executar_pos_jogo import ROOT

def authorize_retry(remote):
 fid='espn-401921835'
 if 'step15_retry' in remote.data:raise ValueError('Retomada do passo 15 já utilizada')
 job=remote.data['jobs'].get(fid,{})
 if job.get('status')!='blocked' or job.get('run_id')!='40643743077' or job.get('api_calls')!=0:
  raise ValueError('Bloqueio original divergente')
 if any(c.get('fixture_id')==fid for m in remote.data['months'].values() for c in m.get('calls',[])):
  raise ValueError('Partida já possui chamada financeira; retomada não autorizada')
 remote.data['step15_retry']={'original_job':copy.deepcopy(job),'run_id':os.environ.get('GITHUB_RUN_ID'),'authorized':True}
 del remote.data['jobs'][fid]
 remote.save()
 return fid

def main():
 remote=RemoteState();fid=authorize_retry(remote)
 try:
  result=run_once(remote,ROOT/'current-main',ROOT/'build/pos-jogo/passo15',operation_mode='authorized_step15_validation')
  print(json.dumps(result,ensure_ascii=False))
  if not any(r.get('fixture_id')==fid and r.get('status')=='package_ready' for d in result for r in d['results']):
   raise ValueError('Passo 15 ainda sem pacote aprovado; consultar diagnóstico')
 finally:
  if fid not in remote.data['jobs']:
   remote.data['jobs'][fid]=remote.data['step15_retry']['original_job']
  remote.data['step15_retry']['finished']=True
  remote.save()
if __name__=='__main__':main()
