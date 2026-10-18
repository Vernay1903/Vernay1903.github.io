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
    target = "Bahia x Flamengo: veja escalações, destaques e onde assistir"
    # Informações da classificação, por si só, NÃO autorizam a promessa
    # dos serviços em destaque.
    blocked, excerpt = editorial.adjusted_service_headline(article, valid, config=config)
    assert blocked == target
    errors = editorial.approved_headline_errors(blocked, valid, config=config)
    assert {"required_transmission_not_verified", "required_probable_lineups_not_verified"} <= set(errors)
    assert "49 pontos" in excerpt and "64 pontos" in excerpt
    assert not editorial.approved_excerpt_errors(excerpt), excerpt

    players_a = "; ".join(f"Jogador Bahia {i}" for i in range(1, 12))
    players_b = "; ".join(f"Jogador Flamengo {i}" for i in range(1, 12))
    valid["probable_lineups_and_coaches"] = {
        "id": "probable_lineups_and_coaches", "status": "verified",
        "facts": [
            {"field": "home_lineup", "text": "Bahia: " + players_a + "."},
            {"field": "away_lineup", "text": "Flamengo: " + players_b + "."},
            {"field": "home_coach", "text": "Técnico Bahia: Exemplo A."},
            {"field": "away_coach", "text": "Técnico Flamengo: Exemplo B."},
        ],
    }
    valid["transmission"] = {
        "id": "transmission", "status": "verified",
        "facts": [{"field": "transmission", "text": "Transmissão: Plataforma Exemplo."}],
    }
    title, excerpt = editorial.adjusted_service_headline(article, valid, config=config)
    assert title == target
    assert editorial.approved_headline_errors(title, valid, config=config) == []
    assert editorial.approved_excerpt_errors(excerpt) == []

    for bad_title in [
        "Real Madrid x Sevilla pela La Liga: horário",
        "Bahia x Flamengo pelo Brasileirão: horário e transmissão",
        "Bahia x Flamengo pelo Brasileirão: horário, prováveis escalações e transmissão",
        "Bahia x Flamengo: veja escalações e onde assistir",
        "Bahia x Flamengo pelo Brasileirão: vice-líder visita sexto colocado",
    ]:
        assert "titulo_fora_do_modelo_fixo" in editorial.approved_headline_errors(
            bad_title, valid, config=config,
        ), bad_title
    bad_excerpt = "As equipes se enfrentam neste domingo (18/10), pela 31ª rodada do Brasileirão."
    assert editorial.approved_excerpt_errors(bad_excerpt)
    lacking_facts = json.loads(json.dumps(valid))
    lacking_facts["transmission"]["facts"] = []
    assert "required_transmission_not_verified" in editorial.approved_headline_errors(
        title, lacking_facts, config=config,
    )
    lacking_facts = json.loads(json.dumps(valid))
    lacking_facts["probable_lineups_and_coaches"]["facts"][0]["text"] = "Bahia: somente um jogador."
    assert "required_probable_lineups_not_verified" in editorial.approved_headline_errors(
        title, lacking_facts, config=config,
    )
    print("OK: título fixo com escalações e onde assistir só quando ambos os serviços estão verificados.")


if __name__ == "__main__":
    main()
