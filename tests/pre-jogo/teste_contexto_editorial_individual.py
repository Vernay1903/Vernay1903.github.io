#!/usr/bin/env python3
"""Prova editorial: duas fontes individuais não exigem citar o adversário.

Tudo sintético, fonte integral já checada, sem chamadas externas nem publicação.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.extrair_fatos_estruturados import extract_individual_team_context
from scripts.qualidade_editorial_pre_jogo import source_depth_errors

CONFIG = json.loads((ROOT / "config/pre-jogo.json").read_text(encoding="utf-8"))
CTX = {
    "home": "Roma",
    "away": "Real Madrid",
    "competition": "Champions League",
    "competition_slug": "champions-league",
    "kickoff_brasilia": "2026-10-14T16:00:00-03:00",
}


def source(team, side, label, segment, url, year="2026"):
    return {
        "url": url, "title": label, "publisher": "Agência esportiva",
        "source_type": "major_sports_media",
        "published_hint": f"Mon, 12 Oct {year} 15:00:00 GMT",
        "checked_at": "2026-10-13T09:00:00-03:00",
        "content_checked": True, "eligible_for_factual_validation": True,
        "editorial_target_side": side, "editorial_target_team": team,
        "page_evidence": {"metadata": {}, "evidence_segments": [segment]},
    }


def build(rows):
    return extract_individual_team_context(
        [{"id":"editorial_context_both_teams","source_candidates":rows}],
        match_context=CTX, config=CONFIG,
    )


def main():
    roma = source(
        "Roma", "home", "Roma chega pressionada após três empates",
        "A Roma empatou três das últimas quatro partidas oficiais e precisa "
        "melhorar sua eficiência ofensiva antes do compromisso da Champions League.",
        "https://www.terra.com.br/esportes/futebol/roma-atual-2026.html",
    )
    madrid1 = source(
        "Real Madrid", "away", "Real Madrid treina para compromisso europeu",
        "O Real Madrid treinou na segunda-feira em seu centro esportivo para "
        "preparar a equipe para a segunda rodada da Champions League.",
        "https://www.terra.com.br/esportes/futebol/madrid-treino-2026.html",
    )
    madrid2 = source(
        "Real Madrid", "away", "Real Madrid prepara equipe com retorno",
        "O Real Madrid retomou a preparação com retorno de atletas ao trabalho "
        "coletivo depois da última rodada do Campeonato Espanhol.",
        "https://www.terra.com.br/esportes/futebol/madrid-retorno-2026.html",
    )
    result = build([roma, madrid1, madrid2])
    assert result is not None and result["status"] == "verified", result
    fields = {f["field"] for f in result["facts"]}
    assert any(x.startswith("home_stakes_individual_") for x in fields), fields
    assert len([x for x in fields if x.startswith("away_stakes_individual_")]) >= 2, fields
    assert not source_depth_errors({"facts_by_requirement":[result]}), result

    old = source("Roma", "home", "Roma volta a empatar", roma["page_evidence"]["evidence_segments"][0],
                 "https://www.terra.com.br/esportes/futebol/roma-antiga.html", year="2021")
    arbitro = source(
        "Real Madrid", "away", "Árbitro de Real Madrid x Roma já apitou jogos",
        "O árbitro trabalhou numa semifinal de 2025 com o Real Madrid e atuará "
        "na partida europeia entre Roma e Real Madrid em 2026.",
        "https://www.terra.com.br/esportes/futebol/arbitro-real-2026.html",
    )
    assert build([old, arbitro]) is None, "Notícia antiga ou arbitragem não comprova pauta"
    solo = build([roma, old])
    assert solo is not None and source_depth_errors({"facts_by_requirement":[solo]}), (
        "Não se libera uma pauta sem cobertura factual de ambos"
    )
    # A reportagem atual pode mencionar PSG, mas ter o Mônaco como
    # protagonista. Os pontos e a campanha de Mônaco não são fatos do PSG.
    psg_ctx = {
        "home": "Manchester City", "away": "PSG",
        "competition": "Champions League",
        "competition_slug": "champions-league",
        "kickoff_brasilia": "2026-10-14T16:00:00-03:00",
    }
    misleading = source(
        "PSG", "away", "Filipe Luís incomoda PSG em disputa pela Ligue 1",
        "O elenco do brasileiro é líder isolado e está invicto, com "
        "quatro vitórias e um empate, somando 13 pontos no campeonato francês.",
        "https://www.terra.com.br/esportes/futebol/monaco-lider-2026.html",
    )
    from scripts.extrair_fatos_estruturados import extract_individual_team_context
    assert extract_individual_team_context(
        [{"id": "editorial_context_both_teams", "source_candidates": [misleading]}],
        match_context=psg_ctx, config=CONFIG,
    ) is None, "Não atribuir ao PSG os pontos ou a campanha do Mônaco"

    from scripts.ler_fontes_candidatas_passo34_9 import editorial_headline_primary_side
    assert editorial_headline_primary_side(
        "Convocação do Real Madrid contra a Roma", CTX, CONFIG
    ) == "away", "Mencionar Roma como rival não a torna protagonista"
    assert editorial_headline_primary_side(
        "Roma x Real Madrid: onde assistir", CTX, CONFIG
    ) is None
    assert editorial_headline_primary_side(
        "Roma x Real Madrid pela Champions: prévia", CTX, CONFIG
    ) is None
    print("OK: notícias individuais atuais, protagonismo correto e histórico bloqueado.")


if __name__ == "__main__":
    main()
