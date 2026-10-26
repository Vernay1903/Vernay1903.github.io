"""Consulta somente leitura dos jogos da NBA para a agenda do Corte dos Esportes.

Este módulo não publica nem modifica agenda.json. Datas e horários sempre em
America/Sao_Paulo. Se qualquer resposta for incompleta, a coleta falha fechada.
"""

import argparse
import datetime as dt
import json
import re
import time
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
ENDPOINT = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
INVALID_STATES = {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED"}
UNDEFINED_STATES = {"STATUS_DELAYED", "STATUS_SUSPENDED", "STATUS_TBD"}


def download_nba(day):
    url = f"{ENDPOINT}?dates={day:%Y%m%d}&limit=1000&lang=pt&region=br"
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "CorteDosEsportes-Agenda/1.0",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(request, timeout=25) as response:
                if response.status != 200:
                    raise ValueError(f"HTTP {response.status}")
                return json.load(response)
        except Exception as exc:
            if attempt == 2:
                raise RuntimeError(f"Coleta NBA falhou em {day}: {exc}") from exc
            time.sleep(2 ** attempt)


def parse_nba(data, target):
    if not isinstance(data, dict):
        raise ValueError("Resposta NBA não é um objeto")
    leagues = data.get("leagues")
    if not isinstance(leagues, list) or len(leagues) != 1 or leagues[0].get("slug") != "nba":
        raise ValueError("Resposta não corresponde à NBA")
    events = data.get("events")
    if not isinstance(events, list) or len(events) >= 1000:
        raise ValueError("Lista NBA inválida ou possivelmente truncada")

    found = {}
    for event in events:
        event_id = event.get("id")
        raw = event.get("date", "")
        if not event_id or not isinstance(raw, str) or not re.search(r"(Z|[+-]\d{2}:\d{2})$", raw):
            raise ValueError("Jogo NBA sem ID ou horário com fuso")
        start = dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(TZ)
        if start.date() != target:
            continue
        competitions = event.get("competitions")
        if not isinstance(competitions, list) or len(competitions) != 1:
            raise ValueError(f"Confronto NBA inválido: {event_id}")
        competition = competitions[0]
        status = event.get("status") or competition.get("status") or {}
        state = status.get("type", {})
        if state.get("name") in INVALID_STATES:
            continue
        if (state.get("state") not in {"pre", "in", "post"}
            or state.get("name") in UNDEFINED_STATES
            or competition.get("dateValid") is False
            or competition.get("timeValid") is False):
            raise ValueError(f"Status/horário NBA indefinido: {event_id}")
        competitors = competition.get("competitors")
        if not isinstance(competitors, list) or len(competitors) != 2:
            raise ValueError(f"Número de equipes NBA inválido: {event_id}")
        names = {}
        for competitor in competitors:
            side = competitor.get("homeAway")
            team_name = competitor.get("team", {}).get("displayName", "")
            if (side not in {"home", "away"} or side in names
                or not isinstance(team_name, str) or not team_name.strip()
                or team_name.strip().lower() in {"tbd", "a definir", "winner", "loser"}):
                raise ValueError(f"Equipe NBA indefinida: {event_id}")
            names[side] = team_name.strip()
        if set(names) != {"home", "away"}:
            raise ValueError(f"Mandante/visitante NBA indefinido: {event_id}")
        entry = {
            "time": start.strftime("%H:%M"),
            "desc": f"{names['home']} x {names['away']} - NBA",
        }
        key = f"nba:{event_id}"
        if key in found and found[key] != entry:
            raise ValueError(f"Dados NBA divergentes para {key}")
        found[key] = entry
    return found


def collect_nba(target, loader=download_nba):
    """Consulta D-1, D e D+1; retorna somente jogos de D em Brasília."""
    found = {}
    for offset in (-1, 0, 1):
        day = target + dt.timedelta(days=offset)
        payload = loader(day)
        for key, entry in parse_nba(payload, target).items():
            if key in found and found[key] != entry:
                raise ValueError(f"Data/equipes NBA divergentes entre consultas: {key}")
            found[key] = entry
    agenda = sorted(found.values(), key=lambda item: (item["time"], item["desc"]))
    if len({(item["time"], item["desc"]) for item in agenda}) != len(agenda):
        raise ValueError("Jogo NBA duplicado com IDs diferentes")
    return agenda


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Teste de leitura da agenda NBA; nenhuma publicação")
    parser.add_argument("--date", help="Data brasileira YYYY-MM-DD (padrão: hoje)")
    args = parser.parse_args()
    date = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(TZ).date()
    agenda = collect_nba(date)
    print(json.dumps({"date": date.isoformat(), "competition": "NBA", "games": len(agenda), "agenda": agenda}, ensure_ascii=False, indent=2))
