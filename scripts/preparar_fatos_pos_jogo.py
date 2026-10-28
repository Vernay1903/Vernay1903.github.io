"""Passo 3: coleta estruturada e conferência editorial explícita, sem redação/publicação."""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.selecionar_pos_jogos import TZ, FINAL, PILOT, integer, norm
from scripts.coletar_competicoes_pre_jogo import BASE, fetch


def when(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Data sem fuso')
    return parsed.astimezone(TZ)


def pair(comp):
    rows = comp['competitors']
    teams = {r['homeAway']: r for r in rows}
    if len(rows) != 2 or set(teams) != {'home', 'away'}:
        raise ValueError('Identidade das equipes ambígua')
    return teams


def upcoming(data, team_id, cutoff, competition_code):
    if str(data['team']['id']) != team_id or not isinstance(data.get('events'), list):
        raise ValueError('Calendário da equipe divergente/incompleto')
    rows = []
    for event in data['events']:
        if len(event.get('competitions', [])) != 1:
            raise ValueError('Evento futuro ambíguo')
        c = event['competitions'][0]
        if c.get('status', {}).get('type', {}).get('name') != 'STATUS_SCHEDULED':
            continue
        kickoff = when(c['date'])
        if kickoff <= cutoff:
            continue
        teams = pair(c)
        if team_id not in {str(t['team']['id']) for t in teams.values()}:
            raise ValueError('Adversários divergentes do calendário')
        league = event.get('league', {})
        code = league.get('slug')
        if not code or not league.get('name'):
            raise ValueError('Competição futura ausente')
        if 'friendl' in code:
            continue
        rows.append({'fixture_id': 'espn-' + str(event['id']),
            'home': teams['home']['team']['displayName'], 'away': teams['away']['team']['displayName'],
            'date_brasilia': kickoff.date().isoformat(),
            'time_brasilia': kickoff.strftime('%H:%M') if event.get('timeValid') is True else None,
            'competition_code': code, 'competition': league['name']})
    rows.sort(key=lambda r: (r['date_brasilia'], r['time_brasilia'] or '00:00'))
    return {'next_match': rows[0] if rows else None,
            'next_in_competition': next((r for r in rows if r['competition_code'] == competition_code), None)}


def match_outcome(comp):
    """Separate match goals from shootout; never infer regulation/extra-time splits."""
    status = comp['status']['type']
    if status.get('completed') is not True or status.get('name') not in FINAL:
        raise ValueError('Partida não encerrada')
    teams = pair(comp)
    score = {k: integer(t['score']) for k, t in teams.items()}
    result = {'decided_by': 'extra_time' if status['name'] == 'STATUS_FINAL_AET' else 'match',
              'match_score': score}
    if status['name'] == 'STATUS_FINAL_PEN':
        penalties = {k: integer(t.get('shootoutScore')) for k, t in teams.items()}
        if penalties['home'] == penalties['away']:
            raise ValueError('Disputa de pênaltis sem vencedor')
        winner = max(penalties, key=penalties.get)
        if any(t.get('winner') is not (k == winner) for k, t in teams.items()):
            raise ValueError('Vencedor dos pênaltis divergente')
        result.update(decided_by='penalties', shootout_score=penalties, winner=winner)
    elif any(t.get('shootoutScore') not in (None, 0, '0') for t in teams.values()):
        raise ValueError('Pênaltis incompatíveis com status')
    return result


def match_goals(comp):
    teams = pair(comp)
    ids = {str(t['team']['id']): k for k, t in teams.items()}
    goals = []
    for detail in comp.get('details', []):
        # Explicit shootout markers only: an in-game penalty is still a goal.
        period = detail.get('period', {})
        if detail.get('shootout') is True or (isinstance(period, dict) and period.get('number') == 5):
            continue
        if detail.get('scoringPlay') is not True:
            continue
        tid = str(detail['team']['id'])
        if tid not in ids or detail.get('ownGoal') is True:
            raise ValueError('Gol contra/equipe desconhecida requer conferência específica')
        participants = detail.get('participants', [])
        if not participants:
            raise ValueError('Gol sem autor')
        goals.append({'side': ids[tid], 'scorer': participants[0]['athlete']['displayName'],
                      'minute': detail.get('clock', {}).get('displayValue')})
    counts = Counter(g['side'] for g in goals)
    if any(counts[k] != integer(t['score']) for k, t in teams.items()):
        raise ValueError('Lista de gols não fecha com o placar')
    return goals


def build(candidate, summary, schedules, review, now=None):
    now = now or datetime.now(TZ)
    if not {candidate['home'], candidate['away']} & PILOT:
        raise ValueError('Partida fora do piloto')
    h = summary['header']
    if 'espn-' + str(h['id']) != candidate['fixture_id'] or h['league']['slug'] != candidate['competition_code']:
        raise ValueError('Identidade/competição diverge da seleção')
    if len(h['competitions']) != 1:
        raise ValueError('Resumo ambíguo')
    c = h['competitions'][0]
    if c['status']['type'].get('completed') is not True or c['status']['type']['name'] not in FINAL:
        raise ValueError('Partida não encerrada')
    kickoff = when(c['date'])
    if kickoff != when(candidate['kickoff']) or kickoff >= now:
        raise ValueError('Data/hora da partida divergente')
    teams = pair(c)
    if any(norm(teams[k]['team']['displayName']) != norm(candidate[k]) for k in teams):
        raise ValueError('Equipes divergem da seleção')
    score = {k: integer(r['score']) for k, r in teams.items()}
    if score != candidate['score']:
        raise ValueError('Placar diverge da seleção')
    outcome = match_outcome(c)
    ids = {str(r['team']['id']): side for side, r in teams.items()}
    goals = match_goals(c)
    if outcome['decided_by'] != 'match' and review.get('outcome') != outcome:
        raise ValueError('Desfecho diverge da conferência externa')
    if review.get('fixture_id') != candidate['fixture_id'] or review.get('method') != 'source_review':
        raise ValueError('Conferência externa ausente/divergente')
    if review.get('score') != score:
        raise ValueError('Conflito de placar com conferência externa')
    for source in review.get('sources', []):
        parsed = urlparse(source['url'])
        if parsed.scheme != 'https' or not parsed.hostname or when(source['checked_at']) > now:
            raise ValueError('Proveniência inválida')
    if len({urlparse(s['url']).hostname for s in review.get('sources', [])}) < 2:
        raise ValueError('Conferência externa insuficiente')
    expected = review.get('goals', [])
    if [(g['side'], norm(g['scorer'])) for g in goals] != [(g['side'], norm(g['scorer'])) for g in expected]:
        raise ValueError('Conflito de autores/ordem dos gols')
    conflicts = []
    for goal, external in zip(goals, expected):
        if external.get('minute_conflict') or goal['minute'] != external.get('minute'):
            conflicts.append({'field': 'goal_minute', 'scorer': goal['scorer'], 'action': 'omit',
                              'provider_value': goal['minute'], 'review': external})
            goal['minute'] = None
    context = {}
    entries = [e for g in summary.get('standings', {}).get('groups', []) for e in g.get('standings', {}).get('entries', [])]
    for tid, side in ids.items() if entries else []:
        found = [e for e in entries if str(e['id']) == tid]
        if len(found) != 1:
            raise ValueError('Campanha ausente/ambígua')
        stats = {s['name']: s for s in found[0]['stats']}
        values = {k: integer(stats[k]) for k in ['gamesPlayed', 'wins', 'ties', 'losses', 'points']}
        if values['gamesPlayed'] != values['wins'] + values['ties'] + values['losses'] or values['points'] != 3 * values['wins'] + values['ties']:
            raise ValueError('Campanha inconsistente')
        # Não deduz posição final/qualificação de tabela parcial.
        context[side] = values
    if context != review.get('campaign'):
        raise ValueError('Campanha diverge da conferência')
    future = {side: upcoming(schedules[tid], tid, now, candidate['competition_code']) for tid, side in ids.items()}
    gaps = [f'{side}.{key}' for side, rows in future.items() for key, value in rows.items() if value is None]
    venue = summary.get('gameInfo', {}).get('venue', {}).get('fullName')
    if not venue or norm(venue) != norm(review.get('venue', '')):
        raise ValueError('Estádio divergente')
    return {'schema_version': 1, 'fixture_id': candidate['fixture_id'], 'generated_at': now.isoformat(),
            'mode': 'facts_only', 'ready_for_drafting': not gaps, 'ready_for_publication': False,
            'validation_method': 'structured_checks_plus_explicit_source_review',
            'match': {k: candidate[k] for k in ['home', 'away', 'match_date', 'competition', 'kickoff']},
            'venue': venue, 'score': score, 'outcome': outcome, 'goals': goals, 'campaign': context,
            'competition_context': review['competition_context'], 'upcoming': future,
            'sources': [{'url': candidate['source_url'], 'checked_at': now.isoformat(),
                         'supports': ['identity', 'score', 'goals', 'venue', 'campaign']},
                        *[{'url': f'{BASE}/all/teams/{tid}/schedule?fixture=true&season={kickoff.year}',
                           'checked_at': now.isoformat(), 'supports': [f'upcoming.{side}']} for tid, side in ids.items()],
                        *review['sources']],
            'conflicts': conflicts, 'gaps': gaps,
            'editorial_rules': ['Placar de pênaltis é separado dos gols da partida; não inferir placar aos 90 minutos nem ocorrência de prorrogação em disputa de pênaltis.',
                                'Não inferir domínio ou qualidade de atuação a partir de placar/estatísticas.',
                                'Não publicar minutos omitidos nem posição final ou classificação não verificadas.',
                                'Horários futuros são de Brasília e devem ser revalidados antes de publicar.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--review', type=Path, required=True)
    p.add_argument('--fixture-id', required=True)
    p.add_argument('--snapshots', type=Path, help='Diretório com summary.json e schedule-ID.json')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    selection = json.loads(a.selection.read_text())
    candidates = [c for c in selection['selected'] if c['fixture_id'] == a.fixture_id]
    if len(candidates) != 1 or not selection.get('collection_complete'):
        raise ValueError('Candidato/seleção incompleto')
    candidate = candidates[0]
    if not re.fullmatch('espn-[0-9]+', a.fixture_id) or not re.fullmatch('[a-z0-9_.-]+', candidate['competition_code']):
        raise ValueError('Identidade inválida')
    if a.snapshots:
        summary = json.loads((a.snapshots / 'summary.json').read_text())
        ids = [str(r['team']['id']) for r in summary['header']['competitions'][0]['competitors']]
        schedules = {i: json.loads((a.snapshots / f'schedule-{i}.json').read_text()) for i in ids}
    elif a.execute:
        summary = fetch(f'{BASE}/{candidate["competition_code"]}/summary?event={a.fixture_id[5:]}')
        ids = [str(r['team']['id']) for r in summary['header']['competitions'][0]['competitors']]
        if not all(i.isdigit() for i in ids): raise ValueError('ID inválido')
        year = when(candidate['kickoff']).year
        schedules = {i: fetch(f'{BASE}/all/teams/{i}/schedule?fixture=true&season={year}') for i in ids}
    else:
        raise ValueError('Informe --snapshots ou --execute')
    print(json.dumps(build(candidate, summary, schedules, json.loads(a.review.read_text())), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
