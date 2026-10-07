"""Regressões: calendários abertos, identidades, seções e rodapés de notícias."""
import json,sys
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts import coletar_competicoes_pre_jogo as c
from scripts import extrair_fatos_estruturados as e, ler_fontes_candidatas_base as r
from scripts.pesquisa_publica_gratuita import TextExtractor
cfg=json.loads((ROOT/'config/pre-jogo.json').read_text())
def event(code):
 return {'id':'123','date':'2030-01-10T22:30Z','timeValid':True,'league':{'slug':code,'name':'Copa nova'},'competitions':[{'date':'2030-01-10T22:30Z','competitors':[{'homeAway':'home','team':{'id':'819','displayName':'Flamengo'}},{'homeAway':'away','team':{'id':'2029','displayName':'Palmeiras'}}],'status':{'type':{'name':'STATUS_SCHEDULED'}}}]}
for code in ['conmebol.libertadores','bra.copa_do_brasil','new.cup']:
 x=c.normalize(event(code),date(2030,1,10),819);assert x and x['provider']=='espn'
assert c.normalize(event('club.friendly'),date(2030,1,10),819) is None
assert c.normalize(event('new.cup'),date(2030,1,11),819) is None
bad=event('new.cup');bad['timeValid']=False;assert c.normalize(bad,date(2030,1,10),819) is None
bad=event('new.cup');bad['competitions'][0]['status']['type']['name']='STATUS_POSTPONED';assert c.normalize(bad,date(2030,1,10),819) is None
try:c.normalize(event('new.cup'),date(2030,1,10),359);raise AssertionError('wrong team accepted')
except ValueError:pass
assert e.mentions_team('Remo x Grêmio','Clube do Remo',cfg)
html='''<title>Remo x Grêmio</title><article itemprop="articleBody"><h1>Remo x Grêmio</h1><p>Estádio: Mangueirão</p><p>Transmissão: Premiere</p><h2>Remo - técnico: Thiago Carpini</h2><p>Provável Leão: Aaa, Bbb, Ccc, Ddd, Eee, Fff, Ggg, Hhh, Iii, Jjj e Kkk.</p><h2>Grêmio - técnico: Renato Gaúcho</h2><p>Escalação provável: Lll, Mmm, Nnn, Ooo, Ppp, Qqq, Rrr, Sss, Ttt, Uuu e Vvv.</p><p>Árbitro: Davi de Oliveira Lacerda</p><p>Quarto Árbitro: Wiomar Santana de Oliveira</p></article><p>Estádio: São Januário, próximo jogo.</p>'''
p=TextExtractor();p.feed(html);p.flush();assert 'São Januário' not in '\n'.join(p.article_lines)
raw={'markdown':'\n'.join(p.article_lines),'metadata':{'title':'Remo x Grêmio'}}
for rid in ['stadium_and_location','transmission','probable_lineups_and_coaches','officiating']:
 src=r.apply_scrape_to_candidate({'url':'https://ge.globo.com/teste','publisher':'ge','source_type':'major_sports_media','title':'Remo x Grêmio'},raw,requirement_id=rid,checked_at=datetime.now(timezone.utc).isoformat(),config=cfg)
 z=e.extract_requirement({'id':rid,'source_candidates':[src]},match_context={'home':'Clube do Remo','away':'Grêmio'},config=cfg)
 assert z['status']=='verified',(rid,z)
print('OK: competições abertas, amistosos/adiamentos excluídos, clube correto e quatro campos extraídos sem rodapé.')
