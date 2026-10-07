"""Calendários por clube, sem lista fechada de competições, e revalidação ESPN."""
import json
import re
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = 'https://site.api.espn.com/apis/site/v2/sports/soccer'
# IDs masculinos profissionais conferidos na resposta do próprio provedor.
TEAMS = {'Arsenal': (359, 'Arsenal'), 'Manchester City': (382, 'Manchester City'),
 'PSG': (160, 'Paris Saint-Germain'), 'Bayern de Munique': (132, 'Bayern Munich'),
 'Inter de Milão': (110, 'Internazionale'), 'Flamengo': (819, 'Flamengo'),
 'Palmeiras': (2029, 'Palmeiras'), 'Grêmio': (6273, 'Grêmio'),
 'Barcelona': (83, 'Barcelona'), 'Real Madrid': (86, 'Real Madrid')}
LEAGUES = {'eng.1': ('premier-league','Premier League'), 'esp.1': ('la-liga','La Liga'),
 'fra.1': ('ligue-1','Ligue 1'), 'ger.1': ('bundesliga','Bundesliga'),
 'ita.1': ('serie-a','Serie A'), 'bra.1': ('brasileirao','Campeonato Brasileiro Série A'),
 'uefa.champions': ('champions-league','Champions League'),
 'conmebol.libertadores': ('libertadores','Libertadores'), 'bra.copa_do_brasil': ('copa-do-brasil','Copa do Brasil')}
TZ = ZoneInfo('America/Sao_Paulo')

def fetch(url):
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={'User-Agent':'CorteDosEsportes/1.0'}), timeout=25) as response:
                data = json.load(response)
            if not isinstance(data, dict):
                raise ValueError('Resposta ESPN inválida')
            return data
        except Exception:
            if attempt == 2: raise
            time.sleep(attempt + 1)

def normalize(event, target, club_id):
    league = event.get('league', {})
    code = league.get('slug', '')
    if not re.fullmatch(r'[a-z0-9_.-]+', code):
        raise ValueError('Partida sem competição identificada')
    if 'friendly' in code or 'friendl' in league.get('name','').lower(): return None
    competitions = event.get('competitions', [])
    if len(competitions) != 1: raise ValueError('Competição ESPN ambígua')
    c = competitions[0]
    teams = {x['homeAway']: x['team'] for x in c['competitors']}
    if set(teams) != {'home','away'} or str(club_id) not in {str(t['id']) for t in teams.values()}:
        raise ValueError('Calendário ESPN devolveu equipes divergentes')
    kickoff = datetime.fromisoformat(c['date'].replace('Z','+00:00'))
    if kickoff.astimezone(TZ).date() != target: return None
    status = c.get('status',{}).get('type',{}).get('name')
    if status != 'STATUS_SCHEDULED' or event.get('timeValid') is not True: return None
    names = {str(i): name for name,(i,_) in TEAMS.items()}
    slug, label = LEAGUES.get(code, ('espn-'+code.replace('.','-').replace('_','-'), league.get('name')))
    if not label: raise ValueError('Nome da competição ausente')
    return {'id':'espn-'+str(event['id']), 'home':names.get(str(teams['home']['id']),teams['home']['displayName']),
      'away':names.get(str(teams['away']['id']),teams['away']['displayName']),
      'competition':label,'competition_slug':slug,'kickoff':kickoff.astimezone(TZ).isoformat(),
      'status':'scheduled','official':True,'first_team':True,'friendly':False,'provider':'espn',
      'provider_data':{'match_id':str(event['id']),'utc_date':c['date'],'competition_code':code,
         'home_team_id':str(teams['home']['id']),'away_team_id':str(teams['away']['id'])}}

def collect(target, config, query=fetch):
    if {c['name'] for c in config['monitored_clubs']} != set(TEAMS):
        raise ValueError('Cadastro ESPN diverge dos clubes monitorados')
    def one(item):
        name,(club_id,expected) = item
        data=query(f'{BASE}/all/teams/{club_id}/schedule?fixture=true')
        team=data.get('team',{})
        if str(team.get('id')) != str(club_id) or team.get('displayName') != expected or team.get('isNational') is True:
            raise ValueError(f'Identidade ESPN divergente: {name}')
        if not isinstance(data.get('events'),list): raise ValueError(f'Calendário ausente: {name}')
        return [r for e in data['events'] if (r:=normalize(e,target,club_id)) is not None]
    with ThreadPoolExecutor(max_workers=5) as pool:
        batches=list(pool.map(one, TEAMS.items()))
    return list({r['id']:r for batch in batches for r in batch}.values())

def merge(primary, extra, config):
    def clubs(row):
        return {c['name'] for c in config['monitored_clubs'] if any(
            name.casefold() in {row['home'].casefold(), row['away'].casefold()}
            for name in [c['name'],*c.get('aliases',[])])}
    result=list(primary)
    for row in extra:
        # Mesmo clube na mesma competição/data: mantém o ID principal e verifica o horário.
        same=[x for x in primary if x['competition_slug']==row['competition_slug'] and clubs(x)&clubs(row)]
        if same:
            if len(same)!=1 or datetime.fromisoformat(same[0]['kickoff'])!=datetime.fromisoformat(row['kickoff']):
                raise ValueError('Divergência de calendário entre provedores')
            same[0]['supplemental_fixture']=row
        else: result.append(row)
    return result

def snapshot(article, package, manifest):
    if manifest.get('target_date') != datetime.strptime(package['date'],'%d/%m/%Y').date().isoformat(): return None
    row=next((r for r in manifest['fixtures'] if r['id']==article.get('fixture_id') and r.get('provider')=='espn'),None)
    if row: return {'source_type':'espn_fixture_data',**row['provider_data']}
    return None

def verify(fixture, match, query=fetch):
    code=fixture['competition_code']; mid=str(fixture['match_id'])
    if not re.fullmatch(r'[a-z0-9_.-]+',code) or not mid.isdigit(): raise ValueError('ID ESPN inválido')
    h=query(f'{BASE}/{code}/summary?event={mid}')['header']
    if str(h['id']) != mid or h['league']['slug'] != code or h.get('timeValid') is not True:
        raise ValueError('Identidade/horário ESPN divergente')
    c=h['competitions'][0]
    ids={x['homeAway']:str(x['team']['id']) for x in c['competitors']}
    if ids != {'home':str(fixture['home_team_id']),'away':str(fixture['away_team_id'])}:
        raise ValueError('Equipes ESPN divergentes')
    current=datetime.fromisoformat(c['date'].replace('Z','+00:00')).astimezone(TZ)
    prepared=datetime.fromisoformat(fixture['utc_date'].replace('Z','+00:00'))
    if c['status']['type']['name']!='STATUS_SCHEDULED' or current<=datetime.now(TZ): raise ValueError('Jogo não está agendado no futuro')
    if current!=prepared or current.strftime('%d/%m/%Y')!=match['date'] or current.strftime('%H:%M')!=match['kickoff_brasilia']:
        raise ValueError('Horário alterado após preparo')
    return {'step':33,'mode':'final_provider_status_check','match':match,'official_source_confirmed':False,
      'structured_provider_confirmed':True,'provider':'espn','postponed_cancelled_or_suspended':False,
      'publication_status_gate_passed':True,'sources_internal_only':True,'attempts':[{'read_ok':True,'match_id':mid}]}
