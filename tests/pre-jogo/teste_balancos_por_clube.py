#!/usr/bin/env python3
"""Regressão: campanhas iguais de adversários NÃO são repetição editorial."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts import qualidade_editorial_pre_jogo as quality


def p(value: str) -> str:
    return "<p>" + value + "</p>"


def main() -> None:
    contract = {
        "match_context": {
            "home": "Bayern de Munique", "away": "Arsenal",
            "display_home": "Bayern de Munique", "display_away": "Arsenal",
        }
    }
    stats = "duas vitórias, um empate e uma derrota"
    bayern = p(
        "O Bayern de Munique acumula " + stats +
        " em seus quatro últimos compromissos da competição. "
        "Essa sequência antecede a partida diante do Arsenal e descreve "
        "apenas os resultados do clube alemão nesse período."
    )
    arsenal = p(
        "O Arsenal também registra " + stats +
        " em seus quatro jogos anteriores da competição. "
        "O balanço corresponde exclusivamente à equipe inglesa, "
        "sem repetir os resultados dos adversários."
    )
    both = (
        p("<strong>Como chega o Bayern</strong>") + bayern
        + p("<strong>Como chega o Arsenal</strong>") + arsenal
    )
    assert quality.repeated_stat_summaries_errors(both, contract) == [], (
        "Dois clubes com o mesmo V/E/D não representam repetição."
    )
    assert not quality.draft_quality_errors(both, contract), (
        "Balanços distintos dos dois clubes não podem disparar travas de repetição."
    )
    repeated = (
        both + p("<strong>Outros números do Bayern</strong>")
        + p(
            "O Bayern de Munique repete o balanço de " + stats +
            " antes da rodada europeia. A informação é apresentada novamente "
            "nesta passagem, sem acrescentar outro resultado ao desempenho recente."
        )
    )
    assert quality.repeated_stat_summaries_errors(repeated, contract), (
        "Repetir os MESMOS números do MESMO clube precisa continuar bloqueado."
    )

    points = [
        p(f"O Bayern soma quatro pontos na Champions. "
          f"Este é o registro da campanha alemã antes da rodada {i}, "
          "sem novidade esportiva no parágrafo.")
        for i in range(4)
    ]
    assert quality.repeated_team_points_errors("".join(points), contract), (
        "Quatro parágrafos com os mesmos quatro pontos do Bayern devem falhar."
    )
    comparative = [
        p("O Bayern tem quatro pontos, enquanto o Arsenal soma seis pontos. "
          "A comparação coloca as duas campanhas lado a lado.")
        for _ in range(4)
    ]
    assert not quality.repeated_team_points_errors("".join(comparative), contract), (
        "Uma frase com DOIS clubes não permite atribuir todos os números a ambos."
    )
    mixed = [
        p("O Bayern chega com quatro pontos na competição. "
          "O Arsenal disputa o próximo jogo de sua campanha europeia.")
        for _ in range(4)
    ]
    assert quality.repeated_team_points_errors("".join(mixed), contract), (
        "Parágrafos com dois clubes, mas frases específicas, exigem atribuição correta."
    )

    # Nomes potencialmente ambíguos nunca devem ser confundidos.
    derby = {"match_context": {"home": "Real Madrid", "away": "Real Betis"}}
    assert quality._mentioned_sides(
        "O Real Madrid chega para o jogo.", quality._team_aliases_for_editorial_stats(derby)
    ) == ["home"]

    print("OK: campanhas iguais preservadas; duplicação do mesmo clube bloqueada.")


if __name__ == "__main__":
    main()
