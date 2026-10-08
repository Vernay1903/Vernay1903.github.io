"""Complementa estádio, forma recente e H2H com dados estruturados gratuitos da ESPN.

Usa apenas o mesmo provedor já empregado na descoberta/revalidação de partidas.
Não inventa fatos, não publica e não substitui estádio fixo aprovado quando o clube
monitorado é mandante.
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import validar_pesquisa_factual as factual_validator  # noqa: E402
from scripts.coletar_competicoes_pre_jogo import BASE, fetch  # noqa: E402

BUILD = ROOT / "build" / "pre-jogo"
TZ = ZoneInfo("America/Sao_Paulo")
MIN_FORM_GAMES = 2


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    if isinstance(value, dict):
        for key in ("value", "displayValue"):
            parsed = _as_int(value.get(key))
            if parsed is not None:
                return parsed
        return None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _competition(event: dict[str, Any]) -> dict[str, Any] | None:
    rows = event.get("competitions")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return None
    return rows[0]


def _when(event: dict[str, Any]) -> datetime | None:
    comp = _competition(event)
    raw = comp.get("date") if comp else event.get("date")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _completed(event: dict[str, Any]) -> bool:
    comp = _competition(event)
    status = comp.get("status") if comp else event.get("status")
    stype = status.get("type") if isinstance(status, dict) else None
    if not isinstance(stype, dict):
        return False
    if stype.get("completed") is True:
        return True
    return stype.get("name") in {"STATUS_FULL_TIME", "STATUS_FINAL", "STATUS_FINAL_AET", "STATUS_FINAL_PEN"}


def _teams(event: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    comp = _competition(event)
    competitors = comp.get("competitors") if comp else None
    if not isinstance(competitors, list):
        return None
    rows: dict[str, dict[str, Any]] = {}
    for item in competitors:
        if not isinstance(item, dict) or item.get("homeAway") not in {"home", "away"}:
            continue
        team = item.get("team")
        if not isinstance(team, dict) or not str(team.get("id", "")).isdigit():
            continue
        rows[item["homeAway"]] = item
    return rows if set(rows) == {"home", "away"} else None


def _league_code(event: dict[str, Any]) -> str:
    league = event.get("league")
    return str(league.get("slug") or "") if isinstance(league, dict) else ""


def _score_pair(event: dict[str, Any]) -> tuple[int, int] | None:
    teams = _teams(event)
    if not teams or not _completed(event):
        return None
    home = _as_int(teams["home"].get("score"))
    away = _as_int(teams["away"].get("score"))
    if home is None or away is None:
        return None
    return home, away


def _team_id(item: dict[str, Any]) -> str:
    team = item.get("team")
    return str(team.get("id")) if isinstance(team, dict) else ""


def _team_name(item: dict[str, Any]) -> str | None:
    team = item.get("team")
    if not isinstance(team, dict):
        return None
    for key in ("shortDisplayName", "displayName", "name"):
        value = team.get(key)
        if isinstance(value, str) and value.strip() and ";" not in value and "\n" not in value:
            return value.strip()
    return None


def _schedule_events(data: dict[str, Any], team_id: str, cutoff: datetime) -> list[tuple[datetime, dict[str, Any]]]:
    team = data.get("team")
    if not isinstance(team, dict) or str(team.get("id")) != str(team_id):
        raise ValueError("Calendário ESPN devolveu identidade de equipe divergente.")
    events = data.get("events")
    if not isinstance(events, list):
        raise ValueError("Calendário ESPN sem lista de eventos.")
    result: list[tuple[datetime, dict[str, Any]]] = []
    for event in events:
        if not isinstance(event, dict) or not _completed(event):
            continue
        when = _when(event)
        teams = _teams(event)
        if when is None or teams is None or when >= cutoff or when > datetime.now(when.tzinfo):
            continue
        if str(team_id) not in {_team_id(teams["home"]), _team_id(teams["away"])}:
            continue
        if _score_pair(event) is None:
            continue
        result.append((when, event))
    result.sort(key=lambda row: row[0], reverse=True)
    return result


def recent_facts(data: dict[str, Any], team_id: str, team_name: str, cutoff: datetime, field_prefix: str) -> list[dict[str, str]] | None:
    rows = _schedule_events(data, team_id, cutoff)[:5]
    if len(rows) < MIN_FORM_GAMES:
        return None
    wins = draws = losses = 0
    details: list[str] = []
    for when, event in rows:
        teams = _teams(event)
        score = _score_pair(event)
        if not teams or not score:
            continue
        home_id = _team_id(teams["home"])
        hg, ag = score
        goals, conceded = (hg, ag) if str(team_id) == home_id else (ag, hg)
        if goals > conceded:
            wins += 1
        elif goals == conceded:
            draws += 1
        else:
            losses += 1
        home_name = _team_name(teams["home"])
        away_name = _team_name(teams["away"])
        if home_name and away_name:
            league = event.get("league")
            comp = league.get("name") if isinstance(league, dict) else None
            suffix = f" ({comp})" if isinstance(comp, str) and comp.strip() else ""
            details.append(f"{when.astimezone(TZ).strftime('%d/%m/%Y')}: {home_name} {hg} x {ag} {away_name}{suffix}")
    if wins + draws + losses != len(rows):
        return None
    facts = [{
        "field": f"{field_prefix}_recent_form",
        "text": (
            f"Forma recente do {team_name}: nos últimos {len(rows)} jogos, "
            f"{wins} {'vitória' if wins == 1 else 'vitórias'}, "
            f"{draws} {'empate' if draws == 1 else 'empates'} e "
            f"{losses} {'derrota' if losses == 1 else 'derrotas'}."
        ),
    }]
    if len(details) >= MIN_FORM_GAMES:
        facts.append({
            "field": f"{field_prefix}_recent_matches",
            "text": f"Resultados recentes do {team_name}: " + "; ".join(details) + ".",
        })
    return facts


def h2h_facts(data: dict[str, Any], home_id: str, away_id: str, home_name: str, away_name: str,
              competition: str, competition_code: str, cutoff: datetime) -> list[dict[str, str]] | None:
    rows = _schedule_events(data, home_id, cutoff)
    games = home_wins = away_wins = draws = 0
    for _when, event in rows:
        if _league_code(event) != competition_code:
            continue
        teams = _teams(event)
        score = _score_pair(event)
        if not teams or not score:
            continue
        if {_team_id(teams["home"]), _team_id(teams["away"])} != {str(home_id), str(away_id)}:
            continue
        hg, ag = score
        games += 1
        if hg == ag:
            draws += 1
        else:
            winner = _team_id(teams["home"]) if hg > ag else _team_id(teams["away"])
            if winner == str(home_id):
                home_wins += 1
            elif winner == str(away_id):
                away_wins += 1
    if games == 0 or games != home_wins + away_wins + draws:
        return None
    return [
        {"field": "h2h_games", "text": f"Confrontos anteriores disponíveis pela {competition}: {games} jogos."},
        {"field": "h2h_home_wins", "text": f"Vitórias do {home_name} nesses jogos pela {competition}: {home_wins}."},
        {"field": "h2h_away_wins", "text": f"Vitórias do {away_name} nesses jogos pela {competition}: {away_wins}."},
        {"field": "h2h_draws", "text": f"Empates nesses jogos pela {competition}: {draws}."},
    ]


def venue_from_summary(data: dict[str, Any], fixture: dict[str, Any]) -> str | None:
    src = fixture.get("provider_data") if isinstance(fixture.get("provider_data"), dict) else {}
    mid = str(src.get("match_id") or "")
    code = str(src.get("competition_code") or "")
    header = data.get("header")
    if not isinstance(header, dict) or str(header.get("id")) != mid:
        return None
    league = header.get("league")
    if not isinstance(league, dict) or str(league.get("slug")) != code:
        return None
    competitions = header.get("competitions")
    if not isinstance(competitions, list) or len(competitions) != 1 or not isinstance(competitions[0], dict):
        return None
    comp = competitions[0]
    competitors = comp.get("competitors")
    if not isinstance(competitors, list):
        return None
    ids = {str(item.get("homeAway")): str((item.get("team") or {}).get("id")) for item in competitors if isinstance(item, dict)}
    if ids.get("home") != str(src.get("home_team_id")) or ids.get("away") != str(src.get("away_team_id")):
        return None
    candidates = []
    game_info = data.get("gameInfo")
    if isinstance(game_info, dict):
        candidates.append(game_info.get("venue"))
    candidates.append(comp.get("venue"))
    for venue in candidates:
        if not isinstance(venue, dict):
            continue
        for key in ("fullName", "name"):
            value = venue.get(key)
            if isinstance(value, str) and 3 <= len(value.strip()) <= 120:
                return value.strip()
    return None


def validated_update(req: dict[str, Any], facts: list[dict[str, str]], urls: list[str], now: str,
                     config: dict[str, Any], *, replace_verified: bool = False) -> dict[str, Any]:
    if req.get("conflict_detected") is True:
        return req
    if req.get("status") == "verified" and not replace_verified:
        return req
    base = deepcopy(req)
    base["status"] = "pending"
    base["facts"] = []
    base["sources"] = []
    base["conflict_detected"] = False
    base["conflicts"] = []
    evidence = {
        "status": "verified",
        "facts": facts,
        "sources": [
            {"publisher": "ESPN", "url": url, "source_type": "structured_data_provider", "checked_at": now}
            for url in sorted(set(urls))
        ],
        "notes": None,
    }
    validated, errors = factual_validator.validate_requirement_evidence(base, evidence, config=config)
    if errors:
        raise ValueError("Evidência ESPN não passou no validador: " + "; ".join(errors))
    validated["fact_extraction_status"] = "validated_structured_espn"
    validated["structured_fact_count"] = len(facts)
    validated["validator_accepted"] = True
    validated["conflict_detected"] = False
    validated["internal_provenance_only"] = True
    return validated


def enrich(article: dict[str, Any], fixture: dict[str, Any], query, now: str, config: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(article)
    if not isinstance(fixture, dict):
        return result
    espn_fixture = fixture if fixture.get("provider") == "espn" else fixture.get("supplemental_fixture")
    if not isinstance(espn_fixture, dict) or espn_fixture.get("provider") != "espn":
        return result
    ctx = result.get("match_context") if isinstance(result.get("match_context"), dict) else {}
    src = espn_fixture.get("provider_data") if isinstance(espn_fixture.get("provider_data"), dict) else {}
    home_id = str(src.get("home_team_id") or "")
    away_id = str(src.get("away_team_id") or "")
    mid = str(src.get("match_id") or "")
    code = str(src.get("competition_code") or "")
    if not (home_id.isdigit() and away_id.isdigit() and mid.isdigit() and code):
        return result
    try:
        cutoff = datetime.fromisoformat(str(espn_fixture["kickoff"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return result
    if cutoff.astimezone(TZ) <= datetime.now(TZ):
        return result
    home = ctx.get("home")
    away = ctx.get("away")
    competition = ctx.get("competition")
    if not all(isinstance(value, str) and value.strip() for value in (home, away, competition)):
        return result

    summary_url = f"{BASE}/{code}/summary?event={mid}"
    summary = query(summary_url)

    def load_schedule(team_id: str) -> tuple[dict[str, Any] | None, str | None]:
        year = cutoff.astimezone(TZ).year
        urls = [
            f"{BASE}/{code}/teams/{team_id}/schedule?season={year}",
            f"{BASE}/all/teams/{team_id}/schedule?season={year}",
            f"{BASE}/all/teams/{team_id}/schedule?fixture=true",
        ]
        fallback: tuple[dict[str, Any] | None, str | None] = (None, None)
        for url in urls:
            try:
                data = query(url)
                rows = _schedule_events(data, team_id, cutoff)
            except Exception:
                continue
            fallback = (data, url)
            if len(rows) >= MIN_FORM_GAMES:
                return data, url
        return fallback

    home_schedule, home_url = load_schedule(home_id)
    away_schedule, away_url = load_schedule(away_id)

    venue = venue_from_summary(summary, espn_fixture)
    home_recent = (
        recent_facts(home_schedule, home_id, home, cutoff, "home")
        if isinstance(home_schedule, dict) else None
    )
    away_recent = (
        recent_facts(away_schedule, away_id, away, cutoff, "away")
        if isinstance(away_schedule, dict) else None
    )
    h2h = (
        h2h_facts(home_schedule, home_id, away_id, home, away, competition, code, cutoff)
        if isinstance(home_schedule, dict) else None
    )

    updated = []
    for req in result.get("requirements", []):
        if not isinstance(req, dict):
            updated.append(req)
            continue
        req_id = req.get("id")
        if req_id == "stadium_and_location" and venue and req.get("editorial_stadium_override") is not True:
            updated.append(validated_update(
                req, [{"field": "stadium", "text": f"A partida será disputada no {venue}."}],
                [summary_url], now, config, replace_verified=True,
            ))
        elif req_id == "recent_form_both_teams" and home_recent and away_recent and home_url and away_url:
            updated.append(validated_update(
                req, home_recent + away_recent, [home_url, away_url], now, config, replace_verified=True,
            ))
        elif req_id == "competition_specific_head_to_head" and h2h and home_url:
            updated.append(validated_update(req, h2h, [home_url], now, config))
        else:
            updated.append(req)
    result["requirements"] = updated
    result["structured_fact_count"] = sum(len(r.get("facts", [])) for r in updated if isinstance(r, dict))
    result["validator_accepted_requirement_ids"] = [
        r["id"] for r in updated if isinstance(r, dict) and r.get("status") == "verified"
    ]
    result["free_structured_espn_supplement_applied"] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Sem --execute não há consulta externa.")
    path = BUILD / f"fatos-estruturados-{args.date}.json"
    fixtures_path = BUILD / "fixtures-normalizados.json"
    if not path.exists() or not fixtures_path.exists():
        raise SystemExit("Manifesto factual ou fixtures ausentes.")
    config = json.loads((ROOT / "config" / "pre-jogo.json").read_text(encoding="utf-8"))
    data = json.loads(path.read_text(encoding="utf-8"))
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    if data.get("target_date") != args.date or fixtures.get("target_date") != args.date:
        raise SystemExit("Data-alvo divergente.")
    by_id = {str(row.get("id")): row for row in fixtures.get("fixtures", []) if isinstance(row, dict)}
    cache: dict[str, dict[str, Any]] = {}
    def query(url: str) -> dict[str, Any]:
        if not url.startswith(BASE + "/"):
            raise ValueError("URL ESPN fora do provedor permitido.")
        if url not in cache:
            cache[url] = fetch(url)
        return cache[url]
    checked = datetime.now(TZ).isoformat()
    articles = []
    for article in data.get("articles", []):
        if not isinstance(article, dict):
            continue
        fixture = by_id.get(str(article.get("fixture_id")))
        articles.append(enrich(article, fixture, query, checked, config) if fixture else article)
    data["articles"] = articles
    data["free_structured_espn_supplement"] = True
    data["structured_fact_count"] = sum(a.get("structured_fact_count", 0) for a in articles)
    if not args.force:
        raise SystemExit("É obrigatório --force para substituir somente arquivo de build.")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ESPN: reforço factual gratuito sem publicação.")
    for article in articles:
        fields = [
            r.get("id") for r in article.get("requirements", [])
            if isinstance(r, dict) and r.get("fact_extraction_status") == "validated_structured_espn"
        ]
        print(article.get("slug"), "campos reforçados=", fields)


if __name__ == "__main__":
    main()
