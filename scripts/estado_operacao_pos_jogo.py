"""Estado remoto exclusivo do piloto, com atualização condicionada ao SHA lido."""
import base64,json,os,urllib.request
from pathlib import Path
REPO='Vernay1903/Vernay1903.github.io'
BRANCH='estado-pos-jogo-piloto'
PATH='estado.json'

class RemoteState:
 def __init__(self):
  self.token=os.environ.get('GH_TOKEN','').strip()
  if not self.token:raise ValueError('Credencial de persistência ausente')
  response=self.request('GET',f'/contents/{PATH}?ref={BRANCH}')
  self.sha=response['sha'];self.data=json.loads(base64.b64decode(response['content']))
  if self.data.get('version')!=1 or not all(isinstance(self.data.get(k),dict) for k in ('timing','jobs','months')):
   raise ValueError('Estado persistente inválido; não reinicializar silenciosamente')
 def request(self,method,path,body=None):
  req=urllib.request.Request('https://api.github.com/repos/'+REPO+path,
   data=json.dumps(body).encode() if body is not None else None,
   headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','Content-Type':'application/json'},method=method)
  with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
 def save(self):
  payload={'branch':BRANCH,'sha':self.sha,'message':'Atualizar estado do piloto pós-jogo',
    'content':base64.b64encode((json.dumps(self.data,ensure_ascii=False,indent=2)+'\n').encode()).decode()}
  result=self.request('PUT',f'/contents/{PATH}',payload)
  self.sha=result['content']['sha']

def observe_live(remote,out,site_root):
 from datetime import datetime
 from selecionar_pos_jogos import select,TZ
 from coletar_competicoes_pre_jogo import fetch
 from tempo_pos_jogo import observe,dates_to_check
 now=datetime.now(TZ);out=Path(out);out.mkdir(parents=True,exist_ok=True)
 news=json.loads((Path(site_root)/'noticias.json').read_text())
 reports=[]
 for day in dates_to_check(now):
  selection=select(day,news,now=now);rows=[]
  if not selection['collection_complete']:
   raise ValueError('Coleta incompleta: '+json.dumps(selection['errors'],ensure_ascii=False))
  selected={c['fixture_id'] for c in selection['selected']}
  remote.data['timing']['fixtures']={k:v for k,v in remote.data['timing']['fixtures'].items() if v.get('match_date')!=day.isoformat() or k in selected}
  for c in selection['selected']:
   summary=fetch(c['source_url'])
   rows.append({'candidate':c,'timing':observe(c,summary,remote.data['timing'],now)})
  reports.append({'selection':selection,'observations':rows})
 remote.data['last_observed_at']=now.isoformat();remote.save()
 (out/'observacao.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'observed_at':now.isoformat(),'reports':reports},ensure_ascii=False))
 return reports

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--site-root',type=Path,required=True)
 a=p.parse_args();observe_live(RemoteState(),a.output,a.site_root)
