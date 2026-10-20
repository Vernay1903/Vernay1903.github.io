#!/usr/bin/env python3
"""Dúvida fundamentada de jogador é notícia, não ausência de contexto."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.qualidade_editorial_pre_jogo import meaningful_team_news, source_depth_errors


def main():
    doubt = ("Germán Cano ainda é dúvida para enfrentar o Palmeiras, enquanto "
             "Kevin Serna e Canobbio aparecem entre as opções no ataque do Fluminense.")
    assert meaningful_team_news(doubt)
    assert not meaningful_team_news("Sem informação confirmada sobre possíveis desfalques.")
    fixture = {"facts_by_requirement": [{
        "status": "verified",
        "facts": [
            {"field": "home_team_news_1",
             "text": "Abel Ferreira cumpre suspensão e João Martins dirige o Palmeiras nesta partida."},
            {"field": "away_team_news_1", "text": doubt},
            {"field": "home_stakes_individual_1",
             "text": "Na vitória sobre o Athletico, o Palmeiras jogou com um atleta a menos e ainda venceu por 2 a 0."},
            {"field": "home_stakes_individual_2",
             "text": "O Palmeiras atingiu 66 pontos e assumiu a liderança do Brasileirão após a vitória mais recente."},
        ],
    }]}
    assert source_depth_errors(fixture) == [], source_depth_errors(fixture)
    print("OK: notícia de dúvida real e fatos independentes dos dois clubes contam para profundidade.")


if __name__ == "__main__":
    main()
