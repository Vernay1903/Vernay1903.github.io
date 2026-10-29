"""Coleta somente leitura da Superliga A masculina/feminina no portal oficial da CBV.

A CBV entrega os jogos dentro de "matchesByRound" no HTML público Next.js.
A origem fornece timestamps com fuso; sempre converter para America/Sao_Paulo.
Este módulo jamais modifica agenda.json ou executa publicação.
"""
import argparse
import datetime as dt
from html.parser import HTMLParser
import json
import re
import time
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
BASE = "https://cbv.com.br/volei-de-quadra/superliga-a-"
GENDERS = ("masculina", "feminina")
NAMES = {"masculina": "Superliga Masculina", "feminina": "Superliga Feminina"}


def download(gender):
    if gender not in GENDERS:
        raise ValueError("Competição não autorizada")
    url = BASE + gender
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; CorteDosEsportesAgenda/1.0)",
                "Accept": "text/html",
                "Accept-Language": "pt-BR,pt;q=0.9",
            })
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status != 200:
                    raise ValueError(f"HTTP {response.status}")
                data = response.read(5_000_001)
                if len(data) > 5_000_000:
                    raise ValueError("Documento CBV excedeu tamanho máximo")
                text = data.decode("utf-8")
                if len(text) < 1000:
                    raise ValueError("Página CBV incompleta")
                return text
        except Exception as exc:
            if attempt == 2:
                raise RuntimeError(f"CBV {gender}: falha ao consultar: {exc}") from exc
            time.sleep(attempt + 1)


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inscript = False
        self.parts = []
        self.current = []
    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.inscript = True
            self.current = []
    def handle_endtag(self, tag):
        if tag == "script" and self.inscript:
            self.parts.append("".join(self.current))
            self.current = []
            self.inscript = False
    def handle_data(self, data):
        if self.inscript:
            self.current.append(data)


def _read_matches_by_round(html):
    parser = _Scripts()
    parser.feed(html)
    chunks = []
    for script in parser.parts:
        script = script.strip()
        if not script.startswith("self.__next_f.push(") or not script.endswith(")"):
            continue
        payload = json.loads(script[len("self.__next_f.push("):-1])
        if isinstance(payload, list) and len(payload) >= 2 and payload[0] == 1 and isinstance(payload[1], str):
            chunks.append(payload[1])
    if not chunks:
        raise ValueError("A CBV não retornou dados estruturados Next.js")
    stream = "".join(chunks)
    key = '"matchesByRound":'
    if stream.count(key) != 1:
        raise ValueError("Tabela da CBV ausente ou ambígua")
    start = stream.index(key) + len(key)
    rounds, end = json.JSONDecoder().raw_decode(stream[start:])
    if not isinstance(rounds, dict) or not rounds:
        raise ValueError("Rodadas da CBV incompletas")
    entries = []
    for label, games in rounds.items():
        if not isinstance(label, str) or not isinstance(games, list):
            raise ValueError("Estrutura da rodada CBV inválida")
        for game in games:
            if not isinstance(game, dict):
                raise ValueError("Partida CBV inválida")
            entries.append(game)
    if len(entries) < 10 or len(entries) > 600:
        raise ValueError(f"Número de partidas CBV fora dos limites: {len(entries)}")
    return entries


def parse_superliga(html, gender, target):
    if gender not in GENDERS or not isinstance(html, str) or not isinstance(target, dt.date):
        raise ValueError("Parâmetros da coleta CBV inválidos")
    if f">{gender.capitalize()}</span>" not in html or "Superliga" not in html:
        raise ValueError("Página não corresponde à Superliga solicitada")
    games = _read_matches_by_round(html)
    seen_ids = {}
    seen_desc = set()
    result = []
    seasons = set()
    for item in games:
        raw = item.get("MatchDateTime")
        if not isinstance(raw, str) or not re.search(r"(Z|[+-]\d\d:\d\d)$", raw):
            raise ValueError("Partida CBV sem data/hora com fuso")
        start = dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(TZ)
        seasons.add(start.year)
        if start.date() != target:
            continue
        game_id = item.get("ChampionshipMatch_ID")
        if not isinstance(game_id, int) or game_id <= 0:
            raise ValueError("Partida CBV sem identificação")
        home, away = item.get("HomeTeam"), item.get("GuestTeam")
        if (not isinstance(home, str) or not isinstance(away, str)
            or not home.strip() or not away.strip() or home.strip() == away.strip()):
            raise ValueError("Equipes CBV inválidas")
        if item.get("postponed") is True:
            continue
        if item.get("postponed") is not False:
            raise ValueError("Situação de adiamento CBV indefinida")
        home = " ".join(home.split())
        away = " ".join(away.split())
        if any(ch in home + away for ch in "\r\n\x00"):
            raise ValueError("Nome de equipe CBV inválido")
        entry = {"time": start.strftime("%H:%M"), "desc": f"{home} x {away} - {NAMES[gender]}"}
        old = seen_ids.get(game_id)
        if old and old != entry:
            raise ValueError("Dados CBV divergentes para a mesma partida")
        if old is None:
            if (entry["time"], entry["desc"]) in seen_desc:
                raise ValueError("Partida CBV duplicada com identificadores diferentes")
            seen_ids[game_id] = entry
            seen_desc.add((entry["time"], entry["desc"]))
            result.append(entry)
    if target.year not in seasons:
        raise ValueError("Temporada CBV não cobre o ano solicitado; não publicar dados desatualizados")
    return sorted(result, key=lambda item: (item["time"], item["desc"]))


def collect_one(gender, target, loader=download):
    return parse_superliga(loader(gender), gender, target)


def collect_both(target, loader=download):
    """Cada gênero tem seu status; falha de um não bloqueia o outro."""
    collected, statuses = [], {}
    for gender in GENDERS:
        try:
            entries = collect_one(gender, target, loader)
            collected.extend(entries)
            statuses[gender] = {"status": "ok", "count": len(entries)}
        except Exception as exc:
            statuses[gender] = {"status": "unavailable", "count": 0, "error": str(exc)[:300]}
    if len({(e["time"], e["desc"]) for e in collected}) != len(collected):
        raise ValueError("Jogos duplicados entre as duas Superligas")
    return sorted(collected, key=lambda e: (e["time"], e["desc"])), statuses


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Diagnóstico CBV somente leitura")
    p.add_argument("--date", help="Data brasileira YYYY-MM-DD")
    args = p.parse_args()
    day = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(TZ).date()
    matches, statuses = collect_both(day)
    print(json.dumps({"date": day.isoformat(), "superligas": statuses, "agenda": matches},
                     ensure_ascii=False, indent=2))
    if any(v["status"] != "ok" for v in statuses.values()):
        raise SystemExit("Coleta de uma ou mais Superligas indisponível")
