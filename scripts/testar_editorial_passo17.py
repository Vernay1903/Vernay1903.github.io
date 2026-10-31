"""Teste único de apuração/redação com fontes arquivadas e orçamento cumulativo."""
import copy
import hashlib
import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from estado_operacao_pos_jogo import RemoteState
from custos_pos_jogo import BudgetCaller
from executar_pos_jogo import ROOT
from apurar_pos_jogo import apurar
from editorial_pos_jogo import prepare
from redigir_pos_jogo_openai import generate

FID='espn-401921834'
KEY='validation_step17_editorial'
HASHES={
 'execucao/2026-10-28/selecao.json':'23de004d102f5c5399cead8ade7acdbfc0e35f22a1900647655a46300c582281',
 'execucao/2026-10-28/espn-401921834/apuracao/paginas.json':'24e7f74958b8aaf61f855ae3eb09f040a2008916866fd001d26766ef01a47d5c',
 'execucao/2026-10-28/espn-401921834/apuracao/descoberta.json':'893dba4b9ac358fa953ed690e5cbbbd89e98adc0c6e24912a0cce0e6d52850a8',
 'execucao/2026-10-28/coleta/d265d6e22c297c51b534.json':'e5ce9c6db9dfee44911317795add61d44c5787eba0a702adb4781a0e2c71d871',
 'execucao/2026-10-28/coleta/74a55528f6b0c494110f.json':'ca742a4b0bb62b3ed1f43cf5d4d6632d09030190de25dccbbbd044f5164fb2e0',
 'execucao/2026-10-28/coleta/c4e0d18570e562d3a88d.json':'0c7d1827cc06568a25bfbb4b5e2662a198cb99207897bfbb44ced8c7b73f3d5b',
}
def read(p): return json.loads(p.read_text())
def save(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def total(data):
 return sum((Decimal(c['charged_usd']) for m in data['months'].values() for c in m['calls'] if c['fixture_id']==FID),Decimal(0))
def reserve_test(remote):
 if KEY in remote.data: raise ValueError('Teste editorial já iniciado; repetição bloqueada')
 job=remote.data['jobs'].get(FID,{})
 if job.get('status')!='package_ready' or job.get('run_id')!='40784987236' or job.get('api_calls')!=8:
  raise ValueError('Estado original divergente')
 original=copy.deepcopy(job)
 remote.data[KEY]={'status':'running','run_id':os.environ.get('GITHUB_RUN_ID'),'original_job':original,
  'source_run_id':'40784987236','mode':'historical_source_replay','manual_article_edits':False,
  'publication_enabled':False,'fixture_cost_before_usd':str(total(remote.data)),
  'max_additional_calls':11,'per_fixture_total_cap_usd':'0.10'}
 job['status']='running'
 remote.save()
 return original

def main():
 archive=ROOT/'build/pos-jogo/passo17-original'
 for path,expected in HASHES.items():
  if hashlib.sha256((archive/path).read_bytes()).hexdigest()!=expected:
   raise ValueError('Fonte arquivada divergente: '+path)
 base=archive/'execucao/2026-10-28'
 candidate=next(c for c in read(base/'selecao.json')['selected'] if c['fixture_id']==FID)
 records=[read(archive/p) for p in HASHES if '/coleta/' in p]
 summary=next(r['data'] for r in records if r['url']==candidate['source_url'])
 schedules={urlparse(r['url']).path.split('/teams/')[1].split('/')[0]:r['data'] for r in records if '/teams/' in r['url']}
 archived_pages=read(base/FID/'apuracao/paginas.json')
 pages_by_url={p['url']:p for p in archived_pages.values() if p.get('format')!='direct_structured_response'}
 def opener(url):
  if url not in pages_by_url:raise ValueError('Página não disponível no arquivo original')
  return copy.deepcopy(pages_by_url[url])
 discovery=read(base/FID/'apuracao/descoberta.json')
 out=ROOT/'build/pos-jogo/passo17-editorial'
 out.mkdir(parents=True,exist_ok=False)
 remote=RemoteState();original=reserve_test(remote)
 record=remote.data[KEY]
 try:
  config=read(ROOT/'config/operacao-pos-jogo.json')
  # Exceção somente de quantidade para a revalidação; valores financeiros inalterados.
  # O mesmo fixture_id inclui TODAS as chamadas do primeiro rascunho no teto de US$0,10.
  config['max_paid_calls_per_fixture']=original['api_calls']+record['max_additional_calls']
  caller=BudgetCaller(remote,FID,config=config)
  snapshot_time=datetime.fromisoformat(candidate['checked_at'])
  facts,narrative=apurar(candidate,summary,schedules,out/'apuracao',snapshot_time,
   caller=caller,opener=opener,discovery=discovery)
  save(out/'apuracao/proveniencia-descoberta.json',{'reused':True,'fresh_pages_required':False,
   'historical_source_replay':True,'source_run_id':'40784987236','archive_hashes_checked':True})
  save(out/'fatos.json',facts);save(out/'narrativa.json',narrative)
  package=prepare(facts,narrative,read(ROOT/'auditoria/pos-jogo/links-autorizados-piloto.json'))
  save(out/'pacote.json',package)
  metadata=generate(package,out/'redacao',execute=True,caller=caller)
  record.update(status='generated_pending_editorial_assessment',metadata=metadata)
 except Exception as exc:
  record.update(status='blocked',reason=str(exc))
  raise
 finally:
  count=remote.data['jobs'][FID]['api_calls']
  remote.data['jobs'][FID]=dict(original,api_calls=count)
  record.update(fixture_cost_total_usd=str(total(remote.data)),
   additional_cost_usd=str(total(remote.data)-Decimal(record['fixture_cost_before_usd'])),
   additional_calls=count-original['api_calls'],finished_at=datetime.now().astimezone().isoformat())
  remote.save();save(out/'resultado.json',record)
  print(json.dumps({k:record[k] for k in ['status','fixture_cost_total_usd','additional_cost_usd','additional_calls']},ensure_ascii=False))
if __name__=='__main__':main()
