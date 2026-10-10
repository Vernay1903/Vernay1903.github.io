#!/usr/bin/env python3
"""Protege a extração de elenco por frase e impede árbitro com título colado."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.extrair_fatos_estruturados import (
    extract_optional_team_news_claims,
    extract_referee_name,
)


def main():
    assert extract_referee_name(
        "Árbitro : Paul Tierney Historial de enfrentamientos directos"
    ) == "Paul Tierney"
    assert extract_referee_name("Referee: Clément Turpin") == "Clément Turpin"
    assert extract_referee_name("Arbitro: João de Sousa") == "João de Sousa"
    assert extract_referee_name("Referee: to be announced") is None

    segment = (
        "PSG e Le Mans FC duelam pela Ligue 1 neste domingo. "
        "O PSG confirmou que o lateral está fora do jogo por suspensão. "
        "O Le Mans FC terá o atacante fora do jogo devido a lesão muscular."
    )
    src = {
        "title": "PSG x Le Mans FC pela Ligue 1",
        "publisher": "Goal",
        "url": "https://www.goal.com/exemplo/psg-le-mans-fc",
        "source_type": "major_sports_media",
        "checked_at": "2026-10-10T12:00:00-03:00",
        "content_checked": True,
        "eligible_for_factual_validation": True,
        "page_evidence": {"evidence_segments": [segment]},
    }
    config = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))
    claims = extract_optional_team_news_claims(
        {"id": "probable_lineups_and_coaches", "source_candidates": [src]},
        match_context={"home": "PSG", "away": "Le Mans FC", "competition": "Ligue 1"},
        config=config,
    )
    content = {row["field"]: row["value"] for row in claims}
    assert "suspensão" in content.get("home_team_news_1", "")
    assert "lesão muscular" in content.get("away_team_news_1", "")
    assert "duelam" not in content.get("home_team_news_1", "")
    print("OK: desfalques isolados por frase e nome de árbitro sem cabeçalho agregado.")


if __name__ == "__main__":
    main()
