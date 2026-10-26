"""Reserva remota antes da API; custo incerto bloqueia novas chamadas."""
import copy,json,os,uuid,urllib.request
from datetime import datetime,date
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
D=Decimal


def usage_cost(response,config):
 usage=response.get('usage')
 if not isinstance(usage,dict):raise ValueError('Consumo ausente')
 inp=usage.get('input_tokens');out=usage.get('output_tokens')
 details=usage.get('input_tokens_details',{})
 cached=details.get('cached_tokens',0);writes=details.get('cache_write_tokens',0)
 if any(type(n) is not int or n<0 for n in (inp,out,cached,writes)) or cached+writes>inp:
  raise ValueError('Consumo inválido')
 multiplier=D(2) if inp>config['long_context_threshold'] else D(1)
 output_multiplier=D('1.5') if inp>config['long_context_threshold'] else D(1)
 cost=((inp-cached-writes)*D(config['input_usd_per_million'])+cached*D(config['cached_input_usd_per_million'])+writes*D(config['cache_write_usd_per_million']))*multiplier/D(1000000)
 cost+=out*D(config['output_usd_per_million'])*output_multiplier/D(1000000)
 cost+=sum(x.get('type')=='web_search_call' for x in response.get('output',[]))*D(config['web_search_usd_per_call'])
 return cost


def reserve_bound(payload,config):
 if payload.get('model')!=config['model']:raise ValueError('Modelo sem tarifa validada')
 output=payload.get('max_output_tokens')
 if type(output) is not int or not 0<output<=7000:raise ValueError('Limite de saída inválido')
 tools=payload.get('tools',[])
 if tools and (len(tools)!=1 or tools[0].get('type')!='web_search' or payload.get('max_tool_calls')!=1):
  raise ValueError('Ferramenta fora do orçamento')
 # Usa a janela inteira, incluindo o preço de contexto longo e cache-write.
 # Deliberadamente conservador: pode bloquear antes de consumir os US$10.
 return D(config['context_window'])*D(config['cache_write_usd_per_million'])*2/D(1000000)+D(output)*D(config['output_usd_per_million'])*D('1.5')/D(1000000)+(D(config['web_search_usd_per_call']) if tools else 0)


class BudgetCaller:
 def __init__(self,remote,fixture_id,config=None,clock=None,transport=None):
  self.remote=remote;self.fixture_id=fixture_id
  self.config=config or json.loads((ROOT/'config/operacao-pos-jogo.json').read_text())
  self.clock=clock or (lambda:datetime.now(ZoneInfo('America/Sao_Paulo')))
  self.transport=transport or self.send
 def send(self,payload):
  key=os.environ.get('OPENAI_API_KEY','').strip()
  if not key:raise ValueError('OPENAI_API_KEY ausente')
  req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),
   headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
  with urllib.request.urlopen(req,timeout=180) as res:return json.load(res)
 def __call__(self,payload):
  now=self.clock()
  if now.tzinfo is None:raise ValueError('Relógio sem fuso')
  day=now.astimezone(ZoneInfo('America/Sao_Paulo')).date()
  if not date.fromisoformat(self.config['price_checked_on'])<=day<=date.fromisoformat(self.config['price_valid_until']):
   raise ValueError('Tarifas precisam de nova conferência')
  if not D(0)<D(self.config['monthly_pilot_cap_usd'])<=10:raise ValueError('Teto inválido')
  if any(m.get('blocked') or any(c.get('status')=='reserved' for c in m.get('calls',[])) for m in self.remote.data['months'].values()):
   raise ValueError('Consumo anterior incerto; conciliar antes de continuar')
  job=self.remote.data['jobs'].get(self.fixture_id)
  if not job or job.get('status')!='running':raise ValueError('Partida não reservada')
  if job.get('api_calls',0)>=self.config['max_paid_calls_per_fixture']:raise ValueError('Limite de chamadas da partida')
  month=self.remote.data['months'].setdefault(day.strftime('%Y-%m'),{'calls':[],'blocked':False})
  bound=reserve_bound(payload,self.config)
  spent=sum(D(c['charged_usd']) for c in month['calls'])
  if spent+bound>D(self.config['monthly_pilot_cap_usd']):raise ValueError('Saldo insuficiente para reserva conservadora')
  entry={'id':uuid.uuid4().hex,'fixture_id':self.fixture_id,'started_at':now.isoformat(),'status':'reserved','charged_usd':str(bound),'reserved_usd':str(bound)}
  month['calls'].append(entry);job['api_calls']=job.get('api_calls',0)+1
  self.remote.save() # Falha de persistência impede a API.
  request=copy.deepcopy(payload);request['service_tier']='default'
  try:
   result=self.transport(request)
   if result.get('service_tier')!='default':raise ValueError('Tarifa da resposta não confirmada')
   model=result.get('model','')
   if model!=self.config['model'] and not model.startswith(self.config['model']+'-'):raise ValueError('Modelo retornado divergente')
   cost=usage_cost(result,self.config)
   if cost>bound:raise ValueError('Custo excedeu reserva; revisar preços')
   entry.update(status='settled',charged_usd=str(cost),usage=result['usage'],response_id=result.get('id'))
   self.remote.save()
   return result
  except Exception:
   entry.update(status='uncertain',charged_usd=str(bound));month['blocked']=True
   self.remote.save()
   raise
