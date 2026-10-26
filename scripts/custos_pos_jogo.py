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


def reserve_bound(payload,config,input_tokens=None):
 if payload.get('model')!=config['model']:raise ValueError('Modelo sem tarifa validada')
 output=payload.get('max_output_tokens')
 if type(output) is not int or not 0<output<=7000:raise ValueError('Limite de saída inválido')
 tools=payload.get('tools',[])
 if tools and (len(tools)!=1 or tools[0].get('type')!='web_search' or payload.get('max_tool_calls')!=1):
  raise ValueError('Ferramenta fora do orçamento')
 # Uma busca: reservar duas janelas completas (antes/depois da ferramenta),
 # com a maior tarifa de contexto longo, mesmo abaixo do limiar.
 if tools:
  inp=2*config['web_search_context_window'];multiplier=D(2);out_multiplier=D('1.5')
 else:
  if type(input_tokens) is not int or not 0<=input_tokens<=config['context_window']-output:
   raise ValueError('Contagem de entrada ausente ou inválida')
  inp=input_tokens;multiplier=D(2) if inp>config['long_context_threshold'] else D(1)
  out_multiplier=D('1.5') if multiplier==2 else D(1)
 price=max(D(config[k]) for k in ('input_usd_per_million','cached_input_usd_per_million','cache_write_usd_per_million'))
 return (D(inp)*price*multiplier+D(output)*D(config['output_usd_per_million'])*out_multiplier)/D(1000000)+(D(config['web_search_usd_per_call']) if tools else 0)



class BudgetCaller:
 def __init__(self,remote,fixture_id,config=None,clock=None,transport=None,counter=None):
  self.remote=remote;self.fixture_id=fixture_id
  self.config=config or json.loads((ROOT/'config/operacao-pos-jogo.json').read_text())
  self.clock=clock or (lambda:datetime.now(ZoneInfo('America/Sao_Paulo')))
  self.transport=transport or self.send
  self.counter=counter or self.count_input
 def count_input(self,payload):
  fields={'model','input','instructions','tools','tool_choice','text','reasoning'}
  request={k:v for k,v in payload.items() if k in fields}
  return self.post('/input_tokens',request)['input_tokens']
 def send(self,payload):return self.post('',payload)
 def post(self,suffix,payload):
  key=os.environ.get('OPENAI_API_KEY','').strip()
  if not key:raise ValueError('OPENAI_API_KEY ausente')
  req=urllib.request.Request('https://api.openai.com/v1/responses'+suffix,data=json.dumps(payload).encode(),
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
  if not D(0)<D(self.config['per_article_cap_usd'])<=D('0.10'):raise ValueError('Teto por matéria inválido')
  article_spent=sum((D(c['charged_usd']) for m in self.remote.data['months'].values() for c in m.get('calls',[]) if c.get('fixture_id')==self.fixture_id),D(0))
  if article_spent>=D(self.config['per_article_cap_usd']):raise ValueError('Teto da matéria já atingido')
  month=self.remote.data['months'].setdefault(day.strftime('%Y-%m'),{'calls':[],'blocked':False})
  # Validar formato/modelo antes de consultar a contagem.
  reserve_bound(payload,self.config,0)
  count=None if payload.get('tools') else self.counter(payload)
  bound=reserve_bound(payload,self.config,count)
  if article_spent+bound>D(self.config['per_article_cap_usd']):raise ValueError('Saldo da matéria insuficiente; limite US$ 0,10')
  spent=sum(D(c['charged_usd']) for c in month['calls'])
  if spent+bound>D(self.config['monthly_pilot_cap_usd']):raise ValueError('Saldo insuficiente para reserva conservadora')
  entry={'id':uuid.uuid4().hex,'fixture_id':self.fixture_id,'started_at':now.isoformat(),'status':'reserved','charged_usd':str(bound),'reserved_usd':str(bound),'model':payload['model'],'counted_input_tokens':count}
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
