#!/usr/bin/env python3
"""Regressão offline: classificação oficial complementa a pauta, sem inventar notícias."""
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.enriquecer_fatos_football_data import (
    verified_standings_context, attach_standings_context,
)
from scripts.qualidade_editorial_pre_jogo import source_depth_errors


def snapshot():
    return {
        "competition": {"code": "PL"},
        "season": {"startDate": "2026-08-01", "endDate": "2027-05-31"},
        "standings": [
            {"type": "TOTAL", "table": [
                {"position": 3, "playedGames": 8, "points": 17, "goalDifference": 11, "team": {"id": 57}},
                {"position": 14, "playedGames": 8, "points": 9, "goalDifference": -6, "team": {"id": 66}},
            ]}
        ],
    }


def extract(data):
    return verified_standings_context(
        data, code="PL", home_id=66, away_id=57,
        home="Nottingham Forest", away="Arsenal", competition="Premier League",
        cutoff=datetime(2026, 10, 18, 15, 30, tzinfo=ZoneInfo("America/Sao_Paulo")),
    )


def main():
    config = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))
    data = snapshot()
    facts = extract(data)
    assert facts and len(facts) == 3, facts
    assert "9 pontos" in facts[0]["text"] and "17 pontos" in facts[1]["text"]
    assert "8 pontos" in facts[2]["text"] and "saldo de -6 gols" in facts[2]["text"]
    assert extract({**data, "season": {"startDate": "2025-08-01", "endDate": "2026-05-31"}}) is None
    assert extract({**data, "competition": {"code": "SA"}}) is None
    assert extract({**data, "standings": [
        {"type": "TOTAL", "table": [data["standings"][0]["table"][0]]},
        {"type": "TOTAL", "table": [data["standings"][0]["table"][1]]},
    ]}) is None, "Times de grupos diferentes não podem ser comparados"
    assert extract({**data, "standings": [
        {"type": "TOTAL", "table": [
            {"position": 3, "playedGames": 8, "points": None, "team": {"id": 57}},
            data["standings"][0]["table"][1],
        ]}
    ]}) is None, "Pontuação ausente não pode ser deduzida"
    assert verified_standings_context(
        data, code="CL", home_id=66, away_id=57,
        home="Nottingham Forest", away="Arsenal", competition="Champions",
        cutoff=datetime(2026, 10, 18, 15, 30, tzinfo=ZoneInfo("America/Sao_Paulo")),
    ) is None
    enriched = attach_standings_context(
        [], facts, "https://api.football-data.org/v4/competitions/PL/standings",
        "2026-10-18T08:00:00-03:00", config,
    )
    assert enriched[0]["status"] == "verified", enriched
    assert enriched[0]["id"] == "editorial_match_stakes", enriched
    assert source_depth_errors({"facts_by_requirement": enriched}) == [], source_depth_errors({"facts_by_requirement": enriched})
    news = {"id": "editorial_match_stakes", "status": "verified", "facts": [
        {"field": "home_team_news_1", "text":
            "Nottingham Forest recuperou um titular após lesão muscular e confirmou o retorno aos treinos para o confronto."}
    ], "sources": [{
        "publisher": "Imprensa", "url": "https://example.com/noticia",
        "source_type": "major_sports_media", "checked_at": "2026-10-18T08:00:00-03:00",
    }]}
    combined = attach_standings_context(
        [news], facts, "https://api.football-data.org/v4/competitions/PL/standings",
        "2026-10-18T08:00:00-03:00", config,
    )
    fields = {f["field"] for f in combined[0]["facts"]}
    assert "home_team_news_1" in fields and "competitive_context" in fields, fields
    print("OK: tabela oficial gera contexto bilateral atual; temporadas/grupos inválidos e informações ausentes bloqueados.")


if __name__ == "__main__":
    main()
