"""Descobre a ficha do jogo em índices oficiais e lê o conteúdo antes da redação."""
import hashlib,json,re,urllib.request,unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin,urlparse
from datetime import datetime
from pathlib import Path

CLUBS={'Manchester City':'52919--man-city','Arsenal':'52280--arsenal','Real Madrid':'50051--real-madrid'}
ALIASES={'slavia prague':'slavia praha','rb leipzig':'leipzig','manchester city':'man city','aek athens fc':'aek athens'}
def norm(s):return ' '.join(re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower()).split())
def team(s):return ALIASES.get(norm(s),norm(s))
class Links(HTMLParser):
 def __init__(self):super().__init__();self.urls=[]
 def handle_starttag(self,t,a):
  if t=='a' and dict(a).get('href'):self.urls.append(dict(a)['href'])
def read_url(url):
 from apurar_pos_jogo import Redirect,safe_url
 req=urllib.request.Request(safe_url(url),headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.build_opener(Redirect()).open(req,timeout=12) as res:
  safe_url(res.url);raw=res.read(2000001)
 if len(raw)>2000000:raise ValueError('Resposta oficial muito grande')
 return raw
def links(raw):
 p=Links();p.feed(raw.decode('utf-8'));return list(dict.fromkeys(p.urls))
def uefa_record(c,d):
 if str(d.get('competition',{}).get('id'))!='1' or d.get('status')!='FINISHED':return None
 if datetime.fromisoformat(d['kickOffTime']['dateTime'].replace('Z','+00:00'))!=datetime.fromisoformat(c['kickoff']):return None
 for side in ('home','away'):
  if team(d[side+'Team']['internationalName'])!=team(c[side]):return None
 score=d.get('score',{}).get('regular')
 if score!=c['score']:return None
 def en(o,key):return o.get('translations',{}).get(key,{}).get('EN')
 return {'competition':en(d['competition'],'name') or d['competition']['code'],'date':d['kickOffTime']['dateTime'],'home':d['homeTeam']['internationalName'],'homeTeamId':d['homeTeam'].get('id'),'away':d['awayTeam']['internationalName'],'awayTeamId':d['awayTeam'].get('id'),'status':d['status'],'score':d['score'],'venue':en(d['stadium'],'name'),'matchday':d['matchday']['longName'],'scorers':[{'player':x['player']['internationalName'],'type':x.get('goalType'),'time':x.get('time'),'teamId':x.get('teamId'),'playerClubId':x['player'].get('clubId')} for x in d.get('playerEvents',{}).get('scorers',[])]}
def official_pages(c,opener):
 pages=[]
 club=next((t for t in (c['home'],c['away']) if t in CLUBS),None)
 if c['competition_code']=='uefa.champions' and club:
  index='https://www.uefa.com/uefachampionsleague/clubs/'+CLUBS[club]+'/matches/'
  cached=Path(__file__).resolve().parents[1]/'config/indice-uefa.json'
  seed=json.loads(cached.read_text()).get(CLUBS[club],{}) if cached.exists() else {}
  uefa_links=list(seed.get('links',[])) if seed.get('index')==index else []
  # O índice é só um localizador. A ficha oficial precisa ser aberta ao vivo
  # e coincidir em clubes, mando, competição, horário e placar.
  def paths():
   yield from uefa_links
   try:fresh=links(read_url(index))
   except (OSError,ValueError):fresh=[]
   yield from (p for p in fresh if p not in uefa_links)

  for path in paths():
   m=re.fullmatch(r'/uefachampionsleague/match/(\d+)--([a-z0-9-]+)-vs-([a-z0-9-]+)/',path)
   if not m or [team(m[2]),team(m[3])]!=[team(c['home']),team(c['away'])]:continue
   url='https://match.uefa.com/v5/matches/'+m[1]
   try:raw=read_url(url);d=json.loads(raw)
   except (OSError,ValueError):continue
   if str(d['id'])!=m[1]:continue
   row=uefa_record(c,d)
   if row:
    pages.append(dict(url=url,text=json.dumps(row,ensure_ascii=False),opened=True,sha256=hashlib.sha256(raw).hexdigest(),match_page=urljoin(index,path),format='official_match_record'));break
 if 'Flamengo' in (c['home'],c['away']) or club=='Manchester City':
  fla='Flamengo' in (c['home'],c['away'])
  clubname='Flamengo' if fla else 'Manchester City';opp=c['away'] if c['home']==clubname else c['home']
  index='https://www.flamengo.com.br/noticias/futebol' if fla else 'https://www.mancity.com/news/mens'
  try:index_links=links(read_url(index))
  except (OSError,ValueError):index_links=[]
  paths=[urljoin(index,p) for p in index_links if ('/noticias/futebol/' if fla else '/news/mens/') in p and team(opp) in norm(p) and urlparse(urljoin(index,p)).hostname==urlparse(index).hostname]
  for url in sorted(paths,key=lambda p:('match-report' not in p and 'vence' not in p,p))[:4]:
   try:page=opener(url)
   except (OSError,ValueError):continue
   t=norm(page['text']);y,mo,day=c['match_date'].split('-')
   if fla and (not re.search(rf'\b{day} {mo} (?:{y}|{y[-2:]})\b',t) or not re.search(r'\b'+str(max(c['score'].values()))+r' (?:a |x )?'+str(min(c['score'].values()))+r'\b',t)):continue
   if not fla and ('match-report' not in url or not re.search(rf'\b0?{int(day)} {datetime.fromisoformat(c["match_date"]).strftime("%b").lower()}[a-z]* {y}\b',t)):continue
   pages.append(dict(page,format='official_club_report'));break
 return pages
