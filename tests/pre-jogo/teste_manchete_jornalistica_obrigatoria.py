#!/usr/bin/env python3
"""Regressão do erro real de 18/10/2026: homepage não pode exibir 'Jogo: horário'."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import montar_pacote_editorial as editorial


def main():
    config = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))
    article = {
        "title": "Bahia x Flamengo pelo Brasileirão: transmissão, horário e prováveis escalações",
        "excerpt": "Bahia e Flamengo se enfrentam pelo Brasileirão.",
        "date": "18/10/2026",
        "match_context": {
            "home": "Bahia", "away": "Flamengo", "display_home": "Bahia", "display_away": "Flamengo",
            "competition": "Brasileirão", "competition_slug": "brasileirao",
            "competition_stage": "REGULAR_SEASON", "competition_matchday": 31,
            "kickoff_brasilia": "2026-10-18T18:30:00-03:00",
        },
    }
    valid = {
        "editorial_match_stakes": {
            "id": "editorial_match_stakes", "status": "verified",
            "facts": [
                {"field": "home_stakes_1", "text": "Na tabela atual do Brasileirão, Bahia ocupa a posição 6, com 49 pontos em 30 jogos disputados."},
                {"field": "away_stakes_1", "text": "Na tabela atual do Brasileirão, Flamengo ocupa a posição 2, com 64 pontos em 30 jogos disputados."},
                {"field": "competitive_context", "text": "Os dois times estão separados por 15 pontos na classificação."},
            ],
        },
    }
    title, excerpt = editorial.adjusted_service_headline(article, valid, config=config)
    assert "vice-líder visita 6º colocado" in title, title
    assert "49 pontos" in excerpt and "64 pontos" in excerpt, excerpt
    assert "31ª rodada" in excerpt, excerpt
    assert not editorial.approved_headline_errors(title, valid, config=config), title
    assert not editorial.approved_excerpt_errors(excerpt), excerpt
    for bad_title in [
        "Real Madrid x Sevilla pela La Liga: horário",
        "Bahia x Flamengo pelo Brasileirão: horário e transmissão",
        "Bahia x Flamengo pelo Brasileirão: horário, prováveis escalações e transmissão",
    ]:
        assert "headline_sem_gancho_editorial" in editorial.approved_headline_errors(
            bad_title, valid, config=config,
        ), bad_title
    bad_excerpt = "As equipes se enfrentam neste domingo (18/10), pela 31ª rodada do Brasileirão."
    assert editorial.approved_excerpt_errors(bad_excerpt)
    insufficient_title, insufficient_excerpt = editorial.adjusted_service_headline(
        article, {}, config=config,
    )
    assert editorial.approved_headline_errors(insufficient_title, {}, config=config)
    assert editorial.approved_excerpt_errors(insufficient_excerpt)
    missing_points = json.loads(json.dumps(valid))
    missing_points["editorial_match_stakes"]["facts"][1]["text"] = "Flamengo tem posição desconhecida."
    fallback_title, fallback_excerpt = editorial.adjusted_service_headline(
        article, missing_points, config=config,
    )
    assert editorial.approved_headline_errors(fallback_title, missing_points, config=config)
    assert editorial.approved_excerpt_errors(fallback_excerpt)
    print("OK: título e resumo com pauta e números verificados; chamados genéricos bloqueados.")


if __name__ == "__main__":
    main()
