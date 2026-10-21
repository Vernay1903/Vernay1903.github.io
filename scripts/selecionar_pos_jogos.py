"""Piloto de seleção somente. Não redige, publica ou altera arquivos do site."""
import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.coletar_competicoes_pre_jogo import BASE, TEAMS, LEAGUES, fetch

TZ = ZoneInfo('America/Sao_Paulo')
PILOT = {'Flamengo', 'Real Madrid', 'Arsenal', 'Manchester City'}
FINAL = {'STATUS_FULL_TIME', 'STATUS_FINAL', 'STATUS_FINAL_AET', 'STATUS_FINAL_PEN'}


def norm(value):
    value = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.sub('[^a-z0-9]+', ' ', value).split())


def integer(value):
    if isinstance(value, dict):
        value = value.get('value', value.get('displayValue'))
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    if isinstance(value, bool) or not re.fullmatch(r'\d+', str(value)):
        raise ValueError('Placar ausente ou inválido')
    return int(value)


def normalize(event, target, club_id, now):
    comps = event.get('competitions', [])
    if len(comps) != 1:
        raise ValueError('Competição ambígua')
    c = comps[0]
    when = datetime.fromisoformat(c['date'].replace('Z', '+00:00'))
    if when.tzinfo is None:
        raise ValueError('Data sem fuso')
    if when.astimezone(TZ).date() != target:
        return None
    status = c.get('status', {}).get('type', {})
    if status.get('name') not in FINAL or status.get('completed') is not True:
        return None
    if when >= now:
        raise ValueError('Jogo encerrado com início no futuro')
    league = event.get('league', {})
    code = league.get('slug', '')
    if not re.fullmatch(r'[a-z0-9_.-]+', code):
        raise ValueError('Competição não identificada')
    if 'friendl' in (code + norm(league.get('name', ''))):
        return None
    rows = c.get('competitors', [])
    teams = {x['homeAway']: x for x in rows}
    if len(rows) != 2 or set(teams) != {'home', 'away'}:
        raise ValueError('Equipes ambíguas')
    ids = {k: str(v['team']['id']) for k, v in teams.items()}
    if str(club_id) not in ids.values():
        raise ValueError('Equipe divergente do calendário')
    names = {str(i): name for name, (i, _) in TEAMS.items()}
    label = LEAGUES.get(code, ('', league.get('name')))[1]
    if not label or not str(event.get('id', '')).isdigit():
        raise ValueError('Identidade da partida incompleta')
    return {
        'fixture_id': 'espn-' + str(event['id']), 'article_type': 'post_match',
        'match_date': target.isoformat(), 'kickoff': when.astimezone(TZ).isoformat(),
        'home': names.get(ids['home'], teams['home']['team']['displayName']),
        'away': names.get(ids['away'], teams['away']['team']['displayName']),
        'competition': label, 'competition_code': code,
        'status': status['name'],
        'score': {k: integer(v.get('score')) for k, v in teams.items()},
        'source_url': f'{BASE}/{code}/summary?event={event["id"]}',
        'checked_at': now.isoformat(), 'ready_for_publication': False,
    }


def duplicate_reason(match, news):
    """Metadados têm prioridade. Legado ambíguo fica para revisão, nunca é liberado."""
    aliases = {'Manchester City': ['Man City'], 'Bayern de Munique': ['Bayern Munich', 'Bayern']}
    for item in news:
        if norm(item.get('category', '')) != 'futebol':
            continue
        kind = item.get('article_type')
        exact = item.get('fixture_id') == match['fixture_id']
        text = norm(str(item.get('title', '')) + ' ' + str(item.get('url', '')))
        if not exact:
            try:
                raw = item.get('match_date') or item.get('date', '')
                day = date.fromisoformat(raw) if '-' in raw else datetime.strptime(raw, '%d/%m/%Y').date()
            except (ValueError, TypeError):
                continue
            # Data editorial pode ser o dia seguinte ao início da partida.
            if day not in {date.fromisoformat(match['match_date']), date.fromisoformat(match['match_date']) + timedelta(days=1)}:
                continue
            if not all(any(' '+norm(n)+' ' in ' '+text+' ' for n in [match[k], *aliases.get(match[k], [])]) for k in ('home', 'away')):
                continue
        result = bool(re.search(r'\b(resultado|resultados|gols|empatou|empata|venceu|vence|vitoria|derrota)\b|\b\d+\s+x\s+\d+\b', text))
        preview = bool(re.search(r'\b(onde assistir|transmissao|escalacoes|previa|horario)\b', text))
        if kind == 'post_match' or (kind != 'pre_match' and result):
            return 'result_already_published'
        if kind == 'pre_match' or (preview and not result):
            continue
        return 'ambiguous_existing_article_review_required'
    return None


def select(target, news, query=fetch, now=None):
    now = now or datetime.now(TZ)
    config = json.loads((ROOT / 'config/pos-jogo-piloto.json').read_text())
    if set(config['monitored_clubs']) != PILOT or len(config['monitored_clubs']) != 4 or config.get('publication_enabled') is not False:
        raise ValueError('Escopo do piloto inválido')
    candidates, blocked, errors = {}, [], []
    for club in config['monitored_clubs']:
        club_id, expected = TEAMS[club]
        try:
            data = query(f'{BASE}/all/teams/{club_id}/schedule?season={target.year}')
            team = data.get('team', {})
            if str(team.get('id')) != str(club_id) or team.get('displayName') != expected or team.get('isNational') is True:
                raise ValueError('Identidade do clube divergente')
            if not isinstance(data.get('events'), list):
                raise ValueError('Calendário ausente')
            for event in data['events']:
                row = normalize(event, target, club_id, now)
                if row is None:
                    continue
                key = row['fixture_id']
                if key in candidates and candidates[key] != row:
                    blocked.append({'fixture_id': key, 'reason': 'conflicting_calendar_data'})
                else:
                    candidates[key] = row
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors.append({'club': club, 'reason': str(exc)})
    conflict_ids = {r['fixture_id'] for r in blocked}
    selected = []
    for key, row in sorted(candidates.items()):
        if key in conflict_ids:
            continue
        reason = duplicate_reason(row, news)
        if reason:
            blocked.append({'fixture_id': key, 'home': row['home'], 'away': row['away'], 'reason': reason})
        else:
            selected.append(row)
    return {'mode': 'selection_only', 'target_date': target.isoformat(), 'clubs': config['monitored_clubs'],
            'collection_complete': not errors, 'selected': selected, 'blocked': blocked, 'errors': errors,
            'publication_enabled': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True)
    parser.add_argument('--noticias', type=Path, default=ROOT / 'noticias.json')
    parser.add_argument('--snapshots', type=Path, help='JSON de calendários por ID para teste offline')
    args = parser.parse_args()
    news = json.loads(args.noticias.read_text())
    if not isinstance(news, list) or not all(isinstance(n, dict) for n in news):
        raise ValueError('noticias.json inválido')
    query = fetch
    if args.snapshots:
        snapshots = json.loads(args.snapshots.read_text())
        query = lambda url: snapshots[url.split('/teams/')[1].split('/')[0]]
    report = select(date.fromisoformat(args.date), news, query)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
