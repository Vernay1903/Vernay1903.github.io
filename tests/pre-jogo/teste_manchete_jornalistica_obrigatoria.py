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

    # Confrontos de copa sem tabela de pontos devem usar os fatos atuais
    # efetivamente verificados; excerpt não pode ficar apenas em dia/rodada.
    cup = json.loads(json.dumps(article))
    cup["match_context"]["competition"] = "Champions League"
    cup["match_context"]["competition_slug"] = "champions-league"
    cup["match_context"]["competition_stage"] = "LEAGUE_STAGE"
    no_table = {
        "recent_form_both_teams": {
            "id": "recent_form_both_teams", "status": "verified",
            "facts": [
                {"field": "home_recent_form", "text":
                 "Forma recente do Bahia: nos últimos cinco jogos da competição, "
                 "três vitórias, um empate e uma derrota."},
                {"field": "away_recent_form", "text":
                 "Forma recente do Flamengo: nos últimos cinco jogos da competição, "
                 "quatro vitórias e uma derrota."},
            ],
        }
    }
    _title, factual_excerpt = editorial.adjusted_service_headline(
        cup, no_table, config=config,
    )
    assert factual_excerpt.startswith("As equipes se enfrentam neste domingo"), factual_excerpt
    assert "três vitórias" in factual_excerpt and "quatro vitórias" in factual_excerpt
    assert editorial.approved_excerpt_errors(factual_excerpt) == [], factual_excerpt
    # Sem nenhum dado, permanece curto e bloqueado: jamais inventar contexto.
    _, empty_excerpt = editorial.adjusted_service_headline(cup, {}, config=config)
    assert editorial.approved_excerpt_errors(empty_excerpt)

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
    # O início com o dia da semana é obrigatório no padrão editorial;
    # só deve passar quando a chamada também traz contexto esportivo.
    boa_abertura = (
        "As equipes se enfrentam neste domingo (18/10), pela 31ª rodada do "
        "Brasileirão. O Bahia ocupa a sexta colocação com 49 pontos e recebe "
        "o Flamengo, segundo colocado com 64 pontos, em uma partida que "
        "pode alterar a disputa pelas primeiras posições."
    )
    assert editorial.approved_excerpt_errors(boa_abertura) == [], boa_abertura
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
    # Regressão de publicações reais em 21/10: o excerpt jamais exibe
    # "Situação competitiva verificada do X" nem balanço parcial da ESPN.
    europe = json.loads(json.dumps(cup))
    europe["match_context"].update({
        "home": "Bayern de Munique", "away": "Arsenal",
        "display_home": "Bayern de Munique", "display_away": "Arsenal",
        "competition": "Champions League", "competition_matchday": 3,
        "kickoff_brasilia": "2026-10-21T16:00:00-03:00",
    })
    public_facts = {
        "editorial_match_stakes": {
            "id": "editorial_match_stakes", "status": "verified",
            "facts": [
                {"field": "away_stakes_1", "text":
                 "Situação competitiva verificada do Arsenal: "
                 "O Arsenal venceu o Nottingham Forest por 1 a 0 no Inglês "
                 "e chegou à décima vitória em 11 jogos da temporada."}
            ],
        },
        "recent_form_both_teams": {
            "id": "recent_form_both_teams", "status": "verified",
            "facts": [{"field": "away_recent_form", "text":
                       "Forma recente do Arsenal: nos últimos 2 jogos registrados "
                       "nessa competição (UEFA Champions League), 1 vitória, "
                       "1 empate e 0 derrotas."}],
        },
    }
    _, natural_excerpt = editorial.adjusted_service_headline(europe, public_facts, config=config)
    assert natural_excerpt.startswith("As equipes se enfrentam nesta quarta-feira"), natural_excerpt
    assert "O Arsenal venceu o Nottingham Forest" in natural_excerpt, natural_excerpt
    assert "Situação competitiva verificada" not in natural_excerpt
    assert "jogos registrados" not in natural_excerpt
    assert "0 derrotas" not in natural_excerpt
    assert editorial.approved_excerpt_errors(natural_excerpt) == [], natural_excerpt

    real = json.loads(json.dumps(europe))
    real["match_context"].update({
        "home": "Real Madrid", "away": "RB Leipzig",
        "display_home": "Real Madrid", "display_away": "RB Leipzig",
    })
    facts_with_history = {
        "editorial_individual_team_context": {
            "id": "editorial_individual_team_context", "status": "verified",
            "facts": [
                {"field": "home_stakes_individual_1", "text":
                 "Contexto esportivo atual verificado do Real Madrid: "
                 "O Real Madrid encerrou o treinamento antes de enfrentar "
                 "o RB Leipzig pela terceira rodada da Champions League."},
            ],
        },
        "editorial_match_stakes": {
            "id": "editorial_match_stakes", "status": "verified",
            "facts": [
                {"field": "home_stakes_1", "text":
                 "Situação competitiva verificada do Real Madrid: Na ocasião, "
                 "o time venceu por 1 a 0 na Alemanha e empatou por 1 a 1 na volta."},
            ],
        },
    }
    _, madrid_excerpt = editorial.adjusted_service_headline(real, facts_with_history, config=config)
    assert "Real Madrid encerrou o treinamento" in madrid_excerpt, madrid_excerpt
    assert madrid_excerpt.count("rodada") == 1, madrid_excerpt
    assert madrid_excerpt.count("Champions League") == 1, madrid_excerpt
    assert "Na ocasião" not in madrid_excerpt, madrid_excerpt
    assert "Contexto esportivo atual verificado" not in madrid_excerpt
    assert editorial.approved_excerpt_errors(madrid_excerpt) == [], madrid_excerpt

    stale_meta = (
        "As equipes se enfrentam nesta quarta-feira (21/10) pela Champions League. "
        "Situação competitiva verificada do Arsenal: nos últimos 2 jogos registrados "
        "nessa competição, 1 vitória, 1 empate e 0 derrotas."
    )
    assert "excerpt_com_metadados_ou_contagem_mecanica" in editorial.approved_excerpt_errors(stale_meta)
    robotic_text = (
        "O Arsenal teve duas vitórias, nenhum empate e nenhuma derrota "
        "antes do duelo com o Bayern."
    )
    assert editorial._excerpt_news_sentence(robotic_text) is None
    robotic_excerpt = (
        "As equipes se enfrentam nesta quarta-feira (21/10), "
        "pela 3ª rodada da fase de liga da Champions League. " + robotic_text
    )
    assert "excerpt_com_metadados_ou_contagem_mecanica" in (
        editorial.approved_excerpt_errors(robotic_excerpt)
    ), robotic_excerpt
    natural_excerpt = (
        "As equipes se enfrentam nesta quarta-feira (21/10), "
        "pela 3ª rodada da fase de liga da Champions League. "
        "O Arsenal venceu o Napoli por 1 a 0 na estreia."
    )
    assert editorial.approved_excerpt_errors(natural_excerpt) == [], natural_excerpt
    print("OK: título fixo com escalações e onde assistir só quando ambos os serviços estão verificados.")


if __name__ == "__main__":
    main()
